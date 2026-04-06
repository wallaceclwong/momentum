"""
API routes for backtesting functionality.
"""
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.session import SessionLocal
from backend.db.crud import (
    create_backtest_run,
    update_backtest_status,
    save_backtest_results,
    get_backtest_result,
    get_backtest_list
)
from backend.engine.backtest import run_backtest

router = APIRouter()


def get_db():
    """Database dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class BacktestRequest(BaseModel):
    """Request model for running a backtest."""
    start_date: str
    end_date: str
    rebalance_freq: str = "monthly"


class BacktestResponse(BaseModel):
    """Response model for backtest run."""
    run_id: str
    status: str
    message: str


def run_backtest_async(run_id: str, start_date: str, end_date: str, rebalance_freq: str):
    """Run backtest in background."""
    db = SessionLocal()
    try:
        # Update status to running
        update_backtest_status(db, run_id, "running")
        
        # Run the backtest
        results = run_backtest(start_date, end_date, rebalance_freq)
        
        # Save results
        results['run_id'] = run_id
        save_backtest_results(db, run_id, results)
        
    except Exception as e:
        # Update status to failed
        update_backtest_status(db, run_id, "failed", str(e))
        import logging
        logging.error(f"Backtest {run_id} failed: {str(e)}")
    finally:
        db.close()


@router.post("/run", response_model=BacktestResponse)
async def run_backtest_endpoint(
    request: BacktestRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Run a backtest asynchronously.
    
    Args:
        request: Backtest parameters
        background_tasks: FastAPI background tasks
        db: Database session
        
    Returns:
        Backtest run ID and status
    """
    try:
        # Validate dates
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(request.end_date, "%Y-%m-%d")
        
        if start_date >= end_date:
            raise HTTPException(status_code=400, detail="start_date must be before end_date")
        
        if end_date > datetime.now():
            raise HTTPException(status_code=400, detail="end_date cannot be in the future")
        
        # Create backtest run record
        backtest = create_backtest_run(
            db,
            start_date,
            end_date,
            request.rebalance_freq
        )
        
        # Add background task
        background_tasks.add_task(
            run_backtest_async,
            backtest.run_id,
            request.start_date,
            request.end_date,
            request.rebalance_freq
        )
        
        return BacktestResponse(
            run_id=backtest.run_id,
            status="pending",
            message="Backtest started successfully"
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start backtest: {str(e)}")


@router.get("/list")
async def list_backtests_endpoint(
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """
    Get list of backtest runs.
    """
    backtests = get_backtest_list(db, limit)
    return [
        {
            "run_id": bt.run_id,
            "status": bt.status,
            "start_date": bt.start_date.isoformat(),
            "end_date": bt.end_date.isoformat(),
            "rebalance_freq": bt.rebalance_freq,
            "created_at": bt.created_at.isoformat(),
            "cagr": bt.cagr,
            "sharpe": bt.sharpe,
            "max_drawdown": bt.max_drawdown,
            "total_return": bt.total_return
        }
        for bt in backtests
    ]


@router.get("/{run_id}")
async def get_backtest_endpoint(
    run_id: str,
    db: Session = Depends(get_db)
):
    """
    Get backtest result by run ID.
    
    Args:
        run_id: Backtest run ID
        db: Database session
        
    Returns:
        Full backtest results
    """
    backtest = get_backtest_result(db, run_id)
    if not backtest:
        raise HTTPException(status_code=404, detail="Backtest not found")
    
    # Format response
    response = {
        "run_id": backtest.run_id,
        "status": backtest.status,
        "parameters": backtest.parameters,
        "created_at": backtest.created_at.isoformat(),
        "updated_at": backtest.updated_at.isoformat() if backtest.updated_at else None
    }
    
    if backtest.status == "completed":
        response.update({
            "metrics": {
                "cagr": backtest.cagr,
                "sharpe": backtest.sharpe,
                "max_drawdown": backtest.max_drawdown,
                "calmar": backtest.calmar,
                "volatility": backtest.volatility,
                "best_day": backtest.best_day,
                "worst_day": backtest.worst_day,
                "win_rate": backtest.win_rate
            },
            "benchmark_metrics": {
                "SPY": {"cagr": backtest.spy_cagr},
                "SPMO": {"cagr": backtest.spmo_cagr},
                "QQQ": {"cagr": backtest.qqq_cagr}
            },
            "nav_series": backtest.nav_series,
            "monthly_returns": backtest.monthly_returns,
            "final_nav": backtest.final_nav,
            "total_return": backtest.total_return,
            "total_trades": backtest.total_trades
        })
    elif backtest.status == "failed":
        response["error_message"] = backtest.error_message
    
    return response




@router.get("/{run_id}/compare")
async def compare_backtest_endpoint(
    run_id: str,
    db: Session = Depends(get_db)
):
    """
    Get side-by-side comparison of portfolio vs benchmarks.
    
    Args:
        run_id: Backtest run ID
        db: Database session
        
    Returns:
        Comparison metrics
    """
    backtest = get_backtest_result(db, run_id)
    if not backtest:
        raise HTTPException(status_code=404, detail="Backtest not found")
    
    if backtest.status != "completed":
        raise HTTPException(status_code=400, detail="Backtest not completed")
    
    # Calculate monthly returns for comparison
    monthly_returns = backtest.monthly_returns or {}
    best_month = None
    worst_month = None
    
    if monthly_returns.get('data'):
        # Flatten monthly returns to find best/worst
        all_returns = []
        for year_idx, year_data in enumerate(monthly_returns['data']):
            for month_idx, month_return in enumerate(year_data):
                if month_return != 0:  # Skip empty months
                    all_returns.append(month_return)
        
        if all_returns:
            best_month = max(all_returns)
            worst_month = min(all_returns)
    
    return {
        "portfolio": {
            "cagr": backtest.cagr,
            "sharpe": backtest.sharpe,
            "max_drawdown": backtest.max_drawdown,
            "calmar": backtest.calmar,
            "best_month": best_month,
            "worst_month": worst_month
        },
        "benchmarks": {
            "SPY": {
                "cagr": backtest.spy_cagr,
                "sharpe": None,  # TODO: Calculate benchmark Sharpe
                "max_drawdown": None,  # TODO: Calculate benchmark drawdown
                "calmar": None
            },
            "SPMO": {
                "cagr": backtest.spmo_cagr,
                "sharpe": None,
                "max_drawdown": None,
                "calmar": None
            },
            "QQQ": {
                "cagr": backtest.qqq_cagr,
                "sharpe": None,
                "max_drawdown": None,
                "calmar": None
            }
        }
    }

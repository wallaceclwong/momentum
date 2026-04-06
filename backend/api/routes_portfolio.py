"""
API routes for portfolio endpoints.
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional

from backend.db.session import SessionLocal
from backend.db.crud import get_latest_portfolio, get_performance_history
from backend.scheduler import get_scheduler_status

router = APIRouter()


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/performance", response_model=Dict[str, Any])
async def get_portfolio_performance(db: Session = Depends(get_db)):
    """
    Get current portfolio performance metrics.
    
    Returns YTD performance, sector breakdown, and holdings.
    """
    try:
        portfolio = get_latest_portfolio(db)
        
        if not portfolio:
            raise HTTPException(
                status_code=404,
                detail="No portfolio data found. Run the screener first."
            )
        
        # Get recent performance history
        performance_history = get_performance_history(db, days=30)
        
        # Format response
        # Add momentum_score to holdings (map from composite_score)
        holdings_with_score = []
        if portfolio.holdings:
            for holding in portfolio.holdings:
                # holdings is stored as JSON in DB, already a dict
                if isinstance(holding, dict):
                    holding_copy = holding.copy()
                else:
                    holding_copy = dict(holding)
                holding_copy["momentum_score"] = holding_copy.get("composite_score", 0)
                holdings_with_score.append(holding_copy)

        response = {
            "snapshot_date": portfolio.snapshot_date.isoformat() if portfolio.snapshot_date else None,
            "total_positions": portfolio.total_positions,
            "sector_breakdown": portfolio.sector_breakdown,
            "sector_weights": portfolio.sector_weights,
            "performance_metrics": {
                "avg_4w_return": portfolio.avg_4w_return,
                "avg_13w_return": portfolio.avg_13w_return,
                "avg_26w_return": portfolio.avg_26w_return,
            },
            "holdings": holdings_with_score,
            "performance_history": [
                {
                    "date": log.log_date.isoformat() if log.log_date else None,
                    "portfolio_ytd": log.portfolio_ytd,
                    "spmo_ytd": log.spmo_ytd,
                    "qqq_ytd": log.qqq_ytd,
                    "total_positions": log.total_positions
                }
                for log in performance_history
            ],
            "scheduler_status": get_scheduler_status()
        }
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/holdings", response_model=List[Dict[str, Any]])
async def get_current_holdings(db: Session = Depends(get_db)):
    """
    Get current portfolio holdings with detailed information.
    
    Returns list of all current positions with metrics.
    """
    try:
        portfolio = get_latest_portfolio(db)
        
        if not portfolio:
            raise HTTPException(
                status_code=404,
                detail="No portfolio data found. Run the screener first."
            )
        
        if not portfolio.holdings:
            return []
        
        # Add additional calculated fields
        holdings = []
        for holding in portfolio.holdings:
            # Calculate position value (assuming $100,000 portfolio for now)
            portfolio_value = 100000
            position_value = portfolio_value * (holding.get("position_weight", 0) / 100)
            
            holding_with_value = {
                **holding,
                "position_value": round(position_value, 2),
                "sector_weight_percent": holding.get("position_weight", 0),
                "momentum_score": holding.get("composite_score", 0)
            }
            holdings.append(holding_with_value)
        
        # Sort by position weight descending
        holdings.sort(key=lambda x: x.get("position_weight", 0), reverse=True)
        
        return holdings
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/sectors", response_model=Dict[str, Any])
async def get_sector_allocation(db: Session = Depends(get_db)):
    """
    Get sector allocation breakdown.
    
    Returns sector weights, position counts, and performance by sector.
    """
    try:
        portfolio = get_latest_portfolio(db)
        
        if not portfolio:
            raise HTTPException(
                status_code=404,
                detail="No portfolio data found. Run the screener first."
            )
        
        # Analyze sector performance from holdings
        sector_performance = {}
        if portfolio.holdings:
            for holding in portfolio.holdings:
                sector = holding.get("sector")
                if sector:
                    if sector not in sector_performance:
                        sector_performance[sector] = {
                            "positions": [],
                            "total_weight": 0,
                            "avg_4w": [],
                            "avg_13w": [],
                            "avg_26w": []
                        }
                    
                    sector_performance[sector]["positions"].append(holding)
                    sector_performance[sector]["total_weight"] += holding.get("position_weight", 0)
                    
                    if holding.get("returns_4w") is not None:
                        sector_performance[sector]["avg_4w"].append(holding["returns_4w"])
                    if holding.get("returns_13w") is not None:
                        sector_performance[sector]["avg_13w"].append(holding["returns_13w"])
                    if holding.get("returns_26w") is not None:
                        sector_performance[sector]["avg_26w"].append(holding["returns_26w"])
        
        # Calculate averages
        for sector in sector_performance:
            perf = sector_performance[sector]
            perf["avg_4w_return"] = sum(perf["avg_4w"]) / len(perf["avg_4w"]) if perf["avg_4w"] else 0
            perf["avg_13w_return"] = sum(perf["avg_13w"]) / len(perf["avg_13w"]) if perf["avg_13w"] else 0
            perf["avg_26w_return"] = sum(perf["avg_26w"]) / len(perf["avg_26w"]) if perf["avg_26w"] else 0
            perf["position_count"] = len(perf["positions"])
        
        response = {
            "snapshot_date": portfolio.snapshot_date.isoformat() if portfolio.snapshot_date else None,
            "sector_weights": portfolio.sector_weights or {},
            "sector_counts": portfolio.sector_breakdown or {},
            "sector_performance": sector_performance,
            "total_weight": sum(sector_performance.get(s, {}).get("total_weight", 0) for s in sector_performance)
        }
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/performance/history", response_model=List[Dict[str, Any]])
async def get_performance_history_endpoint(
    days: int = 30,
    db: Session = Depends(get_db)
):
    """
    Get historical performance data.
    
    Args:
        days: Number of days of history to return (default: 30)
    """
    try:
        history = get_performance_history(db, days)
        
        return [
            {
                "date": log.log_date.isoformat() if log.log_date else None,
                "portfolio_ytd": log.portfolio_ytd,
                "spmo_ytd": log.spmo_ytd,
                "qqq_ytd": log.qqq_ytd,
                "total_positions": log.total_positions,
                "avg_momentum_score": log.avg_momentum_score
            }
            for log in history
        ]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

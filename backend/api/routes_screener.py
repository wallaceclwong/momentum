"""
API routes for screener endpoints.
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime

from backend.db.session import SessionLocal
from backend.db.crud import get_latest_screener_results, get_screener_history
from backend.scheduler import get_scheduler_status

router = APIRouter()


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/latest", response_model=Dict[str, Any])
async def get_latest_screener(db: Session = Depends(get_db)):
    """
    Get the most recent screener results.
    
    Returns top momentum picks by sector with all metrics.
    """
    try:
        results = get_latest_screener_results(db)
        
        if not results:
            raise HTTPException(
                status_code=404, 
                detail="No screener results found. Run the screener first."
            )
        
        # Group results by sector  
        sector_results = {}
        for result in results:
            sector = result.sector
            if sector not in sector_results:
                sector_results[sector] = []
            
            pick = {
                "ticker": result.ticker,
                "returns": {
                    "4W": result.returns_4w,
                    "13W": result.returns_13w,
                    "26W": result.returns_26w
                },
                "composite_score": result.composite_score,
                "l1_surprise": result.l1_surprise,
                "l2_surprise": result.l2_surprise,
                "sector_etf": result.sector_etf,
                "position_weight": result.position_weight * 100 if result.position_weight else 0,  # Convert to %
                "run_date": result.run_date.isoformat() if result.run_date else None
            }
            sector_results[sector].append(pick)
        
        # Sort picks within each sector by composite score
        for sector in sector_results:
            sector_results[sector].sort(
                key=lambda x: x["composite_score"] or 0, 
                reverse=True
            )
        
        return {
            "run_date": results[0].run_date.isoformat() if results else None,
            "total_positions": len(results),
            "sectors": sector_results,
            "scheduler_status": get_scheduler_status()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/history", response_model=List[Dict[str, Any]])
async def get_screener_history_endpoint(
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """
    Get historical screener runs.
    
    Args:
        limit: Number of historical runs to return (default: 10)
    """
    try:
        history = get_screener_history(db, limit)
        
        response_data = []
        for run_group in history:
            if not run_group:
                continue
                
            run_date = run_group[0].run_date.isoformat() if run_group[0].run_date else None
            
            # Group by sector for this run
            sector_data = {}
            for result in run_group:
                sector = result.sector
                if sector not in sector_data:
                    sector_data[sector] = []
                
                sector_data[sector].append({
                    "ticker": result.ticker,
                    "composite_score": result.composite_score,
                    "position_weight": result.position_weight * 100 if result.position_weight else 0
                })
            
            response_data.append({
                "run_date": run_date,
                "total_positions": len(run_group),
                "sectors": sector_data
            })
        
        return response_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.post("/run", response_model=Dict[str, Any])
async def trigger_screener_run():
    """
    Manually trigger a screener run.
    
    This is useful for testing or running outside the normal schedule.
    """
    try:
        from backend.scheduler import run_monthly_screener
        
        # Run the screener
        await run_monthly_screener()
        
        return {
            "status": "success",
            "message": "Screener run triggered successfully",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Screener run failed: {str(e)}")


@router.get("/status", response_model=Dict[str, Any])
async def get_screener_status():
    """
    Get the current status of the screener and scheduler.
    """
    try:
        return get_scheduler_status()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")

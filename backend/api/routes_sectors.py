"""
API routes for sector analysis endpoints.
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Dict, Any
import pandas as pd
import numpy as np

from backend.db.session import SessionLocal
from backend.db.crud import get_latest_screener_results, get_latest_correlation
from backend.data.prices import fetch_price_history
from backend.data.sp500 import get_tickers_by_sector
from backend.config import SECTORS, MOMENTUM_WINDOWS

router = APIRouter()


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/correlation", response_model=Dict[str, Any])
async def get_sector_correlation(db: Session = Depends(get_db)):
    """
    Get sector correlation matrix based on 26-week returns.
    
    Returns correlation matrix between all 11 sectors.
    """
    try:
        # Try to get cached correlation from database
        cached = get_latest_correlation(db)
        if cached and cached.correlation_matrix:
            return {
                "calculation_date": cached.calculation_date.isoformat() if cached.calculation_date else None,
                "window_days": cached.window_days,
                "correlation_matrix": cached.correlation_matrix,
                "cached": True
            }
        
        # Calculate fresh correlation matrix
        correlation_data = await calculate_sector_correlation()
        
        # Save to database
        from backend.db.crud import save_sector_correlation
        save_sector_correlation(db, correlation_data["correlation_matrix"])
        db.commit()
        
        return correlation_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating correlation: {str(e)}")


async def calculate_sector_correlation() -> Dict[str, Any]:
    """Calculate sector correlation matrix using ETF price data."""
    try:
        # Get sector ETF tickers
        etf_tickers = list(SECTORS.keys())
        
        # Fetch 6 months of price data for all sector ETFs
        price_data = fetch_price_history(
            tickers=etf_tickers,
            period="6mo",
            interval="1d"
        )
        
        if not price_data:
            raise Exception("Failed to fetch sector ETF price data")
        
        # Calculate daily returns for each ETF
        returns_data = {}
        for etf, df in price_data.items():
            if df.empty or len(df) < 30:  # Need at least 30 days
                continue
                
            # Calculate daily returns
            df = df.copy()
            df["daily_return"] = df["Close"].pct_change()
            
            # Use last 130 trading days (~26 weeks)
            daily_returns = df["daily_return"].tail(130).dropna()
            
            if len(daily_returns) > 0:
                returns_data[etf] = daily_returns
        
        if len(returns_data) < 2:
            raise Exception("Insufficient data for correlation calculation")
        
        # Create correlation matrix
        returns_df = pd.DataFrame(returns_data)
        correlation_matrix = returns_df.corr()
        
        # Convert to dict format
        correlation_dict = {}
        for etf1 in correlation_matrix.columns:
            correlation_dict[etf1] = {}
            for etf2 in correlation_matrix.columns:
                correlation_dict[etf1][etf2] = round(correlation_matrix.loc[etf1, etf2], 4)
        
        # Add sector names
        correlation_with_names = {}
        for etf, correlations in correlation_dict.items():
            sector_name = SECTORS.get(etf, etf)
            correlation_with_names[sector_name] = {}
            for other_etf, corr in correlations.items():
                other_sector = SECTORS.get(other_etf, other_etf)
                correlation_with_names[sector_name][other_sector] = corr
        
        return {
            "calculation_date": pd.Timestamp.now().isoformat(),
            "window_days": 130,
            "correlation_matrix": correlation_with_names,
            "cached": False
        }
        
    except Exception as e:
        raise Exception(f"Correlation calculation failed: {str(e)}")


@router.get("/performance", response_model=Dict[str, Any])
async def get_sector_performance(db: Session = Depends(get_db)):
    """
    Get performance metrics for all sectors.
    
    Returns average returns, momentum scores, and rankings by sector.
    """
    try:
        # Get latest screener results
        results = get_latest_screener_results(db)
        
        if not results:
            raise HTTPException(
                status_code=404,
                detail="No screener data found. Run the screener first."
            )
        
        # Group and analyze by sector
        sector_metrics = {}
        
        for result in results:
            sector = result.sector
            if sector not in sector_metrics:
                sector_metrics[sector] = {
                    "positions": [],
                    "returns_4w": [],
                    "returns_13w": [],
                    "returns_26w": [],
                    "composite_scores": [],
                    "earnings_surprises": []
                }
            
            sector_metrics[sector]["positions"].append(result.ticker)
            
            if result.returns_4w is not None:
                sector_metrics[sector]["returns_4w"].append(result.returns_4w)
            if result.returns_13w is not None:
                sector_metrics[sector]["returns_13w"].append(result.returns_13w)
            if result.returns_26w is not None:
                sector_metrics[sector]["returns_26w"].append(result.returns_26w)
            if result.composite_score is not None:
                sector_metrics[sector]["composite_scores"].append(result.composite_score)
            if result.l1_surprise is not None:
                sector_metrics[sector]["earnings_surprises"].append(result.l1_surprise)
        
        # Calculate averages and rankings
        sector_performance = {}
        for sector, metrics in sector_metrics.items():
            performance = {
                "sector": sector,
                "position_count": len(metrics["positions"]),
                "avg_4w_return": np.mean(metrics["returns_4w"]) if metrics["returns_4w"] else 0,
                "avg_13w_return": np.mean(metrics["returns_13w"]) if metrics["returns_13w"] else 0,
                "avg_26w_return": np.mean(metrics["returns_26w"]) if metrics["returns_26w"] else 0,
                "avg_composite_score": np.mean(metrics["composite_scores"]) if metrics["composite_scores"] else 0,
                "avg_earnings_surprise": np.mean(metrics["earnings_surprises"]) if metrics["earnings_surprises"] else 0,
                "top_performers": []
            }
            
            # Find top performers in this sector
            sector_results = [r for r in results if r.sector == sector]
            sector_results.sort(key=lambda x: x.composite_score or 0, reverse=True)
            performance["top_performers"] = [
                {
                    "ticker": r.ticker,
                    "composite_score": r.composite_score,
                    "returns_4w": r.returns_4w,
                    "returns_13w": r.returns_13w,
                    "returns_26w": r.returns_26w
                }
                for r in sector_results[:3]  # Top 3
            ]
            
            sector_performance[sector] = performance
        
        # Sort sectors by average composite score
        sorted_sectors = sorted(
            sector_performance.values(),
            key=lambda x: x["avg_composite_score"],
            reverse=True
        )
        
        # Add rankings
        for i, sector in enumerate(sorted_sectors):
            sector["rank"] = i + 1
        
        return {
            "data": sector_performance,
            "rankings": sorted_sectors,
            "summary": {
                "total_sectors": len(sector_performance),
                "strongest_sector": sorted_sectors[0]["sector"] if sorted_sectors else None,
                "weakest_sector": sorted_sectors[-1]["sector"] if sorted_sectors else None
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating sector performance: {str(e)}")


@router.get("/etf-weights", response_model=Dict[str, Any])
async def get_sector_etf_weights():
    """
    Get current sector ETF market cap weights.
    
    Returns the weights used for portfolio allocation.
    """
    try:
        from backend.engine.portfolio import get_sector_etf_weights
        
        weights = get_sector_etf_weights()
        
        # Convert to percentages and add ETF tickers
        weights_with_etf = {}
        for sector, weight in weights.items():
            # Find ETF ticker for this sector
            etf_ticker = None
            for etf, name in SECTORS.items():
                if name == sector:
                    etf_ticker = etf
                    break
            
            weights_with_etf[sector] = {
                "weight_percent": round(weight * 100, 2),
                "etf_ticker": etf_ticker
            }
        
        return {
            "weights": weights_with_etf,
            "total_weight_percent": round(sum(w["weight_percent"] for w in weights_with_etf.values()), 2),
            "calculation_date": pd.Timestamp.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching ETF weights: {str(e)}")

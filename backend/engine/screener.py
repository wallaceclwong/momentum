"""Main screener pipeline - orchestrates the full momentum screening process."""
from typing import Dict, List, Optional
import logging
from datetime import datetime

from backend.config import (
    SECTORS,
    SECTOR_TO_ETF,
    TOP_N_PER_SECTOR,
    MOMENTUM_WINDOWS,
    EARNINGS_LOOKBACK,
)
from backend.data.sp500 import get_tickers_by_sector
from backend.data.prices import fetch_price_history
from backend.data.earnings import get_earnings_surprises_batch
from backend.engine.momentum import calculate_momentum_for_tickers, rank_by_momentum
from backend.engine.earnings_filter import filter_by_earnings_momentum

logger = logging.getLogger(__name__)


def run_momentum_screener(
    sectors: Optional[List[str]] = None,
    top_n: int = TOP_N_PER_SECTOR
) -> Dict[str, List[Dict]]:
    """
    Run the full momentum screener pipeline.
    
    Pipeline:
    1. Fetch S&P 500 constituents by sector
    2. Fetch price history for all tickers
    3. Calculate momentum (4W, 13W, 26W returns)
    4. Fetch earnings surprise data
    5. Filter by earnings momentum (L1, L2 criteria)
    6. Rank and select top N per sector
    
    Args:
        sectors: List of sectors to screen (default: all 11)
        top_n: Number of top stocks to select per sector
    
    Returns:
        Dict mapping sector_name -> list of top picks dicts
        Each dict contains: ticker, returns (4W/13W/26W), composite_score, 
                           l1_surprise, l2_surprise, weight
    """
    if sectors is None:
        sectors = list(SECTORS.values())
    
    logger.info(f"Starting momentum screener for {len(sectors)} sectors")
    
    # Step 1: Get S&P 500 constituents by sector
    tickers_by_sector = get_tickers_by_sector()
    
    results = {}
    
    for sector in sectors:
        logger.info(f"Processing sector: {sector}")
        
        # Get tickers for this sector
        sector_tickers = tickers_by_sector.get(sector, [])
        if not sector_tickers:
            logger.warning(f"No tickers found for sector {sector}")
            results[sector] = []
            continue
        
        logger.info(f"  Found {len(sector_tickers)} tickers in {sector}")
        
        try:
            # Step 2: Fetch price data
            price_data = fetch_price_history(
                tickers=sector_tickers,
                period="1y",
                interval="1d"
            )
            
            if not price_data:
                logger.warning(f"  No price data fetched for {sector}")
                results[sector] = []
                continue
            
            logger.info(f"  Fetched price data for {len(price_data)} tickers")
            
            # Step 3: Calculate momentum
            momentum_data = calculate_momentum_for_tickers(price_data)
            
            # Step 4 & 5: Fetch and filter by earnings
            earnings_data = get_earnings_surprises_batch(
                list(momentum_data.keys()),
                n=EARNINGS_LOOKBACK
            )
            
            tickers_with_momentum = list(momentum_data.keys())
            passed_tickers = filter_by_earnings_momentum(
                tickers_with_momentum,
                earnings_data
            )
            
            logger.info(f"  {len(passed_tickers)}/{len(tickers_with_momentum)} passed earnings filter")
            
            # Filter momentum data to only passed tickers
            passed_momentum = {
                t: momentum_data[t] for t in passed_tickers 
                if t in momentum_data
            }
            
            # Step 6: Rank and select top N
            top_picks = rank_by_momentum(passed_momentum, top_n=top_n)
            
            # Add earnings data to results
            for pick in top_picks:
                ticker = pick["ticker"]
                ticker_earnings = earnings_data.get(ticker, [])
                
                pick["l1_surprise"] = ticker_earnings[0].get("surprise_pct") if len(ticker_earnings) > 0 else None
                pick["l2_surprise"] = ticker_earnings[1].get("surprise_pct") if len(ticker_earnings) > 1 else None
                pick["sector"] = sector
                pick["sector_etf"] = SECTOR_TO_ETF.get(sector)
            
            results[sector] = top_picks
            logger.info(f"  Selected top {len(top_picks)} picks for {sector}")
            
        except Exception as e:
            logger.error(f"  Error processing sector {sector}: {e}", exc_info=True)
            results[sector] = []
    
    logger.info("Momentum screener complete")
    return results


def get_screener_summary(screener_results: Dict[str, List[Dict]]) -> Dict:
    """
    Generate a summary of screener results.
    
    Args:
        screener_results: Output from run_momentum_screener
    
    Returns:
        Summary dict with counts, avg returns, etc.
    """
    total_picks = sum(len(picks) for picks in screener_results.values())
    sectors_with_picks = sum(1 for picks in screener_results.values() if picks)
    
    # Collect all returns
    all_4w = []
    all_13w = []
    all_26w = []
    
    for picks in screener_results.values():
        for pick in picks:
            returns = pick.get("returns", {})
            if returns.get("4W") is not None:
                all_4w.append(returns["4W"])
            if returns.get("13W") is not None:
                all_13w.append(returns["13W"])
            if returns.get("26W") is not None:
                all_26w.append(returns["26W"])
    
    return {
        "timestamp": datetime.now().isoformat(),
        "total_sectors": len(screener_results),
        "sectors_with_picks": sectors_with_picks,
        "total_picks": total_picks,
        "avg_4w_return": sum(all_4w) / len(all_4w) if all_4w else None,
        "avg_13w_return": sum(all_13w) / len(all_13w) if all_13w else None,
        "avg_26w_return": sum(all_26w) / len(all_26w) if all_26w else None,
    }

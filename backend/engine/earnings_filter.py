"""Earnings surprise filtering engine."""
from typing import Dict, List
import logging

from backend.data.earnings import get_last_n_earnings_surprises, has_positive_earnings_momentum
from backend.config import EARNINGS_LOOKBACK

logger = logging.getLogger(__name__)


def filter_by_earnings_momentum(
    tickers: List[str],
    earnings_data: Dict[str, List[Dict]] = None
) -> List[str]:
    """
    Filter tickers to only those with positive earnings momentum.
    
    Criteria (from Substack article):
    1. Last 2 earnings surprises are both positive (L1 > 0 AND L2 > 0), OR
    2. Earnings surprise is improving (L2 < L1, meaning surprise % is growing)
    
    Args:
        tickers: List of ticker symbols to filter
        earnings_data: Pre-fetched earnings data (fetched if not provided)
    
    Returns:
        List of tickers passing the earnings filter
    """
    if earnings_data is None:
        # Fetch earnings data for all tickers
        from backend.data.earnings import get_earnings_surprises_batch
        earnings_data = get_earnings_surprises_batch(tickers, EARNINGS_LOOKBACK)
    
    passed = []
    
    for ticker in tickers:
        ticker_earnings = earnings_data.get(ticker, [])
        
        if not ticker_earnings:
            # No earnings data available - be lenient and allow through
            # This is common for some tickers with limited history
            passed.append(ticker)
            continue
        
        if has_positive_earnings_momentum(ticker_earnings):
            passed.append(ticker)
    
    logger.info(f"Earnings filter: {len(passed)}/{len(tickers)} tickers passed")
    return passed


def get_earnings_summary(ticker: str) -> Dict:
    """
    Get a summary of earnings data for a ticker.
    
    Args:
        ticker: Stock ticker symbol
    
    Returns:
        Dict with L1 and L2 surprise percentages and filter status
    """
    earnings = get_last_n_earnings_surprises(ticker, EARNINGS_LOOKBACK)
    
    if len(earnings) >= 2:
        l1 = earnings[0].get("surprise_pct")
        l2 = earnings[1].get("surprise_pct")
        passed = has_positive_earnings_momentum(earnings)
    elif len(earnings) == 1:
        l1 = earnings[0].get("surprise_pct")
        l2 = None
        passed = True  # Lenient with only 1 data point
    else:
        l1 = None
        l2 = None
        passed = True  # Lenient with no data
    
    return {
        "ticker": ticker,
        "l1_surprise": l1,
        "l2_surprise": l2,
        "passed_filter": passed,
        "earnings_count": len(earnings),
    }

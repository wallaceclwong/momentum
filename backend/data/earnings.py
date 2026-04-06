"""Fetch earnings surprise data using yfinance."""
import yfinance as yf
import pandas as pd
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def fetch_earnings_history(ticker: str) -> Optional[pd.DataFrame]:
    """
    Fetch earnings history for a single ticker.
    
    Args:
        ticker: Stock ticker symbol
    
    Returns:
        DataFrame with earnings data, or None if unavailable
    """
    try:
        stock = yf.Ticker(ticker)
        earnings = stock.earnings_dates
        if earnings is not None and not earnings.empty:
            return earnings
    except Exception as e:
        logger.warning(f"Failed to fetch earnings for {ticker}: {e}")
    return None


def get_last_n_earnings_surprises(ticker: str, n: int = 2) -> List[Dict]:
    """
    Get the last N earnings surprises for a ticker.
    
    Args:
        ticker: Stock ticker symbol
        n: Number of earnings reports to look back
    
    Returns:
        List of dicts with keys: date, eps_estimate, eps_actual, surprise_pct
        Most recent first (index 0 = L1, index 1 = L2)
    """
    df = fetch_earnings_history(ticker)
    if df is None or df.empty:
        return []
    
    # Filter for reports with actual EPS data (past earnings)
    if "Reported EPS" in df.columns:
        past_earnings = df[df["Reported EPS"].notna()].copy()
    else:
        # Fallback: try to infer from index or other columns
        past_earnings = df.dropna(subset=[df.columns[0]]).copy()
    
    if past_earnings.empty:
        return []
    
    # Sort by date descending (most recent first)
    if past_earnings.index.name == "Date" or isinstance(past_earnings.index, pd.DatetimeIndex):
        past_earnings = past_earnings.sort_index(ascending=False)
    
    results = []
    for i, (idx, row) in enumerate(past_earnings.head(n).iterrows()):
        try:
            # Try different column naming conventions
            surprise = None
            if "Surprise(%)" in row:
                surprise = row["Surprise(%)"]
            elif "Surprise" in row:
                surprise = row["Surprise"]
            
            eps_actual = None
            if "Reported EPS" in row:
                eps_actual = row["Reported EPS"]
            elif "Actual" in row:
                eps_actual = row["Actual"]
            
            eps_estimate = None
            if "EPS Estimate" in row:
                eps_estimate = row["EPS Estimate"]
            elif "Estimate" in row:
                eps_estimate = row["Estimate"]
            
            results.append({
                "date": idx if isinstance(idx, pd.Timestamp) else row.get("Date"),
                "eps_estimate": eps_estimate,
                "eps_actual": eps_actual,
                "surprise_pct": surprise,
                "period": f"L{i+1}"  # L1 = most recent, L2 = second most recent
            })
        except Exception as e:
            logger.warning(f"Error parsing earnings row for {ticker}: {e}")
            continue
    
    return results


def get_earnings_surprises_batch(tickers: List[str], n: int = 2) -> Dict[str, List[Dict]]:
    """
    Fetch earnings surprises for multiple tickers.
    
    Args:
        tickers: List of ticker symbols
        n: Number of earnings reports per ticker
    
    Returns:
        Dict mapping ticker -> list of earnings surprise data
    """
    results = {}
    for ticker in tickers:
        try:
            surprises = get_last_n_earnings_surprises(ticker, n)
            if surprises:
                results[ticker] = surprises
        except Exception as e:
            logger.warning(f"Failed to get earnings for {ticker}: {e}")
    
    logger.info(f"Fetched earnings data for {len(results)}/{len(tickers)} tickers")
    return results


def has_positive_earnings_momentum(
    earnings_data: List[Dict],
    require_positive_surprise: bool = True
) -> bool:
    """
    Check if earnings show positive momentum pattern.
    
    Criteria (from article):
    - L1_surprise > 0 AND L2_surprise > 0 (both positive)
    - OR L2_surprise < L1_surprise (improving trend)
    
    Args:
        earnings_data: List of earnings dicts (L1, L2, ...)
        require_positive_surprise: If True, requires at least one positive surprise
    
    Returns:
        True if earnings momentum criteria met
    """
    if len(earnings_data) < 2:
        # Not enough history, be lenient
        return True
    
    l1 = earnings_data[0].get("surprise_pct")
    l2 = earnings_data[1].get("surprise_pct")
    
    # Handle None values
    if l1 is None or l2 is None:
        return True  # Be lenient if data missing
    
    try:
        l1_val = float(l1)
        l2_val = float(l2)
    except (TypeError, ValueError):
        return True  # Be lenient if parsing fails
    
    # Condition 1: Both positive
    both_positive = l1_val > 0 and l2_val > 0
    
    # Condition 2: Improving trend (L2 < L1 means surprise is growing)
    improving = l2_val < l1_val
    
    return both_positive or improving

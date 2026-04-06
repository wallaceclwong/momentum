"""Momentum calculation engine."""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import logging

from backend.config import MOMENTUM_WINDOWS, MOMENTUM_WEIGHTS

logger = logging.getLogger(__name__)


def calculate_returns(
    price_df: pd.DataFrame,
    windows: Dict[str, int] = None
) -> Dict[str, Optional[float]]:
    """
    Calculate return over specified lookback windows.
    
    Args:
        price_df: DataFrame with 'Close' prices, index=datetime
        windows: Dict of {name: trading_days} (e.g., {"4W": 20})
    
    Returns:
        Dict of {window_name: return_pct} where return is (price_now / price_then - 1) * 100
        Returns None if insufficient data
    """
    if windows is None:
        windows = MOMENTUM_WINDOWS
    
    if price_df is None or price_df.empty or len(price_df) < 2:
        return {name: None for name in windows}
    
    results = {}
    current_price = price_df["Close"].iloc[-1]
    
    for name, days in windows.items():
        try:
            if len(price_df) < days + 1:
                results[name] = None
                continue
            
            past_price = price_df["Close"].iloc[-(days + 1)]
            if past_price == 0 or pd.isna(past_price):
                results[name] = None
                continue
            
            ret = (current_price / past_price - 1) * 100
            results[name] = round(ret, 2)
        except Exception as e:
            logger.debug(f"Error calculating {name} return: {e}")
            results[name] = None
    
    return results


def calculate_composite_score(
    returns: Dict[str, Optional[float]],
    weights: Dict[str, float] = None
) -> Optional[float]:
    """
    Calculate weighted composite momentum score.
    
    Args:
        returns: Dict of {window_name: return_pct}
        weights: Dict of {window_name: weight} (default: equal weights)
    
    Returns:
        Weighted average score, or None if no valid returns
    """
    if weights is None:
        weights = MOMENTUM_WEIGHTS
    
    valid_scores = []
    valid_weights = []
    
    for window, ret in returns.items():
        if ret is not None and window in weights:
            valid_scores.append(ret)
            valid_weights.append(weights[window])
    
    if not valid_scores:
        return None
    
    # Normalize weights
    total_weight = sum(valid_weights)
    if total_weight == 0:
        return None
    
    normalized_weights = [w / total_weight for w in valid_weights]
    
    # Weighted average
    score = sum(s * w for s, w in zip(valid_scores, normalized_weights))
    return round(score, 2)


def calculate_momentum_for_tickers(
    price_data: Dict[str, pd.DataFrame],
    windows: Dict[str, int] = None
) -> Dict[str, Dict]:
    """
    Calculate momentum metrics for multiple tickers.
    
    Args:
        price_data: Dict of {ticker: price DataFrame}
        windows: Lookback windows (default from config)
    
    Returns:
        Dict of {ticker: {"returns": {...}, "composite_score": ...}}
    """
    results = {}
    
    for ticker, df in price_data.items():
        try:
            returns = calculate_returns(df, windows)
            composite = calculate_composite_score(returns)
            
            results[ticker] = {
                "returns": returns,
                "composite_score": composite,
                "latest_price": df["Close"].iloc[-1] if not df.empty else None,
            }
        except Exception as e:
            logger.warning(f"Failed to calculate momentum for {ticker}: {e}")
    
    return results


def rank_by_momentum(
    momentum_data: Dict[str, Dict],
    top_n: int = 3
) -> List[Dict]:
    """
    Rank tickers by composite momentum score.
    
    Args:
        momentum_data: Output from calculate_momentum_for_tickers
        top_n: Number of top performers to return
    
    Returns:
        List of dicts sorted by composite_score descending
    """
    scored = []
    
    for ticker, data in momentum_data.items():
        score = data.get("composite_score")
        if score is not None:
            scored.append({
                "ticker": ticker,
                "composite_score": score,
                "returns": data.get("returns", {}),
                "latest_price": data.get("latest_price"),
            })
    
    # Sort by composite score descending
    scored.sort(key=lambda x: x["composite_score"], reverse=True)
    
    return scored[:top_n]

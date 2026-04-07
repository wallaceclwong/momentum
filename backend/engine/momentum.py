"""Momentum calculation engine."""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import logging

from backend.config import (
    MOMENTUM_WINDOWS, MOMENTUM_WEIGHTS,
    SKIP_LAST_MONTH, SKIP_DAYS, VOL_LOOKBACK_DAYS
)

logger = logging.getLogger(__name__)


def calculate_returns(
    price_df: pd.DataFrame,
    windows: Dict[str, int] = None,
    skip_last_month: bool = None,
) -> Dict[str, Optional[float]]:
    """
    Calculate return over specified lookback windows.
    When skip_last_month=True, uses price from SKIP_DAYS ago as 'current'
    to avoid the short-term reversal effect.
    Also computes 52W_HIGH proximity score.
    """
    if windows is None:
        windows = MOMENTUM_WINDOWS
    if skip_last_month is None:
        skip_last_month = SKIP_LAST_MONTH

    if price_df is None or price_df.empty or len(price_df) < 2:
        return {name: None for name in list(windows.keys()) + ["52W_HIGH"]}

    closes = price_df["Close"].dropna()
    if len(closes) < 2:
        return {name: None for name in list(windows.keys()) + ["52W_HIGH"]}

    # Reference price: skip last month to avoid reversal
    skip = SKIP_DAYS if skip_last_month else 0
    if len(closes) <= skip:
        ref_idx = -1
    else:
        ref_idx = -(skip + 1) if skip > 0 else -1

    ref_price = closes.iloc[ref_idx]
    results = {}

    for name, days in windows.items():
        try:
            total_days = days + skip
            if len(closes) < total_days + 1:
                results[name] = None
                continue
            past_price = closes.iloc[-(total_days + 1)]
            if past_price == 0 or pd.isna(past_price) or pd.isna(ref_price):
                results[name] = None
                continue
            ret = (ref_price / past_price - 1) * 100
            results[name] = round(ret, 2)
        except Exception as e:
            logger.debug(f"Error calculating {name} return: {e}")
            results[name] = None

    # 52-week high proximity (0-100): current price / 52W high * 100
    try:
        lookback_252 = closes.iloc[-252:] if len(closes) >= 252 else closes
        high_52w = lookback_252.max()
        current = closes.iloc[-1]
        if high_52w > 0 and not pd.isna(high_52w):
            results["52W_HIGH"] = round((current / high_52w) * 100, 2)
        else:
            results["52W_HIGH"] = None
    except Exception:
        results["52W_HIGH"] = None

    return results


def calculate_volatility(price_df: pd.DataFrame, lookback: int = None) -> Optional[float]:
    """Annualised volatility from daily returns (used for position sizing)."""
    if lookback is None:
        lookback = VOL_LOOKBACK_DAYS
    if price_df is None or price_df.empty or len(price_df) < lookback + 1:
        return None
    try:
        daily_rets = price_df["Close"].dropna().pct_change().dropna()
        if len(daily_rets) < lookback:
            return None
        vol = float(daily_rets.iloc[-lookback:].std() * (252 ** 0.5))
        return round(vol, 6) if vol > 0 else None
    except Exception:
        return None


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
            volatility = calculate_volatility(df)

            results[ticker] = {
                "returns": returns,
                "composite_score": composite,
                "volatility": volatility,
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

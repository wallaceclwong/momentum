"""Momentum calculation engine."""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import logging

from backend.config import (
    MOMENTUM_WINDOWS, MOMENTUM_WEIGHTS,
    SKIP_LAST_MONTH, SKIP_DAYS, VOL_LOOKBACK_DAYS,
    USE_CROSS_SECTIONAL_ZSCORE, MIN_STOCK_PRICE, MIN_ADV_USD,
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


def calculate_trend_quality(price_df: pd.DataFrame, lookback: int = 90) -> Optional[float]:
    """
    R² of log-price vs time over the lookback window (default 90 days).

    Returns a score 0–100 where 100 = perfectly smooth uptrend.
    Rewards stocks that trend steadily vs volatile ones with same avg return.
    """
    if price_df is None or price_df.empty:
        return None
    try:
        closes = price_df["Close"].dropna()
        if len(closes) < lookback:
            return None
        y = np.log(closes.iloc[-lookback:].values.astype(float))
        x = np.arange(len(y))
        # Simple linear regression
        x_mean, y_mean = x.mean(), y.mean()
        ss_tot = ((y - y_mean) ** 2).sum()
        if ss_tot == 0:
            return None
        slope = ((x - x_mean) * (y - y_mean)).sum() / ((x - x_mean) ** 2).sum()
        y_pred = slope * x + (y_mean - slope * x_mean)
        ss_res = ((y - y_pred) ** 2).sum()
        r2 = max(0.0, 1 - ss_res / ss_tot)
        return round(r2 * 100, 2)  # scale to 0-100 to match return % units
    except Exception:
        return None


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
        returns: Dict of {window_name: return_pct or score_0_to_100}
        weights: Dict of {window_name: weight} (default from config)

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

    total_weight = sum(valid_weights)
    if total_weight == 0:
        return None

    normalized_weights = [w / total_weight for w in valid_weights]
    score = sum(s * w for s, w in zip(valid_scores, normalized_weights))
    return round(score, 2)


def _zscore_normalize_signals(results: Dict[str, Dict]) -> Dict[str, Dict]:
    """
    Cross-sectional z-score normalization of each signal across the full universe.

    Converts raw return % and scores to z-scores so that stock selection reflects
    relative strength vs the universe rather than absolute return magnitude.
    This prevents bull-market periods from flooding all scores high.
    """
    signal_keys = list(MOMENTUM_WEIGHTS.keys())  # e.g. 4W, 13W, 26W, 52W_HIGH, TREND_QUALITY

    for key in signal_keys:
        values = [
            results[t]["returns"].get(key)
            for t in results
            if results[t]["returns"].get(key) is not None
        ]
        if len(values) < 2:
            continue
        arr = np.array(values, dtype=float)
        mu, sigma = arr.mean(), arr.std()
        if sigma == 0:
            continue
        for ticker in results:
            raw = results[ticker]["returns"].get(key)
            if raw is not None:
                results[ticker]["returns"][key] = round((raw - mu) / sigma * 10, 4)
                # scale by 10 so z-scores are in similar range to % returns
    return results


def _calc_adv_usd(df: pd.DataFrame, lookback: int = 20) -> Optional[float]:
    """
    Compute 20-day average daily dollar volume (ADV).
    Returns None if Volume column is missing.
    """
    if "Volume" not in df.columns:
        return None
    try:
        closes = df["Close"].dropna()
        volumes = df["Volume"].dropna()
        # Align on common index
        common = closes.index.intersection(volumes.index)
        if len(common) < lookback:
            return None
        adv = float((closes.loc[common] * volumes.loc[common]).iloc[-lookback:].mean())
        return adv
    except Exception:
        return None


def calculate_momentum_for_tickers(
    price_data: Dict[str, pd.DataFrame],
    windows: Dict[str, int] = None,
    earnings_data: Optional[Dict[str, List]] = None,
) -> Dict[str, Dict]:
    """
    Calculate momentum metrics for multiple tickers.

    Args:
        price_data:    Dict of {ticker: OHLCV DataFrame}
        windows:       Lookback windows (default from config)
        earnings_data: Optional {ticker: [{surprise_pct, ...}]} from
                       get_earnings_surprises_batch(). When supplied,
                       L1 surprise is added as a continuous score bonus.

    Returns:
        Dict of {ticker: {"returns": {...}, "composite_score": ...}}
    """
    results = {}

    for ticker, df in price_data.items():
        try:
            # ── Quality filters ────────────────────────────────────────
            latest_price = float(df["Close"].dropna().iloc[-1]) if not df.empty else 0
            if latest_price < MIN_STOCK_PRICE:
                continue

            adv = _calc_adv_usd(df)
            if adv is not None and adv < MIN_ADV_USD:
                logger.debug(f"[FILTER] {ticker} excluded: ADV ${adv:,.0f} < ${MIN_ADV_USD:,.0f}")
                continue

            # ── Signals ───────────────────────────────────────────────
            returns = calculate_returns(df, windows)
            returns["TREND_QUALITY"] = calculate_trend_quality(df)

            # Earnings surprise as continuous score (L1 surprise %, capped ±30)
            if earnings_data and ticker in earnings_data:
                e = earnings_data[ticker]
                l1 = e[0].get("surprise_pct") if e else None
                if l1 is not None:
                    try:
                        returns["EARNINGS_SCORE"] = float(max(-30, min(30, float(l1))))
                    except (TypeError, ValueError):
                        pass

            composite = calculate_composite_score(returns)
            volatility = calculate_volatility(df)

            results[ticker] = {
                "returns":        returns,
                "composite_score": composite,
                "volatility":      volatility,
                "latest_price":    latest_price,
                "adv_usd":         adv,
            }
        except Exception as e:
            logger.warning(f"Failed to calculate momentum for {ticker}: {e}")

    # Cross-sectional z-score normalization (recalculates composite after)
    if USE_CROSS_SECTIONAL_ZSCORE and results:
        results = _zscore_normalize_signals(results)
        for ticker in results:
            results[ticker]["composite_score"] = calculate_composite_score(
                results[ticker]["returns"]
            )

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

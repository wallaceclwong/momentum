"""
Residual momentum — strip market (SPY) and sector-ETF beta from each stock's
returns before computing momentum windows. This targets alpha from
stock-specific momentum and removes exposure to factor-level moves.

Reference: Blitz, Huij, Martens (2011) "Residual Momentum"
  — higher Sharpe and lower crash risk than raw price momentum.

Implementation notes:
  • We work with daily log returns on a rolling lookback (default 252d).
  • For each stock:
        r_stock_t = alpha + beta_m * r_SPY_t + beta_s * r_sector_t + eps_t
    Residuals `eps_t` are cumulated to form a residual-return series,
    which is then fed into the existing momentum window calculator.
  • If the sector ETF is missing, we fall back to market-only regression.
  • If the stock has too little history (< lookback+21), we return the
    original price frame unchanged — caller's filters handle exclusion.
"""
from __future__ import annotations
import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

from backend.config import (
    RESIDUAL_MOMENTUM_LOOKBACK,
    RESIDUAL_REGRESS_SECTOR,
    SECTORS,  # {ETF: sector name}
)

logger = logging.getLogger(__name__)

# Reverse map for convenience: "Information Technology" -> "XLK"
_SECTOR_TO_ETF = {v: k for k, v in SECTORS.items()}


def _log_returns(series: pd.Series) -> pd.Series:
    """Daily log returns (aligned, NaN-dropped)."""
    s = series.astype(float).dropna()
    return np.log(s / s.shift(1)).dropna()


def _regress_residuals(
    r_stock: pd.Series,
    r_market: pd.Series,
    r_sector: Optional[pd.Series] = None,
) -> Optional[pd.Series]:
    """
    OLS regression: r_stock = a + b_m * r_market (+ b_s * r_sector) + eps.
    Returns the residual series aligned to r_stock's index.
    """
    # Align on common dates
    frames = [r_stock.rename("y"), r_market.rename("xm")]
    if r_sector is not None:
        frames.append(r_sector.rename("xs"))
    df = pd.concat(frames, axis=1).dropna()
    if len(df) < 60:
        return None

    y = df["y"].values
    X_cols = [np.ones(len(df)), df["xm"].values]
    if "xs" in df.columns:
        X_cols.append(df["xs"].values)
    X = np.column_stack(X_cols)

    # Solve beta = (X'X)^-1 X'y  with numpy lstsq for stability
    try:
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    except np.linalg.LinAlgError:
        return None

    eps = y - X @ beta
    return pd.Series(eps, index=df.index)


def build_residual_price_frames(
    price_data: Dict[str, pd.DataFrame],
    ticker_to_sector: Dict[str, str],
    lookback: Optional[int] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Build a dict of residual-return-based "price" frames (one per stock)
    that are drop-in compatible with `calculate_returns` / `calculate_trend_quality`.

    The resulting frame has a single "Close" column equal to
    exp(cumulative residual log-returns) — i.e. a synthetic price series
    with market + sector exposure stripped out.

    If the regression cannot be run (missing SPY, missing sector ETF in both
    data and price_data, too little history), the original frame is returned
    unchanged so the pipeline degrades gracefully.

    Args:
        price_data:        {ticker: OHLCV DataFrame}  — must include "SPY" and
                           the 11 sector ETFs (XLK, XLC, ...). The backtester
                           already downloads these; the live scheduler needs
                           to include them too (it does, via get_sector_etf_weights).
        ticker_to_sector:  {ticker: "Information Technology", ...}
        lookback:          days of return history to fit (default from config).

    Returns:
        {ticker: DataFrame(Close=synthetic_residual_price)}
    """
    lookback = lookback or RESIDUAL_MOMENTUM_LOOKBACK

    if "SPY" not in price_data:
        logger.warning("[RESIDUAL] SPY missing from price_data — skipping residualisation")
        return price_data

    spy_rets = _log_returns(price_data["SPY"]["Close"])

    # Pre-compute sector ETF returns
    sector_rets: Dict[str, pd.Series] = {}
    if RESIDUAL_REGRESS_SECTOR:
        for etf in SECTORS.keys():
            if etf in price_data and "Close" in price_data[etf].columns:
                sector_rets[etf] = _log_returns(price_data[etf]["Close"])

    out: Dict[str, pd.DataFrame] = {}
    skipped = 0

    for ticker, df in price_data.items():
        # Pass through SPY and sector ETFs unchanged
        if ticker == "SPY" or ticker in SECTORS:
            out[ticker] = df
            continue

        try:
            closes = df["Close"].dropna()
            if len(closes) < max(60, lookback // 4):
                out[ticker] = df
                skipped += 1
                continue

            stock_rets = _log_returns(closes)

            # Use at most `lookback` most recent days for regression
            stock_rets = stock_rets.iloc[-lookback:]

            # Fetch sector series for this stock
            sector_r = None
            if RESIDUAL_REGRESS_SECTOR:
                sector_name = ticker_to_sector.get(ticker)
                etf = _SECTOR_TO_ETF.get(sector_name) if sector_name else None
                if etf and etf in sector_rets:
                    sector_r = sector_rets[etf]

            eps = _regress_residuals(stock_rets, spy_rets, sector_r)
            if eps is None or len(eps) < 60:
                out[ticker] = df
                skipped += 1
                continue

            # Build synthetic price = exp(cumulative residual returns)
            synth = np.exp(eps.cumsum())
            # Scale to start at the original price of eps.index[0] so that the
            # downstream % return calculations remain in a sensible range.
            first_real_price = float(closes.reindex(eps.index).dropna().iloc[0])
            synth = synth * first_real_price / float(synth.iloc[0])

            # Preserve Volume for ADV filter; only override Close
            new_df = df.copy()
            new_df = new_df.reindex(synth.index.union(new_df.index))
            new_df.loc[synth.index, "Close"] = synth.values
            out[ticker] = new_df

        except Exception as e:
            logger.debug(f"[RESIDUAL] {ticker} failed: {e}")
            out[ticker] = df
            skipped += 1

    total = len(price_data) - 1  # exclude SPY
    residualised = total - skipped
    logger.info(
        f"[RESIDUAL] Built residual frames: {residualised}/{total} "
        f"(skipped={skipped}, sector_regression={RESIDUAL_REGRESS_SECTOR})"
    )
    return out

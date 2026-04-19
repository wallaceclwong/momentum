"""
Sector Rotation Strategy — Top-K UCITS sector ETF momentum rotation.

A parallel strategy to the 33-stock S&P 500 momentum screener, designed to:
  1. Eliminate US estate tax exposure (Ireland-domiciled UCITS ETFs)
  2. Simplify execution (3 ETFs vs 33 stocks)
  3. Reduce operational overhead (no stock screening, no earnings filter)

Strategy:
  - Universe: 11 GICS sector ETFs (US SPDR XL* for backtest, UCITS IE-domiciled for live)
  - Signal: 12-minus-1 month momentum (Asness et al. standard)
  - Selection: hold top-K sectors (default K=3), equal weight
  - Rebalance: monthly, last Friday
  - Risk layers: regime filter + crash protection (reused from 33-stock engine)

References:
  - Asness, Moskowitz & Pedersen (2013), "Value and Momentum Everywhere"
  - Faber (2007), "A Quantitative Approach to Tactical Asset Allocation"
  - Blitz & Hoogteijling (2022), "Residual Equity Momentum for Corporate Bonds"
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dateutil.relativedelta import relativedelta

import numpy as np
import pandas as pd

from backend.config import (
    SECTOR_ROTATION_LOOKBACK,
    SECTOR_ROTATION_SKIP,
    SECTOR_ROTATION_TOP_K,
    SECTOR_BACKTEST_PROXIES,
    SECTOR_LIVE_UCITS,
    USE_SECTOR_REGIME_FILTER,
    USE_SECTOR_CRASH_PROTECTION,
    USE_SECTOR_ABSOLUTE_MOMENTUM,
    SECTOR_ABS_MOM_THRESHOLD,
    BACKTEST_SLIPPAGE,
    BACKTEST_COMMISSION_PER_SHARE,
    REGIME_MA_DAYS,
    REGIME_MA_SHORT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core signal + selection (pure functions — fully unit-testable)
# ---------------------------------------------------------------------------
def compute_sector_momentum(
    monthly_prices: pd.DataFrame,
    as_of: pd.Timestamp,
    lookback: int = SECTOR_ROTATION_LOOKBACK,
    skip: int = SECTOR_ROTATION_SKIP,
) -> Optional[pd.Series]:
    """
    Compute 12-minus-1 momentum for each sector ETF as of a given date.

    Returns a Series of momentum scores indexed by ticker, or None if
    insufficient history.

    Formula: price(t-skip) / price(t-lookback) - 1
    """
    if as_of not in monthly_prices.index:
        raise ValueError(f"{as_of} not in monthly price index")
    idx = monthly_prices.index.get_loc(as_of)
    if idx < lookback:
        return None
    p_recent = monthly_prices.iloc[idx - skip]
    p_long   = monthly_prices.iloc[idx - lookback]
    return (p_recent / p_long - 1).astype(float)


def select_top_sectors(
    momentum_scores: pd.Series,
    top_k: int = SECTOR_ROTATION_TOP_K,
    absolute_threshold: Optional[float] = None,
) -> List[str]:
    """
    Return the top-K tickers (by momentum score, descending).

    If absolute_threshold is not None, only tickers with score > threshold
    qualify (Faber 2007 / Antonacci dual momentum). May return < top_k
    tickers if not enough qualify; may return [] if none qualify.
    """
    if momentum_scores is None:
        return []
    ranked = momentum_scores.dropna().sort_values(ascending=False)
    if absolute_threshold is not None:
        ranked = ranked[ranked > absolute_threshold]
    return ranked.head(top_k).index.tolist()


def build_target_weights(
    top_tickers: List[str],
    all_tickers: List[str],
    deployment: float = 1.0,
) -> Dict[str, float]:
    """
    Build a weight dict covering all sector tickers.
    Top-K get equal weight × deployment; others get 0.
    """
    if not top_tickers:
        return {t: 0.0 for t in all_tickers}
    w = deployment / len(top_tickers)
    return {t: (w if t in top_tickers else 0.0) for t in all_tickers}


# ---------------------------------------------------------------------------
# Rebalance dates (last Friday of month) — matches 33-stock convention
# ---------------------------------------------------------------------------
def get_rebalance_dates(start: datetime, end: datetime) -> List[datetime]:
    dates: List[datetime] = []
    cur = start
    while cur < end:
        last_day = cur.replace(day=28) + timedelta(days=4)
        last_day = last_day - timedelta(days=last_day.day)
        while last_day.weekday() != 4:  # Friday=4
            last_day -= timedelta(days=1)
        if start <= last_day <= end:
            dates.append(last_day)
        cur += relativedelta(months=1)
    return dates


# ---------------------------------------------------------------------------
# Backtest engine (daily NAV tracking, monthly rebalance)
# ---------------------------------------------------------------------------
def run_sector_backtest(
    start_date: str,
    end_date: str,
    daily_prices: pd.DataFrame,
    top_k: int = SECTOR_ROTATION_TOP_K,
    apply_regime: bool = USE_SECTOR_REGIME_FILTER,
    apply_crash_protection: bool = USE_SECTOR_CRASH_PROTECTION,
    apply_absolute_momentum: bool = USE_SECTOR_ABSOLUTE_MOMENTUM,
    abs_mom_threshold: float = SECTOR_ABS_MOM_THRESHOLD,
    slippage_bps: float = BACKTEST_SLIPPAGE,
) -> Dict:
    """
    Run sector rotation backtest.

    Args:
        start_date, end_date: 'YYYY-MM-DD' strings
        daily_prices: wide DataFrame (index=date, cols=ticker) — must include
                      all SECTOR_BACKTEST_PROXIES tickers + 'SPY' + '^VIX'
        top_k: number of top sectors to hold
        apply_regime: scale deployment by SPY MA50/MA200 + VIX regime classifier
        apply_crash_protection: scale deployment by inverse realised portfolio vol
        slippage_bps: per-trade slippage as fraction (0.0005 = 5bps)

    Returns:
        {
          "nav_series": pd.Series (daily NAV, starts at 100),
          "holdings_log": list of dicts per rebalance,
          "metrics": dict with CAGR/Sharpe/MaxDD/Vol/Worst1Y,
          "start_date", "end_date", "top_k",
        }
    """
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt   = datetime.strptime(end_date, "%Y-%m-%d")

    # Subset prices
    sector_tickers = list(SECTOR_BACKTEST_PROXIES.values())
    needed = sector_tickers + (["SPY"] if apply_regime else [])
    missing = [t for t in needed if t not in daily_prices.columns]
    if missing:
        raise ValueError(f"Missing price columns: {missing}")

    prices = daily_prices.loc[start_dt:end_dt].copy()
    if prices.empty:
        raise ValueError(f"No price data in {start_date} -> {end_date}")

    # Restrict to tickers that have data in this window (XLC pre-2018, XLRE pre-2015)
    active_tickers = [t for t in sector_tickers if prices[t].dropna().shape[0] > 0]
    logger.info(f"[SECTOR] Active sectors in window: {active_tickers}")

    # Monthly price snapshots (end-of-month) for momentum signal
    monthly_prices = prices[active_tickers].resample("ME").last()

    # Rebalance schedule
    rebal_dates = get_rebalance_dates(start_dt, end_dt)
    rebal_set = {d.date() for d in rebal_dates}
    logger.info(f"[SECTOR] {len(rebal_dates)} rebalance dates")

    # VIX series for regime (optional)
    vix_series = prices["^VIX"].dropna() if "^VIX" in prices.columns else None

    # Daily NAV tracking
    nav = 100.0
    nav_records: List[Dict] = []
    holdings_log: List[Dict] = []
    current_weights: Dict[str, float] = {t: 0.0 for t in active_tickers}
    prev_portfolio_returns: List[float] = []  # rolling, for crash protection

    trading_days = prices.index

    for i, dt in enumerate(trading_days):
        # ── REBALANCE ────────────────────────────────────────────────────
        if dt.date() in rebal_set:
            # Find the most recent month-end <= dt
            prior_me = monthly_prices.index[monthly_prices.index <= dt]
            if len(prior_me) == 0:
                nav_records.append({"date": dt, "nav": nav}); continue
            signal_date = prior_me[-1]

            # Only rank sectors that have data for full lookback window
            idx_me = monthly_prices.index.get_loc(signal_date)
            if idx_me < SECTOR_ROTATION_LOOKBACK:
                nav_records.append({"date": dt, "nav": nav}); continue

            valid_sectors = [
                t for t in active_tickers
                if pd.notna(monthly_prices[t].iloc[idx_me - SECTOR_ROTATION_LOOKBACK])
                and pd.notna(monthly_prices[t].iloc[idx_me - SECTOR_ROTATION_SKIP])
            ]
            if len(valid_sectors) < top_k:
                nav_records.append({"date": dt, "nav": nav}); continue

            mom_series = compute_sector_momentum(
                monthly_prices[valid_sectors], signal_date
            )
            top = select_top_sectors(
                mom_series, top_k=top_k,
                absolute_threshold=abs_mom_threshold if apply_absolute_momentum else None,
            )

            # ── Regime filter ─────────────────────────────────────────────
            deployment = 1.0
            regime_label = "N/A"
            if apply_regime and "SPY" in prices.columns:
                spy_to_date = prices["SPY"].loc[:dt].dropna()
                if len(spy_to_date) >= REGIME_MA_DAYS:
                    spy_now = float(spy_to_date.iloc[-1])
                    ma200   = float(spy_to_date.iloc[-REGIME_MA_DAYS:].mean())
                    ma50    = float(spy_to_date.iloc[-REGIME_MA_SHORT:].mean())
                    vix_now = None
                    if vix_series is not None:
                        vix_to_date = vix_series.loc[:dt]
                        if len(vix_to_date) > 0:
                            vix_now = float(vix_to_date.iloc[-1])
                    # Reuse 33-stock regime classifier for consistency
                    from backend.engine.regime import _classify
                    regime_label, deployment = _classify(spy_now, ma50, ma200, vix_now)

            # ── Crash protection: vol-scale deployment (simple version) ─
            if apply_crash_protection and len(prev_portfolio_returns) >= 21:
                recent_vol = np.std(prev_portfolio_returns[-21:]) * np.sqrt(252)
                target_vol = 0.15
                crash_scale = min(1.0, target_vol / recent_vol) if recent_vol > 0 else 1.0
                deployment *= crash_scale

            target_weights = build_target_weights(top, active_tickers, deployment)

            # Transaction costs (slippage + commission proxy)
            # Commission on ETFs ~ $0.50/trade at IBKR; approximate as 1bps of trade value
            total_rebal_cost = 0.0
            for t, new_w in target_weights.items():
                old_w = current_weights.get(t, 0.0)
                trade_value = abs(new_w - old_w) * nav
                total_rebal_cost += trade_value * slippage_bps
                total_rebal_cost += trade_value * 0.0001  # 1bps ETF commission proxy
            nav -= total_rebal_cost

            current_weights = target_weights
            holdings_log.append({
                "date": dt,
                "top_sectors": top,
                "weights": dict(current_weights),
                "regime": regime_label,
                "deployment": round(deployment, 4),
                "momentum_scores": {t: float(mom_series[t]) for t in valid_sectors if t in mom_series.index},
                "rebal_cost": round(total_rebal_cost, 4),
                "nav_after_rebal": round(nav, 4),
            })

        # ── DAILY NAV UPDATE ─────────────────────────────────────────────
        if i > 0 and any(w > 0 for w in current_weights.values()):
            prev_dt = trading_days[i - 1]
            port_r = 0.0
            for t, w in current_weights.items():
                if w == 0:
                    continue
                p_now = prices.at[dt, t] if t in prices.columns else np.nan
                p_prev = prices.at[prev_dt, t] if t in prices.columns else np.nan
                if pd.notna(p_now) and pd.notna(p_prev) and p_prev > 0:
                    port_r += w * (p_now / p_prev - 1)
            nav *= (1 + port_r)
            prev_portfolio_returns.append(port_r)

        nav_records.append({"date": dt, "nav": nav})

    # ── Metrics ─────────────────────────────────────────────────────────
    nav_series = pd.Series(
        [r["nav"] for r in nav_records],
        index=pd.to_datetime([r["date"] for r in nav_records]),
    )
    metrics = compute_metrics(nav_series)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "top_k": top_k,
        "nav_series": nav_series,
        "holdings_log": holdings_log,
        "metrics": metrics,
        "n_rebalances": len(holdings_log),
    }


def compute_metrics(nav: pd.Series, rf: float = 0.03) -> Dict:
    """Standard performance metrics on daily NAV."""
    nav = nav.dropna()
    if len(nav) < 2:
        return {"cagr": 0, "sharpe": 0, "max_drawdown": 0,
                "volatility": 0, "worst_1y": 0, "final_nav": float(nav.iloc[-1]) if len(nav) else 0}
    daily_ret = nav.pct_change().dropna()
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / years) - 1 if years > 0 else 0
    vol = float(daily_ret.std() * np.sqrt(252))
    sharpe = (cagr - rf) / vol if vol > 0 else 0
    max_dd = float((nav / nav.cummax() - 1).min())
    worst_1y = float(
        daily_ret.rolling(252).apply(lambda x: (1 + x).prod() - 1, raw=True).min()
    )
    return {
        "cagr": float(cagr), "sharpe": float(sharpe),
        "max_drawdown": max_dd, "volatility": vol,
        "worst_1y": worst_1y, "final_nav": float(nav.iloc[-1]),
        "years": round(years, 2),
    }


# ---------------------------------------------------------------------------
# Live screener: produce today's target allocation
# ---------------------------------------------------------------------------
def run_sector_screener(
    daily_prices: pd.DataFrame,
    as_of: Optional[pd.Timestamp] = None,
    top_k: int = SECTOR_ROTATION_TOP_K,
    use_live_tickers: bool = True,
) -> Dict:
    """
    Compute today's top-K sectors for live trading.

    Args:
        daily_prices: wide DataFrame with sector proxy tickers (XL* or UCITS)
        as_of:        date to score (default: last available trading day)
        top_k:        number of sectors to hold
        use_live_tickers: True → return UCITS tickers; False → return US proxies

    Returns:
        {
          "as_of":           timestamp,
          "top_sectors":     list of sector names,
          "tickers":         list of tickers to buy (UCITS or US)
          "weights":         dict sector_name -> target weight (%)
          "momentum_scores": dict sector_name -> 12-1 momentum
        }
    """
    sector_names = list(SECTOR_BACKTEST_PROXIES.keys())
    proxy_tickers = list(SECTOR_BACKTEST_PROXIES.values())

    # Use US proxies for momentum signal (more data history)
    if as_of is None:
        as_of = daily_prices.index[-1]
    # Need at least lookback + skip months of history
    monthly = daily_prices[proxy_tickers].resample("ME").last()
    signal_date = monthly.index[monthly.index <= as_of][-1]
    mom = compute_sector_momentum(monthly, signal_date)
    if mom is None:
        raise RuntimeError("Insufficient history for momentum signal")

    top_proxy_tickers = select_top_sectors(
        mom, top_k=top_k,
        absolute_threshold=SECTOR_ABS_MOM_THRESHOLD if USE_SECTOR_ABSOLUTE_MOMENTUM else None,
    )
    # Map proxy tickers back to sector names
    proxy_to_sector = {v: k for k, v in SECTOR_BACKTEST_PROXIES.items()}
    top_sector_names = [proxy_to_sector[t] for t in top_proxy_tickers]

    # Output tickers (either UCITS live or US proxy)
    ticker_map = SECTOR_LIVE_UCITS if use_live_tickers else SECTOR_BACKTEST_PROXIES
    live_tickers = [ticker_map[s] for s in top_sector_names]

    # Equal-weight among qualifying sectors (may be < top_k if abs-momentum filter active)
    n = len(top_sector_names)
    equal_w = (1.0 / n) if n > 0 else 0.0
    weights = {s: equal_w for s in top_sector_names}
    # If no sectors qualified, signal "go to cash"
    if n == 0:
        logger.warning("[SECTOR] No sectors have positive momentum — recommend CASH")

    return {
        "as_of": as_of,
        "signal_date": signal_date,
        "top_sectors": top_sector_names,
        "tickers": live_tickers,
        "weights": weights,
        "momentum_scores": {proxy_to_sector[t]: float(mom[t]) for t in mom.index},
        "ticker_map_used": "UCITS" if use_live_tickers else "US_PROXIES",
    }

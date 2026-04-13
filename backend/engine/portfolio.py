"""Portfolio allocation engine - applies sector ETF weights to picks."""
from typing import Dict, List
import yfinance as yf
import pandas as pd
import numpy as np
import logging

from backend.config import SECTORS, SECTOR_TO_ETF, USE_RISK_PARITY_SECTORS, RISK_PARITY_VOL_DAYS

logger = logging.getLogger(__name__)


def get_sector_risk_parity_weights(
    prices: Dict[str, pd.Series] = None,
) -> Dict[str, float]:
    """
    Risk-parity sector weights: each sector weighted inversely to its
    RISK_PARITY_VOL_DAYS rolling volatility.

    Lower-vol sectors (e.g. Utilities, Staples) get MORE weight vs
    high-vol sectors (e.g. Tech, Energy) — equalizing risk contribution.

    Args:
        prices: Optional pre-loaded {etf_ticker: price_series} for backtesting.
                If None, fetches live data.

    Returns:
        Dict mapping sector_name -> weight (sum to 1.0)
    """
    etf_tickers = list(SECTORS.keys())
    sector_vols: Dict[str, float] = {}

    if prices is None:
        try:
            raw = yf.download(
                etf_tickers, period="6mo", interval="1d",
                auto_adjust=True, progress=False, group_by="ticker",
            )
            if isinstance(raw.columns, pd.MultiIndex):
                close = raw.xs("Close", axis=1, level=1)
            else:
                close = raw[["Close"]].rename(columns={"Close": etf_tickers[0]})
        except Exception as e:
            logger.warning(f"[RISK_PARITY] Failed to fetch ETF prices: {e} — using equal weights")
            n = len(SECTORS)
            return {s: 1.0 / n for s in SECTORS.values()}
    else:
        close = pd.DataFrame(prices)

    for etf, sector in SECTORS.items():
        try:
            series = close[etf].dropna() if etf in close.columns else pd.Series(dtype=float)
            if len(series) < RISK_PARITY_VOL_DAYS:
                continue
            daily_rets = series.pct_change().dropna().iloc[-RISK_PARITY_VOL_DAYS:]
            vol = float(daily_rets.std() * (252 ** 0.5))
            if vol > 0:
                sector_vols[sector] = vol
        except Exception as e:
            logger.warning(f"[RISK_PARITY] Vol calc failed for {etf}: {e}")

    if not sector_vols:
        n = len(SECTORS)
        return {s: 1.0 / n for s in SECTORS.values()}

    inv_vols = {s: 1.0 / v for s, v in sector_vols.items()}
    total_inv = sum(inv_vols.values())
    weights = {s: iv / total_inv for s, iv in inv_vols.items()}

    # Fill any missing sectors with zero (will get skipped in screener)
    for sector in SECTORS.values():
        if sector not in weights:
            weights[sector] = 0.0

    logger.info(
        f"[RISK_PARITY] Sector weights computed. "
        f"Lowest vol: {min(sector_vols, key=sector_vols.get)} "
        f"Highest vol: {max(sector_vols, key=sector_vols.get)}"
    )
    return weights


def get_sector_etf_weights(prices: Dict[str, pd.Series] = None) -> Dict[str, float]:
    """
    Return sector weights.

    When USE_RISK_PARITY_SECTORS=True (default), delegates to
    get_sector_risk_parity_weights() — sectors weighted by inverse volatility.

    Falls back to market-cap AUM weights from SPDR ETFs if risk parity fails.

    Args:
        prices: Optional pre-loaded ETF price dict for backtesting.
    """
    if USE_RISK_PARITY_SECTORS:
        return get_sector_risk_parity_weights(prices=prices)

    # ── Legacy: SPDR ETF AUM-based market-cap weights ──────────
    etf_market_caps = {}
    total_market_cap = 0

    for etf_ticker, sector_name in SECTORS.items():
        try:
            etf = yf.Ticker(etf_ticker)
            info = etf.info
            market_cap = info.get("totalAssets") or info.get("marketCap")
            if market_cap:
                etf_market_caps[sector_name] = market_cap
                total_market_cap += market_cap
            else:
                logger.warning(f"No AUM for {etf_ticker}, using equal weight")
        except Exception as e:
            logger.warning(f"Failed to fetch ETF data for {etf_ticker}: {e}")

    if not etf_market_caps or total_market_cap == 0:
        logger.warning("Using equal sector weights due to data fetch failure")
        n_sectors = len(SECTORS)
        return {sector: 1.0 / n_sectors for sector in SECTORS.values()}

    weights = {s: c / total_market_cap for s, c in etf_market_caps.items()}
    logger.info(f"Sector weights (AUM) sum: {sum(weights.values()):.4f}")
    return weights


def allocate_portfolio(
    screener_results: Dict[str, List[Dict]],
    equal_sector_weight: bool = False
) -> List[Dict]:
    """
    Allocate capital to selected stocks using sector ETF weights.
    
    Each sector's budget is divided equally among its Top N picks.
    
    Args:
        screener_results: Output from screener.run_momentum_screener
        equal_sector_weight: If True, use equal weights (1/11 each sector)
                          If False, use live ETF market cap weights
    
    Returns:
        List of portfolio holdings with: ticker, sector, sector_weight, 
                                          position_weight, momentum_metrics
    """
    if equal_sector_weight:
        n_sectors = len([s for s in screener_results.values() if s])  # Only count sectors with picks
        sector_weights = {
            sector: 1.0 / n_sectors if n_sectors > 0 else 0
            for sector in screener_results.keys()
        }
    else:
        sector_weights = get_sector_etf_weights()
    
    portfolio = []
    
    for sector, picks in screener_results.items():
        if not picks:
            continue
        
        sector_budget = sector_weights.get(sector, 0)
        
        # Divide sector budget equally among top picks
        n_picks = len(picks)
        position_weight = sector_budget / n_picks if n_picks > 0 else 0
        
        for pick in picks:
            holding = {
                "ticker": pick["ticker"],
                "sector": sector,
                "sector_etf": pick.get("sector_etf"),
                "sector_weight": round(sector_budget * 100, 2),  # as %
                "position_weight": round(position_weight * 100, 2),  # as %
                "returns_4w": pick.get("returns", {}).get("4W"),
                "returns_13w": pick.get("returns", {}).get("13W"),
                "returns_26w": pick.get("returns", {}).get("26W"),
                "composite_score": pick.get("composite_score"),
                "l1_surprise": pick.get("l1_surprise"),
                "l2_surprise": pick.get("l2_surprise"),
            }
            portfolio.append(holding)
    
    # Normalize weights to ensure they sum to 100%
    total_weight = sum(h["position_weight"] for h in portfolio)
    if total_weight > 0 and abs(total_weight - 100) > 0.01:
        for holding in portfolio:
            holding["position_weight"] = round(
                holding["position_weight"] / total_weight * 100, 2
            )
    
    logger.info(f"Allocated portfolio with {len(portfolio)} positions")
    return portfolio


def get_portfolio_summary(portfolio: List[Dict]) -> Dict:
    """
    Generate summary statistics for the portfolio.
    
    Args:
        portfolio: Output from allocate_portfolio
    
    Returns:
        Summary dict with sector breakdown, avg returns, etc.
    """
    if not portfolio:
        return {"error": "Empty portfolio"}
    
    # Sector breakdown
    sector_counts = {}
    sector_weights = {}
    for holding in portfolio:
        sector = holding["sector"]
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        sector_weights[sector] = sector_weights.get(sector, 0) + holding["position_weight"]
    
    # Average returns
    avg_4w = sum(h["returns_4w"] or 0 for h in portfolio) / len(portfolio)
    avg_13w = sum(h["returns_13w"] or 0 for h in portfolio) / len(portfolio)
    avg_26w = sum(h["returns_26w"] or 0 for h in portfolio) / len(portfolio)
    
    return {
        "total_positions": len(portfolio),
        "sector_breakdown": sector_counts,
        "sector_weights": {s: round(w, 2) for s, w in sector_weights.items()},
        "avg_4w_return": round(avg_4w, 2),
        "avg_13w_return": round(avg_13w, 2),
        "avg_26w_return": round(avg_26w, 2),
    }

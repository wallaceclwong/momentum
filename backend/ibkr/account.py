"""
IBKR account queries — positions and cash balance.

Mirrors backend/etrade/account.py interface so the scheduler can
swap brokers without changing strategy logic.
"""
import os
import logging
from typing import Dict, List, Optional

import pandas as pd

from .gateway import get_ib, is_dry_run

logger = logging.getLogger(__name__)

IBKR_ACCOUNT_ID = os.getenv("IBKR_ACCOUNT_ID", "")


def get_positions() -> List[Dict]:
    """
    Return current open positions.

    Returns:
        List of dicts: {ticker, quantity, current_price, market_value, avg_cost}
    """
    if is_dry_run():
        logger.info("[IBKR] Dry-run: returning empty positions")
        return []

    ib = get_ib()
    if not ib or not ib.isConnected():
        raise RuntimeError("Not connected to IB Gateway. Call connect() first.")

    portfolio = ib.portfolio(IBKR_ACCOUNT_ID) if IBKR_ACCOUNT_ID else ib.portfolio()

    positions = []
    for item in portfolio:
        contract = item.contract
        if contract.secType != "STK":
            continue
        positions.append({
            "ticker":        contract.symbol,
            "quantity":      item.position,
            "current_price": item.marketPrice,
            "market_value":  item.marketValue,
            "avg_cost":      item.averageCost,
            "total_gain_pct": (
                (item.marketPrice - item.averageCost) / item.averageCost * 100
                if item.averageCost else 0
            ),
        })

    logger.info(f"[IBKR] Fetched {len(positions)} positions")
    return positions


def get_cash_balance() -> float:
    """
    Return available capital for trading.
    
    Returns the most conservative of:
    1. NetLiquidation (Total value)
    2. EquityWithLoanValue (Cash + stock value - margin debt)
    3. AvailableFunds (Funds available for new positions)
    """
    if is_dry_run():
        import os
        from backend.config import IBKR_TARGET_CAPITAL
        virtual_capital = float(os.getenv("PAPER_CAPITAL", str(IBKR_TARGET_CAPITAL)))
        logger.info(f"[IBKR] Dry-run: returning virtual capital ${virtual_capital:,.0f}")
        return virtual_capital

    ib = get_ib()
    if not ib or not ib.isConnected():
        raise RuntimeError("Not connected to IB Gateway. Call connect() first.")

    account_values = ib.accountValues(IBKR_ACCOUNT_ID) if IBKR_ACCOUNT_ID else ib.accountValues()
    
    metrics = {}
    for av in account_values:
        if av.currency == "USD":
            if av.tag in ["NetLiquidation", "EquityWithLoanValue", "AvailableFunds"]:
                metrics[av.tag] = float(av.value)

    if not metrics:
        raise RuntimeError("Could not fetch USD account metrics from IBKR")

    # Use the most conservative (lowest) value to avoid margin rejections
    # Usually AvailableFunds is the limiting factor for new buys.
    val = min(metrics.values())
    
    logger.info(
        f"[IBKR] Account Metrics: "
        f"NetLiq=${metrics.get('NetLiquidation', 0):,.0f}, "
        f"Equity=${metrics.get('EquityWithLoanValue', 0):,.0f}, "
        f"Available=${metrics.get('AvailableFunds', 0):,.0f}"
    )
    logger.info(f"[IBKR] Using conservative balance: ${val:,.2f}")
    
    return val


def get_position_price_history(
    duration: str = "13 M",
    bar_size: str = "1 day",
) -> Dict[str, pd.DataFrame]:
    """
    Fetch IBKR historical bars for all currently held positions.

    Use-case: Phase 5A requires 252+ days of daily bars for residual-momentum
    regression and position-level P&L. Pulling from IBKR (the same source as
    execution prices) eliminates Yahoo-vs-IBKR reconciliation drift for the
    stocks you actually own. Bulk S&P 500 screening still uses yfinance.

    Args:
        duration:   IB duration string (default 13 months — enough for 252d
                    momentum + sector-beta regression).
        bar_size:   "1 day" is standard.

    Returns:
        {ticker: DataFrame(Open, High, Low, Close, Volume, ...)}
        Empty dict in dry-run or if no positions.
    """
    from .market_data import fetch_position_history
    positions = get_positions()
    tickers = [p["ticker"] for p in positions if p.get("ticker")]
    if not tickers:
        logger.info("[IBKR] No positions — skipping historical fetch")
        return {}
    logger.info(
        f"[IBKR] Fetching {duration} of {bar_size} bars for "
        f"{len(tickers)} positions (sequential, ~{len(tickers)*0.5:.0f}s)..."
    )
    return fetch_position_history(tickers, duration=duration, bar_size=bar_size)

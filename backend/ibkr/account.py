"""
IBKR account queries — positions and cash balance.

Mirrors backend/etrade/account.py interface so the scheduler can
swap brokers without changing strategy logic.
"""
import os
import logging
from typing import Dict, List

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
    Return available cash (NetLiquidation for the account).

    Returns:
        Cash balance in USD as float.
    """
    if is_dry_run():
        import os
        virtual_capital = float(os.getenv("PAPER_CAPITAL", "100000"))
        logger.info(f"[IBKR] Dry-run: returning virtual capital ${virtual_capital:,.0f}")
        return virtual_capital

    ib = get_ib()
    if not ib or not ib.isConnected():
        raise RuntimeError("Not connected to IB Gateway. Call connect() first.")

    account_values = ib.accountValues(IBKR_ACCOUNT_ID) if IBKR_ACCOUNT_ID else ib.accountValues()

    for av in account_values:
        if av.tag == "NetLiquidation" and av.currency == "USD":
            value = float(av.value)
            logger.info(f"[IBKR] Net liquidation value: ${value:,.2f}")
            return value

    raise RuntimeError("Could not fetch NetLiquidation from account values")

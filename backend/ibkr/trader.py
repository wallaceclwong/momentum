"""
IBKR order placement for momentum strategy rebalancing.

Uses Adaptive Market Orders (IBALGO) which fill at/near midpoint
with minimal market impact — suitable for monthly rebalancing.

Dry-run mode: logs the full trade plan but places no orders.
"""
import time
import logging
from typing import Dict, List, Tuple

from .gateway import get_ib, is_dry_run

logger = logging.getLogger(__name__)

MIN_TRADE_VALUE = 50.0  # skip tiny adjustments below this USD threshold


def compute_rebalance_trades(
    target_weights: Dict[str, float],
    current_positions: List[Dict],
    portfolio_value: float,
) -> Tuple[List[Dict], List[Dict]]:
    """
    Compare target vs current holdings and compute required trades.

    Args:
        target_weights:     {ticker: weight} — weights should sum to ~1.0
        current_positions:  output of get_positions()
        portfolio_value:    total portfolio value in USD

    Returns:
        (buys, sells) — each is a list of trade dicts
    """
    current = {p["ticker"]: p for p in current_positions if p.get("ticker")}

    buys: List[Dict] = []
    sells: List[Dict] = []

    # Positions to close entirely (not in new target)
    for ticker, pos in current.items():
        if ticker not in target_weights:
            sells.append({
                "ticker":          ticker,
                "shares":          abs(pos["quantity"]),
                "estimated_value": abs(pos["market_value"]),
                "reason":          "Not in new target portfolio",
            })

    # Positions to open or resize
    for ticker, weight in target_weights.items():
        target_value  = portfolio_value * weight
        current_value = current.get(ticker, {}).get("market_value", 0)
        diff_value    = target_value - current_value

        if abs(diff_value) < MIN_TRADE_VALUE:
            continue  # skip tiny adjustments

        current_price = current.get(ticker, {}).get("current_price") or 1.0
        shares = abs(diff_value) / current_price

        if diff_value > 0:
            buys.append({
                "ticker":          ticker,
                "shares":          round(shares, 4),
                "estimated_value": round(diff_value, 2),
                "reason":          "Underweight — buy to target",
            })
        else:
            sells.append({
                "ticker":          ticker,
                "shares":          round(shares, 4),
                "estimated_value": round(abs(diff_value), 2),
                "reason":          "Overweight — trim to target",
            })

    return buys, sells


def _place_adaptive_order(ticker: str, action: str, shares: float) -> Dict:
    """
    Place a single Adaptive Market Order via ib_insync.

    Adaptive algo fills near midpoint with minimal market impact.
    """
    try:
        from ib_insync import Stock, Order
    except ImportError:
        raise ImportError("ib_insync is not installed. Run: pip install ib_insync")

    ib = get_ib()
    if not ib or not ib.isConnected():
        raise RuntimeError("Not connected to IB Gateway.")

    contract = Stock(ticker, "SMART", "USD")
    ib.qualifyContracts(contract)

    order = Order()
    order.action          = action            # "BUY" or "SELL"
    order.orderType       = "MKT"
    order.totalQuantity   = max(1, round(shares))
    order.algoStrategy    = "Adaptive"
    order.algoParams      = [("adaptivePriority", "Patient")]
    order.tif             = "DAY"

    trade = ib.placeOrder(contract, order)
    logger.info(f"[IBKR] {action} {order.totalQuantity} {ticker}  orderId={trade.order.orderId}")

    return {
        "action":    action,
        "ticker":    ticker,
        "shares":    order.totalQuantity,
        "order_id":  trade.order.orderId,
        "status":    "submitted",
    }


def execute_rebalance(
    buys:          List[Dict],
    sells:         List[Dict],
    dry_run:       bool = True,
    delay_seconds: float = 0.5,
) -> Dict:
    """
    Execute a full rebalance: sells first, then buys.

    Args:
        buys:          list of buy trade dicts from compute_rebalance_trades()
        sells:         list of sell trade dicts from compute_rebalance_trades()
        dry_run:       if True, log plan only — no orders placed
        delay_seconds: pause between orders to avoid rate limits

    Returns:
        {sells: [...], buys: [...], errors: [...]}
    """
    results = {"sells": [], "buys": [], "errors": []}

    all_trades = [("SELL", t) for t in sells] + [("BUY", t) for t in buys]

    if dry_run or is_dry_run():
        logger.info(f"[DRY RUN] Would execute {len(sells)} sells + {len(buys)} buys:")
        for action, t in all_trades:
            logger.info(
                f"  {action:4s}  {t['ticker']:<6s}  "
                f"{t['shares']:>8.2f} shares  "
                f"~${t['estimated_value']:>9,.0f}  — {t['reason']}"
            )
        results["sells"] = sells
        results["buys"]  = buys
        return results

    # ── Live execution ─────────────────────────────────────────
    for action, trade in all_trades:
        try:
            result = _place_adaptive_order(
                ticker=trade["ticker"],
                action=action,
                shares=trade["shares"],
            )
            if action == "SELL":
                results["sells"].append(result)
            else:
                results["buys"].append(result)

            if delay_seconds > 0:
                time.sleep(delay_seconds)

        except Exception as e:
            logger.error(f"[IBKR] Order failed: {action} {trade['ticker']}: {e}")
            results["errors"].append({
                "action": action,
                "ticker": trade["ticker"],
                "error":  str(e),
            })

    return results

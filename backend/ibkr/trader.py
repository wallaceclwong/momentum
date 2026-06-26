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
    from backend.config import (
        USE_DRIFT_THRESHOLD,
        REBALANCE_DRIFT_THRESHOLD,
    )

    current = {p["ticker"]: p for p in current_positions if p.get("ticker")}

    buys: List[Dict] = []
    sells: List[Dict] = []
    skipped_drift = 0

    # Positions to close entirely (not in new target) — always execute fully
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
            continue  # skip tiny dollar adjustments

        # Phase 5A: drift-threshold partial rebalancing
        # Skip trades where position is already within DRIFT_THRESHOLD of target.
        # New positions (current_value == 0) always trade.
        if USE_DRIFT_THRESHOLD and current_value > 0 and target_value > 0:
            drift = abs(diff_value) / target_value
            if drift < REBALANCE_DRIFT_THRESHOLD:
                skipped_drift += 1
                logger.debug(
                    f"[DRIFT] {ticker}: drift {drift:.1%} < "
                    f"{REBALANCE_DRIFT_THRESHOLD:.0%} — skipping rebalance"
                )
                continue

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

    if USE_DRIFT_THRESHOLD and skipped_drift > 0:
        logger.info(
            f"[DRIFT] Skipped {skipped_drift} trades within "
            f"{REBALANCE_DRIFT_THRESHOLD:.0%} of target (partial rebalance)"
        )

    return buys, sells


def _place_order(ticker: str, action: str, shares: float, strategy: str = "ADAPTIVE") -> Dict:
    """
    Place an order via ib_insync using selected strategy.
    
    Strategies:
      - "ADAPTIVE": IBALGO fills near midpoint with Urgent priority.
      - "MARKET":   Standard IB market order.
    """
    try:
        from ib_insync import Stock, Order, TagValue
    except ImportError:
        raise ImportError("ib_insync is not installed. Run: pip install ib_insync")

    from backend.config import IBKR_ADAPTIVE_PRIORITY

    ib = get_ib()
    if not ib or not ib.isConnected():
        raise RuntimeError("Not connected to IB Gateway.")

    contract = Stock(ticker, "SMART", "USD")
    ib.qualifyContracts(contract)

    order = Order()
    order.action        = action            # "BUY" or "SELL"
    order.totalQuantity = max(1, round(shares))
    order.tif           = "DAY"

    if strategy == "ADAPTIVE":
        order.orderType    = "MKT"
        order.algoStrategy = "Adaptive"
        order.algoParams   = [TagValue("adaptivePriority", IBKR_ADAPTIVE_PRIORITY)]
        strategy_label     = f"Adaptive({IBKR_ADAPTIVE_PRIORITY})"
    else:
        order.orderType    = "MKT"
        strategy_label     = "Market"

    trade = ib.placeOrder(contract, order)
    logger.info(f"[IBKR] {action} {order.totalQuantity} {ticker} ({strategy_label})  orderId={trade.order.orderId}")

    return {
        "action":    action,
        "ticker":    ticker,
        "shares":    order.totalQuantity,
        "order_id":  trade.order.orderId,
        "status":    "submitted",
        "strategy":  strategy,
    }


def execute_rebalance(
    buys:          List[Dict],
    sells:         List[Dict],
    dry_run:       bool = True,
    delay_seconds: float = 0.5,
) -> Dict:
    """
    Execute a full rebalance: sells first, then buys.
    
    Implements fallback: if Adaptive order is rejected, try a standard Market order.
    """
    from backend.config import IBKR_ORDER_STRATEGY

    results = {"sells": [], "buys": [], "errors": []}

    all_trades = [("SELL", t) for t in sells] + [("BUY", t) for t in buys]

    if dry_run or is_dry_run():
        logger.info(f"[DRY RUN] Would execute {len(sells)} sells + {len(buys)} buys (Strategy: {IBKR_ORDER_STRATEGY}):")
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
        ticker = trade["ticker"]
        shares = trade["shares"]
        
        try:
            # Attempt desired strategy
            result = _place_order(ticker, action, shares, strategy=IBKR_ORDER_STRATEGY)
            
            if action == "SELL":
                results["sells"].append(result)
            else:
                results["buys"].append(result)

            if delay_seconds > 0:
                time.sleep(delay_seconds)

        except Exception as e:
            error_msg = str(e)
            
            # Fallback logic: if Adaptive fails, try standard Market
            if IBKR_ORDER_STRATEGY == "ADAPTIVE" and "rejected" in error_msg.lower():
                logger.warning(f"[IBKR] Adaptive order rejected for {ticker}, falling back to MARKET order...")
                try:
                    fb_result = _place_order(ticker, action, shares, strategy="MARKET")
                    if action == "SELL":
                        results["sells"].append(fb_result)
                    else:
                        results["buys"].append(fb_result)
                    continue 
                except Exception as fb_e:
                    error_msg = f"Adaptive failed, then Market fallback failed: {fb_e}"

            logger.error(f"[IBKR] Order failed: {action} {ticker}: {error_msg}")
            results["errors"].append({
                "action": action,
                "ticker": ticker,
                "error":  error_msg,
            })

    return results

"""
E*Trade order placement for momentum strategy rebalancing.
"""
import uuid
import time
import logging
from typing import Dict, List, Tuple, Optional
from .auth import get_oauth_session, BASE_URL
from .account import get_portfolio, get_balance, parse_positions

logger = logging.getLogger(__name__)


def compute_rebalance_trades(
    target_weights: Dict[str, float],
    current_positions: List[Dict],
    portfolio_value: float,
    min_trade_value: float = 50.0
) -> Tuple[List[Dict], List[Dict]]:
    """
    Compare target vs current holdings and compute required trades.

    Returns:
        (buys, sells) — each is a list of {ticker, shares, estimated_value}
    """
    current = {p["ticker"]: p for p in current_positions if p["ticker"]}

    buys, sells = [], []

    # Positions to close (not in target)
    for ticker, pos in current.items():
        if ticker not in target_weights:
            sells.append({
                "ticker": ticker,
                "shares": pos["quantity"],
                "estimated_value": pos["market_value"],
                "reason": "Not in target portfolio"
            })

    # Positions to open or resize
    for ticker, weight in target_weights.items():
        target_value = portfolio_value * weight
        current_value = current.get(ticker, {}).get("market_value", 0)
        diff_value = target_value - current_value

        if abs(diff_value) < min_trade_value:
            continue  # Skip tiny adjustments

        price = current.get(ticker, {}).get("current_price", 0) or 1
        shares = abs(diff_value) / price

        if diff_value > 0:
            buys.append({
                "ticker": ticker,
                "shares": round(shares, 4),
                "estimated_value": round(diff_value, 2),
                "reason": "Underweight — buy to target"
            })
        else:
            sells.append({
                "ticker": ticker,
                "shares": round(shares, 4),
                "estimated_value": round(abs(diff_value), 2),
                "reason": "Overweight — trim to target"
            })

    return buys, sells


def _build_order_payload(client_order_id: str, ticker: str, action: str, quantity: float) -> Dict:
    """Build E*Trade order preview/place payload."""
    return {
        "PreviewOrderRequest": {
            "orderType": "EQ",
            "clientOrderId": client_order_id,
            "Order": [{
                "allOrNone": "false",
                "priceType": "MARKET",
                "orderTerm": "GOOD_FOR_DAY",
                "marketSession": "REGULAR",
                "stopPrice": "",
                "Instrument": [{
                    "Product": {"securityType": "EQ", "symbol": ticker},
                    "orderAction": action,
                    "quantityType": "QUANTITY",
                    "quantity": str(max(1, round(quantity)))
                }]
            }]
        }
    }


def place_order(
    account_id_key: str,
    ticker: str,
    action: str,
    quantity: float,
    dry_run: bool = True
) -> Dict:
    """
    Preview then place a single market order.

    Args:
        account_id_key: E*Trade account ID key
        ticker: Stock symbol
        action: 'BUY' or 'SELL'
        quantity: Number of shares
        dry_run: If True, only preview — don't place

    Returns:
        Result dict with status and order details
    """
    session = get_oauth_session()
    if not session:
        raise RuntimeError("Not authenticated.")

    client_order_id = str(uuid.uuid4())[:8]
    payload = _build_order_payload(client_order_id, ticker, action, quantity)

    # Step 1: Preview
    preview_resp = session.post(
        f"{BASE_URL}/v1/accounts/{account_id_key}/orders/preview.json",
        json=payload
    )
    preview_resp.raise_for_status()
    preview_data = preview_resp.json().get("PreviewOrderResponse", {})
    preview_ids  = preview_data.get("PreviewIds", [{}])
    preview_id   = preview_ids[0].get("previewId") if preview_ids else None
    est_commission = preview_data.get("Order", [{}])[0].get("estimatedCommission", 0)

    result = {
        "ticker":        ticker,
        "action":        action,
        "quantity":      max(1, round(quantity)),
        "client_order_id": client_order_id,
        "preview_id":    preview_id,
        "est_commission": est_commission,
        "status":        "previewed"
    }

    if dry_run or not preview_id:
        return result

    # Step 2: Place
    place_payload = {
        "PlaceOrderRequest": {
            "orderType": "EQ",
            "clientOrderId": client_order_id,
            "Order": payload["PreviewOrderRequest"]["Order"],
            "PreviewIds": [{"previewId": preview_id}]
        }
    }
    place_resp = session.post(
        f"{BASE_URL}/v1/accounts/{account_id_key}/orders/place.json",
        json=place_payload
    )
    place_resp.raise_for_status()
    place_data  = place_resp.json().get("PlaceOrderResponse", {})
    order_ids   = place_data.get("OrderIds", [{}])
    order_id    = order_ids[0].get("orderId") if order_ids else None

    result["order_id"] = order_id
    result["status"]   = "placed" if order_id else "failed"
    return result


def execute_rebalance(
    account_id_key: str,
    buys: List[Dict],
    sells: List[Dict],
    dry_run: bool = True,
    delay_seconds: float = 0.5
) -> Dict:
    """
    Execute a full rebalance: sells first (free up cash), then buys.

    Args:
        account_id_key: E*Trade account ID key
        buys: List of {ticker, shares, ...} from compute_rebalance_trades
        sells: List of {ticker, shares, ...} from compute_rebalance_trades
        dry_run: Preview only — don't actually place orders
        delay_seconds: Pause between orders to avoid rate limiting

    Returns:
        Summary of all order results
    """
    results = {"sells": [], "buys": [], "errors": [], "dry_run": dry_run}

    # Sells first — free up cash before buying
    for trade in sells:
        try:
            qty = abs(trade["shares"])
            if qty < 1:
                continue
            r = place_order(account_id_key, trade["ticker"], "SELL", qty, dry_run)
            results["sells"].append(r)
            logger.info(f"{'[DRY]' if dry_run else '[LIVE]'} SELL {trade['ticker']} x{round(qty)} → {r['status']}")
            time.sleep(delay_seconds)
        except Exception as e:
            error = {"ticker": trade["ticker"], "action": "SELL", "error": str(e)}
            results["errors"].append(error)
            logger.error(f"SELL {trade['ticker']} failed: {e}")

    # Buys
    for trade in buys:
        try:
            qty = abs(trade["shares"])
            if qty < 1:
                continue
            r = place_order(account_id_key, trade["ticker"], "BUY", qty, dry_run)
            results["buys"].append(r)
            logger.info(f"{'[DRY]' if dry_run else '[LIVE]'} BUY  {trade['ticker']} x{round(qty)} → {r['status']}")
            time.sleep(delay_seconds)
        except Exception as e:
            error = {"ticker": trade["ticker"], "action": "BUY", "error": str(e)}
            results["errors"].append(error)
            logger.error(f"BUY {trade['ticker']} failed: {e}")

    placed = len(results["sells"]) + len(results["buys"])
    errors = len(results["errors"])
    logger.info(f"Rebalance complete: {placed} orders {'previewed' if dry_run else 'placed'}, {errors} errors")
    return results

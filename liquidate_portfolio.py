#!/usr/bin/env python
"""Liquidate all positions and cancel pending orders on IBKR paper account."""
import sys
import time
sys.path.insert(0, '.')

from backend.ibkr.gateway import connect, get_ib
from backend.ibkr.account import get_positions
from backend.ibkr.trader import execute_rebalance

print("=" * 70)
print("LIQUIDATING ALL POSITIONS")
print("=" * 70)

try:
    connect()
    ib = get_ib()
    
    if not ib or not ib.isConnected():
        print("[ERROR] Not connected to IB Gateway")
        sys.exit(1)
    
    # First, cancel any pre-existing pending orders
    print("Cancelling pre-existing pending orders...")
    ib.reqOpenOrders()
    time.sleep(1)
    pre_existing_orders = ib.openOrders()
    
    if not pre_existing_orders:
        print("No pre-existing pending orders to cancel.")
    else:
        cancelled_count = 0
        for order in pre_existing_orders:
            try:
                print(f"Cancelling order {order.orderId}...", end=" ")
                ib.cancelOrder(order)
                print("✓")
                cancelled_count += 1
                time.sleep(0.5)
            except Exception as e:
                print(f"✗ Error: {e}")
        print(f"Cancelled {cancelled_count} pre-existing orders")
    
    time.sleep(2)  # Wait for cancellations to process
    
    # Get current positions
    positions = get_positions()
    print(f"\nFound {len(positions)} open positions\n")
    
    if not positions:
        print("No positions to liquidate.")
    else:
        # Create sell list for all positions
        sells = []
        for pos in positions:
            sells.append({
                "ticker": pos['ticker'],
                "shares": pos['quantity'],
                "estimated_value": pos['market_value'],
                "reason": "Liquidation"
            })
        
        # Execute sells (not dry-run)
        print("Executing sell orders...")
        result = execute_rebalance(buys=[], sells=sells, dry_run=False, delay_seconds=0.5)
        
        print(f"\nSells executed: {len(result['sells'])}")
        for sell in result['sells']:
            print(f"  ✓ {sell['action']} {sell['shares']} {sell['ticker']} (Order {sell['order_id']})")
        
        if result['errors']:
            print(f"\nErrors: {len(result['errors'])}")
            for err in result['errors']:
                print(f"  ✗ {err['action']} {err['ticker']}: {err['error']}")
    
    # Wait for orders to settle
    print("\nWaiting for orders to settle (5 seconds)...")
    time.sleep(5)
    
    # Final status
    print("\n" + "=" * 70)
    print("FINAL STATUS")
    print("=" * 70)
    
    final_positions = get_positions()
    print(f"Remaining positions: {len(final_positions)}")
    for pos in final_positions:
        print(f"  {pos['ticker']}: {pos['quantity']} shares @ ${pos['current_price']:.2f}")
    
    ib.reqOpenOrders()
    time.sleep(1)
    final_orders = ib.openOrders()
    print(f"Pending orders: {len(final_orders)}")
    for order in final_orders:
        try:
            print(f"  Order {order.orderId}: {order.action} {order.totalQuantity} (Status: {order.status})")
        except:
            pass
    
    print("\n" + "=" * 70)
    
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

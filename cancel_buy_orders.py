#!/usr/bin/env python
"""Cancel all pending BUY orders on IBKR paper account."""
import sys
import time
sys.path.insert(0, '.')

from backend.ibkr.gateway import connect, get_ib

print("=" * 70)
print("CANCELLING ALL PENDING BUY ORDERS")
print("=" * 70)

try:
    connect()
    ib = get_ib()
    
    if not ib or not ib.isConnected():
        print("[ERROR] Not connected to IB Gateway")
        sys.exit(1)
    
    # Get pending orders
    print("\nFetching pending orders...")
    ib.reqOpenOrders()
    time.sleep(1)
    open_orders = ib.openOrders()
    
    # Filter for BUY orders only
    buy_orders = [o for o in open_orders if o.action == "BUY"]
    
    print(f"Found {len(buy_orders)} pending BUY orders out of {len(open_orders)} total orders\n")
    
    if not buy_orders:
        print("No pending BUY orders to cancel.")
    else:
        cancelled_count = 0
        for order in buy_orders:
            try:
                print(f"Cancelling BUY order {order.orderId}...", end=" ")
                ib.cancelOrder(order)
                print("✓")
                cancelled_count += 1
                time.sleep(0.5)
            except Exception as e:
                print(f"✗ Error: {e}")
        
        print(f"\nCancelled {cancelled_count} BUY orders")
    
    # Final status
    print("\n" + "=" * 70)
    print("FINAL STATUS")
    print("=" * 70)
    
    ib.reqOpenOrders()
    time.sleep(1)
    final_orders = ib.openOrders()
    
    buy_count = len([o for o in final_orders if o.action == "BUY"])
    sell_count = len([o for o in final_orders if o.action == "SELL"])
    
    print(f"Remaining orders: {len(final_orders)}")
    print(f"  BUY orders: {buy_count}")
    print(f"  SELL orders: {sell_count}")
    
    if final_orders:
        print("\nRemaining orders:")
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

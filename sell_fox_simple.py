#!/usr/bin/env python
"""Simple FOX market sell order."""
import sys
import time
sys.path.insert(0, '.')

from ib_insync import IB

print("=" * 70)
print("SELLING FOX - MARKET ORDER")
print("=" * 70)

try:
    # Use a fresh connection with a different client ID
    ib = IB()
    ib.connect('127.0.0.1', 4001, clientId=2, timeout=10)
    print("[CONNECTED] to IB Gateway")
    
    if not ib or not ib.isConnected():
        print("[ERROR] Not connected to IB Gateway")
        sys.exit(1)
    
    print("\nPlacing FOX market order...")
    
    from ib_insync import Stock, Order
    
    # Create contract
    contract = Stock('FOX', 'SMART', 'USD')
    ib.qualifyContracts(contract)
    
    # Create market order
    order = Order()
    order.action = "SELL"
    order.totalQuantity = 61  # We know it's 61 shares
    order.orderType = "MKT"
    order.tif = "DAY"
    
    # Place order
    trade = ib.placeOrder(contract, order)
    print(f"✓ Market order placed: Order {trade.order.orderId}")
    print(f"  SELL 61 FOX @ market")
    
    time.sleep(3)
    
    # Check status
    print("\n" + "=" * 70)
    print("ORDER STATUS")
    print("=" * 70)
    
    ib.reqOpenOrders()
    time.sleep(1)
    open_orders = ib.openOrders()
    
    print(f"Pending orders: {len(open_orders)}")
    for order in open_orders:
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

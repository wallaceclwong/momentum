#!/usr/bin/env python
"""Cancel FOX limit order and place a market order instead."""
import sys
import time
sys.path.insert(0, '.')

from backend.ibkr.gateway import connect, get_ib

print("=" * 70)
print("SELLING FOX WITH MARKET ORDER")
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
    
    print(f"Found {len(open_orders)} pending orders\n")
    
    # Cancel all pending orders
    for order in open_orders:
        print(f"Cancelling order {order.orderId}...", end=" ")
        try:
            ib.cancelOrder(order)
            print("✓")
            time.sleep(0.5)
        except Exception as e:
            print(f"✗ Error: {e}")
    
    time.sleep(2)  # Wait for cancellation to process
    
    # Now place a market order for FOX
    print("\nPlacing FOX market order...")
    try:
        from ib_insync import Stock, Order
        
        # Get current FOX position
        from backend.ibkr.account import get_positions
        positions = get_positions()
        fox_pos = next((p for p in positions if p['ticker'] == 'FOX'), None)
        
        if not fox_pos:
            print("[ERROR] FOX position not found")
            sys.exit(1)
        
        current_price = fox_pos['current_price']
        shares = fox_pos['quantity']
        
        print(f"  Current price: ${current_price:.2f}")
        print(f"  Shares: {shares}")
        
        # Create contract and order
        contract = Stock('FOX', 'SMART', 'USD')
        ib.qualifyContracts(contract)
        
        order = Order()
        order.action = "SELL"
        order.totalQuantity = int(shares)
        order.orderType = "MKT"
        order.tif = "DAY"
        
        # Place order
        trade = ib.placeOrder(contract, order)
        print(f"\n✓ Market order placed: Order {trade.order.orderId}")
        print(f"  SELL {int(shares)} FOX @ market")
        
        time.sleep(3)
        
    except Exception as e:
        print(f"[ERROR] Failed to place market order: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Final status
    print("\n" + "=" * 70)
    print("FINAL STATUS")
    print("=" * 70)
    
    ib.reqOpenOrders()
    time.sleep(1)
    final_orders = ib.openOrders()
    
    print(f"Pending orders: {len(final_orders)}")
    for order in final_orders:
        try:
            print(f"  Order {order.orderId}: {order.action} {order.totalQuantity} (Status: {order.status})")
        except:
            pass
    
    # Check positions
    from backend.ibkr.account import get_positions
    final_positions = get_positions()
    print(f"\nRemaining positions: {len(final_positions)}")
    for pos in final_positions:
        print(f"  {pos['ticker']}: {pos['quantity']} shares")
    
    print("\n" + "=" * 70)
    
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

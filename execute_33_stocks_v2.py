#!/usr/bin/env python
"""Execute 33 stock portfolio orders - v2 with robust connection handling."""
import sys
import time
sys.path.insert(0, '.')

from ib_insync import IB, Stock, Order

# Pre-selected 33 stocks from the screener (3 per sector)
STOCKS_33 = [
    'SNDK', 'LITE', 'CIEN',  # Info Tech
    'VZ', 'SATS', 'T',  # Comm Services
    'ROST', 'TPR', 'SBUX',  # Consumer Disc
    'BG', 'CASY', 'TGT',  # Consumer Staples
    'APA', 'VLO', 'HAL',  # Energy
    'CBOE', 'CME', 'CB',  # Financials
    'MRNA', 'MRK', 'JNJ',  # Health Care
    'VRT', 'FIX', 'PWR',  # Industrials
    'ALB', 'DOW', 'CF',  # Materials
    'IRM', 'VTR', 'DLR',  # Real Estate
    'EIX', 'NEE', 'AEP',  # Utilities
]

PORTFOLIO_VALUE = 125_000.0
ALLOCATION_PER_STOCK = PORTFOLIO_VALUE / len(STOCKS_33)

print("=" * 80)
print("EXECUTING 33 STOCK PORTFOLIO - v2")
print("=" * 80)

try:
    # Connect to IB Gateway
    print("\n[1/2] Connecting to IB Gateway...")
    ib = IB()
    ib.connect('127.0.0.1', 4001, clientId=7, timeout=15)
    print("✓ Connected")
    
    # Wait for connection to fully establish
    print("  Waiting for connection to stabilize (5 seconds)...")
    time.sleep(5)
    
    # Verify connection is active
    if not ib.isConnected():
        print("[ERROR] Connection lost after initial connect")
        sys.exit(1)
    
    print("✓ Connection verified")
    
    # Execute orders
    print("\n[2/2] Executing 33 BUY orders...")
    print(f"  Portfolio value: ${PORTFOLIO_VALUE:,.0f}")
    print(f"  Allocation per stock: ${ALLOCATION_PER_STOCK:,.2f}")
    
    orders_placed = 0
    errors = 0
    
    for i, ticker in enumerate(STOCKS_33, 1):
        try:
            # Create contract
            contract = Stock(ticker, 'SMART', 'USD')
            ib.qualifyContracts(contract)
            
            # Create order
            order = Order()
            order.action = "BUY"
            order.totalQuantity = 1  # Will be sized by price
            order.orderType = "MKT"
            order.tif = "DAY"
            
            # Get current price to calculate shares
            ticker_data = ib.reqMktData(contract, "", False, False)
            time.sleep(0.5)  # Wait for price data
            
            if ticker_data.last > 0:
                shares = int(ALLOCATION_PER_STOCK / ticker_data.last)
                order.totalQuantity = shares
                
                # Place order
                trade = ib.placeOrder(contract, order)
                print(f"  {i:2d}. {ticker:<6s} BUY {shares:>6d} shares @ ~${ticker_data.last:.2f}  Order {trade.order.orderId}")
                orders_placed += 1
            else:
                print(f"  {i:2d}. {ticker:<6s} [SKIP] No price data")
                errors += 1
            
            time.sleep(0.3)  # Delay between orders
            
        except Exception as e:
            print(f"  {i:2d}. {ticker:<6s} [ERROR] {str(e)[:50]}")
            errors += 1
    
    print(f"\n✓ Orders executed:")
    print(f"  Placed: {orders_placed}")
    print(f"  Errors: {errors}")
    
    # Wait for orders to settle
    print("\nWaiting for orders to settle (15 seconds)...")
    time.sleep(15)
    
    # Final status
    print("\n" + "=" * 80)
    print("FINAL STATUS")
    print("=" * 80)
    
    ib.reqOpenOrders()
    time.sleep(1)
    open_orders = ib.openOrders()
    
    print(f"\nPending orders: {len(open_orders)}")
    
    print("\n" + "=" * 80)
    if orders_placed > 0:
        print("✓ PORTFOLIO DEPLOYED")
        print(f"Orders placed: {orders_placed} BUY")
        print(f"Portfolio value: ${PORTFOLIO_VALUE:,.0f}")
        print("\nCheck your IBKR account for live positions.")
    else:
        print("✗ NO ORDERS PLACED")
        print("IB Gateway connection issue - please check and retry")
    print("=" * 80)
    
except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

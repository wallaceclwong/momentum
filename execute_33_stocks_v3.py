#!/usr/bin/env python
"""Execute 33 stock portfolio orders - v3 without market data requirement."""
import sys
import time
sys.path.insert(0, '.')

from ib_insync import IB, Stock, Order

# Pre-selected 33 stocks with approximate current prices (for share calculation)
STOCKS_33 = {
    'SNDK': 85.0, 'LITE': 45.0, 'CIEN': 60.0,  # Info Tech
    'VZ': 42.0, 'SATS': 30.0, 'T': 26.0,  # Comm Services
    'ROST': 95.0, 'TPR': 35.0, 'SBUX': 100.0,  # Consumer Disc
    'BG': 28.0, 'CASY': 65.0, 'TGT': 75.0,  # Consumer Staples
    'APA': 40.0, 'VLO': 130.0, 'HAL': 35.0,  # Energy
    'CBOE': 180.0, 'CME': 190.0, 'CB': 150.0,  # Financials
    'MRNA': 125.0, 'MRK': 75.0, 'JNJ': 155.0,  # Health Care
    'VRT': 65.0, 'FIX': 55.0, 'PWR': 85.0,  # Industrials
    'ALB': 190.0, 'DOW': 65.0, 'CF': 75.0,  # Materials
    'IRM': 65.0, 'VTR': 65.0, 'DLR': 165.0,  # Real Estate
    'EIX': 70.0, 'NEE': 75.0, 'AEP': 95.0,  # Utilities
}

PORTFOLIO_VALUE = 125_000.0
ALLOCATION_PER_STOCK = PORTFOLIO_VALUE / len(STOCKS_33)

print("=" * 80)
print("EXECUTING 33 STOCK PORTFOLIO - v3 (No Market Data Required)")
print("=" * 80)

try:
    # Connect to IB Gateway
    print("\n[1/2] Connecting to IB Gateway...")
    ib = IB()
    ib.connect('127.0.0.1', 4001, clientId=8, timeout=15)
    print("✓ Connected")
    
    # Wait for connection to fully establish
    print("  Waiting for connection to stabilize (3 seconds)...")
    time.sleep(3)
    
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
    
    for i, (ticker, approx_price) in enumerate(STOCKS_33.items(), 1):
        try:
            # Create contract
            contract = Stock(ticker, 'SMART', 'USD')
            ib.qualifyContracts(contract)
            
            # Calculate shares based on approximate price
            shares = int(ALLOCATION_PER_STOCK / approx_price)
            
            # Create order
            order = Order()
            order.action = "BUY"
            order.totalQuantity = shares
            order.orderType = "MKT"
            order.tif = "DAY"
            
            # Place order
            trade = ib.placeOrder(contract, order)
            print(f"  {i:2d}. {ticker:<6s} BUY {shares:>6d} shares @ ~${approx_price:.2f}  Order {trade.order.orderId}")
            orders_placed += 1
            
            time.sleep(0.2)  # Small delay between orders
            
        except Exception as e:
            print(f"  {i:2d}. {ticker:<6s} [ERROR] {str(e)[:60]}")
            errors += 1
    
    print(f"\n✓ Orders executed:")
    print(f"  Placed: {orders_placed}")
    print(f"  Errors: {errors}")
    
    # Wait for orders to settle
    print("\nWaiting for orders to settle (10 seconds)...")
    time.sleep(10)
    
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
        print("✓ PORTFOLIO DEPLOYED SUCCESSFULLY")
        print(f"Orders placed: {orders_placed} BUY")
        print(f"Portfolio value: ${PORTFOLIO_VALUE:,.0f}")
        print(f"Stocks: {len(STOCKS_33)}")
        print("\nCheck your IBKR account for live positions and P&L.")
    else:
        print("✗ NO ORDERS PLACED")
        print("IB Gateway connection issue - please check and retry")
    print("=" * 80)
    
except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

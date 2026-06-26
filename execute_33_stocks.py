#!/usr/bin/env python
"""Execute 33 stock portfolio orders (using pre-selected stocks from screener)."""
import sys
import time
sys.path.insert(0, '.')

from backend.ibkr.trader import compute_rebalance_trades, execute_rebalance
from ib_insync import IB

# Pre-selected 33 stocks from the screener (3 per sector)
STOCKS_33 = {
    # Information Technology
    'SNDK': 0.0303,
    'LITE': 0.0303,
    'CIEN': 0.0303,
    # Communication Services
    'VZ': 0.0303,
    'SATS': 0.0303,
    'T': 0.0303,
    # Consumer Discretionary
    'ROST': 0.0303,
    'TPR': 0.0303,
    'SBUX': 0.0303,
    # Consumer Staples
    'BG': 0.0303,
    'CASY': 0.0303,
    'TGT': 0.0303,
    # Energy
    'APA': 0.0303,
    'VLO': 0.0303,
    'HAL': 0.0303,
    # Financials
    'CBOE': 0.0303,
    'CME': 0.0303,
    'CB': 0.0303,
    # Health Care
    'MRNA': 0.0303,
    'MRK': 0.0303,
    'JNJ': 0.0303,
    # Industrials
    'VRT': 0.0303,
    'FIX': 0.0303,
    'PWR': 0.0303,
    # Materials
    'ALB': 0.0303,
    'DOW': 0.0303,
    'CF': 0.0303,
    # Real Estate
    'IRM': 0.0303,
    'VTR': 0.0303,
    'DLR': 0.0303,
    # Utilities
    'EIX': 0.0303,
    'NEE': 0.0303,
    'AEP': 0.0303,
}

print("=" * 80)
print("EXECUTING 33 STOCK PORTFOLIO")
print("=" * 80)

try:
    # Connect to IB Gateway
    print("\n[1/2] Connecting to IB Gateway...")
    ib = IB()
    ib.connect('127.0.0.1', 4001, clientId=6, timeout=10)
    print("✓ Connected")
    
    # Compute rebalance trades
    print("\n[2/2] Executing orders...")
    portfolio_value = 125_000.0
    
    buys, sells = compute_rebalance_trades(
        target_weights=STOCKS_33,
        current_positions=[],
        portfolio_value=portfolio_value
    )
    
    print(f"  BUY orders: {len(buys)}")
    print(f"  Portfolio value: ${portfolio_value:,.0f}")
    
    # Show top 10
    print(f"\n  Top 10 positions:")
    sorted_buys = sorted(buys, key=lambda x: x['estimated_value'], reverse=True)
    for i, buy in enumerate(sorted_buys[:10], 1):
        print(f"    {i:2d}. {buy['ticker']:<6s} {buy['shares']:>8.2f} shares  ~${buy['estimated_value']:>9,.0f}")
    
    # Execute orders
    print(f"\nExecuting {len(buys)} BUY orders...")
    result = execute_rebalance(buys=buys, sells=sells, dry_run=False, delay_seconds=0.3)
    
    print(f"\n✓ Orders executed:")
    print(f"  BUY orders placed: {len(result['buys'])}")
    print(f"  Errors: {len(result['errors'])}")
    
    if result['errors']:
        print(f"\n  Errors:")
        for err in result['errors'][:5]:
            print(f"    - {err['action']} {err['ticker']}: {err['error']}")
    
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
    print("✓ PORTFOLIO DEPLOYED")
    print("=" * 80)
    print(f"Orders placed: {len(result['buys'])} BUY")
    print(f"Portfolio value: ${portfolio_value:,.0f}")
    print("\nCheck your IBKR account for live positions.")
    print("=" * 80)
    
except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

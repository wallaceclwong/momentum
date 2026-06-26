#!/usr/bin/env python
"""Deploy momentum strategy: run screener and rebalance to 33-stock portfolio."""
import sys
import time
sys.path.insert(0, '.')

from backend.engine.screener import run_momentum_screener
from backend.engine.portfolio import allocate_portfolio
from backend.ibkr.trader import compute_rebalance_trades, execute_rebalance
from ib_insync import IB, Stock, Order

print("=" * 80)
print("DEPLOYING MOMENTUM STRATEGY - 33 STOCK PORTFOLIO")
print("=" * 80)

try:
    # Connect to IB Gateway
    print("\n[1/3] Connecting to IB Gateway...")
    ib = IB()
    ib.connect('127.0.0.1', 4001, clientId=4, timeout=10)
    print("✓ Connected")
    
    # Get account balance
    print("\n[2/3] Running momentum screener...")
    print("  (This may take 2-3 minutes...)")
    
    screener_results = run_momentum_screener(top_n=3)  # 3 per sector × 11 sectors = 33 stocks
    
    total_picks = sum(len(picks) for picks in screener_results.values())
    print(f"✓ Screener complete: {total_picks} stocks selected")
    
    # Display results by sector
    print("\n  Results by sector:")
    for sector, picks in screener_results.items():
        if picks:
            print(f"    {sector}: {len(picks)} stocks")
            for pick in picks[:2]:  # Show first 2
                print(f"      - {pick['ticker']}: momentum={pick.get('composite_score', 0):.2f}")
    
    # Allocate portfolio
    print("\n[3/3] Allocating portfolio and executing orders...")
    portfolio = allocate_portfolio(screener_results, equal_sector_weight=False)
    
    # Convert to target weights dict
    target_weights = {h['ticker']: h['position_weight'] / 100.0 for h in portfolio}
    
    print(f"✓ Portfolio allocated: {len(portfolio)} stocks")
    print(f"  Total allocation: {sum(target_weights.values()):.1%}")
    
    # Use $125K (keeping $7K buffer from $132K)
    portfolio_value = 125_000.0
    
    # Compute rebalance trades
    buys, sells = compute_rebalance_trades(
        target_weights=target_weights,
        current_positions=[],  # Empty - we just liquidated
        portfolio_value=portfolio_value
    )
    
    print(f"\n  Rebalance plan:")
    print(f"    BUY orders: {len(buys)}")
    print(f"    SELL orders: {len(sells)}")
    print(f"    Portfolio value: ${portfolio_value:,.0f}")
    
    # Show top 10 buys
    print(f"\n  Top 10 positions to buy:")
    sorted_buys = sorted(buys, key=lambda x: x['estimated_value'], reverse=True)
    for i, buy in enumerate(sorted_buys[:10], 1):
        print(f"    {i:2d}. {buy['ticker']:<6s} {buy['shares']:>8.2f} shares  ~${buy['estimated_value']:>9,.0f}")
    
    if len(sorted_buys) > 10:
        print(f"    ... and {len(sorted_buys) - 10} more")
    
    # Execute rebalance
    print("\n" + "=" * 80)
    print("EXECUTING REBALANCE")
    print("=" * 80)
    
    confirm = input("\nProceed with rebalance? (yes/no): ").strip().lower()
    if confirm != 'yes':
        print("Rebalance cancelled.")
        sys.exit(0)
    
    print(f"\nExecuting {len(buys)} BUY orders...")
    result = execute_rebalance(buys=buys, sells=sells, dry_run=False, delay_seconds=0.3)
    
    print(f"\n✓ Rebalance executed:")
    print(f"  BUY orders placed: {len(result['buys'])}")
    print(f"  SELL orders placed: {len(result['sells'])}")
    print(f"  Errors: {len(result['errors'])}")
    
    if result['errors']:
        print("\n  Errors encountered:")
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
    print("✓ MOMENTUM STRATEGY DEPLOYED SUCCESSFULLY")
    print("=" * 80)
    print(f"\nTarget: {len(portfolio)} stocks")
    print(f"Portfolio value: ${portfolio_value:,.0f}")
    print(f"Orders placed: {len(result['buys'])} BUY")
    print("\nCheck your IBKR account for live positions and P&L.")
    
except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

#!/usr/bin/env python
"""Deploy momentum strategy: run screener and rebalance to 33-stock portfolio."""
import sys
import time
sys.path.insert(0, '.')

from backend.engine.screener import run_momentum_screener
from backend.engine.portfolio import allocate_portfolio, get_sector_etf_weights
from backend.ibkr.account import get_cash_balance, get_positions
from backend.ibkr.trader import compute_rebalance_trades, execute_rebalance
from ib_insync import IB

print("=" * 80)
print("DEPLOYING MOMENTUM STRATEGY - 33 STOCK PORTFOLIO")
print("=" * 80)

try:
    # Connect to IB Gateway
    print("\n[1/4] Connecting to IB Gateway...")
    ib = IB()
    ib.connect('127.0.0.1', 4001, clientId=3, timeout=10)
    print("✓ Connected")
    
    # Get current cash balance
    print("\n[2/4] Checking account balance...")
    cash_balance = get_cash_balance()
    print(f"✓ Available cash: ${cash_balance:,.2f}")
    
    # Run momentum screener
    print("\n[3/4] Running momentum screener...")
    print("  (This may take 2-3 minutes...)")
    
    screener_results = run_momentum_screener(top_n=3)  # 3 per sector × 11 sectors = 33 stocks
    
    total_picks = sum(len(picks) for picks in screener_results.values())
    print(f"✓ Screener complete: {total_picks} stocks selected")
    
    # Display results by sector
    print("\n  Results by sector:")
    for sector, picks in screener_results.items():
        if picks:
            print(f"    {sector}: {len(picks)} stocks")
            for pick in picks:
                print(f"      - {pick['ticker']}: momentum={pick.get('composite_score', 0):.2f}")
    
    # Allocate portfolio
    print("\n[4/4] Allocating portfolio...")
    portfolio = allocate_portfolio(screener_results, equal_sector_weight=False)
    
    # Convert to target weights dict
    target_weights = {h['ticker']: h['position_weight'] / 100.0 for h in portfolio}
    
    print(f"✓ Portfolio allocated: {len(portfolio)} stocks")
    print(f"  Total allocation: {sum(target_weights.values()):.1%}")
    
    # Compute rebalance trades
    print("\n[5/5] Computing rebalance trades...")
    portfolio_value = cash_balance * 0.95  # Use 95% of cash (keep 5% buffer)
    
    buys, sells = compute_rebalance_trades(
        target_weights=target_weights,
        current_positions=[],  # Empty - we just liquidated
        portfolio_value=portfolio_value
    )
    
    print(f"✓ Rebalance plan:")
    print(f"  BUY orders: {len(buys)}")
    print(f"  SELL orders: {len(sells)}")
    print(f"  Portfolio value: ${portfolio_value:,.0f}")
    
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
        for err in result['errors']:
            print(f"    - {err['action']} {err['ticker']}: {err['error']}")
    
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
    
    positions = get_positions()
    print(f"Open positions: {len(positions)}")
    
    if positions:
        print("\n  Holdings:")
        total_value = 0
        for pos in sorted(positions, key=lambda x: x['market_value'], reverse=True)[:15]:
            print(f"    {pos['ticker']:<6s} {pos['quantity']:>8.0f} shares @ ${pos['current_price']:>7.2f}  ${pos['market_value']:>10,.0f}")
            total_value += pos['market_value']
        
        if len(positions) > 15:
            remaining_value = sum(p['market_value'] for p in positions[15:])
            print(f"    ... and {len(positions) - 15} more positions  ${remaining_value:>10,.0f}")
        
        print(f"\n  Total portfolio value: ${total_value + sum(p['market_value'] for p in positions[15:]):,.0f}")
    
    print("\n" + "=" * 80)
    print("✓ MOMENTUM STRATEGY DEPLOYED SUCCESSFULLY")
    print("=" * 80)
    
except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

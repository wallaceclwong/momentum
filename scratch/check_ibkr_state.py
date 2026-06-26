import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.ibkr.gateway import connect, disconnect, get_ib
from backend.ibkr.account import get_positions, get_cash_balance

try:
    connect()
    ib = get_ib()
    
    print("\n--- IBKR Account Status ---")
    positions = get_positions()
    cash = get_cash_balance()
    
    print(f"\nNet Liquidation: ${cash:,.2f}")
    print(f"Total Positions: {len(positions)}")
    
    if positions:
        print("\nTop 10 Positions:")
        for p in sorted(positions, key=lambda x: abs(x['market_value']), reverse=True)[:10]:
            print(f"  {p['ticker']:<6s} | {p['quantity']:>8.1f} shares | ${p['market_value']:>10,.2f}")
    else:
        print("\nNo positions found.")

    # Check for any pending orders
    trades = ib.trades()
    if trades:
        print(f"\nPending/Active Orders: {len(trades)}")
        for t in trades:
            if not t.isDone():
                print(f"  {t.contract.symbol:<6s} | {t.order.action} {t.order.totalQuantity} | Status: {t.orderStatus.status}")

finally:
    disconnect()

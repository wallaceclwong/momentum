import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.ibkr.gateway import connect, disconnect, get_ib

try:
    connect()
    ib = get_ib()
    
    print("Fetching active orders...")
    trades = ib.trades()
    active_trades = [t for t in trades if not t.isDone()]
    
    if not active_trades:
        print("No active orders found.")
    else:
        print(f"Cancelling {len(active_trades)} active orders...")
        for t in active_trades:
            print(f"  Cancelling: {t.order.action} {t.order.totalQuantity} {t.contract.symbol} (Status: {t.orderStatus.status})")
            ib.cancelOrder(t.order)
        
        print("\nWaiting for cancellations to process...")
        ib.sleep(3)
        
        # Verify
        remaining = [t for t in ib.trades() if not t.isDone()]
        if not remaining:
            print("All orders cancelled successfully.")
        else:
            print(f"Warning: {len(remaining)} orders still active.")

finally:
    disconnect()

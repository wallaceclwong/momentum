from ib_insync import IB
import os
from dotenv import load_dotenv

load_dotenv()

IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", "4001"))
IBKR_CLIENT_ID = 101 # unique client id

ib = IB()

try:
    ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
    trades = ib.trades()
    
    print(f"--- Trade Status Summary ({len(trades)} trades found) ---")
    
    status_counts = {}
    for t in trades:
        status = t.orderStatus.status
        status_counts[status] = status_counts.get(status, 0) + 1
        
    for status, count in status_counts.items():
        print(f"{status}: {count}")
    
    print("\nRecent 10 Trades Details:")
    for t in trades[:10]:
        print(f"  {t.contract.symbol:6s} | {t.order.action:4s} | {t.order.totalQuantity:8.0f} | {t.orderStatus.status:8s} | Filled: {t.orderStatus.filled}")
        
    ib.disconnect()
except Exception as e:
    print(f"Error: {e}")

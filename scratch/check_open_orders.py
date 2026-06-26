"""Check all pending open orders on IBKR paper account."""
import sys, os, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from ib_insync import IB, util
util.logToConsole(logging.WARNING)
import time

HOST    = os.getenv("IBKR_HOST", "127.0.0.1")
PORT    = int(os.getenv("IBKR_PORT", "4001"))
ACCOUNT = os.getenv("IBKR_ACCOUNT_ID", "")

print(f"\n{'='*60}")
print(f"  IBKR Open Orders  —  account={ACCOUNT}")
print(f"{'='*60}\n")

ib = IB()
try:
    ib.connect(HOST, PORT, clientId=77)
except Exception as e:
    print(f"[ERROR] Cannot connect: {e}")
    sys.exit(1)

ib.reqOpenOrders()
time.sleep(2)
orders = ib.openOrders()
trades = ib.openTrades()

if not trades:
    print("  No open orders found.")
else:
    print(f"  {'#':<4} {'Action':<6} {'Ticker':<8} {'Qty':>6} {'Type':<6} {'Status':<18} {'OrderId'}")
    print(f"  {'-'*4} {'-'*6} {'-'*8} {'-'*6} {'-'*6} {'-'*18} {'-'*10}")
    for i, trade in enumerate(trades, 1):
        o = trade.order
        c = trade.contract
        s = trade.orderStatus
        print(f"  {i:<4} {o.action:<6} {c.symbol:<8} {int(o.totalQuantity):>6} {o.orderType:<6} {s.status:<18} #{o.orderId}")

print(f"\n  Total pending: {len(trades)}")
print(f"\n{'='*60}\n")
ib.disconnect()

import sys, os, logging, time
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv(".env")

from ib_insync import IB, util

# util.logToConsole(logging.INFO)

HOST    = os.getenv("IBKR_HOST", "127.0.0.1")
PORT    = int(os.getenv("IBKR_PORT", "4001"))

ib = IB()
try:
    ib.connect(HOST, PORT, clientId=99)
    print(f"Connected to {HOST}:{PORT}")
    
    # Request ALL open orders (from any client)
    ib.reqAllOpenOrders()
    ib.sleep(2)
    
    open_trades = ib.openTrades()
    print(f"\nOPEN ORDERS ({len(open_trades)}):")
    for t in open_trades:
        print(f"  {t.order.action} {t.order.totalQuantity} {t.contract.symbol} @ {t.order.lmtPrice} ({t.orderStatus.status})")
    
    # Request all trades for today
    print(f"\nALL TRADES (from today):")
    all_trades = ib.trades()
    for t in all_trades:
        print(f"  {t.contract.symbol}: {t.order.action} {t.order.totalQuantity} {t.orderStatus.status} @ fill {t.orderStatus.avgFillPrice}")

    # Check positions
    print(f"\nPOSITIONS:")
    positions = ib.positions()
    for p in positions:
        print(f"  {p.contract.symbol}: {p.position} shares")

    # Check cash
    for v in ib.accountValues():
        if v.tag == 'CashBalance' and v.currency == 'USD':
            print(f"\nCASH: ${v.value}")

    ib.disconnect()
except Exception as e:
    print(f"Error: {e}")

"""
Place GTC market orders for IUIS, IUIT, IUMS on IBKR paper account.
GTC = Good Till Cancelled — will fill at LSE open (~15:00 HKT today).

Shares based on $134,907 NAV / 3 equal weight / latest prices.
"""
import sys, os, logging, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from ib_insync import IB, Stock, Order, util, TagValue
util.logToConsole(logging.WARNING)

HOST    = os.getenv("IBKR_HOST", "127.0.0.1")
PORT    = int(os.getenv("IBKR_PORT", "4001"))
ACCOUNT = os.getenv("IBKR_ACCOUNT_ID", "")

# Use exact last known prices (no premium) - within 3% TWS constraint
# IUMS qty 869 split into 2 legs (TWS size limit = 500 per order)
ORDERS = [
    {"symbol": "IUIS", "exchange": "LSEETF", "qty": 257, "limit_px": 174.47},  # Industrials
    {"symbol": "IUIT", "exchange": "LSEETF", "qty": 286, "limit_px": 157.04},  # Info Tech
    {"symbol": "IUMS", "exchange": "LSEETF", "qty": 450, "limit_px": 51.74},   # Materials leg 1
    {"symbol": "IUMS", "exchange": "LSEETF", "qty": 419, "limit_px": 51.74},   # Materials leg 2 (450+419=869)
]

print(f"\n{'='*60}")
print(f"  Placing GTC BUY orders — account={ACCOUNT}")
print(f"{'='*60}\n")

ib = IB()
try:
    ib.connect(HOST, PORT, clientId=88)
except Exception as e:
    print(f"[ERROR] Cannot connect: {e}")
    sys.exit(1)

placed = []
for spec in ORDERS:
    contract = Stock(spec["symbol"], "SMART", "USD", primaryExchange=spec["exchange"])
    try:
        ib.qualifyContracts(contract)
    except Exception as e:
        print(f"  [WARN] Could not qualify {spec['symbol']}: {e} — using unqualified")

    order = Order()
    order.action        = "BUY"
    order.totalQuantity = spec["qty"]
    order.orderType     = "LMT"           # Limit order — bypasses Error 354 (no live data)
    order.lmtPrice      = spec["limit_px"]  # 1% above last price → fills immediately at open
    order.tif           = "GTC"           # Good Till Cancelled — survives overnight

    trade = ib.placeOrder(contract, order)
    time.sleep(1.5)
    print(f"  [OK] BUY {spec['qty']} {spec['symbol']} LMT ${spec['limit_px']:.2f} GTC  orderId={trade.order.orderId}  status={trade.orderStatus.status}")
    placed.append(trade)

print(f"\n  {len(placed)}/3 orders placed. They will fill at LSE open (~15:00 HKT).")

# Quick summary of all open orders
time.sleep(1)
ib.reqOpenOrders()
time.sleep(2)
all_trades = ib.openTrades()
print(f"\n  Current open orders on account: {len(all_trades)}")
for t in all_trades:
    print(f"    {t.order.action} {int(t.order.totalQuantity)} {t.contract.symbol}  tif={t.order.tif}  status={t.orderStatus.status}")

print(f"\n{'='*60}\n")
ib.disconnect()

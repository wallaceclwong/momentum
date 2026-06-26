import sys, os, logging, time
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv(".env")

from ib_insync import IB, util

HOST    = os.getenv("IBKR_HOST", "127.0.0.1")
PORT    = int(os.getenv("IBKR_PORT", "4001"))

ib = IB()
try:
    ib.connect(HOST, PORT, clientId=100)
    print(f"Connected to {HOST}:{PORT}")
    
    print("\nACCOUNT VALUES:")
    for v in ib.accountValues():
        if v.tag in ["NetLiquidation", "EquityWithLoanValue", "AvailableFunds", "CashBalance", "TotalCashBalance", "UnsettledCash"]:
             print(f"  {v.tag:25} {v.currency:5} {v.value}")

    print("\nPOSITIONS:")
    for p in ib.positions():
        print(f"  {p.contract.symbol:6} {p.position:>8} {p.contract.currency:5}")

    ib.disconnect()
except Exception as e:
    print(f"Error: {e}")

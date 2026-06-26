import sys, os, logging, time
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv(".env")

from ib_insync import IB, util

HOST    = os.getenv("IBKR_HOST", "127.0.0.1")
PORT    = int(os.getenv("IBKR_PORT", "4001"))

ib = IB()
try:
    ib.connect(HOST, PORT, clientId=101)
    
    print("\nFILLS (Last 24h):")
    fills = ib.fills()
    for f in fills:
        print(f"  {f.execution.time} {f.execution.side} {f.execution.shares} {f.contract.symbol} @ {f.execution.price}")

    ib.disconnect()
except Exception as e:
    print(f"Error: {e}")

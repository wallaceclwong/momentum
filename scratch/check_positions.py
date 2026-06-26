from ib_insync import IB
import os
from dotenv import load_dotenv

load_dotenv()

IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", "4001"))
IBKR_CLIENT_ID = 102

ib = IB()

try:
    ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
    positions = ib.positions()
    
    print(f"--- Current Holdings ({len(positions)} positions found) ---")
    if not positions:
        print("No holdings found.")
    else:
        print(f"{'Ticker':<10} | {'Quantity':<10} | {'Avg Cost':<10}")
        print("-" * 35)
        for p in positions:
            print(f"{p.contract.symbol:<10} | {p.position:<10.2f} | {p.avgCost:<10.2f}")
        
    ib.disconnect()
except Exception as e:
    print(f"Error: {e}")

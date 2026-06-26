from ib_insync import IB
import os
from dotenv import load_dotenv

load_dotenv()

IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", "4001"))
IBKR_CLIENT_ID = 99  # unique ID for this check

ib = IB()
try:
    ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
    summary = ib.accountSummary()
    print("--- Detailed Account Summary ---")
    for s in summary:
        if s.tag in ["Net Liquidation", "AvailableFunds", "BuyingPower", "EquityWithLoanValue"]:
            print(f"{s.tag}: {s.value} {s.currency}")
    ib.disconnect()
except Exception as e:
    print(f"Error: {e}")

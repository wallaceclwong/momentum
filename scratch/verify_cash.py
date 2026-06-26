from ib_insync import IB
import os
from dotenv import load_dotenv

load_dotenv()

IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", "4001"))
IBKR_CLIENT_ID = 210

ib = IB()

try:
    ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
    
    print("-" * 40)
    print(f"{'DEEP ACCOUNT VERIFICATION':^40}")
    print("-" * 40)
    
    # Check Summary
    summary = ib.accountSummary()
    metrics = {}
    for s in summary:
        if s.tag in ["GrossPositionValue", "NetLiquidation", "AvailableFunds"]:
            metrics[s.tag] = s.value
            
    print(f"Gross Position Value: ${metrics.get('GrossPositionValue', '0.00')}")
    print(f"Net Liquidation Val:  ${metrics.get('NetLiquidation', '0.00')}")
    print(f"Available Funds:      ${metrics.get('AvailableFunds', '0.00')}")
    
    # Check Positions
    positions = ib.positions()
    print("-" * 40)
    print(f"Positions Count: {len(positions)}")
    if positions:
        for p in positions:
            print(f"  STILL HELD: {p.contract.symbol} ({p.position} shares)")
    else:
        print("  SUCCESS: Account is 100% cash.")
    print("-" * 40)
    
    ib.disconnect()
except Exception as e:
    print(f"Error: {e}")

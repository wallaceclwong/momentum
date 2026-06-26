from ib_insync import IB
import os
from dotenv import load_dotenv

load_dotenv()

IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", "4001"))
IBKR_CLIENT_ID = 110

ib = IB()

try:
    ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
    
    # 1. Total Account Equity (Net Liquidation)
    summary = ib.accountSummary()
    net_liq = 0
    available = 0
    for s in summary:
        if s.tag == "NetLiquidation":
            net_liq = float(s.value)
        if s.tag == "AvailableFunds":
            available = float(s.value)
            
    # 2. Market Value of current 10 positions
    positions = ib.positions()
    total_mkt_val = sum(p.position * p.avgCost for p in positions)
    
    # 3. Configured Target
    target_capital = float(os.getenv("PAPER_CAPITAL", 0))
    
    print("-" * 40)
    print(f"{'ALLOCATION AUDIT':^40}")
    print("-" * 40)
    print(f"Target Portfolio Size (.env): ${target_capital:,.2f}")
    print(f"Actual Account Equity (Net):  ${net_liq:,.2f}")
    print(f"Current Value of Holdings:    ${total_mkt_val:,.2f}")
    print(f"Remaining Cash/Buying Power:  ${available:,.2f}")
    print("-" * 40)
    
    if target_capital > net_liq:
        print(f"WARNING: Target is GREATER than Equity. (Leverage: {target_capital/net_liq:.1f}x)")
    else:
        print("NOTE: Target is within your cash balance.")
    print("-" * 40)
    
    ib.disconnect()
except Exception as e:
    print(f"Error: {e}")

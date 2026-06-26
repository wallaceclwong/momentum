import sys, os, logging, time
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv(".env")

from ib_insync import IB, Stock, util

HOST    = os.getenv("IBKR_HOST", "127.0.0.1")
PORT    = int(os.getenv("IBKR_PORT", "4001"))

ib = IB()
try:
    ib.connect(HOST, PORT, clientId=102)
    print(f"Connected to {HOST}:{PORT}")
    
    symbols = ["IUIS", "IUIT", "IUMS"]
    contracts = [Stock(s, "SMART", "USD", primaryExchange="LSEETF") for s in symbols]
    ib.qualifyContracts(*contracts)
    
    print("\nMARKET DATA (IBKR delayed/frozen):")
    # Request market data
    for c in contracts:
        ticker = ib.reqMktData(c, "", False, False)
        ib.sleep(2) # Give it time to fill
        print(f"  {c.symbol:6}: Last={ticker.last} Close={ticker.close} Bid={ticker.bid} Ask={ticker.ask}")
        ib.cancelMktData(c)

    ib.disconnect()
except Exception as e:
    print(f"Error: {e}")

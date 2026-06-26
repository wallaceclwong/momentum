from ib_insync import IB, MarketOrder, TagValue, Stock
import os
from dotenv import load_dotenv
import time

load_dotenv()

IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", "4001"))
IBKR_CLIENT_ID = 200  # Unique ID for liquidation

ib = IB()

def liquidate():
    try:
        print(f"Connecting to {IBKR_HOST}:{IBKR_PORT}...")
        ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
        
        # Request Delayed Data (3) since user may not have real-time subscriptions
        ib.reqMarketDataType(3)
        print("Using Delayed Market Data (Type 3)")
        
        # Monitor errors
        def onError(reqId, errorCode, errorString, contract):
            print(f"  [IB ERROR] Code {errorCode}: {errorString}")
        ib.errorEvent += onError

        positions = ib.positions()
        if not positions:
            print("No positions found to liquidate.")
            return

        print(f"Found {len(positions)} positions. Liquidating with 500-share chunking for safety...")
        
        for p in positions:
            contract = p.contract
            ib.qualifyContracts(contract)
            
            total_to_sell = abs(p.position)
            ticker = contract.symbol
            
            print(f"  Processing {ticker} ({total_to_sell} shares)...")
            
            while total_to_sell > 0:
                chunk_size = min(total_to_sell, 500)
                order = MarketOrder("SELL", chunk_size)
                trade = ib.placeOrder(contract, order)
                
                print(f"    [SUBMITTED] SELL {chunk_size} {ticker}... waiting for fill")
                
                # Wait for fill
                start_time = time.time()
                while not trade.isDone() and time.time() - start_time < 30:
                    ib.sleep(1)
                
                if trade.orderStatus.remaining == 0:
                    total_to_sell -= chunk_size
                    print(f"    [FILLED] {chunk_size} {ticker} sold. ({total_to_sell} remaining)")
                else:
                    print(f"    [FAILED] {ticker} chunk failed: {trade.orderStatus.status}")
                    break
        
        # Verify positions BEFORE disconnecting
        print("\nVerifying final position list...")
        final_positions = ib.positions()
        if not final_positions:
            print("SUCCESS: Core positions list is empty.")
        else:
            for p in final_positions:
                print(f"  REMAINING: {p.contract.symbol} ({p.position} shares)")

        ib.disconnect()
    except Exception as e:
        print(f"Error during liquidation: {e}")
        if ib.isConnected():
            ib.disconnect()
    except Exception as e:
        print(f"Error during liquidation: {e}")
        if ib.isConnected():
            ib.disconnect()

if __name__ == "__main__":
    liquidate()

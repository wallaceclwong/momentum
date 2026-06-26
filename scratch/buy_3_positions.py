from ib_insync import IB, Order
from backend.ibkr.ucits_contracts import build_ibkr_contract

def main():
    ib = IB()
    try:
        print("Connecting to IBKR paper account on port 4001...")
        ib.connect('127.0.0.1', 4001, clientId=101)
        print("Connected.")
        
        trades_to_place = [
            ("IUES", 805),
            ("IUIT", 264),
            ("IUIS", 257)
        ]
        
        for ticker, shares in trades_to_place:
            print(f"Placing BUY order for {shares} shares of {ticker}...")
            contract = build_ibkr_contract(ticker)
            ib.qualifyContracts(contract)
            
            order = Order()
            order.action = "BUY"
            order.totalQuantity = shares
            order.orderType = "MKT"
            order.tif = "GTC"
            
            trade = ib.placeOrder(contract, order)
            ib.sleep(1) # Wait a bit for order status
            print(f"Order {trade.order.orderId} status: {trade.orderStatus.status}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if ib.isConnected():
            ib.disconnect()
            print("Disconnected.")

if __name__ == "__main__":
    main()

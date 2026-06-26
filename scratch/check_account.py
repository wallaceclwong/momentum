from backend.ibkr.gateway import connect, disconnect, get_ib
import pandas as pd

def check_account():
    connect()
    try:
        ib = get_ib()
        print("\n--- POSITIONS ---")
        positions = ib.positions()
        if not positions:
            print("No positions found.")
        for p in positions:
            print(f"Account: {p.account} | Symbol: {p.contract.symbol} | Amount: {p.position} | Avg Cost: {p.avgCost}")

        print("\n--- TRADES (ALL) ---")
        trades = ib.trades()
        for t in trades:
             print(f"Order {t.order.orderId}: {t.contract.symbol} {t.order.action} {t.order.totalQuantity} | Status: {t.orderStatus.status}")

    finally:
        disconnect()

if __name__ == "__main__":
    check_account()

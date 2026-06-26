from backend.ibkr.gateway import connect, disconnect, get_ib
import time

def check_orders():
    connect()
    try:
        ib = get_ib()
        print("\n--- OPEN TRADES ---")
        trades = ib.openTrades()
        if not trades:
            print("No open trades found.")
        for t in trades:
            print(f"ID: {t.order.orderId} | {t.contract.symbol} | {t.order.action} {t.order.totalQuantity} | Status: {t.orderStatus.status} | Filled: {t.orderStatus.filled}")

        print("\n--- RECENT FILLS ---")
        fills = ib.fills()
        if not fills:
            print("No recent fills found.")
        for f in fills:
            print(f"Time: {f.execution.time} | {f.contract.symbol} | {f.execution.side} {f.execution.shares} @ {f.execution.price}")

    finally:
        disconnect()

if __name__ == "__main__":
    check_orders()

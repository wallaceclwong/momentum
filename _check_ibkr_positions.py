import sqlite3
import json

conn = sqlite3.connect(r'C:\Users\ASUS\Momentum\sp500-momentum\data\momentum_screener.db')

# Get latest live rebalance
row = conn.execute(
    'SELECT id, as_of, trades_json, fills_json FROM sector_rebalances '
    'WHERE mode="live" AND status="executed" ORDER BY id DESC LIMIT 1'
).fetchone()

if not row:
    print("No live rebalances found.")
    exit(0)

id, as_of, trades_json, fills_json = row
trades = json.loads(trades_json) if trades_json else []
fills = json.loads(fills_json) if fills_json else []

print(f"=== Latest Live Rebalance #{id} (as of {as_of}) ===")
print(f"\nTRADES ({len(trades)}):")
for t in trades:
    print(f"  {t['action']:4} {t['ticker']:6} {t['delta_shares']:>8.2f} sh @ ${t['est_price']:>7.2f} → target {t['target_shares']:>8.2f} sh")

print(f"\nFILLS ({len(fills)}):")
if fills:
    for f in fills:
        try:
            print(f"  {f['ticker']:6} {f['action']:4} {f['shares']:>8.2f} sh @ ${f['fill_price']:>7.2f} ({f['status']})")
        except KeyError as e:
            print(f"  [Malformed fill record: {f}]")
else:
    print("  No fills recorded (simulated or pending)")

# Reconstruct current positions from trades
print(f"\n=== CURRENT POSITIONS (reconstructed) ===")
positions = {}
for t in trades:
    ticker = t['ticker']
    target = float(t.get('target_shares', 0))
    if target > 0:
        positions[ticker] = {
            'shares': target,
            'price': t['est_price'],
            'value': target * t['est_price']
        }

if positions:
    total_value = sum(p['value'] for p in positions.values())
    for ticker, pos in positions.items():
        weight = pos['value'] / total_value * 100
        print(f"  {ticker:6} {pos['shares']:>8.2f} sh @ ${pos['price']:>7.2f} = ${pos['value']:>10,.0f} ({weight:5.1f}%)")
    print(f"\n  TOTAL: ${total_value:,.0f}")
else:
    print("  No positions (all cash or no trades)")

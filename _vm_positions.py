#!/usr/bin/env python3
import sqlite3
import json

conn = sqlite3.connect('data/momentum_screener.db')
rows = conn.execute(
    'SELECT trades_json FROM sector_rebalances WHERE mode="paper" AND status="executed" ORDER BY id ASC'
).fetchall()

positions = {}
for (trades_json,) in rows:
    trades = json.loads(trades_json or '[]')
    for t in trades:
        tk = t['ticker']
        target = float(t.get('target_shares', 0))
        if target > 0:
            positions[tk] = {'shares': target, 'price': t['est_price'], 'value': target * t['est_price']}
        elif target <= 0:
            positions.pop(tk, None)

if positions:
    total = sum(p['value'] for p in positions.values())
    print('=== VM PAPER POSITIONS (simulate mode) ===')
    for tk, pos in positions.items():
        wt = pos['value'] / total * 100
        print(f'  {tk:6} {pos["shares"]:>8.2f} sh @ ${pos["price"]:>7.2f} = ${pos["value"]:>10,.0f} ({wt:5.1f}%)')
    print(f'  TOTAL: ${total:,.0f}')
else:
    print('No positions on VM')

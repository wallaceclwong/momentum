"""
Inspect and reset paper positions in the DB.

Since we've sold FOX on the real IBKR paper account and are now 100% cash,
this script inserts a synthetic 'executed' rebalance record with empty trades
so that get_last_paper_positions() returns {} (flat) on the next run.
"""
import sys, os, json, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "momentum_screener.db")
DB_PATH = os.path.normpath(DB_PATH)

conn = sqlite3.connect(DB_PATH)

# ── Show current paper position state ───────────────────────────────────────
print("=" * 60)
print("CURRENT PAPER REBALANCE HISTORY (last 10 rows)")
print("=" * 60)
rows = conn.execute(
    """SELECT id, as_of, mode, status, portfolio_nav, n_trades,
              total_buy_value, total_sell_value, trades_json
       FROM sector_rebalances
       ORDER BY id DESC LIMIT 10"""
).fetchall()

for r in rows:
    rid, as_of, mode, status, nav, n, buys, sells, tj = r
    trades = json.loads(tj or "[]")
    tickers = [(t["action"], t["ticker"], round(t.get("target_shares",0),1)) for t in trades]
    print(f"  [{rid}] {as_of[:10]}  mode={mode}  status={status}  nav=${nav:,.0f}  trades={n}")
    for action, tk, tgt in tickers:
        print(f"         {action} {tk} -> target_shares={tgt}")

# ── Replay current ghost positions ───────────────────────────────────────────
print("\n" + "=" * 60)
print("REPLAYED PAPER POSITIONS (what scheduler sees as 'current')")
print("=" * 60)
paper_rows = conn.execute(
    """SELECT trades_json FROM sector_rebalances
       WHERE mode='paper' AND status='executed'
       ORDER BY id ASC"""
).fetchall()

positions = {}
for (tj,) in paper_rows:
    for t in json.loads(tj or "[]"):
        tk = t["ticker"]
        target = float(t.get("target_shares", 0))
        price  = float(t.get("est_price", 0))
        if target <= 1e-6:
            positions.pop(tk, None)
        else:
            positions[tk] = {"shares": target, "price": price, "value": target * price}

if not positions:
    print("  (already flat - no action needed)")
else:
    for tk, pos in positions.items():
        print(f"  {tk}: {pos['shares']:.2f} shares @ ${pos['price']:.2f} = ${pos['value']:,.2f}")

    # ── Insert a flat/cash reset record ──────────────────────────────────────
    print("\n[ACTION] Inserting cash-reset record to clear ghost positions...")
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    # Build full-exit trades for every ghost position
    exit_trades = []
    for tk, pos in positions.items():
        exit_trades.append({
            "action": "SELL",
            "ticker": tk,
            "sector": "RESET",
            "target_shares": 0.0,
            "current_shares": pos["shares"],
            "delta_shares": -pos["shares"],
            "est_price": pos["price"],
            "est_value_usd": pos["value"],
            "reason": "Manual cash reset - all positions liquidated on IBKR",
        })

    conn.execute(
        """INSERT INTO sector_rebalances
           (as_of, signal_id, mode, portfolio_nav, n_trades,
            total_buy_value, total_sell_value, estimated_cost,
            trades_json, fills_json, status, error_message)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            now, None, "paper", 134907.06, len(exit_trades),
            0.0, sum(p["value"] for p in positions.values()), 0.0,
            json.dumps(exit_trades), None, "executed",
            "Manual reset: sold all paper positions to match IBKR flat cash state"
        )
    )
    conn.commit()
    print(f"  Done. Inserted {len(exit_trades)} exit trades -> paper positions now FLAT.")

conn.close()
print("\nDone.\n")

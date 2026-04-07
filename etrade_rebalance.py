"""
Momentum strategy rebalance against E*Trade Brokerage (MARGIN) account.
Runs screener → computes target weights → shows buy/sell trades.
Pass --execute to actually place orders in sandbox.
"""
import sys
import argparse
sys.path.insert(0, '.')

from backend.etrade.auth import get_oauth_session, BASE_URL, SANDBOX
from backend.etrade.account import get_portfolio, get_balance, parse_positions
from backend.etrade.trader import compute_rebalance_trades, execute_rebalance
from backend.data.sp500 import get_ticker_to_sector, get_tickers_by_sector
from backend.engine.portfolio import get_sector_etf_weights
from backend.engine.momentum import calculate_momentum_for_tickers
from backend.data.prices import fetch_price_history

ACCOUNT_ID_KEY = "dBZOKt9xDrtRSAOl4MSiiA"  # Brokerage MARGIN

parser = argparse.ArgumentParser()
parser.add_argument("--execute", action="store_true", help="Place orders (default: dry run)")
parser.add_argument("--capital", type=float, default=100000.0, help="Virtual portfolio size in USD (default: 100000)")
args = parser.parse_args()

print(f"\n{'='*60}")
print(f"Momentum Rebalance — E*Trade {'SANDBOX' if SANDBOX else 'LIVE'}")
print(f"Account: Brokerage (MARGIN)  |  {'DRY RUN' if not args.execute else '⚠ LIVE EXECUTION'}")
print(f"{'='*60}")

# ── 1. Run momentum screener ──────────────────────────────────
print("\n📡 Running momentum screener...")
ticker_to_sector = get_ticker_to_sector()
sector_to_tickers = get_tickers_by_sector()
sector_weights = get_sector_etf_weights()
all_tickers = list(ticker_to_sector.keys())

price_data = fetch_price_history(all_tickers, period="6mo", interval="1d")
momentum_data = calculate_momentum_for_tickers(price_data)

# Top 3 per sector
target_holdings = {}
screener_output = {}
for sector, tickers in sector_to_tickers.items():
    scores = [
        (t, momentum_data[t]["composite_score"])
        for t in tickers
        if t in momentum_data and momentum_data[t].get("composite_score") is not None
    ]
    scores.sort(key=lambda x: x[1], reverse=True)
    top3 = [t for t, _ in scores[:3]]
    sw = sector_weights.get(sector, 0.0)
    if top3 and sw > 0:
        w = sw / len(top3)
        for t in top3:
            target_holdings[t] = w
    screener_output[sector] = [(t, s) for t, s in scores[:3]]

print(f"✅ Screener complete — {len(target_holdings)} target positions across {len(sector_to_tickers)} sectors")

# ── 2. Show target portfolio ──────────────────────────────────
print(f"\n🎯 Target Portfolio:")
print(f"  {'Ticker':8s} {'Sector':25s} {'Weight':>8s}")
print(f"  {'-'*44}")
for sector, picks in screener_output.items():
    sw = sector_weights.get(sector, 0.0)
    if picks and sw > 0:
        w = sw / len(picks)
        for t, score in picks:
            print(f"  {t:8s} {sector:25s} {w*100:>7.2f}%")

total_w = sum(target_holdings.values())
print(f"\n  Total weight: {total_w*100:.1f}%")

# ── 3. Get current E*Trade state ──────────────────────────────
print(f"\n📊 Fetching E*Trade account state...")
session = get_oauth_session()
if not session:
    print("ERROR: Not authenticated. Run etrade_step1_get_url.py first.")
    sys.exit(1)

try:
    bal_data  = get_balance(ACCOUNT_ID_KEY)
    port_data = get_portfolio(ACCOUNT_ID_KEY)
except Exception as e:
    print(f"ERROR fetching account data: {e}")
    sys.exit(1)

positions = parse_positions(port_data)
computed  = bal_data.get("BalanceResponse", {}).get("Computed", {})
rtv       = computed.get("RealTimeValues", {})
total_val = float(rtv.get("totalAccountValue", 0) or 0)
cash      = float(computed.get("cashAvailableForInvestment", 0) or 0)

print(f"  Total Account Value: ${total_val:>12,.2f}")
print(f"  Cash Available:      ${cash:>12,.2f}")
print(f"  Current Positions:   {len(positions)}")

if positions:
    print(f"\n  Current Holdings:")
    for p in positions:
        print(f"    {p['ticker']:8s}  qty={p['quantity']:>8.2f}  ${p['market_value']:>10,.2f}")

# ── 4. Compute trades needed ──────────────────────────────────
portfolio_value = total_val if total_val > 0 else (cash if cash > 0 else args.capital)

if total_val <= 0:
    print(f"\n  ℹ  Sandbox API reports $0 (sandbox limitation) — using --capital ${args.capital:,.0f} for simulation")

buys, sells = compute_rebalance_trades(target_holdings, positions, portfolio_value)

print(f"\n📋 Rebalance Plan (portfolio value: ${portfolio_value:,.2f}):")
print(f"{'='*60}")

if sells:
    print(f"\n🔴 SELL ({len(sells)}):")
    print(f"  {'Ticker':8s} {'Shares':>10s} {'Est. Value':>12s}  Reason")
    print(f"  {'-'*55}")
    for s in sells:
        print(f"  {s['ticker']:8s} {s['shares']:>10.4f} ${s['estimated_value']:>11,.2f}  {s['reason']}")
else:
    print(f"\n🔴 SELL: nothing to sell")

if buys:
    print(f"\n🟢 BUY ({len(buys)}):")
    print(f"  {'Ticker':8s} {'Shares':>10s} {'Est. Value':>12s}  Reason")
    print(f"  {'-'*55}")
    for b in buys:
        print(f"  {b['ticker']:8s} {b['shares']:>10.4f} ${b['estimated_value']:>11,.2f}  {b['reason']}")
else:
    print(f"\n🟢 BUY: already fully invested")

print(f"\n{'='*60}")
print(f"Total: {len(sells)} sells  |  {len(buys)} buys")

if args.execute:
    print(f"\n⚡ Placing orders in E*Trade {'SANDBOX' if SANDBOX else 'LIVE'}...")
    exec_results = execute_rebalance(
        ACCOUNT_ID_KEY,
        buys=buys,
        sells=sells,
        dry_run=False,
        delay_seconds=0.5
    )

    print(f"\n{'='*60}")
    print(f"📤 SELL Orders Placed ({len(exec_results['sells'])}):")
    for r in exec_results["sells"]:
        status_icon = "✅" if r["status"] == "placed" else "⚠"
        print(f"  {status_icon} SELL {r['ticker']:8s} x{r['quantity']:>6}  order_id={r.get('order_id','N/A')}")

    print(f"\n📥 BUY Orders Placed ({len(exec_results['buys'])}):")
    for r in exec_results["buys"]:
        status_icon = "✅" if r["status"] == "placed" else "⚠"
        print(f"  {status_icon} BUY  {r['ticker']:8s} x{r['quantity']:>6}  order_id={r.get('order_id','N/A')}")

    if exec_results["errors"]:
        print(f"\n❌ Errors ({len(exec_results['errors'])}):")
        for e in exec_results["errors"]:
            print(f"  {e['action']} {e['ticker']}: {e['error']}")

    total_placed = len(exec_results["sells"]) + len(exec_results["buys"])
    print(f"\n{'='*60}")
    print(f"✅ Done — {total_placed} orders placed, {len(exec_results['errors'])} errors")
else:
    print("\n✅ Dry run complete. Run with --execute to place orders in sandbox.")

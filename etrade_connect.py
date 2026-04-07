"""
E*Trade connection test + account info.
Run this to authenticate and verify API access.
"""
import sys
import json
sys.path.insert(0, '.')

from backend.etrade.auth import interactive_login, get_oauth_session, SANDBOX
from backend.etrade.account import get_accounts, get_portfolio, get_balance, parse_positions

print(f"\n{'='*60}")
print(f"E*Trade API Test — {'SANDBOX' if SANDBOX else 'LIVE'} mode")
print(f"{'='*60}")

# Try cached tokens first
session = get_oauth_session()
if session:
    print("Found cached tokens — trying to use them...")
    try:
        accounts = get_accounts()
        print("✅ Cached tokens still valid\n")
    except Exception:
        print("Cached tokens expired — re-authenticating...")
        session = interactive_login()
else:
    session = interactive_login()

# List accounts
print("\n📋 Your Accounts:")
print("-" * 40)
accounts = get_accounts()
for acct in accounts:
    print(f"  Account: {acct.get('accountDesc', 'N/A')}")
    print(f"  Type:    {acct.get('accountType', 'N/A')}")
    print(f"  Status:  {acct.get('accountStatus', 'N/A')}")
    print(f"  ID Key:  {acct.get('accountIdKey', 'N/A')}")
    print()

if not accounts:
    print("  No accounts found.")
    sys.exit(0)

# Show balance + positions for first account
acct = accounts[0]
acct_key = acct.get("accountIdKey")
print(f"\n💰 Balance for {acct.get('accountDesc', acct_key)}:")
print("-" * 40)
try:
    bal = get_balance(acct_key)
    computed = bal.get("BalanceResponse", {}).get("Computed", {})
    rtv = computed.get("RealTimeValues", {})
    print(f"  Total Account Value: ${rtv.get('totalAccountValue', 'N/A'):,.2f}")
    print(f"  Cash Available:      ${computed.get('cashAvailableForInvestment', 'N/A'):,.2f}")
except Exception as e:
    print(f"  Could not fetch balance: {e}")

print(f"\n📊 Current Positions:")
print("-" * 40)
try:
    port = get_portfolio(acct_key)
    positions = parse_positions(port)
    if positions:
        for p in positions:
            print(f"  {p['ticker']:6s}  qty={p['quantity']:8.2f}  price=${p['current_price']:8.2f}  value=${p['market_value']:10,.2f}")
    else:
        print("  No positions (empty portfolio)")
except Exception as e:
    print(f"  Could not fetch portfolio: {e}")

print("\n✅ E*Trade connection test complete.")

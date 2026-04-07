"""Step 2: Exchange verifier code for access token, then show accounts."""
import sys, json
sys.path.insert(0, '.')
from pathlib import Path
from backend.etrade.auth import get_access_token, get_oauth_session, SANDBOX
from backend.etrade.account import get_accounts, get_portfolio, get_balance, parse_positions

if len(sys.argv) < 2:
    print("Usage: python etrade_step2_verify.py <VERIFIER_CODE>")
    sys.exit(1)

verifier = sys.argv[1].strip()
req_path = Path("data/etrade_request_token.json")
if not req_path.exists():
    print("ERROR: Run etrade_step1_get_url.py first.")
    sys.exit(1)

req_tokens = json.loads(req_path.read_text())
tokens = get_access_token(req_tokens["oauth_token"], req_tokens["oauth_token_secret"], verifier)
req_path.unlink()  # Clean up

print(f"\n✅ Authentication successful!\n")

# Show accounts
accounts = get_accounts()
print(f"📋 Your Accounts:")
print("-" * 50)
for acct in accounts:
    print(f"  {acct.get('accountDesc','N/A'):30s}  [{acct.get('accountType','N/A')}]  Key: {acct.get('accountIdKey','N/A')}")

if not accounts:
    print("  No accounts found.")
    sys.exit(0)

# Balance for first account
acct_key = accounts[0].get("accountIdKey")
print(f"\n💰 Balance:")
print("-" * 50)
try:
    bal = get_balance(acct_key)
    computed = bal.get("BalanceResponse", {}).get("Computed", {})
    rtv = computed.get("RealTimeValues", {})
    total = rtv.get("totalAccountValue", 0)
    cash  = computed.get("cashAvailableForInvestment", 0)
    print(f"  Total Account Value:    ${float(total):>12,.2f}")
    print(f"  Cash for Investment:    ${float(cash):>12,.2f}")
except Exception as e:
    print(f"  Balance error: {e}")

# Positions
print(f"\n📊 Current Positions:")
print("-" * 50)
try:
    port = get_portfolio(acct_key)
    positions = parse_positions(port)
    if positions:
        print(f"  {'Ticker':8s} {'Qty':>10s} {'Price':>10s} {'Value':>12s}")
        print(f"  {'-'*42}")
        for p in positions:
            print(f"  {p['ticker']:8s} {p['quantity']:>10.2f} ${p['current_price']:>9.2f} ${p['market_value']:>11,.2f}")
    else:
        print("  No positions (empty portfolio — ready for paper trading!)")
except Exception as e:
    print(f"  Portfolio error: {e}")

print(f"\n✅ E*Trade connection verified. Ready to simulate!")

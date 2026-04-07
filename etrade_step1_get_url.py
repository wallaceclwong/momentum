"""Step 1: Get the E*Trade authorization URL."""
import sys, json
sys.path.insert(0, '.')
from pathlib import Path
from backend.etrade.auth import get_request_token, get_authorize_url, SANDBOX

tokens = get_request_token()
url = get_authorize_url(tokens["oauth_token"])

# Save request tokens for step 2
Path("data/etrade_request_token.json").write_text(json.dumps(tokens))

print(f"\n{'='*60}")
print(f"E*Trade {'SANDBOX' if SANDBOX else 'LIVE'} — Step 1")
print(f"{'='*60}")
print(f"\n1. Open this URL in your browser:\n")
print(f"   {url}\n")
print(f"2. Log in with your E*Trade credentials")
print(f"3. Copy the verifier code shown")
print(f"4. Run:  python etrade_step2_verify.py <VERIFIER_CODE>\n")

"""
E*Trade OAuth 1.0a authentication.
Handles request token, authorization, and access token flow.
"""
import os
import json
import logging
from pathlib import Path
from requests_oauthlib import OAuth1Session
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Sandbox vs Live URLs
SANDBOX = os.getenv("ETRADE_SANDBOX", "true").lower() == "true"

BASE_URL      = "https://apisb.etrade.com" if SANDBOX else "https://api.etrade.com"
AUTHORIZE_URL = "https://us.etrade.com/e/t/etws/authorize"

REQUEST_TOKEN_URL = f"{BASE_URL}/oauth/request_token"
ACCESS_TOKEN_URL  = f"{BASE_URL}/oauth/access_token"
RENEW_TOKEN_URL   = f"{BASE_URL}/oauth/renew_access_token"

CONSUMER_KEY    = os.getenv("ETRADE_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("ETRADE_CONSUMER_SECRET")

# Token cache file
TOKEN_CACHE = Path(__file__).resolve().parents[2] / "data" / "etrade_tokens.json"


def get_request_token() -> dict:
    """Step 1: Get a request token from E*Trade."""
    session = OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        callback_uri="oob"
    )
    resp = session.fetch_request_token(REQUEST_TOKEN_URL)
    logger.info("Got request token")
    return resp


def get_authorize_url(oauth_token: str) -> str:
    """Step 2: Build the URL the user must visit to authorize."""
    return f"{AUTHORIZE_URL}?key={CONSUMER_KEY}&token={oauth_token}"


def get_access_token(oauth_token: str, oauth_token_secret: str, verifier: str) -> dict:
    """Step 3: Exchange verifier code for access token."""
    session = OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=oauth_token,
        resource_owner_secret=oauth_token_secret,
        verifier=verifier
    )
    tokens = session.fetch_access_token(ACCESS_TOKEN_URL)
    logger.info("Got access token")
    _save_tokens(tokens)
    return tokens


def _save_tokens(tokens: dict):
    """Save tokens to local cache."""
    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_CACHE, "w") as f:
        json.dump(tokens, f)


def _load_tokens() -> dict | None:
    """Load cached tokens."""
    if TOKEN_CACHE.exists():
        with open(TOKEN_CACHE) as f:
            return json.load(f)
    return None


def get_oauth_session() -> OAuth1Session | None:
    """
    Return an authenticated OAuth1Session using cached tokens.
    Returns None if no valid tokens cached — user must re-authorize.
    """
    tokens = _load_tokens()
    if not tokens:
        return None
    return OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=tokens.get("oauth_token"),
        resource_owner_secret=tokens.get("oauth_token_secret")
    )


def renew_token() -> bool:
    """
    Renew access token (valid within 24h of last auth).
    Returns True if renewal succeeded.
    """
    tokens = _load_tokens()
    if not tokens:
        return False
    try:
        session = OAuth1Session(
            CONSUMER_KEY,
            client_secret=CONSUMER_SECRET,
            resource_owner_key=tokens.get("oauth_token"),
            resource_owner_secret=tokens.get("oauth_token_secret")
        )
        resp = session.get(RENEW_TOKEN_URL)
        if resp.status_code == 200:
            logger.info("Access token renewed successfully")
            return True
        logger.warning(f"Token renewal failed: {resp.status_code} {resp.text}")
        return False
    except Exception as e:
        logger.error(f"Token renewal error: {e}")
        return False


def interactive_login() -> OAuth1Session:
    """
    Full interactive OAuth flow via terminal.
    Prints the URL, waits for verifier code from user.
    """
    print(f"\n{'='*60}")
    print(f"E*Trade {'SANDBOX' if SANDBOX else 'LIVE'} Authentication")
    print(f"{'='*60}")

    # Step 1: Request token
    req_tokens = get_request_token()
    auth_url = get_authorize_url(req_tokens["oauth_token"])

    print(f"\n1. Open this URL in your browser:")
    print(f"\n   {auth_url}\n")
    print("2. Log in with your E*Trade credentials")
    print("3. Copy the 5-digit verifier code shown")
    verifier = input("\nEnter verifier code: ").strip()

    # Step 3: Exchange for access token
    tokens = get_access_token(
        req_tokens["oauth_token"],
        req_tokens["oauth_token_secret"],
        verifier
    )
    print("\n✅ Authentication successful! Tokens saved.\n")

    return get_oauth_session()

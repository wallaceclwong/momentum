"""
E*Trade account & portfolio queries.
"""
import logging
from typing import Dict, List, Optional
from .auth import get_oauth_session, BASE_URL

logger = logging.getLogger(__name__)


def get_accounts() -> List[Dict]:
    """List all accounts."""
    session = get_oauth_session()
    if not session:
        raise RuntimeError("Not authenticated. Run interactive_login() first.")

    resp = session.get(f"{BASE_URL}/v1/accounts/list.json")
    resp.raise_for_status()
    data = resp.json()
    accounts = data.get("AccountListResponse", {}).get("Accounts", {}).get("Account", [])
    if isinstance(accounts, dict):
        accounts = [accounts]
    return accounts


def get_portfolio(account_id_key: str) -> Dict:
    """Get current portfolio positions for an account."""
    session = get_oauth_session()
    if not session:
        raise RuntimeError("Not authenticated.")

    resp = session.get(
        f"{BASE_URL}/v1/accounts/{account_id_key}/portfolio.json"
    )
    resp.raise_for_status()
    return resp.json()


def get_balance(account_id_key: str) -> Dict:
    """Get account balance."""
    session = get_oauth_session()
    if not session:
        raise RuntimeError("Not authenticated.")

    resp = session.get(
        f"{BASE_URL}/v1/accounts/{account_id_key}/balance.json",
        params={"instType": "BROKERAGE", "realTimeNAV": "true"}
    )
    resp.raise_for_status()
    return resp.json()


def parse_positions(portfolio_data: Dict) -> List[Dict]:
    """Extract clean position list from portfolio response."""
    positions = []
    try:
        accounts = portfolio_data.get("PortfolioResponse", {}).get("AccountPortfolio", [])
        if isinstance(accounts, dict):
            accounts = [accounts]
        for acct in accounts:
            for pos in acct.get("Position", []):
                product = pos.get("Product", {})
                quick = pos.get("Quick", {})
                positions.append({
                    "ticker":          product.get("symbol"),
                    "quantity":        pos.get("quantity", 0),
                    "current_price":   quick.get("lastTrade", 0),
                    "market_value":    pos.get("marketValue", 0),
                    "total_gain_pct":  pos.get("totalGainPct", 0),
                })
    except Exception as e:
        logger.error(f"Error parsing positions: {e}")
    return positions

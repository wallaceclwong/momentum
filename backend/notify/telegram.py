"""
Telegram notification helper.
Sends messages to a configured chat via Bot API.
"""
import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")


def send(message: str, parse_mode: str = "Markdown") -> bool:
    """
    Send a Telegram message. Returns True on success.
    Silently logs errors — never raises so scheduler keeps running.
    """
    if not BOT_TOKEN or not CHAT_ID:
        logger.warning("[TELEGRAM] Not configured — set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": message, "parse_mode": parse_mode},
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info("[TELEGRAM] Message sent")
            return True
        logger.warning(f"[TELEGRAM] Failed: {resp.status_code} {resp.text}")
        return False
    except Exception as e:
        logger.error(f"[TELEGRAM] Error: {e}")
        return False


def notify_rebalance_complete(placed: int, errors: int, portfolio_value: float,
                               buys: list, sells: list, dry_run: bool = False):
    mode = "DRY RUN" if dry_run else "LIVE"
    status = "OK" if errors == 0 else f"WARNING — {errors} errors"
    top_buys = ", ".join([b["ticker"] for b in buys[:5]])
    top_sells = ", ".join([s["ticker"] for s in sells[:5]])

    msg = (
        f"*Momentum Rebalance Complete* [{mode}]\n\n"
        f"Status: {status}\n"
        f"Orders: {placed} placed\n"
        f"Portfolio: ${portfolio_value:,.0f}\n\n"
        f"*Buys ({len(buys)}):* {top_buys}{'...' if len(buys) > 5 else ''}\n"
        f"*Sells ({len(sells)}):* {top_sells if sells else 'none'}{'...' if len(sells) > 5 else ''}\n\n"
        f"_Next rebalance: last Friday of next month_"
    )
    send(msg)


def notify_token_expired():
    msg = (
        "*Action Required — E\\*Trade Token Expired*\n\n"
        "The scheduler cannot rebalance until you re-authenticate.\n\n"
        "*Steps:*\n"
        "1\\. Run on your PC:\n"
        "`python etrade_step1_get_url.py`\n"
        "2\\. Open the URL, log in, copy the code\n"
        "3\\. Run:\n"
        "`python etrade_step2_verify.py <CODE>`\n"
        "4\\. Copy token to VM:\n"
        "`scp data/etrade_tokens.json root@100.109.76.69:/root/momentum/data/`"
    )
    send(msg, parse_mode="MarkdownV2")


def notify_error(context: str, error: str):
    msg = (
        f"*Momentum Scheduler Error*\n\n"
        f"Context: {context}\n"
        f"Error: `{error}`"
    )
    send(msg)


def notify_startup(mode: str):
    msg = (
        f"*Momentum Scheduler Started*\n\n"
        f"Mode: {mode}\n"
        f"Token renewal: daily 08:55 AM ET\n"
        f"Rebalance: last Friday of month at 15:50 ET"
    )
    send(msg)

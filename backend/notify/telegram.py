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


def notify_sector_rebalance(plan, mode: str, status: str = "executed"):
    """
    Send Telegram alert for a sector rotation rebalance.

    plan: RebalancePlan dataclass from backend.engine.sector_executor
    mode: "simulate" | "ibkr" | "dry_run"
    status: "executed" | "planned" | "failed"
    """
    sig = plan.signal
    emoji_status = {"executed": "✅", "planned": "👀", "failed": "🚨"}.get(status, "⚪")
    mode_label   = {"simulate": "SIMULATE (DB only)",
                    "ibkr": "IBKR LIVE",
                    "dry_run": "DRY RUN"}.get(mode, mode.upper())

    # ── Signal header ─────────────────────────────────────────────
    trend_arrow = "↑" if sig.trend_value > 0 else "↓"
    deploy_str  = "DEPLOY" if sig.deploy else "CASH (trend down)"
    top_str     = ", ".join(sig.top_sectors) if sig.top_sectors else "—"

    # ── Trade summary ─────────────────────────────────────────────
    n = len(plan.trades)
    if n == 0:
        trade_block = "_No trades — portfolio at target_"
    else:
        lines = []
        for t in plan.trades[:6]:   # max 6 to keep message compact
            sign = "+" if t.action == "BUY" else "−"
            lines.append(
                f"`{t.action:<4} {t.ticker:<5} {sign}{abs(t.delta_shares):>7.1f}sh "
                f"${t.est_price:>7.2f}  ${t.est_value_usd:>7,.0f}`"
            )
        if n > 6:
            lines.append(f"_...+{n - 6} more_")
        trade_block = "\n".join(lines)

    msg = (
        f"{emoji_status} *Sector Rotation Rebalance* — _{mode_label}_\n\n"
        f"*Signal* (as of {sig.as_of.date()}):\n"
        f"  SPY 12m: {trend_arrow} {sig.trend_value:+.2%} → *{deploy_str}*\n"
        f"  Top-3: {top_str}\n\n"
        f"*Trades* ({n}):\n{trade_block}\n\n"
        f"*NAV:* ${plan.portfolio_nav:,.0f}  |  *Cost:* ${plan.estimated_cost:,.2f}  "
        f"({plan.estimated_cost / max(plan.portfolio_nav, 1):.2%})\n"
        f"Status: *{status}*"
    )
    send(msg)


def notify_sector_signal(signal):
    """Send Telegram alert for screener signal only (no rebalance)."""
    trend_arrow = "↑" if signal.trend_value > 0 else "↓"
    deploy_str  = "DEPLOY" if signal.deploy else "CASH (trend down)"
    top_str     = ", ".join(signal.top_sectors) if signal.top_sectors else "—"
    msg = (
        f"📊 *Sector Rotation Signal*\n\n"
        f"As of {signal.as_of.date()}  (month-end {signal.signal_date.date()})\n"
        f"SPY 12m: {trend_arrow} {signal.trend_value:+.2%}  → *{deploy_str}*\n"
        f"Top-3: {top_str}"
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

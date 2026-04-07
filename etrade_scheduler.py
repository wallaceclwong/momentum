"""
Monthly momentum rebalance scheduler for E*Trade.

Schedule:
  - Every day 08:55 AM  → renew OAuth token (keeps session alive)
  - Every Friday        → check if last Friday of month; if so, rebalance
  - Every run           → log results to data/scheduler.log

Usage:
  python etrade_scheduler.py            # start scheduler (runs forever)
  python etrade_scheduler.py --now      # force rebalance immediately
  python etrade_scheduler.py --dry-run  # show what would happen, no orders

Notes:
  - E*Trade tokens expire every 24h; daily renewal keeps them valid
  - If token is expired and renewal fails, an alert is logged — re-run
    etrade_step1_get_url.py + etrade_step2_verify.py to re-authenticate
"""
import sys
import logging
import argparse
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, '.')

# ── Logging ───────────────────────────────────────────────────
LOG_PATH = Path("data/scheduler.log")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ── Imports ───────────────────────────────────────────────────
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.etrade.auth import renew_token, get_oauth_session, SANDBOX
from backend.notify.telegram import (
    notify_rebalance_complete, notify_token_expired,
    notify_error, notify_startup, send
)
from backend.etrade.account import get_portfolio, get_balance, parse_positions
from backend.etrade.trader import compute_rebalance_trades, execute_rebalance
from backend.engine.paper_trading import record_rebalance
from backend.data.sp500 import get_ticker_to_sector, get_tickers_by_sector
from backend.engine.portfolio import get_sector_etf_weights
from backend.engine.momentum import calculate_momentum_for_tickers
from backend.data.prices import fetch_price_history

ACCOUNT_ID_KEY = "dBZOKt9xDrtRSAOl4MSiiA"  # Brokerage MARGIN
VIRTUAL_CAPITAL = 100_000.0                  # Portfolio size for simulation


# ── Helpers ───────────────────────────────────────────────────
def is_last_friday_of_month(d: date = None) -> bool:
    """Return True if d (default: today) is the last Friday of its month."""
    d = d or date.today()
    if d.weekday() != 4:  # 4 = Friday
        return False
    return (d + timedelta(days=7)).month != d.month


def get_target_weights() -> dict:
    """Run screener and return target weight dict {ticker: weight}."""
    ticker_to_sector = get_ticker_to_sector()
    sector_to_tickers = get_tickers_by_sector()
    sector_weights = get_sector_etf_weights()
    all_tickers = list(ticker_to_sector.keys())

    price_data = fetch_price_history(all_tickers, period="6mo", interval="1d")
    momentum_data = calculate_momentum_for_tickers(price_data)

    target = {}
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
                target[t] = w
    return target


# ── Jobs ──────────────────────────────────────────────────────
def job_renew_token():
    """Daily job: renew E*Trade OAuth token."""
    logger.info("[TOKEN] Daily token renewal...")
    ok = renew_token()
    if ok:
        logger.info("[TOKEN] Renewed successfully")
    else:
        logger.warning("[TOKEN] Renewal failed - manual re-authentication may be needed")
        logger.warning("  Run: python etrade_step1_get_url.py  then  python etrade_step2_verify.py <CODE>")
        notify_token_expired()


def job_monthly_rebalance(dry_run: bool = False, force: bool = False):
    """Friday job: rebalance if it's the last Friday of the month."""
    today = date.today()

    if not force and not is_last_friday_of_month(today):
        logger.info(f"[SKIP] {today} is not last Friday of month")
        return

    logger.info(f"{'='*60}")
    logger.info(f"[REBALANCE DAY] {today}  |  {'DRY RUN' if dry_run else 'LIVE'}")
    logger.info(f"{'='*60}")

    # Ensure token is valid
    if not renew_token():
        logger.error("[ERROR] Cannot rebalance - token expired. Re-authenticate first.")
        notify_token_expired()
        return

    # Get target portfolio
    logger.info("[SCREENER] Running momentum screener...")
    try:
        target_weights = get_target_weights()
        logger.info(f"[SCREENER] {len(target_weights)} target positions")
    except Exception as e:
        logger.error(f"[ERROR] Screener failed: {e}")
        notify_error("Screener", str(e))
        return

    # Get current positions
    try:
        port_data = get_portfolio(ACCOUNT_ID_KEY)
        bal_data  = get_balance(ACCOUNT_ID_KEY)
        positions = parse_positions(port_data)
        computed  = bal_data.get("BalanceResponse", {}).get("Computed", {})
        rtv       = computed.get("RealTimeValues", {})
        total_val = float(rtv.get("totalAccountValue", 0) or 0)
        portfolio_value = total_val if total_val > 0 else VIRTUAL_CAPITAL
    except Exception as e:
        logger.error(f"[ERROR] Failed to fetch account state: {e}")
        notify_error("Account fetch", str(e))
        return

    # Compute trades
    buys, sells = compute_rebalance_trades(target_weights, positions, portfolio_value)
    logger.info(f"[PLAN] {len(sells)} sells, {len(buys)} buys  (portfolio: ${portfolio_value:,.0f})")

    # Execute
    results = execute_rebalance(
        ACCOUNT_ID_KEY,
        buys=buys,
        sells=sells,
        dry_run=dry_run,
        delay_seconds=0.5
    )

    placed = len(results["sells"]) + len(results["buys"])
    errors = len(results["errors"])
    status = 'OK' if errors == 0 else 'WARN'
    logger.info(f"[{status}] Rebalance complete: {placed} orders {'previewed' if dry_run else 'placed'}, {errors} errors")

    for err in results["errors"]:
        logger.error(f"  {err['action']} {err['ticker']}: {err['error']}")

    notify_rebalance_complete(placed, errors, portfolio_value, buys, sells, dry_run)

    # Record trades to local portfolio tracker (paper or live)
    try:
        from backend.data.sp500 import get_ticker_to_sector
        ticker_to_sector = get_ticker_to_sector()
        rid = record_rebalance(target_weights, ticker_to_sector, capital=VIRTUAL_CAPITAL)
        logger.info(f"[TRACKER] Portfolio tracker updated: {rid}")
    except Exception as e:
        logger.error(f"[TRACKER] Failed to update portfolio tracker: {e}")


# ── Main ──────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--now",     action="store_true", help="Force rebalance immediately")
    parser.add_argument("--dry-run", action="store_true", help="Preview only — no orders placed")
    args = parser.parse_args()

    env_label = "SANDBOX" if SANDBOX else "LIVE"

    if args.now:
        logger.info(f"[FORCED] Rebalance triggered  [{env_label}]")
        job_monthly_rebalance(dry_run=args.dry_run, force=True)
        sys.exit(0)

    # Start scheduler
    scheduler = BlockingScheduler(timezone="America/New_York")

    # Daily token renewal at 08:55 AM ET (before market open)
    scheduler.add_job(
        job_renew_token,
        CronTrigger(hour=8, minute=55),
        id="renew_token",
        name="Daily Token Renewal"
    )

    # Every Friday at 15:50 ET (10 min before close) — rebalance if last Friday
    scheduler.add_job(
        lambda: job_monthly_rebalance(dry_run=args.dry_run),
        CronTrigger(day_of_week="fri", hour=15, minute=50),
        id="monthly_rebalance",
        name="Monthly Momentum Rebalance"
    )

    logger.info(f"{'='*60}")
    logger.info(f"Momentum Scheduler Started  [{env_label}]")
    logger.info(f"  Token renewal : daily at 08:55 AM ET")
    logger.info(f"  Rebalance     : last Friday of month at 15:50 ET")
    logger.info(f"  Log file      : {LOG_PATH.resolve()}")
    logger.info(f"  Mode          : {'DRY RUN' if args.dry_run else 'LIVE ORDERS'}")
    logger.info(f"{'='*60}")
    notify_startup(env_label)

    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped.")

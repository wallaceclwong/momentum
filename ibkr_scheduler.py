"""
Monthly momentum rebalance scheduler for Interactive Brokers.

Schedule:
  - Every Friday 15:50 ET → rebalance if last Friday of month
  - Every run             → log results to data/ibkr_scheduler.log

Usage:
  python ibkr_scheduler.py                # start scheduler (runs forever)
  python ibkr_scheduler.py --now          # force rebalance immediately
  python ibkr_scheduler.py --dry-run      # show trade plan, no orders placed

Dry-run mode:
  Active by default until IBKR_LIVE=true is set in .env.
  No IB Gateway connection is attempted in dry-run mode.

Setup (when credentials available):
  1. Fill .env with IBKR_HOST / IBKR_PORT / IBKR_ACCOUNT_ID / IBKR_LIVE=true
  2. Run ibkr_setup_vm.sh on the VM to install IB Gateway
  3. systemctl start ib-gateway
  4. python ibkr_scheduler.py --now --dry-run  (verify plan)
  5. python ibkr_scheduler.py --now            (live rebalance)
"""
import sys
import logging
import argparse
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, ".")

# ── Logging ───────────────────────────────────────────────────
LOG_PATH = Path("data/ibkr_scheduler.log")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ── Imports ───────────────────────────────────────────────────
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.ibkr.gateway import connect, disconnect, is_dry_run, IBKR_LIVE
from backend.ibkr.account import get_positions, get_cash_balance
from backend.ibkr.trader import compute_rebalance_trades, execute_rebalance
from backend.notify.telegram import (
    notify_rebalance_complete, notify_error, notify_startup, send,
)
from backend.engine.regime import get_regime
from backend.data.sp500 import get_ticker_to_sector, get_tickers_by_sector
from backend.engine.portfolio import get_sector_etf_weights
from backend.engine.momentum import calculate_momentum_for_tickers
from backend.data.prices import fetch_price_history
from backend.engine.paper_trading import record_rebalance

VIRTUAL_CAPITAL = 100_000.0   # used in dry-run mode
_PEAK_NAV       = VIRTUAL_CAPITAL


# ── Helpers ───────────────────────────────────────────────────

def is_last_friday_of_month(d: date = None) -> bool:
    """Return True if d (default: today) is the last Friday of its month."""
    d = d or date.today()
    if d.weekday() != 4:
        return False
    return (d + timedelta(days=7)).month != d.month


def get_target_weights(deployment: float = 1.0) -> dict:
    """Run screener and return {ticker: weight} target portfolio."""
    from backend.config import USE_VOLATILITY_WEIGHTING, MAX_POSITION_WEIGHT, USE_EARNINGS_IN_SCREENER, EARNINGS_LOOKBACK
    from backend.data.earnings import get_earnings_surprises_batch
    from backend.engine.earnings_filter import filter_by_earnings_momentum

    ticker_to_sector = get_ticker_to_sector()
    sector_to_tickers = get_tickers_by_sector()
    sector_weights = get_sector_etf_weights()
    all_tickers = list(ticker_to_sector.keys())

    price_data = fetch_price_history(all_tickers, period="13mo", interval="1d")

    earnings_data = {}
    if USE_EARNINGS_IN_SCREENER:
        logger.info("[SCREENER] Fetching earnings surprise data...")
        try:
            earnings_data = get_earnings_surprises_batch(list(price_data.keys()), n=EARNINGS_LOOKBACK)
            logger.info(f"[SCREENER] Earnings data fetched for {len(earnings_data)} tickers")
        except Exception as e:
            logger.warning(f"[SCREENER] Earnings fetch failed, continuing without: {e}")

    momentum_data = calculate_momentum_for_tickers(price_data, earnings_data=earnings_data or None)

    target = {}
    for sector, tickers in sector_to_tickers.items():
        scores = [
            (t, momentum_data[t]["composite_score"])
            for t in tickers
            if t in momentum_data and momentum_data[t].get("composite_score") is not None
        ]
        scores.sort(key=lambda x: x[1], reverse=True)
        # Take top 6, apply earnings filter, keep best 3 that pass
        top6 = [t for t, _ in scores[:6]]
        if earnings_data:
            passed = filter_by_earnings_momentum(top6, earnings_data)
            top3 = passed[:3] if passed else top6[:3]
        else:
            top3 = top6[:3]
        sw = sector_weights.get(sector, 0.0) * deployment
        if not top3 or sw <= 0:
            continue

        if USE_VOLATILITY_WEIGHTING:
            vols = [momentum_data[t].get("volatility") for t in top3]
            if all(v is not None and v > 0 for v in vols):
                inv_vols = [1.0 / v for v in vols]
                total_inv = sum(inv_vols)
                for t, iv in zip(top3, inv_vols):
                    target[t] = sw * (iv / total_inv)
                continue

        w = sw / len(top3)
        for t in top3:
            target[t] = w

    # Concentration cap: no single position > MAX_POSITION_WEIGHT
    capped = {t: min(w, MAX_POSITION_WEIGHT) for t, w in target.items()}
    total_before = sum(target.values())
    total_after = sum(capped.values())
    clipped = total_before - total_after
    if clipped > 1e-6:
        uncapped = {t: w for t, w in capped.items() if w < MAX_POSITION_WEIGHT}
        if uncapped:
            uncapped_total = sum(uncapped.values())
            for t in uncapped:
                capped[t] += clipped * (uncapped[t] / uncapped_total)
    return capped


# ── Main rebalance job ─────────────────────────────────────────

def job_monthly_rebalance(dry_run: bool = False, force: bool = False):
    """Friday job: full rebalance if it's the last Friday of the month."""
    global _PEAK_NAV

    today = date.today()
    if not force and not is_last_friday_of_month(today):
        logger.info(f"[SKIP] {today} is not last Friday of month")
        return

    mode_label = "DRY RUN" if (dry_run or is_dry_run()) else "LIVE"
    logger.info("=" * 60)
    logger.info(f"[REBALANCE DAY] {today}  |  {mode_label}")
    logger.info("=" * 60)

    # ── Regime filter ──────────────────────────────────────────
    try:
        regime = get_regime()
        logger.info(
            f"[REGIME] {regime['label']}  SPY={regime['spy_price']}"
            f"  MA200={regime['spy_ma200']}  deploy={regime['deployment']:.0%}"
        )
        send(
            f"*Regime check:* {regime['label']} market\n"
            f"SPY: ${regime['spy_price']} vs MA200: ${regime['spy_ma200']}\n"
            f"Deployment: {regime['deployment']:.0%}"
        )
        deployment = regime["deployment"]
    except Exception as e:
        logger.warning(f"[REGIME] Failed to get regime, defaulting to 100%: {e}")
        deployment = 1.0

    # ── Circuit breaker ────────────────────────────────────────
    try:
        import yfinance as yf
        from backend.db import SessionLocal, PaperPosition

        db = SessionLocal()
        positions_db = db.query(PaperPosition).all()
        db.close()

        if positions_db:
            tickers = [p.ticker for p in positions_db]
            raw = yf.download(tickers, period="2d", interval="1d", progress=False, auto_adjust=True)
            close = raw["Close"]
            current_val = 0.0
            for p in positions_db:
                try:
                    col = close[p.ticker] if hasattr(close, "columns") else close
                    current_val += p.shares * float(col.dropna().iloc[-1])
                except Exception:
                    pass

            if current_val > _PEAK_NAV:
                _PEAK_NAV = current_val

            from backend.config import CIRCUIT_BREAKER_THRESHOLD
            if current_val < _PEAK_NAV * CIRCUIT_BREAKER_THRESHOLD:
                drawdown = (1 - current_val / _PEAK_NAV) * 100
                msg = (
                    f"*Circuit Breaker Triggered*\n"
                    f"Portfolio down {drawdown:.1f}% from peak\n"
                    f"Skipping rebalance to protect capital"
                )
                logger.warning(f"[CIRCUIT BREAKER] {drawdown:.1f}% drawdown — skipping")
                send(msg)
                return
    except Exception as e:
        logger.warning(f"[CIRCUIT BREAKER] Could not check: {e}")

    # ── Run screener ───────────────────────────────────────────
    logger.info("[SCREENER] Running momentum screener...")
    try:
        target_weights = get_target_weights(deployment=deployment)
        logger.info(f"[SCREENER] {len(target_weights)} target positions (deploy={deployment:.0%})")
    except Exception as e:
        logger.error(f"[ERROR] Screener failed: {e}")
        notify_error("Screener", str(e))
        return

    # ── Connect to IB Gateway (skipped in dry-run) ─────────────
    if not (dry_run or is_dry_run()):
        try:
            connect()
        except Exception as e:
            logger.error(f"[ERROR] Cannot connect to IB Gateway: {e}")
            notify_error("IB Gateway connection", str(e))
            return

    # ── Get current state ──────────────────────────────────────
    try:
        current_positions = get_positions()
        portfolio_value   = get_cash_balance() if not (dry_run or is_dry_run()) else VIRTUAL_CAPITAL
        logger.info(f"[ACCOUNT] {len(current_positions)} positions, portfolio value ${portfolio_value:,.0f}")
    except Exception as e:
        logger.error(f"[ERROR] Failed to fetch account state: {e}")
        notify_error("Account fetch", str(e))
        return

    # ── Compute trades ─────────────────────────────────────────
    buys, sells = compute_rebalance_trades(target_weights, current_positions, portfolio_value)
    logger.info(f"[PLAN] {len(sells)} sells, {len(buys)} buys  (portfolio: ${portfolio_value:,.0f})")

    # ── Execute ────────────────────────────────────────────────
    results = execute_rebalance(
        buys=buys,
        sells=sells,
        dry_run=(dry_run or is_dry_run()),
        delay_seconds=0.5,
    )

    placed = len(results["sells"]) + len(results["buys"])
    errors = len(results["errors"])
    status = "OK" if errors == 0 else "WARN"
    verb   = "previewed" if (dry_run or is_dry_run()) else "placed"
    logger.info(f"[{status}] Rebalance complete: {placed} orders {verb}, {errors} errors")

    for err in results["errors"]:
        logger.error(f"  {err['action']} {err['ticker']}: {err['error']}")

    notify_rebalance_complete(placed, errors, portfolio_value, buys, sells, dry_run or is_dry_run())

    # ── Update paper tracker ───────────────────────────────────
    try:
        ticker_to_sector = get_ticker_to_sector()
        rid = record_rebalance(target_weights, ticker_to_sector, capital=VIRTUAL_CAPITAL)
        logger.info(f"[TRACKER] Portfolio tracker updated: {rid}")
    except Exception as e:
        logger.error(f"[TRACKER] Failed to update portfolio tracker: {e}")

    # ── Disconnect ─────────────────────────────────────────────
    if not (dry_run or is_dry_run()):
        disconnect()


# ── Entry point ────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IBKR Momentum Rebalance Scheduler")
    parser.add_argument("--now",     action="store_true", help="Force rebalance immediately")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                        help="Preview trade plan only — no orders placed")
    args = parser.parse_args()

    broker_label = "IBKR LIVE" if IBKR_LIVE else "IBKR DRY-RUN"

    if args.now:
        logger.info(f"[FORCED] Rebalance triggered  [{broker_label}]")
        job_monthly_rebalance(dry_run=args.dry_run, force=True)
        sys.exit(0)

    # ── Start scheduler ────────────────────────────────────────
    scheduler = BlockingScheduler(timezone="America/New_York")

    # Every Friday 15:50 ET — rebalance if last Friday of month
    scheduler.add_job(
        lambda: job_monthly_rebalance(dry_run=args.dry_run),
        CronTrigger(day_of_week="fri", hour=15, minute=50),
        id="monthly_rebalance",
        name="Monthly Momentum Rebalance",
    )

    logger.info("=" * 60)
    logger.info(f"IBKR Momentum Scheduler Started  [{broker_label}]")
    logger.info(f"  Rebalance : last Friday of month at 15:50 ET")
    logger.info(f"  Log file  : {LOG_PATH.resolve()}")
    logger.info(f"  Mode      : {'DRY RUN — no orders placed' if not IBKR_LIVE else 'LIVE ORDERS'}")
    logger.info("=" * 60)

    notify_startup(broker_label)

    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped.")
        disconnect()

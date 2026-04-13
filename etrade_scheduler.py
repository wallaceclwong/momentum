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
import pandas as pd
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
from backend.engine.regime import get_regime
from backend.data.sp500 import get_ticker_to_sector, get_tickers_by_sector
from backend.engine.portfolio import get_sector_etf_weights
from backend.engine.momentum import calculate_momentum_for_tickers
from backend.data.prices import fetch_price_history

ACCOUNT_ID_KEY   = "dBZOKt9xDrtRSAOl4MSiiA"  # Brokerage MARGIN
VIRTUAL_CAPITAL  = 100_000.0                  # Portfolio size for simulation
_PEAK_NAV        = VIRTUAL_CAPITAL            # tracks peak for circuit breaker


# ── Helpers ───────────────────────────────────────────────────
def is_last_friday_of_month(d: date = None) -> bool:
    """Return True if d (default: today) is the last Friday of its month."""
    d = d or date.today()
    if d.weekday() != 4:  # 4 = Friday
        return False
    return (d + timedelta(days=7)).month != d.month


def get_target_weights(deployment: float = 1.0) -> dict:
    """Run screener and return target weight dict {ticker: weight}."""
    from backend.config import (
        USE_VOLATILITY_WEIGHTING, MAX_POSITION_WEIGHT,
        USE_EARNINGS_IN_SCREENER, EARNINGS_LOOKBACK,
        USE_CRASH_PROTECTION,
    )
    from backend.data.earnings import get_earnings_surprises_batch
    from backend.engine.earnings_filter import filter_by_earnings_momentum
    from backend.engine.crash_protection import compute_crash_scale

    ticker_to_sector = get_ticker_to_sector()
    sector_to_tickers = get_tickers_by_sector()
    sector_weights = get_sector_etf_weights()
    all_tickers = list(ticker_to_sector.keys())

    price_data = fetch_price_history(all_tickers, period="13mo", interval="1d")

    # Fetch earnings data once for all tickers (used as continuous score + filter)
    earnings_data = {}
    if USE_EARNINGS_IN_SCREENER:
        logger.info("[SCREENER] Fetching earnings surprise data...")
        try:
            earnings_data = get_earnings_surprises_batch(list(price_data.keys()), n=EARNINGS_LOOKBACK)
            logger.info(f"[SCREENER] Earnings data fetched for {len(earnings_data)} tickers")
        except Exception as e:
            logger.warning(f"[SCREENER] Earnings fetch failed, continuing without: {e}")

    momentum_data = calculate_momentum_for_tickers(price_data, earnings_data=earnings_data or None)

    # ── Crash protection: scale deployment by inverse realised portfolio vol ──
    if USE_CRASH_PROTECTION:
        try:
            from backend.etrade.account import get_positions as _get_pos, get_cash_balance as _get_cash
            current_positions = _get_pos()
            if current_positions:
                portfolio_value = _get_cash()
                cur_weights = {
                    p["ticker"]: abs(p["market_value"]) / portfolio_value
                    for p in current_positions if portfolio_value > 0
                }
                price_df = pd.DataFrame({t: df["Close"] for t, df in price_data.items() if "Close" in df.columns})
                crash_scale = compute_crash_scale(cur_weights, price_df)
                deployment = round(deployment * crash_scale, 4)
                logger.info(f"[CRASH] crash_scale={crash_scale:.3f}  final_deploy={deployment:.0%}")
        except Exception as e:
            logger.warning(f"[CRASH] Crash scale compute failed, skipping: {e}")

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
            top3 = passed[:3] if passed else top6[:3]  # fallback if all filtered out
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

    # ── Regime filter ──────────────────────────────────────────────
    regime = get_regime()
    logger.info(f"[REGIME] {regime['label']}  SPY={regime['spy_price']}  MA200={regime['spy_ma200']}  deploy={regime['deployment']:.0%}")
    send(f"*Regime check:* {regime['label']} market\nSPY: ${regime['spy_price']} vs MA200: ${regime['spy_ma200']}\nDeployment: {regime['deployment']:.0%}")

    # ── Circuit breaker ───────────────────────────────────────────
    global _PEAK_NAV
    from backend.db import SessionLocal, PaperPosition
    try:
        db = SessionLocal()
        positions = db.query(PaperPosition).all()
        db.close()
        import yfinance as yf
        if positions:
            tickers = [p.ticker for p in positions]
            raw = yf.download(tickers, period="2d", interval="1d", progress=False, auto_adjust=True)
            current_val = sum(
                p.shares * float(raw["Close"][p.ticker].dropna().iloc[-1])
                for p in positions if p.ticker in raw["Close"].columns
            )
            if current_val > _PEAK_NAV:
                _PEAK_NAV = current_val
            from backend.config import CIRCUIT_BREAKER_THRESHOLD
            if current_val < _PEAK_NAV * CIRCUIT_BREAKER_THRESHOLD:
                drawdown = (1 - current_val / _PEAK_NAV) * 100
                msg = f"*Circuit Breaker Triggered*\nPortfolio down {drawdown:.1f}% from peak\nSkipping rebalance to protect capital"
                logger.warning(f"[CIRCUIT BREAKER] {drawdown:.1f}% drawdown from peak — skipping")
                send(msg)
                return
    except Exception as e:
        logger.warning(f"[CIRCUIT BREAKER] Could not check: {e}")

    # Ensure token is valid
    if not renew_token():
        logger.error("[ERROR] Cannot rebalance - token expired. Re-authenticate first.")
        notify_token_expired()
        return

    # Get target portfolio
    logger.info("[SCREENER] Running momentum screener...")
    try:
        target_weights = get_target_weights(deployment=regime["deployment"])
        logger.info(f"[SCREENER] {len(target_weights)} target positions  (deploy={regime['deployment']:.0%})")
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

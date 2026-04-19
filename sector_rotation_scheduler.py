"""
Automated monthly sector rotation — Antonacci UCITS strategy.

Execution modes:
  --dry-run   (default)  Show signal + planned trades, no orders placed
  --paper                Simulate fills, persist to paper_positions table
  --live                 Place real orders via IBKR (requires IBKR_LIVE=true)

Scheduler commands:
  screener    Print today's signal (no rebalance)
  plan        Show rebalance plan without executing
  rebalance   Execute rebalance (requires mode flag)
  schedule    Run forever; rebalance on last Friday each month

Usage examples:
  python sector_rotation_scheduler.py screener
  python sector_rotation_scheduler.py plan --nav 330000
  python sector_rotation_scheduler.py rebalance --paper --nav 330000
  python sector_rotation_scheduler.py rebalance --live
  python sector_rotation_scheduler.py schedule --paper

Safety:
  - Live mode refuses to run unless .env has IBKR_LIVE=true
  - Dry-run mode doesn't connect to IBKR at all
  - Paper mode doesn't connect to IBKR; simulates fills at latest close
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backend.config import SECTOR_ROTATION_TOP_K
from backend.engine.sector_executor import (
    SectorSignal, RebalancePlan, Trade,
    generate_signal, compute_trades,
    persist_signal, persist_rebalance, get_last_paper_positions,
)
from backend.ibkr.ucits_contracts import UCITS_CONTRACT_SPECS, TICKER_TO_SPEC
from run_sector_backtest import load_prices

# ─── Logging ───────────────────────────────────────────────────────────────
LOG_PATH = Path("data/sector_rotation_scheduler.log")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("sector_rotation")


# ─── Utilities ─────────────────────────────────────────────────────────────
def is_last_friday_of_month(d: Optional[date] = None) -> bool:
    d = d or date.today()
    if d.weekday() != 4:   # Friday = 4
        return False
    return (d + timedelta(days=7)).month != d.month


def is_ibkr_live_enabled() -> bool:
    """
    Returns True if IBKR_LIVE=true is set in environment.

    NOTE: despite the name, this flag controls whether we CONNECT to
    IB Gateway at all — it does NOT distinguish paper-account from
    live-real-money account. That distinction is determined by the
    IB Gateway port (IBKR_PORT):
        4001 = paper account
        4002 = live-real-money account
    So for paper-account trading set IBKR_LIVE=true AND IBKR_PORT=4001.
    """
    return os.environ.get("IBKR_LIVE", "").lower() == "true"


# ─── Signal printing ───────────────────────────────────────────────────────
def print_signal(signal: SectorSignal) -> None:
    print("\n" + "=" * 70)
    print(f"SECTOR ROTATION SIGNAL  (as of {signal.as_of.date()})")
    print("=" * 70)
    print(f"  Signal month-end: {signal.signal_date.date()}")
    print(f"  Trend filter:     {signal.trend_mode}")
    print(f"  Trend value:      {signal.trend_value:>+7.2%}")
    print(f"  Deploy:           {'YES — buy top-3 sectors' if signal.deploy else 'NO — go to cash'}")
    print()
    print(f"  All sectors ranked by 12-1 momentum:")
    for i, (sector, mom) in enumerate(signal.all_ranked, 1):
        spec = UCITS_CONTRACT_SPECS.get(sector, {})
        tk   = spec.get("symbol", "N/A")
        mark = " ← BUY" if sector in signal.top_sectors else ""
        print(f"    {i:>2}. {sector:<28s}  {mom:>+7.2%}   ({tk}){mark}")
    print()
    if signal.deploy:
        print(f"  Target allocation:")
        for tk, w in signal.target_weights.items():
            sec = TICKER_TO_SPEC.get(tk, {}).get("sector", "?")
            print(f"    {tk:<6s}  {sec:<28s}  {w:>5.1%}")
    print()


def print_plan(plan: RebalancePlan) -> None:
    print("\n" + "=" * 70)
    print(f"REBALANCE PLAN  (NAV ${plan.portfolio_nav:,.0f})")
    print("=" * 70)
    if not plan.trades:
        print("  No trades needed — portfolio already at target (within drift tolerance).")
        return
    print(f"  {'Action':<6s} {'Ticker':<6s} {'Sector':<28s} {'ΔShares':>10s} "
          f"{'Price':>9s} {'Value':>10s}  Reason")
    print("  " + "-" * 100)
    for t in plan.trades:
        print(f"  {t.action:<6s} {t.ticker:<6s} {t.sector:<28s} "
              f"{t.delta_shares:>+10.2f} ${t.est_price:>8.2f} "
              f"${t.est_value_usd:>9,.0f}  {t.reason}")
    print(f"\n  Total buy value:  ${plan.total_buy_value:>10,.0f}")
    print(f"  Total sell value: ${plan.total_sell_value:>10,.0f}")
    print(f"  Estimated cost:   ${plan.estimated_cost:>10,.2f}  "
          f"({plan.estimated_cost / max(plan.portfolio_nav, 1):>.2%} of NAV)")
    print()


# ─── IBKR execution (wraps existing trader.py) ─────────────────────────────
def execute_via_ibkr(plan: RebalancePlan, delay_s: float = 0.5) -> Dict:
    """
    Place orders via IBKR for UCITS LSE ETFs.
    Uses Adaptive algo with Urgent priority (per user memory).
    """
    if not is_ibkr_live_enabled():
        raise RuntimeError(
            "IBKR_LIVE is not set to 'true' in environment — cannot connect "
            "to IB Gateway. For paper-account testing: set IBKR_LIVE=true AND "
            "IBKR_PORT=4001 in .env. For real money: IBKR_LIVE=true AND "
            "IBKR_PORT=4002."
        )
    try:
        from ib_insync import Order, TagValue
    except ImportError as e:
        raise ImportError("ib_insync not installed. pip install ib_insync") from e

    from backend.ibkr.gateway import connect, disconnect, get_ib
    from backend.ibkr.ucits_contracts import build_ibkr_contract
    from backend.config import IBKR_ADAPTIVE_PRIORITY

    connect()
    try:
        ib = get_ib()
        if not ib or not ib.isConnected():
            raise RuntimeError("IBKR not connected after connect()")

        fills: List[Dict] = []
        # Sells first, then buys (free up cash before deploying)
        ordered = sorted(plan.trades, key=lambda t: 0 if t.action == "SELL" else 1)
        for t in ordered:
            try:
                contract = build_ibkr_contract(t.ticker)
                ib.qualifyContracts(contract)

                order = Order()
                order.action        = t.action
                order.totalQuantity = max(1, round(abs(t.delta_shares)))
                order.tif           = "DAY"
                order.orderType     = "MKT"
                order.algoStrategy  = "Adaptive"
                order.algoParams    = [TagValue("adaptivePriority", IBKR_ADAPTIVE_PRIORITY)]

                trade = ib.placeOrder(contract, order)
                fill_info = {
                    "ticker":       t.ticker,
                    "action":       t.action,
                    "shares":       order.totalQuantity,
                    "order_id":     trade.order.orderId,
                    "est_price":    t.est_price,
                    "est_value":    t.est_value_usd,
                    "status":       "submitted",
                }
                logger.info(f"[IBKR] {t.action} {order.totalQuantity} {t.ticker} (LSE UCITS) orderId={trade.order.orderId}")
                fills.append(fill_info)
                time.sleep(delay_s)
            except Exception as e:
                logger.error(f"[IBKR] Order failed: {t.action} {t.ticker}: {e}")
                fills.append({
                    "ticker": t.ticker,
                    "action": t.action,
                    "status": "failed",
                    "error":  str(e),
                })
        return {"fills": fills}
    finally:
        disconnect()


# ─── Orchestration ─────────────────────────────────────────────────────────
def run_screener() -> SectorSignal:
    """Compute today's signal and print. No DB writes, no trades."""
    prices = load_prices("2000-01-01", datetime.today().strftime("%Y-%m-%d"))
    sig = generate_signal(prices)
    print_signal(sig)
    return sig


def run_plan(nav: float, use_last_paper: bool = True) -> RebalancePlan:
    """Compute plan without executing. Saves signal to DB."""
    prices = load_prices("2000-01-01", datetime.today().strftime("%Y-%m-%d"))
    sig = generate_signal(prices)
    print_signal(sig)

    # Price lookup from latest row
    latest = prices.iloc[-1]
    # For UCITS tickers we need prices — use US SPDR proxies as price proxy
    # (acceptable only for dry-run/planning; in live mode IBKR will use real UCITS prices)
    sector_for_ticker = {spec["symbol"]: sector for sector, spec in UCITS_CONTRACT_SPECS.items()}
    proxy_for_sector = {sector: sector_to_proxy(sector) for sector in UCITS_CONTRACT_SPECS.keys()}
    price_lookup = {}
    for ucits_tk, sector in sector_for_ticker.items():
        proxy = proxy_for_sector[sector]
        if proxy in prices.columns and not pd.isna(latest.get(proxy)):
            price_lookup[ucits_tk] = float(latest[proxy])

    positions = get_last_paper_positions() if use_last_paper else {}
    plan = compute_trades(sig, positions, portfolio_nav=nav, price_lookup=price_lookup)
    print_plan(plan)

    signal_id = persist_signal(sig)
    persist_rebalance(plan, mode="dry_run", signal_id=signal_id, status="planned")
    logger.info(f"[PLAN] saved signal_id={signal_id}, mode=dry_run, trades={len(plan.trades)}")
    return plan


def sector_to_proxy(sector: str) -> str:
    from backend.config import SECTOR_BACKTEST_PROXIES
    return SECTOR_BACKTEST_PROXIES[sector]


def run_rebalance(nav: float, mode: str) -> RebalancePlan:
    """
    Execute rebalance.

    Modes:
      dry_run: plan only
      paper:   simulate fills at latest close, persist to paper_* tables
      live:    place real IBKR orders (requires IBKR_LIVE=true)
    """
    if mode not in ("dry_run", "paper", "live"):
        raise ValueError(f"Unknown mode: {mode}")

    plan = run_plan(nav, use_last_paper=(mode == "paper"))
    signal_id = persist_signal(plan.signal)

    if mode == "dry_run":
        logger.info("[REBAL] dry_run — no fills recorded")
        return plan

    if mode == "paper":
        # Simulate: assume fills at est_price
        fills = [{
            "ticker":    t.ticker,
            "action":    t.action,
            "shares":    abs(t.delta_shares),
            "fill_price": t.est_price,
            "status":    "simulated",
        } for t in plan.trades]
        persist_rebalance(plan, mode="paper", signal_id=signal_id,
                          fills=fills, status="executed")
        logger.info(f"[REBAL] paper: simulated {len(fills)} fills")
        return plan

    # mode == "live"
    if not is_ibkr_live_enabled():
        raise RuntimeError("IBKR_LIVE not set to 'true' — refusing live orders")
    try:
        result = execute_via_ibkr(plan)
        persist_rebalance(plan, mode="live", signal_id=signal_id,
                          fills=result["fills"], status="executed")
        logger.info(f"[REBAL] live: {len(result['fills'])} orders submitted")
    except Exception as e:
        persist_rebalance(plan, mode="live", signal_id=signal_id,
                          status="failed", error=str(e))
        logger.exception("[REBAL] live execution failed")
        raise
    return plan


def run_scheduler_loop(nav: float, mode: str) -> None:
    """Blocking scheduler — wakes up daily, rebalances on last Friday."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    sched = BlockingScheduler(timezone="US/Eastern")

    def job():
        d = date.today()
        if not is_last_friday_of_month(d):
            logger.info(f"[SCHED] {d} is not last Friday of month — skipping")
            return
        logger.info(f"[SCHED] {d} is last Friday — rebalancing (mode={mode})")
        try:
            run_rebalance(nav, mode=mode)
        except Exception:
            logger.exception("[SCHED] rebalance failed")

    # Run Fridays 15:50 US/Eastern (~10 min before close)
    sched.add_job(job, CronTrigger(day_of_week="fri", hour=15, minute=50))
    logger.info(f"[SCHED] started — mode={mode}, nav=${nav:,.0f}, next rebalance = last Friday of month")
    sched.start()


# ─── CLI ───────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Sector rotation scheduler")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("screener", help="Print today's signal only")

    p_plan = sub.add_parser("plan", help="Show rebalance plan, persist as dry_run")
    p_plan.add_argument("--nav", type=float, required=True,
                        help="Current portfolio NAV in USD")

    p_rebal = sub.add_parser("rebalance", help="Execute rebalance")
    p_rebal.add_argument("--nav", type=float, required=True,
                         help="Current portfolio NAV in USD")
    g = p_rebal.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", dest="mode", action="store_const", const="dry_run")
    g.add_argument("--paper",   dest="mode", action="store_const", const="paper")
    g.add_argument("--live",    dest="mode", action="store_const", const="live")

    p_sched = sub.add_parser("schedule", help="Run scheduler loop (blocking)")
    p_sched.add_argument("--nav", type=float, required=True)
    g2 = p_sched.add_mutually_exclusive_group(required=True)
    g2.add_argument("--dry-run", dest="mode", action="store_const", const="dry_run")
    g2.add_argument("--paper",   dest="mode", action="store_const", const="paper")
    g2.add_argument("--live",    dest="mode", action="store_const", const="live")

    args = parser.parse_args()

    if args.cmd == "screener":
        run_screener()
    elif args.cmd == "plan":
        run_plan(args.nav)
    elif args.cmd == "rebalance":
        run_rebalance(args.nav, mode=args.mode)
    elif args.cmd == "schedule":
        run_scheduler_loop(args.nav, mode=args.mode)


if __name__ == "__main__":
    main()

"""
CLI entrypoint to run and compare sector rotation backtests.

Usage:
  python run_sector_backtest.py                        # default: full history + key windows
  python run_sector_backtest.py --start 2000-01-01 --end 2026-04-10
  python run_sector_backtest.py --no-regime            # disable regime filter
  python run_sector_backtest.py --top-k 5              # hold top-5 instead of top-3

Prints comparison table: sector rotation vs 33-stock DB results + benchmarks.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

# Make backend importable
sys.path.insert(0, str(Path(__file__).resolve().parent))
from backend.config import (
    SECTOR_BACKTEST_PROXIES, SECTOR_ROTATION_TOP_K,
    USE_SECTOR_REGIME_FILTER, USE_SECTOR_CRASH_PROTECTION, USE_SECTOR_ABSOLUTE_MOMENTUM,
)
from backend.engine.sector_rotation import run_sector_backtest, run_sector_screener

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("sector_bt")

CACHE_PATH = Path(__file__).parent / "data" / "sector_price_cache.parquet"


def load_prices(start: str, end: str) -> pd.DataFrame:
    """Load or download daily adjusted-close prices for all needed tickers."""
    tickers = list(SECTOR_BACKTEST_PROXIES.values()) + ["SPY", "^VIX"]

    # Buffer start date for momentum lookback (need 400 days prior to start)
    buf_start = (datetime.strptime(start, "%Y-%m-%d") - timedelta(days=400)).strftime("%Y-%m-%d")

    cached = pd.DataFrame()
    if CACHE_PATH.exists():
        try:
            cached = pd.read_parquet(CACHE_PATH)
            cached.index = pd.to_datetime(cached.index)
        except Exception as e:
            logger.warning(f"Cache read failed: {e}")

    need_download = (
        cached.empty
        or any(t not in cached.columns for t in tickers)
        or cached.index.min() > pd.Timestamp(buf_start)
        or cached.index.max() < pd.Timestamp(end)
    )

    if need_download:
        logger.info(f"Downloading {tickers} from {buf_start} to {end}...")
        raw = yf.download(
            tickers=tickers, start=buf_start, end=end,
            auto_adjust=True, progress=False, group_by="ticker", threads=True,
        )
        if isinstance(raw.columns, pd.MultiIndex):
            try:
                fresh = raw.xs("Close", axis=1, level=1)
            except KeyError:
                fresh = raw.xs("Adj Close", axis=1, level=1)
        else:
            fresh = raw[["Close"]].rename(columns={"Close": tickers[0]})
        fresh.index = pd.to_datetime(fresh.index)
        combined = fresh if cached.empty else fresh.combine_first(cached)
        combined = combined.dropna(how="all").sort_index()
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(CACHE_PATH)
        cached = combined
        logger.info(f"Cache updated: shape={cached.shape}")

    # Return full cache (backtest will slice by date)
    return cached


def print_metrics_row(label: str, metrics: dict) -> None:
    print(f"  {label:<40s}  CAGR={metrics['cagr']:>6.2%}  "
          f"Sharpe={metrics['sharpe']:>5.2f}  MaxDD={metrics['max_drawdown']:>6.2%}  "
          f"Vol={metrics['volatility']:>5.2%}  NAV={metrics['final_nav']:>7.1f}")


def run_all_windows(apply_regime: bool, apply_crash: bool, top_k: int,
                    apply_abs_mom: bool = True) -> None:
    prices = load_prices("2000-01-01", datetime.today().strftime("%Y-%m-%d"))
    print(f"\nPrice data: {prices.shape[0]} days × {prices.shape[1]} tickers, "
          f"{prices.index.min().date()} -> {prices.index.max().date()}")

    windows = [
        ("2000-01-01", "2026-04-10", "Full history (26yr)"),
        ("2000-01-01", "2014-12-31", "TRAIN 2000-2014"),
        ("2015-01-01", "2026-04-10", "TEST  2015-2026"),
        ("2010-01-01", "2014-12-31", "P3 2010-2014 (QE bull)"),
        ("2015-01-01", "2019-12-31", "P4 2015-2019 (low-vol bull)"),
        ("2020-01-01", "2024-12-31", "P5 2020-2024 (COVID+rally)"),
    ]

    print(f"\nSettings: top_k={top_k}  regime={apply_regime}  crash={apply_crash}  abs_mom={apply_abs_mom}")
    print("═" * 100)

    results = {}
    for start, end, label in windows:
        try:
            r = run_sector_backtest(
                start, end, prices,
                top_k=top_k,
                apply_regime=apply_regime,
                apply_crash_protection=apply_crash,
                apply_absolute_momentum=apply_abs_mom,
            )
            print_metrics_row(label, r["metrics"])
            results[label] = r["metrics"]
        except Exception as e:
            print(f"  {label:<40s}  ERROR: {e}")

    # Comparison to 33-stock OOS results (from retirement/output/oos_test_results.json)
    oos_path = Path(r"C:\Users\ASUS\retirement\output\oos_test_results.json")
    if oos_path.exists():
        oos = json.loads(oos_path.read_text())
        print("\n── 33-stock strategy (fresh OOS, post-survivorship-bias-fix) ──────")
        for t in oos["main_tests"]:
            if "cagr" not in t:
                continue
            print(f"  {t['label']:<40s}  CAGR={t['cagr']:>6.2%}  "
                  f"Sharpe={t['sharpe']:>5.2f}  MaxDD={t['max_drawdown']:>6.2%}  "
                  f"Vol={t.get('volatility',0):>5.2%}  NAV={t['final_nav']:>7.1f}")

    # Current screener pick (today's top-3 sectors)
    print("\n── Today's sector screener pick (live UCITS tickers) ──────────────")
    try:
        pick = run_sector_screener(prices, top_k=top_k, use_live_tickers=True)
        print(f"  Signal date: {pick['signal_date'].date()}")
        print(f"  Top sectors: {pick['top_sectors']}")
        print(f"  Live UCITS tickers: {pick['tickers']}")
        print(f"  Momentum scores:")
        for s, m in sorted(pick["momentum_scores"].items(), key=lambda x: -x[1]):
            mark = " ← BUY" if s in pick["top_sectors"] else ""
            print(f"    {s:<30s} {m:>7.2%}{mark}")
    except Exception as e:
        print(f"  screener error: {e}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=SECTOR_ROTATION_TOP_K)
    parser.add_argument("--regime", dest="regime", action="store_true")
    parser.add_argument("--no-regime", dest="regime", action="store_false")
    parser.set_defaults(regime=USE_SECTOR_REGIME_FILTER)
    parser.add_argument("--crash", dest="crash", action="store_true")
    parser.add_argument("--no-crash", dest="crash", action="store_false")
    parser.set_defaults(crash=USE_SECTOR_CRASH_PROTECTION)
    parser.add_argument("--abs-mom", dest="abs_mom", action="store_true")
    parser.add_argument("--no-abs-mom", dest="abs_mom", action="store_false",
                        help="Disable absolute-momentum filter (Faber dual-momentum)")
    parser.set_defaults(abs_mom=USE_SECTOR_ABSOLUTE_MOMENTUM)
    args = parser.parse_args()

    run_all_windows(
        apply_regime=args.regime,
        apply_crash=args.crash,
        top_k=args.top_k,
        apply_abs_mom=args.abs_mom,
    )

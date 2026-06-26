"""
Head-to-head backtest: abs_mom_12m vs SMA-100 vs SMA-210 vs No-Filter

Tests the four trend-filter variants across six time windows, including the
documented TRAIN (2000-2014) and TEST (2015-2026) sets, to validate whether
the May-2026 switch from abs_mom_12m to SMA-100 holds up out-of-sample.

Usage:
    py compare_trend_filters.py

Output: console table + compare_trend_filters.csv in this directory.
"""
from __future__ import annotations

import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backend.config import SECTOR_BACKTEST_PROXIES, SECTOR_ROTATION_MAX_TECH_SECTORS
from backend.engine.sector_rotation import run_sector_backtest

# ── Price cache (reuse run_sector_backtest.py cache) ─────────────────────────
CACHE_PATH = Path(__file__).parent / "data" / "sector_price_cache.parquet"


def load_prices() -> pd.DataFrame:
    tickers = list(SECTOR_BACKTEST_PROXIES.values()) + ["SPY", "^VIX"]
    buf_start = "1999-01-01"
    end = datetime.today().strftime("%Y-%m-%d")

    cached = pd.DataFrame()
    if CACHE_PATH.exists():
        try:
            cached = pd.read_parquet(CACHE_PATH)
            cached.index = pd.to_datetime(cached.index)
        except Exception:
            pass

    need_dl = (
        cached.empty
        or any(t not in cached.columns for t in tickers)
        or cached.index.min() > pd.Timestamp(buf_start)
        or cached.index.max() < pd.Timestamp(end)
    )
    if need_dl:
        print(f"Downloading price data {buf_start} → {end} ...")
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
        print(f"  Cache updated: {cached.shape[0]} days × {cached.shape[1]} tickers")
    return cached


# ── Filter variants to compare ────────────────────────────────────────────────
FILTERS = [
    {"label": "abs_mom_12m",  "mode": "abs_mom_12m", "sma_days": 252, "dual": False},
    {"label": "SMA-100",      "mode": "sma",         "sma_days": 100, "dual": False},
    {"label": "SMA-210",      "mode": "sma",         "sma_days": 210, "dual": False},
    {"label": "No-Filter",    "mode": "abs_mom_12m", "sma_days": 252, "dual": False, "disabled": True},
]

# ── Time windows ─────────────────────────────────────────────────────────────
# Window tuple: (start, end, label, is_train)
# is_train=True marks the documented training set used in original filter choice.
WINDOWS = [
    ("2000-01-01", "2026-04-30", "Full  2000-2026  (26yr)",   False),
    ("2000-01-01", "2014-12-31", "TRAIN 2000-2014  (15yr) *", True),   # original train set
    ("2015-01-01", "2026-04-30", "TEST  2015-2026  (11yr)",   False),
    ("2020-01-01", "2024-12-31", "P5    2020-2024  (COVID+)", False),  # fast-crash relevance
    ("2010-01-01", "2014-12-31", "P3    2010-2014  (QE bull)",False),  # whipsaw risk
    ("2015-01-01", "2019-12-31", "P4    2015-2019  (low-vol)",False),
]


def cash_pct(holdings_log: list[dict]) -> float:
    """Fraction of rebalance decisions that went to cash (deployment == 0)."""
    if not holdings_log:
        return float("nan")
    cash_count = sum(1 for h in holdings_log if len(h.get("top_sectors", [])) == 0)
    return cash_count / len(holdings_log)


def run_filter(flt: dict, start: str, end: str, prices: pd.DataFrame) -> dict | None:
    try:
        apply_trend = not flt.get("disabled", False)
        r = run_sector_backtest(
            start, end, prices,
            top_k=3,
            apply_regime=False,
            apply_crash_protection=False,
            apply_absolute_momentum=True,
            apply_trend_filter=apply_trend,
            trend_mode=flt["mode"],
            trend_sma_days=flt["sma_days"],
            trend_dual_confirmation=flt["dual"],
            max_tech_sectors=SECTOR_ROTATION_MAX_TECH_SECTORS,
        )
        m = r["metrics"]
        m["cash_pct"] = cash_pct(r.get("holdings_log", []))
        return m
    except Exception as e:
        return {"error": str(e)}


def fmt(v, fmt_str: str, fallback: str = "  n/a  ") -> str:
    if v is None or (isinstance(v, float) and (v != v)):
        return fallback
    return format(v, fmt_str)


def print_table(all_results: list[dict]) -> None:
    COL_W = 16
    HDR_W = 32

    filter_labels = [f["label"] for f in FILTERS]

    print()
    total_w = HDR_W + COL_W * len(FILTERS) + 2
    print("=" * total_w)
    print("  TREND FILTER COMPARISON — SECTOR ROTATION BUCKET 2 ($330k)")
    print("  Regime=OFF  Crash-prot=OFF  AbsMom=ON  Tech-cap=1  Top-K=3")
    print("  * = original TRAIN set used to justify abs_mom_12m choice")
    print("=" * total_w)

    metrics_to_show = [
        ("CAGR",      "cagr",          ".2%"),
        ("Sharpe",    "sharpe",        ".2f"),
        ("MaxDD",     "max_drawdown",  ".2%"),
        ("Vol",       "volatility",    ".2%"),
        ("Cash%",     "cash_pct",      ".0%"),
    ]

    for window_start, window_end, window_label, is_train in WINDOWS:
        marker = "  ← key validation" if is_train else ""
        sep = HDR_W + COL_W * len(FILTERS)
        print(f"\n  {'─'*sep}")
        print(f"  Window: {window_label}{marker}")
        print(f"  {'Metric':<14}", end="")
        for fl in filter_labels:
            print(f"  {fl:>{COL_W-2}}", end="")
        print()
        print(f"  {'─'*14}", end="")
        for _ in filter_labels:
            print(f"  {'─'*(COL_W-2)}", end="")
        print()

        for metric_label, metric_key, fmt_str in metrics_to_show:
            print(f"  {metric_label:<14}", end="")
            row_vals = []
            for flt in FILTERS:
                res = all_results_map.get((flt["label"], window_label), {})
                v = res.get(metric_key)
                row_vals.append(v)

            # Find best CAGR and worst MaxDD for highlighting
            cagr_vals = [all_results_map.get((f["label"], window_label), {}).get("cagr") for f in FILTERS]
            valid_cagr = [v for v in cagr_vals if v is not None]
            best_cagr = max(valid_cagr) if valid_cagr else None
            dd_vals = [all_results_map.get((f["label"], window_label), {}).get("max_drawdown") for f in FILTERS]
            valid_dd = [v for v in dd_vals if v is not None]
            best_dd = max(valid_dd) if valid_dd else None  # least negative = best

            for i, (flt, v) in enumerate(zip(FILTERS, row_vals)):
                s = fmt(v, fmt_str)
                if metric_key == "cagr" and v == best_cagr:
                    s = f"[{s}]"   # mark best CAGR with brackets
                elif metric_key == "max_drawdown" and v == best_dd:
                    s = f"[{s}]"   # mark best (least negative) MDD
                print(f"  {s:>{COL_W-2}}", end="")
            print()


if __name__ == "__main__":
    prices = load_prices()
    print(f"\nPrice data loaded: {prices.shape[0]} days, "
          f"{prices.index.min().date()} → {prices.index.max().date()}")

    # Pre-run all combinations
    all_results_map: dict[tuple[str, str], dict] = {}
    total = len(FILTERS) * len(WINDOWS)
    done = 0
    print(f"\nRunning {total} backtests ({len(FILTERS)} filters × {len(WINDOWS)} windows)...")

    for window_start, window_end, window_label, is_train in WINDOWS:
        for flt in FILTERS:
            done += 1
            print(f"  [{done:>2}/{total}] {flt['label']:<14}  {window_label}", end="\r")
            result = run_filter(flt, window_start, window_end, prices)
            all_results_map[(flt["label"], window_label)] = result or {}

    print(" " * 80, end="\r")  # clear progress line

    print_table(all_results_map)

    # ── Export to CSV ─────────────────────────────────────────────────────────
    rows = []
    for (filter_label, window_label), metrics in all_results_map.items():
        row = {"filter": filter_label, "window": window_label}
        row.update({k: v for k, v in metrics.items() if not isinstance(v, (dict, list))})
        rows.append(row)
    out_path = Path(__file__).parent / "compare_trend_filters.csv"
    pd.DataFrame(rows).to_csv(out_path, index=False)

    print(f"\n  Results saved → {out_path}")
    print()
    print("  Legend:")
    print("  [val] = best performer in that window for that metric")
    print("  Cash% = fraction of monthly rebalances where filter sent to cash")
    print("  abs_mom_12m = SPY 12-month return > 0 (Antonacci, original choice)")
    print("  SMA-100     = SPY > 100-day SMA (new May-2026 setting)")
    print("  SMA-210     = SPY > 210-day SMA (Faber variant, previously tested)")
    print("  No-Filter   = pure momentum, always deployed (baseline)")
    print()

"""
Compare trend filter variants for UCITS sector rotation.

Tests 5 variants on the same OOS windows:
  1. No filter                    — 12-1 momentum only, top-K
  2. SMA 10-month (current)       — Faber GTAA default
  3. SMA 12-month                 — longer lookback, less whipsaw
  4. SMA 10-month + dual confirm  — require 2 consecutive months below SMA
  5. Abs-mom 12-month (Antonacci) — SPY 12m total return > 0

For each variant reports CAGR / Sharpe / MaxDD / final NAV across:
  TRAIN 2000-2014, TEST 2015-2026, Full 26yr, P3/P4/P5 subperiods.

Then applies after-tax HK NRA adjustments and compares terminal wealth vs
the 33-stock OOS baseline (from retirement/output/oos_test_results.json).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backend.engine.sector_rotation import (
    run_sector_backtest, apply_after_tax_adjustments,
)
from run_sector_backtest import load_prices  # reuse price loader + cache

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(levelname)s %(message)s")

WINDOWS = [
    ("2000-01-01", "2026-04-10", "Full 2000-2026"),
    ("2000-01-01", "2014-12-31", "TRAIN 2000-14"),
    ("2015-01-01", "2026-04-10", "TEST  2015-26"),
    ("2008-01-01", "2009-12-31", "GFC 2008-09"),
    ("2020-01-01", "2024-12-31", "P5 2020-24"),
]

# Each variant: (label, kwargs to run_sector_backtest)
VARIANTS = [
    ("1. No filter (plain)", dict(
        apply_trend_filter=False, apply_absolute_momentum=True,
    )),
    ("2. SMA 10mo (current)", dict(
        apply_trend_filter=True, trend_mode="sma", trend_sma_days=210,
        trend_dual_confirmation=False, apply_absolute_momentum=True,
    )),
    ("3. SMA 12mo (longer)", dict(
        apply_trend_filter=True, trend_mode="sma", trend_sma_days=252,
        trend_dual_confirmation=False, apply_absolute_momentum=True,
    )),
    ("4. SMA 10mo + dual-conf", dict(
        apply_trend_filter=True, trend_mode="sma", trend_sma_days=210,
        trend_dual_confirmation=True, apply_absolute_momentum=True,
    )),
    ("5. Antonacci 12m abs-mom", dict(
        apply_trend_filter=True, trend_mode="abs_mom_12m",
        apply_absolute_momentum=True,
    )),
]


def main() -> None:
    prices = load_prices("2000-01-01", datetime.today().strftime("%Y-%m-%d"))
    print(f"\nPrice data: {prices.shape[0]} days × {prices.shape[1]} tickers, "
          f"{prices.index.min().date()} -> {prices.index.max().date()}\n")

    # Collect results: results[window][variant] = metrics
    results: dict = {w[2]: {} for w in WINDOWS}

    for variant_label, kwargs in VARIANTS:
        print(f"Running {variant_label} ...")
        for start, end, w_label in WINDOWS:
            try:
                r = run_sector_backtest(start, end, prices,
                                         apply_regime=False, apply_crash_protection=False,
                                         **kwargs)
                results[w_label][variant_label] = r["metrics"]
            except Exception as e:
                results[w_label][variant_label] = {"error": str(e)}

    # ── Print comparison table per window ──────────────────────────────
    print("\n" + "=" * 110)
    print("SECTOR ROTATION FILTER COMPARISON (all variants, same OOS windows)")
    print("=" * 110)

    for _, _, w_label in WINDOWS:
        print(f"\n── {w_label} " + "─" * (100 - len(w_label)))
        header = f"  {'Variant':<28s} {'CAGR':>7s}  {'Sharpe':>6s}  {'MaxDD':>7s}  {'Vol':>6s}  {'FinalNAV':>9s}"
        print(header)
        print("  " + "-" * 75)
        for v_label, _ in VARIANTS:
            m = results[w_label][v_label]
            if "error" in m:
                print(f"  {v_label:<28s} ERR: {m['error']}")
                continue
            print(f"  {v_label:<28s} {m['cagr']:>6.2%}  {m['sharpe']:>6.2f}  "
                  f"{m['max_drawdown']:>6.2%}  {m['volatility']:>5.2%}  {m['final_nav']:>9.1f}")

    # ── After-tax comparison for the TEST window (forward estimate) ────
    print("\n" + "=" * 110)
    print("AFTER-TAX TERMINAL WEALTH  (HK NRA holder, $330K bucket 2, 15-year horizon)")
    print("Using TEST 2015-2026 pre-tax CAGRs as forward estimate. Estate tax = one-time hit at death.")
    print("=" * 110)

    # 33-stock baseline from retirement project OOS
    stock_cagr = None
    oos_path = Path(r"C:\Users\ASUS\retirement\output\oos_test_results.json")
    if oos_path.exists():
        for t in json.loads(oos_path.read_text()).get("main_tests", []):
            if "TEST" in t.get("label", "") and "cagr" in t:
                stock_cagr = t["cagr"]

    header = f"  {'Variant':<28s} {'PreTax':>7s}  {'AftWHT':>7s}  {'Term15y':>10s}  {'EstTax':>9s}  {'Net15y':>10s}  {'EffCAGR':>8s}  {'vs33st':>9s}"
    print(header)
    print("  " + "-" * 98)

    if stock_cagr is not None:
        a = apply_after_tax_adjustments(stock_cagr, "US_DIRECT", horizon_years=15)
        print(f"  {'0. 33-stock US direct':<28s} {a['pre_tax_cagr']:>6.2%}  {a['after_wht_cagr']:>6.2%}  "
              f"${a['terminal_gross']:>9,.0f}  ${a['us_estate_tax']:>8,.0f}  ${a['terminal_net']:>9,.0f}  "
              f"{a['effective_cagr_after_all_tax']:>7.2%}  {'(base)':>9s}")
        base_net = a["terminal_net"]
    else:
        base_net = None

    for v_label, _ in VARIANTS:
        m = results["TEST  2015-26"][v_label]
        if "error" in m:
            continue
        a = apply_after_tax_adjustments(m["cagr"], "UCITS", horizon_years=15)
        gap = (a["terminal_net"] - base_net) if base_net else 0.0
        print(f"  {v_label:<28s} {a['pre_tax_cagr']:>6.2%}  {a['after_wht_cagr']:>6.2%}  "
              f"${a['terminal_gross']:>9,.0f}  ${a['us_estate_tax']:>8,.0f}  ${a['terminal_net']:>9,.0f}  "
              f"{a['effective_cagr_after_all_tax']:>7.2%}  ${gap:>+8,.0f}")

    # ── Save raw results for downstream use ────────────────────────────
    out_path = Path(r"C:\Users\ASUS\retirement\output\sector_filter_comparison.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, default=str, indent=2))
    print(f"\nRaw results saved: {out_path}")


if __name__ == "__main__":
    main()

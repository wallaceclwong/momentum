"""
Phase 5A ablation backtest.

Toggles USE_RESIDUAL_MOMENTUM on/off and compares CAGR / Sharpe / MaxDD
over the same historical period. Drift-threshold and enhanced-regime are
live-mode features (they only activate in the IBKR rebalance path / live
regime calls), so they do NOT affect backtest results — the ablation is
just baseline vs residual momentum.

Usage:
    $env:PYTHONPATH = "."
    C:\\Users\\ASUS\\Momentum\\.venv\\Scripts\\python.exe scratch/ablation_phase5a.py
"""
from __future__ import annotations
import json
import logging
import sys
from typing import Dict

# Project root on sys.path
sys.path.insert(0, ".")

# Silence yfinance noise
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
# But keep our backtest progress visible
logging.getLogger("backend.engine.backtest").setLevel(logging.INFO)

# Backtest window — 6.5 years covering multiple regimes:
#   2018 Q4 correction, 2020 COVID crash, 2022 bear, 2023-24 bull/mixed
# Bugs fixed: 400-day download buffer + SPY/sector-ETFs always kept in
# ticker_dfs so residual momentum is active from the first rebalance.
START = "2018-01-01"
END   = "2024-06-30"


def _run(label: str, use_residual: bool) -> Dict:
    """Toggle the residual-momentum flag and run a backtest."""
    # Mutate the config BEFORE importing modules that read it at call time.
    # calculate_momentum_for_tickers reads the flag inside the function body,
    # so a module-level monkey-patch is picked up per-run.
    from backend import config as _cfg
    _cfg.USE_RESIDUAL_MOMENTUM = use_residual

    # Also patch any imports that cached the value (defensive)
    import backend.engine.momentum as _mom
    if hasattr(_mom, "USE_RESIDUAL_MOMENTUM"):
        _mom.USE_RESIDUAL_MOMENTUM = use_residual

    print(f"\n{'=' * 70}")
    print(f"  RUN: {label}   USE_RESIDUAL_MOMENTUM={use_residual}")
    print(f"  {START} → {END}")
    print(f"{'=' * 70}")

    from backend.engine.backtest import run_backtest
    result = run_backtest(START, END)

    m = result.get("metrics", {}) or {}
    summary = {
        "label":       label,
        "residual":    use_residual,
        "final_nav":   result.get("final_nav"),
        "total_ret":   result.get("total_return"),
        "cagr":        m.get("cagr"),
        "sharpe":      m.get("sharpe_ratio") or m.get("sharpe"),
        "max_dd":      m.get("max_drawdown"),
        "volatility":  m.get("volatility"),
        "win_rate":    m.get("win_rate"),
        "n_rebalances": result.get("total_trades"),
    }
    print(f"  Result: {json.dumps(summary, default=str, indent=2)}")
    return summary


def _fmt_pct(v, digits=2):
    if v is None:
        return "  n/a "
    return f"{v*100:+{6+digits}.{digits}f}%"


def _fmt_num(v, digits=2):
    if v is None:
        return "  n/a "
    return f"{v:{6+digits}.{digits}f}"


def main():
    print("\nPhase 5A Ablation — Residual Momentum On vs Off")
    print(f"Period: {START} to {END}\n")

    baseline = _run("BASELINE",  use_residual=False)
    with_res = _run("+RESIDUAL", use_residual=True)

    # ── Comparison table ───────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  PHASE 5A ABLATION RESULTS")
    print("=" * 80)
    print(f"  Period: {START} to {END}\n")
    print(f"  {'Metric':<20} {'Baseline':>14} {'+Residual':>14} {'Delta':>14}")
    print(f"  {'-' * 20} {'-' * 14} {'-' * 14} {'-' * 14}")
    for key, label, fmt in [
        ("cagr",       "CAGR",         _fmt_pct),
        ("sharpe",     "Sharpe",       _fmt_num),
        ("max_dd",     "Max Drawdown", _fmt_pct),
        ("volatility", "Volatility",   _fmt_pct),
        ("total_ret",  "Total Return", _fmt_pct),
        ("win_rate",   "Win Rate",     _fmt_pct),
    ]:
        b = baseline.get(key)
        r = with_res.get(key)
        delta = (r - b) if (b is not None and r is not None) else None
        delta_str = fmt(delta) if delta is not None else "  n/a "
        print(f"  {label:<20} {fmt(b):>14} {fmt(r):>14} {delta_str:>14}")

    print("\n  Note: drift-threshold and enhanced-regime are LIVE-only features.")
    print("  They don't affect backtest results — only residual momentum does.")
    print("=" * 80)


if __name__ == "__main__":
    main()

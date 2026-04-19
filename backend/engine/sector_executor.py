"""
Sector-rotation execution logic.

Pipeline:
  (1) Generate signal     → top-K sectors or cash (Antonacci 12m abs-mom)
  (2) Build target map    → sector → UCITS ticker → target weight
  (3) Compute trades      → list of BUY/SELL intents vs current portfolio
  (4) Persist to DB       → sector_signals + sector_rebalances
  (5) Execute or dry-run  → IBKR adapter called externally

All functions are pure (no IO) except persist_signal() / persist_rebalance()
which write to the momentum_screener SQLite DB.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from backend.config import (
    SECTOR_ROTATION_TOP_K,
    SECTOR_BACKTEST_PROXIES,
    SECTOR_LIVE_UCITS,
    USE_SECTOR_TREND_FILTER,
    SECTOR_TREND_MODE,
    SECTOR_TREND_SMA_DAYS,
    SECTOR_TREND_DUAL_CONFIRMATION,
    USE_SECTOR_ABSOLUTE_MOMENTUM,
    SECTOR_ABS_MOM_THRESHOLD,
)
from backend.engine.sector_rotation import (
    compute_sector_momentum,
    compute_trend_signal,
    select_top_sectors,
)
from backend.ibkr.ucits_contracts import UCITS_CONTRACT_SPECS, TICKER_TO_SPEC

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "momentum_screener.db"
MIN_TRADE_VALUE_USD = 50.0      # skip trivial re-weights below $50
DRIFT_THRESHOLD     = 0.05      # don't rebalance positions within 5% of target


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class SectorSignal:
    """Output of monthly signal generation."""
    as_of:            pd.Timestamp
    signal_date:      pd.Timestamp    # month-end the signal was computed from
    deploy:           bool            # trend filter verdict
    trend_mode:       str
    trend_value:      float           # SPY 12m return, or (spy-sma)/sma
    top_sectors:      List[str]       # sector NAMES (empty if cash)
    ucits_tickers:    List[str]       # corresponding UCITS tickers
    target_weights:   Dict[str, float]  # ticker → weight (0..1)
    momentum_scores:  Dict[str, float]  # sector_name → 12-1 momentum
    all_ranked:       List[Tuple[str, float]]  # [(sector, mom), ...] desc

    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "as_of":       self.as_of.isoformat() if self.as_of is not None else None,
            "signal_date": self.signal_date.isoformat() if self.signal_date is not None else None,
        }


@dataclass
class Trade:
    action:          str          # "BUY" | "SELL"
    ticker:          str
    sector:          str
    target_shares:   float
    current_shares:  float
    delta_shares:    float
    est_price:       float
    est_value_usd:   float
    reason:          str


@dataclass
class RebalancePlan:
    as_of:            pd.Timestamp
    signal:           SectorSignal
    portfolio_nav:    float
    current_positions: Dict[str, Dict]      # ticker → {shares, price, value}
    trades:           List[Trade]
    total_buy_value:  float
    total_sell_value: float
    estimated_cost:   float


# ---------------------------------------------------------------------------
# (1) Signal generation
# ---------------------------------------------------------------------------
def generate_signal(
    daily_prices: pd.DataFrame,
    as_of: Optional[pd.Timestamp] = None,
    top_k: int = SECTOR_ROTATION_TOP_K,
    proxy_to_sector: Optional[Dict[str, str]] = None,
) -> SectorSignal:
    """
    Full monthly signal: trend filter + top-K momentum selection.

    Args:
        daily_prices:  wide DataFrame with sector proxy tickers + SPY
        as_of:         evaluation date; default = last row of daily_prices
        top_k:         number of sectors to hold
        proxy_to_sector: override mapping; default derived from config

    Returns SectorSignal with everything downstream code needs.
    """
    if as_of is None:
        as_of = daily_prices.index[-1]
    as_of = pd.Timestamp(as_of)

    proxy_to_sector = proxy_to_sector or {v: k for k, v in SECTOR_BACKTEST_PROXIES.items()}
    proxy_tickers = list(SECTOR_BACKTEST_PROXIES.values())

    # ── Trend filter (Antonacci 12m by default) ────────────────────────────
    spy_monthly = daily_prices["SPY"].resample("ME").last()
    trend_val = 1.0
    trend_value_num = 0.0
    if USE_SECTOR_TREND_FILTER:
        trend_val = compute_trend_signal(
            daily_prices["SPY"], as_of,
            mode=SECTOR_TREND_MODE,
            sma_days=SECTOR_TREND_SMA_DAYS,
            dual_confirmation=SECTOR_TREND_DUAL_CONFIRMATION,
            monthly_history=spy_monthly,
        )
        # Also compute raw metric for logging
        if SECTOR_TREND_MODE == "abs_mom_12m":
            m = spy_monthly.loc[:as_of].dropna()
            if len(m) >= 13:
                trend_value_num = float(m.iloc[-1] / m.iloc[-13] - 1)
        else:
            d = daily_prices["SPY"].loc[:as_of].dropna()
            if len(d) >= SECTOR_TREND_SMA_DAYS:
                sma = float(d.iloc[-SECTOR_TREND_SMA_DAYS:].mean())
                trend_value_num = float(d.iloc[-1] / sma - 1)

    deploy = trend_val == 1.0

    # ── Sector momentum ranking ────────────────────────────────────────────
    monthly = daily_prices[proxy_tickers].resample("ME").last()
    signal_date = monthly.index[monthly.index <= as_of][-1]
    mom = compute_sector_momentum(monthly, signal_date)
    if mom is None:
        raise RuntimeError(f"Insufficient history for momentum signal at {as_of}")

    all_ranked = sorted(
        [(proxy_to_sector[t], float(v)) for t, v in mom.items()],
        key=lambda x: -x[1],
    )

    # Apply selection
    if not deploy:
        top_sectors: List[str] = []
    else:
        top_proxy = select_top_sectors(
            mom, top_k=top_k,
            absolute_threshold=SECTOR_ABS_MOM_THRESHOLD if USE_SECTOR_ABSOLUTE_MOMENTUM else None,
        )
        top_sectors = [proxy_to_sector[t] for t in top_proxy]

    ucits_tickers = [SECTOR_LIVE_UCITS[s] for s in top_sectors]
    n = len(top_sectors)
    w = (1.0 / n) if n > 0 else 0.0
    target_weights = {SECTOR_LIVE_UCITS[s]: w for s in top_sectors}

    return SectorSignal(
        as_of=as_of,
        signal_date=signal_date,
        deploy=deploy,
        trend_mode=SECTOR_TREND_MODE,
        trend_value=trend_value_num,
        top_sectors=top_sectors,
        ucits_tickers=ucits_tickers,
        target_weights=target_weights,
        momentum_scores={k: v for k, v in all_ranked},
        all_ranked=all_ranked,
    )


# ---------------------------------------------------------------------------
# (3) Trade computation
# ---------------------------------------------------------------------------
def compute_trades(
    signal: SectorSignal,
    current_positions: Dict[str, Dict],
    portfolio_nav: float,
    price_lookup: Dict[str, float],
    min_trade_value: float = MIN_TRADE_VALUE_USD,
    drift_threshold: float = DRIFT_THRESHOLD,
) -> RebalancePlan:
    """
    Compute the list of trades to move current_positions → target_weights.

    Args:
        signal:            output of generate_signal()
        current_positions: {ticker: {"shares": float, "price": float, "value": float}}
        portfolio_nav:     current portfolio USD value (positions + cash)
        price_lookup:      latest price per UCITS ticker (for new positions)
        min_trade_value:   skip trades smaller than this (USD)
        drift_threshold:   skip re-weights where drift < threshold (fraction)

    Returns RebalancePlan.
    """
    trades: List[Trade] = []
    total_buy  = 0.0
    total_sell = 0.0

    target = dict(signal.target_weights)  # ticker → weight

    # Build ticker → sector reverse map (for labelling)
    ticker_to_sector = {
        spec["symbol"]: sector for sector, spec in UCITS_CONTRACT_SPECS.items()
    }

    # ── 1. Full-exit positions no longer in target ─────────────────────────
    for ticker, pos in current_positions.items():
        if ticker not in target:
            shares = pos.get("shares", 0)
            price  = pos.get("price", price_lookup.get(ticker, 0))
            value  = shares * price
            if abs(value) < min_trade_value:
                continue
            trades.append(Trade(
                action="SELL",
                ticker=ticker,
                sector=ticker_to_sector.get(ticker, "UNKNOWN"),
                target_shares=0.0,
                current_shares=shares,
                delta_shares=-shares,
                est_price=price,
                est_value_usd=value,
                reason="Not in new target (rotated out)",
            ))
            total_sell += value

    # ── 2. Open or resize positions in target ──────────────────────────────
    for ticker, weight in target.items():
        target_val   = portfolio_nav * weight
        price        = price_lookup.get(ticker) or current_positions.get(ticker, {}).get("price", 0)
        if price <= 0:
            logger.warning(f"[TRADES] no price for {ticker}, skipping")
            continue
        target_shares = target_val / price

        cur = current_positions.get(ticker, {})
        cur_shares = cur.get("shares", 0)
        cur_value  = cur_shares * price
        delta_val  = target_val - cur_value

        if abs(delta_val) < min_trade_value:
            continue

        # Drift threshold (only for existing positions; new positions always trade)
        if cur_value > 0 and target_val > 0:
            drift = abs(delta_val) / target_val
            if drift < drift_threshold:
                continue

        delta_shares = target_shares - cur_shares
        action = "BUY" if delta_shares > 0 else "SELL"
        trades.append(Trade(
            action=action,
            ticker=ticker,
            sector=ticker_to_sector.get(ticker, "UNKNOWN"),
            target_shares=round(target_shares, 4),
            current_shares=cur_shares,
            delta_shares=round(delta_shares, 4),
            est_price=price,
            est_value_usd=round(abs(delta_val), 2),
            reason=("New position" if cur_shares == 0 else
                    "Rebalance underweight" if delta_shares > 0 else
                    "Rebalance overweight"),
        ))
        if action == "BUY":
            total_buy += abs(delta_val)
        else:
            total_sell += abs(delta_val)

    # ── 3. Cost estimate (1 bps slippage + ~$5 IBKR LSE commission per trade) ──
    cost_est = (total_buy + total_sell) * 0.0001 + 5.0 * len(trades)

    return RebalancePlan(
        as_of=signal.as_of,
        signal=signal,
        portfolio_nav=portfolio_nav,
        current_positions=current_positions,
        trades=trades,
        total_buy_value=round(total_buy, 2),
        total_sell_value=round(total_sell, 2),
        estimated_cost=round(cost_est, 2),
    )


# ---------------------------------------------------------------------------
# (4) DB persistence
# ---------------------------------------------------------------------------
DDL_SECTOR_SIGNALS = """
CREATE TABLE IF NOT EXISTS sector_signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    as_of           TEXT    NOT NULL,
    signal_date     TEXT    NOT NULL,
    deploy          INTEGER NOT NULL,
    trend_mode      TEXT    NOT NULL,
    trend_value     REAL,
    top_sectors     TEXT    NOT NULL,     -- JSON list of sector names
    ucits_tickers   TEXT    NOT NULL,     -- JSON list of UCITS tickers
    target_weights  TEXT    NOT NULL,     -- JSON {ticker: weight}
    momentum_scores TEXT    NOT NULL,     -- JSON {sector: momentum}
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

DDL_SECTOR_REBALANCES = """
CREATE TABLE IF NOT EXISTS sector_rebalances (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    as_of              TEXT    NOT NULL,
    signal_id          INTEGER,
    mode               TEXT    NOT NULL,  -- "paper" | "live" | "dry_run"
    portfolio_nav      REAL    NOT NULL,
    n_trades           INTEGER NOT NULL,
    total_buy_value    REAL    NOT NULL,
    total_sell_value   REAL    NOT NULL,
    estimated_cost     REAL    NOT NULL,
    trades_json        TEXT    NOT NULL,  -- serialized trade list
    fills_json         TEXT,                -- actual fills (for live)
    status             TEXT    NOT NULL,  -- "planned" | "executed" | "failed"
    error_message      TEXT,
    created_at         TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (signal_id) REFERENCES sector_signals(id)
)
"""


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(DDL_SECTOR_SIGNALS)
    conn.execute(DDL_SECTOR_REBALANCES)
    conn.commit()
    return conn


def persist_signal(signal: SectorSignal) -> int:
    """Save signal to DB, return row id."""
    conn = _get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO sector_signals
               (as_of, signal_date, deploy, trend_mode, trend_value,
                top_sectors, ucits_tickers, target_weights, momentum_scores)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                signal.as_of.isoformat(),
                signal.signal_date.isoformat(),
                1 if signal.deploy else 0,
                signal.trend_mode,
                signal.trend_value,
                json.dumps(signal.top_sectors),
                json.dumps(signal.ucits_tickers),
                json.dumps(signal.target_weights),
                json.dumps(signal.momentum_scores),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def persist_rebalance(
    plan: RebalancePlan,
    mode: str,
    signal_id: Optional[int] = None,
    fills: Optional[List[Dict]] = None,
    status: str = "planned",
    error: Optional[str] = None,
) -> int:
    """Save rebalance plan to DB, return row id."""
    conn = _get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO sector_rebalances
               (as_of, signal_id, mode, portfolio_nav, n_trades,
                total_buy_value, total_sell_value, estimated_cost,
                trades_json, fills_json, status, error_message)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                plan.as_of.isoformat(),
                signal_id,
                mode,
                plan.portfolio_nav,
                len(plan.trades),
                plan.total_buy_value,
                plan.total_sell_value,
                plan.estimated_cost,
                json.dumps([asdict(t) for t in plan.trades]),
                json.dumps(fills) if fills is not None else None,
                status,
                error,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_last_paper_positions() -> Dict[str, Dict]:
    """
    Reconstruct current paper positions by REPLAYING all paper rebalances
    chronologically.

    Why replay (not just use latest row): when a rebalance is idempotent
    (0 trades), it stores an empty trades_json, which would look like
    "no positions" if we only read the latest row.  The true state is
    whatever the last NON-trivial run produced, carried forward.

    Each Trade's `target_shares` is the ABSOLUTE post-trade state for that
    ticker (not a delta) — so replay is straightforward:
      - Any trade with target_shares > 0 → set position to target_shares
      - Any trade with target_shares == 0 (full exit) → remove position
      - Tickers NOT in a run → unchanged from prior run
    """
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT trades_json FROM sector_rebalances
               WHERE mode='paper' AND status='executed'
               ORDER BY id ASC"""
        ).fetchall()
    finally:
        conn.close()

    positions: Dict[str, Dict] = {}
    for (trades_json,) in rows:
        trades = json.loads(trades_json or "[]")
        for t in trades:
            tk = t["ticker"]
            target = float(t.get("target_shares", 0))
            price  = float(t.get("est_price", 0))
            if target <= 1e-6:
                # Full exit
                positions.pop(tk, None)
            else:
                positions[tk] = {
                    "shares": target,
                    "price":  price,
                    "value":  target * price,
                }
    return positions

"""Unit tests for sector_executor trade computation logic."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest

from backend.engine.sector_executor import (
    SectorSignal, compute_trades, Trade,
)


@pytest.fixture
def simple_signal():
    """Signal: deploy, top-3 sectors IUIS/IUIT/IUMS at 33.3% each."""
    return SectorSignal(
        as_of=pd.Timestamp("2026-04-30"),
        signal_date=pd.Timestamp("2026-03-31"),
        deploy=True,
        trend_mode="abs_mom_12m",
        trend_value=0.15,
        top_sectors=["Industrials", "Information Technology", "Materials"],
        ucits_tickers=["IUIS", "IUIT", "IUMS"],
        target_weights={"IUIS": 1/3, "IUIT": 1/3, "IUMS": 1/3},
        momentum_scores={"Industrials": 0.366, "Information Technology": 0.35,
                         "Materials": 0.261},
        all_ranked=[],
    )


@pytest.fixture
def cash_signal():
    """Signal: trend filter says cash."""
    return SectorSignal(
        as_of=pd.Timestamp("2009-01-30"),
        signal_date=pd.Timestamp("2008-12-31"),
        deploy=False,
        trend_mode="abs_mom_12m",
        trend_value=-0.35,
        top_sectors=[],
        ucits_tickers=[],
        target_weights={},
        momentum_scores={},
        all_ranked=[],
    )


def test_empty_portfolio_deploy(simple_signal):
    """Starting from cash: should generate 3 buys."""
    plan = compute_trades(
        simple_signal,
        current_positions={},
        portfolio_nav=330_000,
        price_lookup={"IUIS": 50.0, "IUIT": 100.0, "IUMS": 40.0},
    )
    assert len(plan.trades) == 3
    assert all(t.action == "BUY" for t in plan.trades)
    # Each should be ~$110K (33% of $330K)
    for t in plan.trades:
        assert 100_000 < t.est_value_usd < 120_000


def test_same_target_no_trades(simple_signal):
    """Current matches target within drift: no trades."""
    nav = 300_000
    # Build positions exactly at target
    positions = {
        "IUIS": {"shares": 100_000 / 50.0, "price": 50.0, "value": 100_000},
        "IUIT": {"shares": 100_000 / 100.0, "price": 100.0, "value": 100_000},
        "IUMS": {"shares": 100_000 / 40.0, "price": 40.0, "value": 100_000},
    }
    plan = compute_trades(
        simple_signal, positions, portfolio_nav=nav,
        price_lookup={"IUIS": 50.0, "IUIT": 100.0, "IUMS": 40.0},
    )
    assert len(plan.trades) == 0


def test_cash_signal_closes_all(simple_signal, cash_signal):
    """Trend flipped to cash: close all existing positions."""
    positions = {
        "IUIS": {"shares": 2000, "price": 50.0, "value": 100_000},
        "IUIT": {"shares": 1000, "price": 100.0, "value": 100_000},
    }
    plan = compute_trades(
        cash_signal, positions, portfolio_nav=200_000,
        price_lookup={"IUIS": 50.0, "IUIT": 100.0},
    )
    assert all(t.action == "SELL" for t in plan.trades)
    assert len(plan.trades) == 2
    assert plan.total_sell_value == pytest.approx(200_000)
    assert plan.total_buy_value == 0


def test_sector_rotation_one_swap(simple_signal):
    """
    Old top-3 = IUIS/IUIT/IUFS. New top-3 = IUIS/IUIT/IUMS.
    Should: sell IUFS, buy IUMS, keep IUIS/IUIT (within drift).
    """
    positions = {
        "IUIS": {"shares": 2200, "price": 50.0, "value": 110_000},
        "IUIT": {"shares": 1100, "price": 100.0, "value": 110_000},
        "IUFS": {"shares": 500,  "price": 220.0, "value": 110_000},
    }
    plan = compute_trades(
        simple_signal, positions, portfolio_nav=330_000,
        price_lookup={"IUIS": 50.0, "IUIT": 100.0, "IUMS": 40.0, "IUFS": 220.0},
    )
    actions = {(t.ticker, t.action) for t in plan.trades}
    assert ("IUFS", "SELL") in actions
    assert ("IUMS", "BUY") in actions


def test_drift_threshold_skips_small_moves(simple_signal):
    """Drift < 5% should be skipped."""
    # Slightly off target but under drift threshold
    nav = 330_000
    positions = {
        # 112K vs 110K target = 1.8% drift, < 5% threshold
        "IUIS": {"shares": 112_000 / 50.0, "price": 50.0, "value": 112_000},
        # 108K vs 110K = 1.8% drift
        "IUIT": {"shares": 108_000 / 100.0, "price": 100.0, "value": 108_000},
        # 110K exact
        "IUMS": {"shares": 110_000 / 40.0, "price": 40.0, "value": 110_000},
    }
    plan = compute_trades(
        simple_signal, positions, portfolio_nav=nav,
        price_lookup={"IUIS": 50.0, "IUIT": 100.0, "IUMS": 40.0},
    )
    assert len(plan.trades) == 0


def test_cost_estimate_positive(simple_signal):
    plan = compute_trades(
        simple_signal, {}, portfolio_nav=330_000,
        price_lookup={"IUIS": 50.0, "IUIT": 100.0, "IUMS": 40.0},
    )
    assert plan.estimated_cost > 0
    # For 3 trades ~$110K each: slippage 0.0001 × $330K + 3 × $5 = $48
    assert 30 < plan.estimated_cost < 100


def test_position_replay_survives_idempotent_runs(tmp_path, monkeypatch):
    """
    Regression for position-reconstruction bug:
    After a full-entry run (3 BUYs), subsequent idempotent runs (0 trades)
    must not cause next non-trivial run to re-buy everything.
    """
    from backend.engine import sector_executor as se
    # Point DB at a tmp file
    tmp_db = tmp_path / "test_positions.db"
    monkeypatch.setattr(se, "DB_PATH", tmp_db)

    # Fabricate sequence: id=1 has 3 BUYs with target_shares; id=2 has 0 trades (empty)
    buy_trades = [
        {"action": "BUY", "ticker": "IUIS", "sector": "Industrials",
         "target_shares": 634.0, "current_shares": 0.0, "delta_shares": 634.0,
         "est_price": 173.51, "est_value_usd": 110000, "reason": "New position"},
        {"action": "BUY", "ticker": "IUIT", "sector": "Information Technology",
         "target_shares": 713.0, "current_shares": 0.0, "delta_shares": 713.0,
         "est_price": 154.35, "est_value_usd": 110000, "reason": "New position"},
        {"action": "BUY", "ticker": "IUMS", "sector": "Materials",
         "target_shares": 2120.0, "current_shares": 0.0, "delta_shares": 2120.0,
         "est_price": 51.88, "est_value_usd": 110000, "reason": "New position"},
    ]

    # Directly insert into DB simulating past runs
    import json, sqlite3
    conn = sqlite3.connect(str(tmp_db))
    conn.execute(se.DDL_SECTOR_SIGNALS); conn.execute(se.DDL_SECTOR_REBALANCES); conn.commit()
    conn.execute(
        "INSERT INTO sector_rebalances (as_of, mode, portfolio_nav, n_trades, "
        "total_buy_value, total_sell_value, estimated_cost, trades_json, status) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("2026-03-27", "paper", 330000, 3, 330000, 0, 48.0,
         json.dumps(buy_trades), "executed"),
    )
    # Idempotent run: empty trades
    conn.execute(
        "INSERT INTO sector_rebalances (as_of, mode, portfolio_nav, n_trades, "
        "total_buy_value, total_sell_value, estimated_cost, trades_json, status) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("2026-04-24", "paper", 330000, 0, 0, 0, 0, json.dumps([]), "executed"),
    )
    conn.commit(); conn.close()

    # Replay should yield all 3 positions, NOT empty
    positions = se.get_last_paper_positions()
    assert set(positions.keys()) == {"IUIS", "IUIT", "IUMS"}, \
        f"expected 3 positions after replay, got {list(positions.keys())}"
    assert positions["IUIS"]["shares"] == 634.0
    assert positions["IUIT"]["shares"] == 713.0
    assert positions["IUMS"]["shares"] == 2120.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

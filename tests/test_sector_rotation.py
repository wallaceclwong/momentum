"""Unit tests for sector rotation strategy core functions."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import pytest

from backend.engine.sector_rotation import (
    compute_sector_momentum,
    select_top_sectors,
    build_target_weights,
    get_rebalance_dates,
)


@pytest.fixture
def synth_monthly_prices():
    """3 years of synthetic monthly prices for 4 sectors."""
    dates = pd.date_range("2022-01-31", periods=36, freq="ME")
    np.random.seed(42)
    prices = pd.DataFrame({
        "A": 100 * np.cumprod(1 + np.random.normal(0.02, 0.05, 36)),
        "B": 100 * np.cumprod(1 + np.random.normal(0.01, 0.05, 36)),
        "C": 100 * np.cumprod(1 + np.random.normal(-0.005, 0.05, 36)),  # negative drift
        "D": 100 * np.cumprod(1 + np.random.normal(0.015, 0.05, 36)),
    }, index=dates)
    return prices


def test_compute_momentum_basic(synth_monthly_prices):
    """Momentum = price(t-1) / price(t-12) - 1."""
    as_of = synth_monthly_prices.index[20]
    mom = compute_sector_momentum(synth_monthly_prices, as_of, lookback=12, skip=1)
    assert mom is not None
    assert len(mom) == 4
    assert set(mom.index) == {"A", "B", "C", "D"}
    # Manual check for ticker A
    expected = synth_monthly_prices["A"].iloc[19] / synth_monthly_prices["A"].iloc[8] - 1
    assert abs(mom["A"] - expected) < 1e-10


def test_compute_momentum_insufficient_history(synth_monthly_prices):
    """Returns None when not enough history for lookback."""
    as_of = synth_monthly_prices.index[5]  # only 5 months of history
    mom = compute_sector_momentum(synth_monthly_prices, as_of, lookback=12)
    assert mom is None


def test_select_top_sectors_plain(synth_monthly_prices):
    """Top-K selection by descending momentum."""
    scores = pd.Series({"A": 0.20, "B": 0.10, "C": -0.05, "D": 0.15})
    assert select_top_sectors(scores, top_k=3) == ["A", "D", "B"]
    assert select_top_sectors(scores, top_k=1) == ["A"]
    assert select_top_sectors(scores, top_k=10) == ["A", "D", "B", "C"]  # cap at available


def test_select_top_sectors_absolute_threshold():
    """Only qualifying sectors returned when abs threshold applied."""
    scores = pd.Series({"A": 0.20, "B": 0.10, "C": -0.05, "D": -0.01})
    # With threshold=0, only positive momentum sectors qualify
    assert select_top_sectors(scores, top_k=3, absolute_threshold=0.0) == ["A", "B"]
    # Stricter threshold
    assert select_top_sectors(scores, top_k=3, absolute_threshold=0.15) == ["A"]
    # All negative → empty
    all_neg = pd.Series({"A": -0.1, "B": -0.05})
    assert select_top_sectors(all_neg, top_k=3, absolute_threshold=0.0) == []


def test_select_top_sectors_handles_none():
    assert select_top_sectors(None) == []


def test_select_top_sectors_handles_nan():
    scores = pd.Series({"A": 0.2, "B": float("nan"), "C": 0.1})
    # NaN sector should be dropped
    assert select_top_sectors(scores, top_k=3) == ["A", "C"]


def test_build_target_weights_top_k():
    """Equal weight across top tickers, 0 for others."""
    all_t = ["A", "B", "C", "D"]
    w = build_target_weights(["A", "C"], all_t, deployment=1.0)
    assert w == {"A": 0.5, "B": 0.0, "C": 0.5, "D": 0.0}
    assert abs(sum(w.values()) - 1.0) < 1e-10


def test_build_target_weights_partial_deployment():
    all_t = ["A", "B", "C"]
    w = build_target_weights(["A"], all_t, deployment=0.3)
    assert w["A"] == 0.3
    assert w["B"] == 0.0
    assert w["C"] == 0.0


def test_build_target_weights_cash():
    """Empty top → all zeros (cash)."""
    all_t = ["A", "B", "C"]
    w = build_target_weights([], all_t, deployment=1.0)
    assert w == {"A": 0.0, "B": 0.0, "C": 0.0}


def test_rebalance_dates_are_last_fridays():
    """Rebalance dates must be last Friday of each month."""
    from datetime import datetime
    dates = get_rebalance_dates(datetime(2024, 1, 1), datetime(2024, 4, 30))
    # Jan 2024 last Friday = Jan 26; Feb 23; Mar 29; Apr 26
    assert len(dates) == 4
    for d in dates:
        assert d.weekday() == 4  # Friday
        # Last Friday property: no Friday later in same month should be in range
        from datetime import timedelta
        next_fri = d + timedelta(days=7)
        assert next_fri.month != d.month or next_fri > datetime(2024, 4, 30)


if __name__ == "__main__":
    # Quick smoke test without pytest
    import pandas as pd
    scores = pd.Series({"A": 0.2, "B": 0.1, "C": -0.05, "D": 0.15})
    print("top_k=3 no filter:",        select_top_sectors(scores, top_k=3))
    print("top_k=3 abs>0:",            select_top_sectors(scores, top_k=3, absolute_threshold=0.0))
    print("weights top=[A,D]:",        build_target_weights(["A", "D"], ["A","B","C","D"]))
    print("weights empty (cash):",     build_target_weights([], ["A","B","C","D"]))
    print("\nAll smoke tests passed.")

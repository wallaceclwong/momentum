"""Engine modules for S&P 500 momentum screener."""
from .momentum import (
    calculate_returns,
    calculate_composite_score,
    calculate_momentum_for_tickers,
    rank_by_momentum,
)
from .earnings_filter import (
    filter_by_earnings_momentum,
    get_earnings_summary,
)
from .screener import (
    run_momentum_screener,
    get_screener_summary,
)
from .portfolio import (
    get_sector_etf_weights,
    allocate_portfolio,
    get_portfolio_summary,
)

__all__ = [
    # momentum
    "calculate_returns",
    "calculate_composite_score",
    "calculate_momentum_for_tickers",
    "rank_by_momentum",
    # earnings_filter
    "filter_by_earnings_momentum",
    "get_earnings_summary",
    # screener
    "run_momentum_screener",
    "get_screener_summary",
    # portfolio
    "get_sector_etf_weights",
    "allocate_portfolio",
    "get_portfolio_summary",
]

"""
Configuration constants for S&P 500 Momentum Screener
"""

# 11 SPDR Sector ETFs mapped to GICS sector names
SECTORS = {
    "XLK": "Information Technology",
    "XLC": "Communication Services",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLE": "Energy",
    "XLF": "Financials",
    "XLV": "Health Care",
    "XLI": "Industrials",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLU": "Utilities",
}

# Reverse mapping: sector name -> ETF ticker
SECTOR_TO_ETF = {v: k for k, v in SECTORS.items()}

# Momentum calculation windows (trading days)
MOMENTUM_WINDOWS = {
    "4W": 20,   # ~1 month
    "13W": 65,  # ~3 months
    "26W": 130, # ~6 months
}

# Number of top stocks to select per sector
TOP_N_PER_SECTOR = 3

# Number of recent earnings to look back
EARNINGS_LOOKBACK = 2

# Yahoo Finance data fetch parameters
YFINANCE_PERIOD = "1y"  # Fetch 1 year of history to cover all windows
YFINANCE_INTERVAL = "1d"  # Daily data

# Momentum score weights — longer lookback weighted more, plus 52W high proximity
# TREND_QUALITY is R² of log-price vs time: rewards smooth uptrends over volatile spikes
MOMENTUM_WEIGHTS = {
    "4W":           0.5,
    "13W":          1.0,
    "26W":          1.5,
    "52W_HIGH":     1.0,
    "TREND_QUALITY": 1.0,
}

# Skip last month to avoid short-term reversal (standard in academic literature)
SKIP_LAST_MONTH = True
SKIP_DAYS = 21

# Normalize each momentum window score across the full universe before combining.
# This prevents high-momentum bull-market periods from dominating — focuses on
# relative strength vs peers rather than absolute return levels.
USE_CROSS_SECTIONAL_ZSCORE = True

# Volatility-weighted position sizing within each sector
USE_VOLATILITY_WEIGHTING = True
VOL_LOOKBACK_DAYS = 20

# Quality filters — exclude illiquid / penny stocks
MIN_STOCK_PRICE = 5.0        # must be above $5 to qualify
MIN_HISTORY_DAYS = 252       # at least 1 year of price history

# Maximum allocation to any single position (concentration cap)
# Prevents over-weighting a single name regardless of sector weight
MAX_POSITION_WEIGHT = 0.05   # 5% max per stock

# Market regime filter: reduce exposure when SPY < 200-day MA
USE_REGIME_FILTER = True
REGIME_MA_DAYS = 200
REGIME_BEAR_DEPLOYMENT = 0.3   # 30% in bear (was 50% — more defensive)

# Drawdown circuit breaker: skip rebalance if portfolio down >15% from peak
CIRCUIT_BREAKER_THRESHOLD = 0.85

# Backtest transaction costs (realistic estimates for US equities)
BACKTEST_SLIPPAGE = 0.0005           # 5bps per side (institutional estimate)
BACKTEST_COMMISSION_PER_SHARE = 0.005

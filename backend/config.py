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
    "4W":             0.5,
    "13W":            1.0,
    "26W":            1.5,
    "52W_HIGH":       1.0,
    "TREND_QUALITY":  1.0,
    "EARNINGS_SCORE": 0.75,  # L1 EPS surprise %, capped ±30 — only used in live screener
}

# Whether to fetch and include earnings surprise in live screener runs.
# Disabled automatically in backtests (no historical EPS data available).
USE_EARNINGS_IN_SCREENER = True

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
MIN_STOCK_PRICE = 5.0          # must be above $5 to qualify
MIN_HISTORY_DAYS = 252         # at least 1 year of price history
MIN_ADV_USD = 1_000_000        # minimum 20-day avg daily dollar volume ($1M)

# Maximum allocation to any single position (concentration cap)
# Prevents over-weighting a single name regardless of sector weight
MAX_POSITION_WEIGHT = 0.05   # 5% max per stock

# Market regime filter — graduated 5-state model using SPY MAs + VIX
USE_REGIME_FILTER = True
REGIME_MA_DAYS   = 200          # long-term trend
REGIME_MA_SHORT  = 50           # short-term trend
REGIME_VIX_HIGH  = 20           # elevated fear
REGIME_VIX_EXTREME = 30         # crisis fear
# Deployment by regime state (fraction of capital to deploy)
REGIME_STRONG_BULL   = 1.00     # SPY > MA50 > MA200, VIX < 20
REGIME_BULL          = 0.80     # SPY > MA200, VIX < 25
REGIME_VOLATILE_BULL = 0.50     # SPY > MA200 but VIX elevated
REGIME_BEAR          = 0.30     # SPY < MA200, VIX < 30
REGIME_CRISIS        = 0.15     # SPY < MA200 + VIX >= 30
REGIME_BEAR_DEPLOYMENT = 0.30   # kept for backward compat

# Risk-parity sector weighting: weight each sector inversely to its 60-day volatility
# True = risk parity  |  False = market-cap ETF weights (legacy)
USE_RISK_PARITY_SECTORS = True
RISK_PARITY_VOL_DAYS = 60       # lookback for sector ETF volatility

# Individual position stop-loss: exit any holding down more than threshold from entry
USE_STOP_LOSS   = True
STOP_LOSS_PCT   = 0.15          # 15% loss from entry triggers exit

# Momentum crash protection (Barroso & Santa-Clara 2015)
# Scales ALL position sizes by min(1, TARGET_VOL / realised_portfolio_vol)
# Protects against rapid momentum reversals (2009, 2020) without needing a VIX signal
USE_CRASH_PROTECTION          = True
CRASH_PROTECTION_TARGET_VOL   = 0.15   # annualised vol target (15%)
CRASH_PROTECTION_LOOKBACK     = 21     # trading days (~1 month) for vol estimation

# Tax-aware rebalancing (backtest + live)
# Keeps a current holding when: held < 1yr AND has an unrealised gain AND
# the best replacement candidate doesn't beat its score by TAX_SCORE_THRESHOLD.
# Defers short-term capital gains tax realisation at the cost of slight stale picks.
USE_TAX_AWARE_REBALANCING = False  # HK has no CGT — monthly rotation is optimal
TAX_SHORT_TERM_RATE       = 0.37   # US top bracket short-term rate
TAX_LONG_TERM_RATE        = 0.20   # US long-term rate
TAX_MIN_HOLDING_DAYS      = 365    # days needed for long-term treatment
TAX_SCORE_THRESHOLD       = 0.30   # new pick must beat current by this z-score margin

# Drawdown circuit breaker: skip rebalance if portfolio down >15% from peak
CIRCUIT_BREAKER_THRESHOLD = 0.85

# Backtest transaction costs (realistic estimates for US equities)
BACKTEST_SLIPPAGE = 0.0005           # 5bps per side (institutional estimate)
BACKTEST_COMMISSION_PER_SHARE = 0.005

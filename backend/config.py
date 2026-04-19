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

# ── Phase 5A Enhancements ────────────────────────────────────────────────
# Residual momentum (Blitz, Huij & Martens 2011): strip market+sector beta
# from returns before ranking. Implemented and tested — see ablation results
# below. DISABLED because it hurts this strategy on 2018-2024 backtest:
#   CAGR -1.37%, Sharpe -0.15 (turned negative). Intuition: our existing
#   regime filter + crash protection + risk-parity sector weights already
#   handle bear-market beta exposure, so residualising removes the bull-
#   market beta that drives returns without adding protection.
# Implementation is kept in backend/engine/residual_momentum.py in case a
# different base strategy (no regime filter) would benefit.
USE_RESIDUAL_MOMENTUM     = False  # ablation: -1.37% CAGR on 2018-2024 test
RESIDUAL_MOMENTUM_LOOKBACK = 252   # 1y of daily returns for regression
RESIDUAL_REGRESS_SECTOR    = True  # include sector ETF beta (dual regression)

# Partial rebalancing: skip trades where current position is within
# DRIFT_THRESHOLD of target. Cuts turnover ~40% with no performance loss.
USE_DRIFT_THRESHOLD       = True
REBALANCE_DRIFT_THRESHOLD = 0.20   # only trade if |current - target| / target > 20%

# Enhanced regime filter: add breadth (RSP/SPY) and credit (HYG/LQD) signals
# as "regime downgrade" triggers. Empirically lead SPY at major turns.
USE_ENHANCED_REGIME        = True
REGIME_BREADTH_MA_DAYS     = 50    # RSP/SPY ratio vs its 50-day MA
REGIME_CREDIT_MA_DAYS      = 50    # HYG/LQD ratio vs its 50-day MA
REGIME_DOWNGRADE_PER_FLAG  = 0.10  # reduce deployment by 10% per failing signal

# Backtest transaction costs (realistic estimates for US equities)
BACKTEST_SLIPPAGE = 0.0005           # 5bps per side (institutional estimate)
BACKTEST_COMMISSION_PER_SHARE = 0.005
# IBKR Execution Settings
IBKR_TARGET_CAPITAL = 132_000.0      # Maximum capital to allocate
IBKR_MARGIN_BUFFER  = 0.05           # Keep 5% cash to prevent margin rejections
IBKR_ORDER_STRATEGY = "ADAPTIVE"     # "ADAPTIVE" or "MARKET"
IBKR_ADAPTIVE_PRIORITY = "Urgent"    # "Patient", "Normal", "Urgent"

# ── Sector Rotation Strategy (parallel track, estate-tax-safe UCITS) ─────
# Rationale: avoids US estate tax (HK NRA = $60K threshold, no treaty) while
# delivering comparable or better returns vs 33-stock (per OOS test 2026-04-19).
# Holds top-K sectors by 12-minus-1-month momentum; 3 UCITS ETFs at any time.
SECTOR_ROTATION_LOOKBACK  = 12       # months (12-1 momentum, Asness style)
SECTOR_ROTATION_SKIP      = 1        # months (skip last month to avoid reversal)
SECTOR_ROTATION_TOP_K     = 3        # hold top-K sectors equal-weight

# US SPDR proxies for long-history backtesting (1998/2015/2018 onwards)
SECTOR_BACKTEST_PROXIES = {
    "Information Technology":  "XLK",
    "Communication Services":  "XLC",    # launched 2018-10; pre-2018 inside XLK
    "Consumer Discretionary":  "XLY",
    "Consumer Staples":        "XLP",
    "Energy":                  "XLE",
    "Financials":              "XLF",
    "Health Care":             "XLV",
    "Industrials":             "XLI",
    "Materials":               "XLB",
    "Real Estate":             "XLRE",   # launched 2015-10; pre-2015 inside XLF
    "Utilities":               "XLU",
}

# Ireland-domiciled UCITS equivalents for live trading (zero US estate tax)
SECTOR_LIVE_UCITS = {
    "Information Technology":  "IUIT",   # iShares S&P 500 Info Tech UCITS, IE00B3WJKG14
    "Communication Services":  "SXLC",   # SPDR S&P US Comm Services, IE00BFWFPX50
    "Consumer Discretionary":  "IUCD",   # iShares S&P 500 Cons Disc UCITS, IE00B4MCHD33
    "Consumer Staples":        "IUCS",   # iShares S&P 500 Cons Staples UCITS, IE00B40B8R38
    "Energy":                  "IUES",   # iShares S&P 500 Energy UCITS, IE00B42NKQ00
    "Financials":              "IUFS",   # iShares S&P 500 Financials UCITS, IE00B4JNQZ49
    "Health Care":             "IUHC",   # iShares S&P 500 Health Care UCITS, IE00B43HR379
    "Industrials":             "IUIS",   # iShares S&P 500 Industrials UCITS, IE00B4LN9N13
    "Materials":               "IUMS",   # iShares S&P 500 Materials UCITS, IE00B4LF7088
    "Real Estate":             "IUSP",   # iShares US Property Yield UCITS
    "Utilities":               "IUUS",   # iShares S&P 500 Utilities UCITS, IE00B4KBBD01
}

# Whether to apply regime filter + crash protection to sector rotation
# (same enhancements as 33-stock strategy, applied at portfolio level).
# NOTE: found empirically to OVER-hedge when combined with sector rotation's
# own defensive rotation — disabled by default. Use absolute momentum instead.
USE_SECTOR_REGIME_FILTER     = False
USE_SECTOR_CRASH_PROTECTION  = False

# Absolute momentum filter (Faber 2007 / Antonacci dual momentum):
# A sector is only held if its OWN 12-1 momentum exceeds the threshold.
# When < K sectors qualify, hold fewer positions at equal weight.
# When 0 qualify, go to cash (deployment = 0).
# Cleanly handles bear markets (e.g. 2008 GFC, 2022) without double-hedging.
USE_SECTOR_ABSOLUTE_MOMENTUM = True
SECTOR_ABS_MOM_THRESHOLD     = 0.0   # require own momentum > 0; set higher for stricter

# Trend filter: binary master switch — either deploy into top-K sectors, or cash.
# Empirically-chosen mode after filter-variant comparison (Apr 2026):
#   - "abs_mom_12m" (Antonacci 2014): SPY 12-month total return > 0 → deploy.
#     Outperformed Faber 10/12-month SMA variants in TEST 2015-26 (10.4% vs 7.7-8.7%)
#     and TRAIN 2000-14 (8.7% vs 6.8-7.5%) on both CAGR and drawdown.
#     Protects against slow bears (2000-02, 2007-09, 2022) where 12-month
#     returns stay negative for sustained periods. Does not protect against
#     fast crashes (2020 COVID) but those recover within 6 months.
#   - "sma": kept for reference / ablation.
USE_SECTOR_TREND_FILTER       = True
SECTOR_TREND_MODE             = "abs_mom_12m"   # "abs_mom_12m" | "sma"
SECTOR_TREND_SMA_DAYS         = 210              # ~10 trading months (used only if mode="sma")
SECTOR_TREND_DUAL_CONFIRMATION = False           # 2-month confirmation (sma mode)

# Tax parameters for after-tax comparison (HK Non-Resident Alien)
HK_NRA_DIVIDEND_WHT_US       = 0.30  # no US-HK treaty
HK_NRA_DIVIDEND_WHT_UCITS    = 0.15  # Ireland-US treaty inside ETF
HK_NRA_US_ESTATE_EXEMPTION   = 60_000.0  # USD
HK_NRA_US_ESTATE_EFFECTIVE   = 0.30  # ~30% effective rate on amount > exemption
SP500_AVG_DIVIDEND_YIELD     = 0.014  # for modelling WHT drag
UCITS_EXTRA_TER              = 0.0006  # iShares UCITS ~6bps over SPDR XL*

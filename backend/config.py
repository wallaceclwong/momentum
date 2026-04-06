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

# Default equal weights for composite momentum score
# Can be adjusted to emphasize shorter or longer-term momentum
MOMENTUM_WEIGHTS = {
    "4W": 1.0,
    "13W": 1.0,
    "26W": 1.0,
}

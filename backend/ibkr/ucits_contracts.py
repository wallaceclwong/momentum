"""
IBKR contract specs for Ireland-domiciled UCITS sector ETFs.

Traded on London Stock Exchange (LSE) — preferred venue for HK IBKR
accounts due to:
  - Best intraday liquidity for iShares UCITS S&P 500 sector line
  - USD-denominated share classes available for most tickers → avoids
    GBP/EUR FX conversion round-trips on a USD-funded account
  - IBKR HK supports LSE natively (SMART routing + Adaptive algo)

Alternative venues:
  - Xetra (Frankfurt, EUR):  slightly wider spreads, EUR FX conversion
  - SWX (SIX Swiss Exchange, CHF): thin volume for some tickers
  - AEB (Amsterdam, EUR):    iShares distributor class

For now we hard-code LSE USD listings where available and fall back to
LSE GBP listings (tickers don't follow a perfectly consistent convention).
"""
from __future__ import annotations
from typing import Dict, Optional

# Ticker format: "LSE_SYMBOL:CURRENCY"
# LSE symbols: USD-denominated classes end in 'S' or 'P' in many iShares
# series; GBP classes typically do NOT have the suffix.
# We use USD-denominated classes preferentially.
UCITS_CONTRACT_SPECS: Dict[str, Dict[str, str]] = {
    # sector → {symbol, exchange, currency, isin}
    "Information Technology":  {
        "symbol": "IUIT", "exchange": "LSEETF", "currency": "USD",
        "isin": "IE00B3WJKG14",
        "description": "iShares S&P 500 Information Technology Sector UCITS ETF USD (Acc)",
    },
    "Communication Services":  {
        "symbol": "SXLC", "exchange": "LSEETF", "currency": "USD",
        "isin": "IE00BFWFPX50",
        "description": "SPDR S&P U.S. Communication Services Select Sector UCITS ETF",
    },
    "Consumer Discretionary":  {
        "symbol": "IUCD", "exchange": "LSEETF", "currency": "USD",
        "isin": "IE00B4MCHD33",
        "description": "iShares S&P 500 Consumer Discretionary Sector UCITS ETF USD (Acc)",
    },
    "Consumer Staples":        {
        "symbol": "IUCS", "exchange": "LSEETF", "currency": "USD",
        "isin": "IE00B40B8R38",
        "description": "iShares S&P 500 Consumer Staples Sector UCITS ETF USD (Acc)",
    },
    "Energy":                  {
        "symbol": "IUES", "exchange": "LSEETF", "currency": "USD",
        "isin": "IE00B42NKQ00",
        "description": "iShares S&P 500 Energy Sector UCITS ETF USD (Acc)",
    },
    "Financials":              {
        "symbol": "IUFS", "exchange": "LSEETF", "currency": "USD",
        "isin": "IE00B4JNQZ49",
        "description": "iShares S&P 500 Financials Sector UCITS ETF USD (Acc)",
    },
    "Health Care":             {
        "symbol": "IUHC", "exchange": "LSEETF", "currency": "USD",
        "isin": "IE00B43HR379",
        "description": "iShares S&P 500 Health Care Sector UCITS ETF USD (Acc)",
    },
    "Industrials":             {
        "symbol": "IUIS", "exchange": "LSEETF", "currency": "USD",
        "isin": "IE00B4LN9N13",
        "description": "iShares S&P 500 Industrials Sector UCITS ETF USD (Acc)",
    },
    "Materials":               {
        "symbol": "IUMS", "exchange": "LSEETF", "currency": "USD",
        "isin": "IE00B4LF7088",
        "description": "iShares S&P 500 Materials Sector UCITS ETF USD (Acc)",
    },
    "Real Estate":             {
        "symbol": "IUSP", "exchange": "LSEETF", "currency": "USD",
        "isin": "IE00B1FZS350",
        "description": "iShares US Property Yield UCITS ETF",
    },
    "Utilities":               {
        "symbol": "IUUS", "exchange": "LSEETF", "currency": "USD",
        "isin": "IE00B4KBBD01",
        "description": "iShares S&P 500 Utilities Sector UCITS ETF USD (Acc)",
    },
}

# Reverse: ticker → spec (useful for position reconciliation)
TICKER_TO_SPEC: Dict[str, Dict[str, str]] = {
    v["symbol"]: {**v, "sector": k}
    for k, v in UCITS_CONTRACT_SPECS.items()
}


def get_ucits_spec(sector_or_ticker: str) -> Optional[Dict[str, str]]:
    """Look up contract spec by sector NAME or UCITS TICKER."""
    if sector_or_ticker in UCITS_CONTRACT_SPECS:
        return UCITS_CONTRACT_SPECS[sector_or_ticker]
    if sector_or_ticker in TICKER_TO_SPEC:
        return TICKER_TO_SPEC[sector_or_ticker]
    return None


def build_ibkr_contract(sector_or_ticker: str):
    """
    Build an ib_insync Stock contract for a UCITS sector ETF.

    Returns an unqualified Contract — caller should run ib.qualifyContracts()
    before placing orders (required for SMART routing on LSE listings).
    """
    try:
        from ib_insync import Stock
    except ImportError as e:
        raise ImportError("ib_insync not installed. pip install ib_insync") from e

    spec = get_ucits_spec(sector_or_ticker)
    if spec is None:
        raise KeyError(f"No UCITS contract spec for '{sector_or_ticker}'")
    # Using SMART routing with primaryExchange hint for reliable LSE routing
    c = Stock(
        symbol=spec["symbol"],
        exchange="SMART",
        currency=spec["currency"],
        primaryExchange=spec["exchange"],
    )
    return c


def list_all_tickers() -> list:
    """Return list of all UCITS tickers in the universe."""
    return [spec["symbol"] for spec in UCITS_CONTRACT_SPECS.values()]

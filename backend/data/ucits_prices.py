"""
Fetch real-time UCITS ETF prices from Yahoo Finance.

Used for live/paper rebalancing to get actual LSE UCITS prices instead of
using US SPDR proxy prices (which are 10-15x higher and cause wrong share calculations).
"""
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from backend.ibkr.ucits_contracts import UCITS_CONTRACT_SPECS

logger = logging.getLogger(__name__)


def fetch_ucits_prices(
    tickers: Optional[list] = None,
    fallback_to_proxy: bool = False,
) -> Dict[str, float]:
    """
    Fetch latest close prices for UCITS ETFs from Yahoo Finance.
    
    Args:
        tickers: List of UCITS tickers (e.g. ["IUIS", "IUIT"]). 
                 If None, fetches all tickers from UCITS_CONTRACT_SPECS.
        fallback_to_proxy: If True and UCITS price unavailable, use US proxy
                          (NOT recommended for live trading, only for backtesting)
    
    Returns:
        Dict mapping ticker -> price (USD)
    
    Example:
        >>> prices = fetch_ucits_prices(["IUIS", "IUIT", "IUES"])
        >>> prices
        {'IUIS': 15.45, 'IUIT': 48.16, 'IUES': 11.30}
    """
    if tickers is None:
        tickers = [spec["symbol"] for spec in UCITS_CONTRACT_SPECS.values()]
    
    prices = {}
    
    # Yahoo Finance uses .L suffix for LSE
    yf_tickers = [f"{tk}.L" for tk in tickers]
    
    try:
        # Download last 5 days to ensure we get latest close even if today is weekend
        data = yf.download(
            yf_tickers,
            period="5d",
            progress=False,
        )
        
        if data.empty:
            logger.warning("[UCITS] No price data returned from Yahoo Finance")
            return prices
        
        # Handle both single-ticker (Series) and multi-ticker (DataFrame) cases
        if isinstance(data, pd.Series):
            # Single ticker
            if not data.empty:
                prices[tickers[0]] = float(data.iloc[-1])
        elif "Close" in data.columns:
            # Multi-ticker
            close_data = data["Close"]
            if isinstance(close_data, pd.Series):
                # Single ticker in DataFrame format
                if not close_data.empty:
                    prices[tickers[0]] = float(close_data.iloc[-1])
            else:
                # Multiple tickers
                for yf_tk, tk in zip(yf_tickers, tickers):
                    if yf_tk in close_data.columns:
                        series = close_data[yf_tk].dropna()
                        if not series.empty:
                            prices[tk] = float(series.iloc[-1])
                            logger.info(f"[UCITS] {tk}: ${prices[tk]:.2f}")
        
        # Log any missing prices
        missing = set(tickers) - set(prices.keys())
        if missing:
            logger.warning(f"[UCITS] No prices for: {missing}")
        
    except Exception as e:
        logger.error(f"[UCITS] Failed to fetch prices: {e}")
    
    return prices


def get_ucits_price_lookup(
    signal_tickers: list,
    current_position_tickers: list,
) -> Dict[str, float]:
    """
    Fetch prices for all tickers needed for rebalancing.
    
    Args:
        signal_tickers: Tickers in the new target allocation
        current_position_tickers: Tickers currently held (may need to sell)
    
    Returns:
        Dict mapping ticker -> price (USD)
    """
    all_tickers = list(set(signal_tickers + current_position_tickers))
    return fetch_ucits_prices(all_tickers)


if __name__ == "__main__":
    # Test script
    logging.basicConfig(level=logging.INFO)
    
    print("Fetching all UCITS ETF prices...")
    prices = fetch_ucits_prices()
    
    print("\nResults:")
    print("-" * 50)
    for ticker in sorted(prices.keys()):
        print(f"{ticker:6s} ${prices[ticker]:>8.2f}")
    
    print(f"\nTotal: {len(prices)} prices fetched")

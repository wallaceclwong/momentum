"""Scrape S&P 500 constituents from Wikipedia."""
import pandas as pd
import requests
from io import StringIO
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def fetch_sp500_constituents() -> pd.DataFrame:
    """
    Fetch S&P 500 constituents from Wikipedia.
    
    Returns:
        DataFrame with columns: [Symbol, Security, GICS Sector, GICS Sub-Industry, ...]
    """
    try:
        response = requests.get(WIKIPEDIA_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
        tables = pd.read_html(StringIO(response.text))
        # First table is the S&P 500 list
        sp500_table = tables[0]
        
        # Standardize column names
        sp500_table = sp500_table.rename(columns={
            "Symbol": "Ticker",
            "Security": "Name",
            "GICS Sector": "Sector",
            "GICS Sub-Industry": "SubIndustry"
        })
        
        logger.info(f"Fetched {len(sp500_table)} S&P 500 constituents")
        return sp500_table
    except Exception as e:
        logger.error(f"Failed to fetch S&P 500 constituents: {e}")
        raise


def get_ticker_to_sector() -> Dict[str, str]:
    """
    Get mapping of ticker -> GICS Sector name.
    
    Returns:
        Dict like {"AAPL": "Information Technology", "JPM": "Financials", ...}
    """
    df = fetch_sp500_constituents()
    return dict(zip(df["Ticker"], df["Sector"]))


def get_tickers_by_sector() -> Dict[str, List[str]]:
    """
    Group tickers by their GICS sector.
    
    Returns:
        Dict like {"Information Technology": ["AAPL", "MSFT", ...], ...}
    """
    df = fetch_sp500_constituents()
    sector_groups = df.groupby("Sector")["Ticker"].apply(list).to_dict()
    return sector_groups


def get_all_tickers() -> List[str]:
    """Get list of all S&P 500 ticker symbols."""
    df = fetch_sp500_constituents()
    return df["Ticker"].tolist()


def get_ticker_info(ticker: str) -> Dict[str, str]:
    """Get detailed info for a specific ticker."""
    df = fetch_sp500_constituents()
    row = df[df["Ticker"] == ticker]
    if row.empty:
        return {}
    return row.iloc[0].to_dict()

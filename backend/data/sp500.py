"""Scrape S&P 500 constituents from Wikipedia."""
import pandas as pd
import requests
from io import StringIO
from datetime import datetime
from functools import lru_cache
from typing import Dict, List, Tuple, Optional
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


@lru_cache(maxsize=1)
def _fetch_wiki_tables() -> tuple:
    """
    Fetch both Wikipedia tables (cached in-process):
      [0] = current constituents
      [1] = historical changes
    """
    response = requests.get(WIKIPEDIA_URL, headers=HEADERS, timeout=15)
    response.raise_for_status()
    tables = pd.read_html(StringIO(response.text))
    return tuple(tables)


def fetch_sp500_constituents() -> pd.DataFrame:
    """
    Fetch S&P 500 constituents from Wikipedia.
    
    Returns:
        DataFrame with columns: [Symbol, Security, GICS Sector, GICS Sub-Industry, ...]
    """
    try:
        tables = _fetch_wiki_tables()
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


def get_constituents_at_date(as_of: datetime) -> pd.DataFrame:
    """
    Approximate point-in-time S&P 500 constituents by reversing Wikipedia changes.
    Removes stocks added AFTER as_of, adds back stocks removed AFTER as_of.
    Falls back to current list if changes table is unavailable.
    """
    current_df = fetch_sp500_constituents().copy()
    try:
        tables = _fetch_wiki_tables()
        if len(tables) < 2:
            return current_df
        changes = tables[1].copy()

        # Normalise column names — Wikipedia structure varies slightly
        changes.columns = [str(c).strip() for c in changes.columns]
        date_col   = next((c for c in changes.columns if "date" in c.lower()), None)
        added_col  = next((c for c in changes.columns if "added" in c.lower() and "tick" in c.lower()), None)
        removed_col = next((c for c in changes.columns if "remov" in c.lower() and "tick" in c.lower()), None)

        if not date_col or not added_col or not removed_col:
            logger.warning("[SP500] Could not parse changes table columns — using current list")
            return current_df

        changes[date_col] = pd.to_datetime(changes[date_col], errors="coerce")
        changes = changes.dropna(subset=[date_col])

        # Only care about changes that happened AFTER our as_of date
        future_changes = changes[changes[date_col] > pd.Timestamp(as_of)]

        ticker_to_sector = dict(zip(current_df["Ticker"], current_df["Sector"]))
        current_set = set(current_df["Ticker"].tolist())

        for _, row in future_changes.iterrows():
            added   = str(row[added_col]).strip() if pd.notna(row[added_col]) else ""
            removed = str(row[removed_col]).strip() if pd.notna(row[removed_col]) else ""

            # Reverse the change:
            if added and added != "nan":
                current_set.discard(added)          # stock added AFTER → not in index yet
            if removed and removed != "nan":
                current_set.add(removed)            # stock removed AFTER → was still in index

        # Rebuild DataFrame — keep rows that are still in current_set
        result = current_df[current_df["Ticker"].isin(current_set)].copy()
        logger.info(f"[SP500] Point-in-time as of {as_of.date()}: {len(result)} constituents "
                    f"(current={len(current_df)})")
        return result

    except Exception as e:
        logger.warning(f"[SP500] Point-in-time fallback: {e}")
        return current_df


def get_ticker_to_sector(as_of: Optional[datetime] = None) -> Dict[str, str]:
    """
    Get mapping of ticker -> GICS Sector name.
    Pass as_of to get a point-in-time list (backtest use).
    """
    df = get_constituents_at_date(as_of) if as_of else fetch_sp500_constituents()
    return dict(zip(df["Ticker"], df["Sector"]))


def get_tickers_by_sector(as_of: Optional[datetime] = None) -> Dict[str, List[str]]:
    """
    Group tickers by their GICS sector.
    Pass as_of to get a point-in-time list (backtest use).
    """
    df = get_constituents_at_date(as_of) if as_of else fetch_sp500_constituents()
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

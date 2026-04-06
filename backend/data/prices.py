"""yfinance data fetcher for OHLCV prices."""
import yfinance as yf
import pandas as pd
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


def fetch_price_history(
    tickers: List[str],
    period: str = "1y",
    interval: str = "1d"
) -> Dict[str, pd.DataFrame]:
    """
    Fetch OHLCV price history for multiple tickers using yfinance.
    
    Args:
        tickers: List of ticker symbols
        period: Data period (e.g., "1y", "6mo", "3mo")
        interval: Data interval ("1d", "1wk", "1mo")
    
    Returns:
        Dict mapping ticker -> DataFrame with columns [Open, High, Low, Close, Volume]
    """
    results = {}
    
    # Download in batch for efficiency, fallback to individual on failure
    try:
        batch_data = yf.download(
            tickers=tickers,
            period=period,
            interval=interval,
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True
        )
        
        if len(tickers) == 1:
            # Single ticker returns DataFrame directly
            ticker = tickers[0]
            if batch_data is not None and not batch_data.empty:
                results[ticker] = batch_data
        else:
            # Multiple tickers returns MultiIndex DataFrame
            for ticker in tickers:
                try:
                    if ticker in batch_data.columns.get_level_values(0):
                        df = batch_data[ticker].dropna()
                        if not df.empty:
                            results[ticker] = df
                except Exception as e:
                    logger.warning(f"Error extracting {ticker} from batch: {e}")
    except Exception as e:
        logger.warning(f"Batch download failed: {e}, falling back to individual")
    
    # Fallback: fetch individually for any missing tickers
    missing = set(tickers) - set(results.keys())
    for ticker in missing:
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period=period, interval=interval, auto_adjust=True)
            if df is not None and not df.empty:
                results[ticker] = df
        except Exception as e:
            logger.warning(f"Failed to fetch {ticker}: {e}")
    
    logger.info(f"Successfully fetched prices for {len(results)}/{len(tickers)} tickers")
    return results


def get_latest_price(ticker: str) -> Optional[float]:
    """Get the most recent closing price for a ticker."""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="5d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception as e:
        logger.warning(f"Failed to get latest price for {ticker}: {e}")
    return None

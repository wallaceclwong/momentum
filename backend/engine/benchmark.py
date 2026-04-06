"""
Benchmark data fetching and processing.
"""
import yfinance as yf
import pandas as pd
from typing import Dict, List, Optional
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Benchmark tickers
BENCHMARK_TICKERS = {
    'SPY': 'S&P 500',
    'SPMO': 'SPDR MSCI USA StrategicFactors Momentum ETF',
    'QQQ': 'Invesco QQQ Trust'
}

BENCHMARK_CACHE_PATH = None

def _get_benchmark_cache_path() -> Path:
    """Get path to benchmark cache file."""
    global BENCHMARK_CACHE_PATH
    if BENCHMARK_CACHE_PATH is None:
        BENCHMARK_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "benchmark_cache.parquet"
    return BENCHMARK_CACHE_PATH


def fetch_benchmark(ticker: str, start_date: str, end_date: str, use_cache: bool = True) -> pd.DataFrame:
    """
    Fetch benchmark price data and calculate returns.
    
    Args:
        ticker: Benchmark ticker symbol
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        use_cache: Whether to use local cache
        
    Returns:
        DataFrame with columns: [date, price, daily_return, cumulative_return]
    """
    cache_path = _get_benchmark_cache_path()
    
    # Try to load from cache first
    if use_cache and cache_path.exists():
        try:
            cache_df = pd.read_parquet(cache_path)
            cache_df['date'] = pd.to_datetime(cache_df['date'])
            
            # Filter for this ticker and date range
            ticker_data = cache_df[
                (cache_df['ticker'] == ticker) & 
                (cache_df['date'] >= start_date) & 
                (cache_df['date'] <= end_date)
            ].copy()
            
            if len(ticker_data) > 0:
                logger.info(f"Using cached data for {ticker}: {len(ticker_data)} rows")
                return ticker_data[['date', 'price', 'daily_return', 'cumulative_return']]
        except Exception as e:
            logger.warning(f"Cache read failed for {ticker}: {e}")
    
    # Fetch from yfinance
    try:
        data = yf.download(ticker, start=start_date, end=end_date, progress=False)
        
        if data.empty:
            logger.warning(f"No data found for {ticker}")
            return pd.DataFrame()
        
        # Handle MultiIndex columns (newer yfinance returns MultiIndex for single tickers)
        if isinstance(data.columns, pd.MultiIndex):
            if ('Close', ticker) in data.columns:
                prices = data[('Close', ticker)]
            elif ('Adj Close', ticker) in data.columns:
                prices = data[('Adj Close', ticker)]
            else:
                prices = data.xs('Close', axis=1, level=0).iloc[:, 0]
        else:
            col = 'Close' if 'Close' in data.columns else 'Adj Close'
            prices = data[col]
        prices = prices.rename('price')
        
        # Calculate returns
        daily_returns = prices.pct_change()
        cumulative_returns = (1 + daily_returns).cumprod() - 1
        
        # Combine into DataFrame
        result = pd.DataFrame({
            'date': prices.index,
            'ticker': ticker,
            'price': prices.values,
            'daily_return': daily_returns.values,
            'cumulative_return': cumulative_returns.values
        })
        
        logger.info(f"Fetched {len(result)} days of data for {ticker}")
        
        # Update cache
        if use_cache:
            _update_benchmark_cache(result)
        
        return result[['date', 'price', 'daily_return', 'cumulative_return']]
        
    except Exception as e:
        logger.error(f"Error fetching {ticker}: {str(e)}")
        return pd.DataFrame()


def _update_benchmark_cache(new_data: pd.DataFrame):
    """Update benchmark cache with new data."""
    cache_path = _get_benchmark_cache_path()
    
    try:
        if cache_path.exists():
            existing = pd.read_parquet(cache_path)
            # Remove existing data for this ticker
            existing = existing[existing['ticker'] != new_data['ticker'].iloc[0]]
            # Append new data
            combined = pd.concat([existing, new_data], ignore_index=True)
        else:
            combined = new_data
        
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(cache_path)
        logger.info(f"Updated benchmark cache: {len(combined)} total rows")
    except Exception as e:
        logger.warning(f"Failed to update benchmark cache: {e}")


def fetch_all_benchmarks(start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
    """
    Fetch all benchmark data.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        
    Returns:
        Dictionary mapping ticker to DataFrame
    """
    results = {}
    
    for ticker in BENCHMARK_TICKERS.keys():
        df = fetch_benchmark(ticker, start_date, end_date)
        if not df.empty:
            results[ticker] = df
        else:
            logger.warning(f"Failed to fetch data for {ticker}")
    
    return results


def align_benchmarks_with_portfolio(
    portfolio_dates: pd.DatetimeIndex, 
    benchmark_data: Dict[str, pd.DataFrame]
) -> Dict[str, pd.Series]:
    """
    Align benchmark data with portfolio dates.
    
    Args:
        portfolio_dates: Dates from portfolio backtest
        benchmark_data: Dictionary of benchmark DataFrames
        
    Returns:
        Dictionary mapping ticker to aligned price Series
    """
    aligned = {}
    
    for ticker, df in benchmark_data.items():
        if df.empty:
            continue
            
        # Convert to Series with date index
        price_series = df.set_index('date')['price']
        
        # Align with portfolio dates
        aligned_series = price_series.reindex(portfolio_dates, method='ffill')
        
        # Normalize to first value = 100
        if not aligned_series.empty and aligned_series.iloc[0] > 0:
            aligned_series = (aligned_series / aligned_series.iloc[0]) * 100
        
        aligned[ticker] = aligned_series
    
    return aligned


def calculate_benchmark_comparison(
    portfolio_metrics: Dict[str, float],
    benchmark_data: Dict[str, pd.DataFrame]
) -> Dict[str, Dict[str, float]]:
    """
    Calculate benchmark metrics for comparison.
    
    Args:
        portfolio_metrics: Portfolio performance metrics
        benchmark_data: Aligned benchmark price series
        
    Returns:
        Dictionary with metrics for each benchmark
    """
    from .metrics import calculate_benchmark_metrics
    
    comparison = {}
    
    for ticker, price_series in benchmark_data.items():
        if price_series.empty:
            continue
            
        metrics = calculate_benchmark_metrics(price_series)
        comparison[ticker] = metrics
    
    return comparison


def get_benchmark_info() -> Dict[str, str]:
    """Get benchmark ticker information."""
    return BENCHMARK_TICKERS.copy()

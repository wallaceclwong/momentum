"""
Performance metrics calculator for backtesting results.
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


def cagr(nav_series: pd.Series) -> float:
    """Calculate Compound Annual Growth Rate."""
    if len(nav_series) < 2:
        return 0.0
    
    start_value = nav_series.iloc[0]
    end_value = nav_series.iloc[-1]
    years = len(nav_series) / 252.0  # Approximate trading days per year
    
    if start_value <= 0:
        return 0.0
    
    return (end_value / start_value) ** (1 / years) - 1


def sharpe(daily_returns: pd.Series, rf: float = 0.05 / 252) -> float:
    """Calculate Sharpe ratio."""
    if len(daily_returns) < 2:
        return 0.0
    
    excess_returns = daily_returns - rf
    if excess_returns.std() == 0:
        return 0.0
    
    return np.sqrt(252) * excess_returns.mean() / excess_returns.std()


def max_drawdown(nav_series: pd.Series) -> float:
    """Calculate maximum drawdown."""
    if len(nav_series) < 2:
        return 0.0
    
    cumulative_max = nav_series.expanding().max()
    drawdown = (nav_series - cumulative_max) / cumulative_max
    return drawdown.min()


def calmar(nav_series: pd.Series) -> float:
    """Calculate Calmar ratio (CAGR / Max Drawdown)."""
    cagr_val = cagr(nav_series)
    max_dd = max_drawdown(nav_series)
    
    if max_dd == 0:
        return 0.0
    
    return cagr_val / abs(max_dd)


def monthly_returns(nav_series: pd.Series) -> pd.DataFrame:
    """Calculate monthly returns table."""
    if len(nav_series) < 2:
        return pd.DataFrame()
    
    # Calculate daily returns
    daily_returns = nav_series.pct_change().dropna()
    
    # Group by year and month
    monthly_data = []
    for (year, month), group in daily_returns.groupby([daily_returns.index.year, daily_returns.index.month]):
        monthly_return = (1 + group).prod() - 1
        monthly_data.append({
            'year': year,
            'month': month,
            'return': monthly_return
        })
    
    monthly_df = pd.DataFrame(monthly_data)
    
    if monthly_df.empty:
        return pd.DataFrame()
    
    # Create pivot table
    pivot_table = monthly_df.pivot(
        index='year', 
        columns='month', 
        values='return'
    )
    
    # Add annual column
    pivot_table['Annual'] = pivot_table.apply(
        lambda row: (1 + row.dropna()).prod() - 1, 
        axis=1
    )
    
    # Sort columns properly
    month_order = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    pivot_table = pivot_table.reindex(columns=month_order + ['Annual'])
    
    return pivot_table


def rolling_sharpe(daily_returns: pd.Series, window: int = 252) -> pd.Series:
    """Calculate rolling Sharpe ratio."""
    if len(daily_returns) < window:
        return pd.Series()
    
    excess_returns = daily_returns - 0.05 / 252  # Risk-free rate
    rolling_mean = excess_returns.rolling(window=window).mean()
    rolling_std = excess_returns.rolling(window=window).std()
    
    rolling_sharpe = np.sqrt(252) * rolling_mean / rolling_std
    return rolling_sharpe


def calculate_all_metrics(nav_series: pd.Series) -> Dict[str, float]:
    """Calculate all performance metrics."""
    if len(nav_series) < 2:
        return {
            'cagr': 0.0,
            'sharpe': 0.0,
            'max_drawdown': 0.0,
            'calmar': 0.0,
            'volatility': 0.0,
            'best_day': 0.0,
            'worst_day': 0.0,
            'win_rate': 0.0
        }
    
    daily_returns = nav_series.pct_change().dropna()
    
    return {
        'cagr': cagr(nav_series),
        'sharpe': sharpe(daily_returns),
        'max_drawdown': max_drawdown(nav_series),
        'calmar': calmar(nav_series),
        'volatility': daily_returns.std() * np.sqrt(252),
        'best_day': daily_returns.max(),
        'worst_day': daily_returns.min(),
        'win_rate': (daily_returns > 0).mean()
    }


def calculate_benchmark_metrics(price_series: pd.Series) -> Dict[str, float]:
    """Calculate metrics for benchmark (same as portfolio but without special handling)."""
    return calculate_all_metrics(price_series)


def prepare_nav_series(nav_data: List[Dict]) -> pd.Series:
    """Convert nav data list to pandas Series."""
    if not nav_data:
        return pd.Series()
    
    df = pd.DataFrame(nav_data)
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date').sort_index()
    
    return pd.Series(df['nav'].values, index=df.index)

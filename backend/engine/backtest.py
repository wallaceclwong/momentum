"""
Backtesting engine for momentum strategy.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging
from dateutil.relativedelta import relativedelta

from ..data.sp500 import get_ticker_to_sector, get_tickers_by_sector
from ..data.prices import fetch_price_history
from ..engine.momentum import calculate_momentum_for_tickers
from ..engine.portfolio import get_sector_etf_weights
from .benchmark import fetch_all_benchmarks, align_benchmarks_with_portfolio
from .metrics import calculate_all_metrics, prepare_nav_series
from ..config import (
    USE_REGIME_FILTER, REGIME_MA_DAYS, REGIME_MA_SHORT,
    REGIME_BEAR_DEPLOYMENT, USE_VOLATILITY_WEIGHTING,
    BACKTEST_SLIPPAGE, BACKTEST_COMMISSION_PER_SHARE,
    MAX_POSITION_WEIGHT, USE_STOP_LOSS, STOP_LOSS_PCT,
    RISK_PARITY_VOL_DAYS,
)
from ..engine.regime import _classify

logger = logging.getLogger(__name__)


def get_last_friday_of_month(date: datetime) -> datetime:
    """Get the last Friday of a given month."""
    # Find the last day of the month
    last_day = date.replace(day=28) + timedelta(days=4)
    last_day = last_day - timedelta(days=last_day.day)
    
    # Find the last Friday
    while last_day.weekday() != 4:  # Friday is weekday 4
        last_day -= timedelta(days=1)
    
    return last_day


def get_rebalance_dates(start_date: datetime, end_date: datetime) -> List[datetime]:
    """
    Get monthly rebalance dates (last Friday of each month).
    
    Args:
        start_date: Backtest start date
        end_date: Backtest end date
        
    Returns:
        List of rebalance dates
    """
    dates = []
    current = start_date
    
    while current < end_date:
        last_friday = get_last_friday_of_month(current)
        if start_date <= last_friday <= end_date:
            dates.append(last_friday)
        current += relativedelta(months=1)
    
    return dates


def calculate_portfolio_returns(
    holdings: Dict[str, float], 
    price_data: pd.DataFrame,
    prev_prices: pd.Series
) -> float:
    """
    Calculate daily portfolio return.
    
    Args:
        holdings: Dictionary of ticker -> weight
        price_data: Current day prices
        prev_prices: Previous day prices
        
    Returns:
        Daily portfolio return
    """
    if prev_prices.empty or price_data.empty:
        return 0.0
    
    daily_return = 0.0
    
    for ticker, weight in holdings.items():
        if ticker in price_data.index and ticker in prev_prices.index:
            stock_return = (price_data[ticker] / prev_prices[ticker]) - 1
            daily_return += weight * stock_return
    
    return daily_return


def run_screener_at_date(
    date: datetime,
    preloaded_prices: Optional[Dict[str, pd.DataFrame]] = None
) -> Tuple[Dict[str, List[str]], Dict[str, float]]:
    """
    Run momentum screener at a specific date.
    
    Args:
        date: Rebalance date
        preloaded_prices: Pre-downloaded price data sliced to date
        
    Returns:
        Tuple of (top_picks_by_sector, sector_weights)
    """
    # Get S&P 500 sector mapping
    ticker_to_sector = get_ticker_to_sector()
    sector_to_tickers = get_tickers_by_sector()
    
    if preloaded_prices is None:
        # Fetch 6 months of history (enough for 26W momentum)
        all_tickers = list(ticker_to_sector.keys())
        logger.info(f"Fetching price data for {len(all_tickers)} tickers")
        price_data = fetch_price_history(all_tickers, period="6mo", interval="1d")
    else:
        price_data = preloaded_prices
    
    if not price_data:
        logger.warning("No price data available")
        return {}, {}
    
    # Calculate momentum scores — returns Dict[str, Dict]
    logger.info("Calculating momentum scores")
    momentum_data = calculate_momentum_for_tickers(price_data)
    
    # Select top 3 per sector
    top_picks_by_sector = {}
    for sector, tickers in sector_to_tickers.items():
        sector_scores = [
            (ticker, momentum_data[ticker]['composite_score'])
            for ticker in tickers
            if ticker in momentum_data and momentum_data[ticker].get('composite_score') is not None
        ]
        # Sort by score descending, take top 3
        sector_scores.sort(key=lambda x: x[1], reverse=True)
        top_picks_by_sector[sector] = [t for t, _ in sector_scores[:3]]
    
    # Get sector ETF weights
    sector_weights = get_sector_etf_weights()
    
    logger.info(f"Selected {sum(len(picks) for picks in top_picks_by_sector.values())} total positions")
    return top_picks_by_sector, sector_weights


PRICE_CACHE_PATH = None  # set lazily relative to project root


def _get_cache_path() -> "Path":
    from pathlib import Path
    global PRICE_CACHE_PATH
    if PRICE_CACHE_PATH is None:
        # Resolve to <project_root>/data/price_cache.parquet
        PRICE_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "price_cache.parquet"
    return PRICE_CACHE_PATH


def _download_bulk_prices(tickers: List[str], start_date: str, end_date: str) -> pd.DataFrame:
    """
    Return adj-close prices (wide DataFrame: index=date, columns=ticker).
    Reads from Parquet cache first; downloads only what's missing.
    """
    import yfinance as yf
    from pathlib import Path

    cache_path = _get_cache_path()
    buffer_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=200)).strftime("%Y-%m-%d")
    need_start = pd.Timestamp(buffer_start)
    need_end   = pd.Timestamp(end_date)

    cached: pd.DataFrame = pd.DataFrame()
    if cache_path.exists():
        try:
            cached = pd.read_parquet(cache_path)
            cached.index = pd.to_datetime(cached.index)
        except Exception as e:
            logger.warning(f"Cache read failed, re-downloading: {e}")
            cached = pd.DataFrame()

    # Determine which tickers and dates still need downloading
    cached_tickers  = set(cached.columns) if not cached.empty else set()
    missing_tickers = [t for t in tickers if t not in cached_tickers]

    if cached.empty:
        cache_start = need_start
        cache_end   = need_end
    else:
        cache_start = min(cached.index.min(), need_start)
        cache_end   = max(cached.index.max(), need_end)

    need_download = (
        missing_tickers
        or (not cached.empty and need_start < cached.index.min())
        or (not cached.empty and need_end   > cached.index.max())
    )

    if need_download:
        dl_tickers = list(set(tickers) | cached_tickers) if not cached.empty else tickers
        dl_start   = cache_start.strftime("%Y-%m-%d")
        dl_end     = (cache_end + timedelta(days=1)).strftime("%Y-%m-%d")
        logger.info(f"Downloading prices for {len(dl_tickers)} tickers ({dl_start} – {dl_end}) …")

        raw = yf.download(
            tickers=dl_tickers,
            start=dl_start,
            end=dl_end,
            progress=False,
            auto_adjust=True,
            group_by="ticker",
            threads=True,
        )
        if not raw.empty:
            if isinstance(raw.columns, pd.MultiIndex):
                try:
                    fresh = raw.xs("Close", axis=1, level=1)
                except KeyError:
                    fresh = raw.xs("Adj Close", axis=1, level=1)
            else:
                fresh = raw[["Close"]].rename(columns={"Close": dl_tickers[0]}) if len(dl_tickers) == 1 else raw

            fresh.index = pd.to_datetime(fresh.index)

            # Merge with existing cache
            if not cached.empty:
                combined = fresh.combine_first(cached)
            else:
                combined = fresh

            combined = combined.dropna(how="all").sort_index()
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                combined.to_parquet(cache_path)
                logger.info(f"Cache updated → {combined.shape} rows×cols saved to {cache_path}")
            except Exception as e:
                logger.warning(f"Cache write failed: {e}")

            cached = combined
    else:
        logger.info(f"Using cached prices for {len(tickers)} tickers")

    # Slice to requested tickers and date range
    available = [t for t in tickers if t in cached.columns]
    result = cached.loc[need_start:need_end, available]
    return result.dropna(how="all")


def run_backtest(
    start_date: str,
    end_date: str,
    rebalance_freq: str = "monthly"
) -> Dict:
    """
    Run backtest of momentum strategy.

    Strategy:
    - At each monthly rebalance date (last Friday), score S&P 500 stocks by
      4W/13W/26W momentum using only data available *before* that date (no lookahead).
    - Select top 3 per sector, weight by sector ETF weights.
    - Track daily portfolio NAV using pre-downloaded prices.
    
    Returns:
        Dictionary with backtest results
    """
    logger.info(f"Starting backtest from {start_date} to {end_date}")

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    # ── 1. Get universe ──────────────────────────────────────────────────────
    ticker_to_sector = get_ticker_to_sector()
    sector_to_tickers = get_tickers_by_sector()
    sector_weights = get_sector_etf_weights()
    all_tickers = list(ticker_to_sector.keys())
    # Include SPY for regime filter (not in S&P 500 member list)
    download_tickers = list(set(all_tickers) | {"SPY"})

    # ── 2. Pre-download ALL prices once (bulk) ────────────────────────
    # Also include sector ETFs (for risk parity) and VIX (for regime)
    sector_etfs = ["XLK","XLC","XLY","XLP","XLE","XLF","XLV","XLI","XLB","XLRE","XLU"]
    download_tickers = list(set(all_tickers) | {"SPY", "^VIX"} | set(sector_etfs))
    logger.info(f"Downloading prices for {len(download_tickers)} tickers ({start_date} – {end_date}) …")
    all_prices = _download_bulk_prices(download_tickers, start_date, end_date)
    if all_prices.empty:
        raise RuntimeError("Price download returned empty data")
    logger.info(f"Downloaded prices shape: {all_prices.shape}")

    # ── 3. Build rebalance schedule ──────────────────────────────────────────
    rebalance_dates = get_rebalance_dates(start_dt, end_dt)
    logger.info(f"Rebalance dates: {len(rebalance_dates)}")
    rebalance_set = set(rd.date() for rd in rebalance_dates)

    # ── 4. Iterate over trading days ─────────────────────────────────────────
    trading_days = all_prices.loc[start_date:end_date].index
    nav = 100.0
    current_holdings: Dict[str, float] = {}
    entry_prices: Dict[str, float] = {}    # ticker -> price when position opened
    stopped_tickers: set = set()           # stopped-out this month, skip until rebalance
    nav_records: List[Dict] = []
    positions_count: List[int] = []

    for i, trade_date in enumerate(trading_days):
        is_rebalance = trade_date.date() in rebalance_set

        if is_rebalance:
            logger.info(f"Rebalancing on {trade_date.date()}")
            prices_to_date: pd.DataFrame = all_prices.loc[:trade_date]
            stopped_tickers.clear()   # reset stops at each rebalance

            # ── Graduated regime filter (SPY MA50/MA200 + VIX) ────────────
            deployment = 1.0
            if USE_REGIME_FILTER:
                spy_series = prices_to_date.get("SPY") if hasattr(prices_to_date, 'get') else (
                    prices_to_date["SPY"] if "SPY" in prices_to_date.columns else None
                )
                vix_series = (
                    prices_to_date["^VIX"] if "^VIX" in prices_to_date.columns else None
                )
                if spy_series is not None and len(spy_series.dropna()) >= REGIME_MA_DAYS:
                    spy_clean = spy_series.dropna()
                    spy_now = float(spy_clean.iloc[-1])
                    ma200   = float(spy_clean.iloc[-REGIME_MA_DAYS:].mean())
                    ma50    = float(spy_clean.iloc[-REGIME_MA_SHORT:].mean()) if len(spy_clean) >= REGIME_MA_SHORT else spy_now
                    vix_now = float(vix_series.dropna().iloc[-1]) if vix_series is not None and len(vix_series.dropna()) > 0 else None
                    _, deployment = _classify(spy_now, ma50, ma200, vix_now)
                    logger.info(f"  Regime deploy={deployment:.0%}  SPY={spy_now:.1f}  MA50={ma50:.1f}  MA200={ma200:.1f}  VIX={vix_now}")

            # ── Point-in-time constituents (survivorship bias fix) ───────
            from ..data.sp500 import get_tickers_by_sector as _gts
            pit_sector_to_tickers = _gts(as_of=trade_date.to_pydatetime())

            # ── Build per-ticker DataFrames — min 252 days history filter ─
            MIN_HISTORY = 252
            ticker_dfs: Dict[str, pd.DataFrame] = {}
            for col in prices_to_date.columns:
                series = prices_to_date[col].dropna()
                if len(series) >= MIN_HISTORY:
                    ticker_dfs[col] = series.to_frame(name="Close")

            from ..engine.momentum import calculate_momentum_for_tickers as _calc
            momentum_data = _calc(ticker_dfs)

            # ── Risk-parity sector weights (computed from ETFs to date) ──
            etf_prices_to_date = {
                etf: prices_to_date[etf].dropna()
                for etf in sector_etfs
                if etf in prices_to_date.columns
            }
            from ..engine.portfolio import get_sector_etf_weights as _gsw
            sector_weights = _gsw(prices=etf_prices_to_date)

            # ── Select top 3 per sector ───────────────────────────────────
            new_holdings: Dict[str, float] = {}
            for sector, tickers in pit_sector_to_tickers.items():
                # Exclude tickers stopped out this rebalance cycle
                eligible = [t for t in tickers if t not in stopped_tickers]
                scores = [
                    (t, momentum_data[t]["composite_score"])
                    for t in eligible
                    if t in momentum_data and momentum_data[t].get("composite_score") is not None
                ]
                scores.sort(key=lambda x: x[1], reverse=True)
                top3 = [t for t, _ in scores[:3]]
                sw = sector_weights.get(sector, 0.0) * deployment
                if not top3 or sw <= 0:
                    continue

                # ── Volatility-weighted sizing within sector ──────────────
                if USE_VOLATILITY_WEIGHTING:
                    vols = [momentum_data[t].get("volatility") for t in top3]
                    if all(v is not None and v > 0 for v in vols):
                        inv_vols = [1.0 / v for v in vols]
                        total_inv = sum(inv_vols)
                        for t, iv in zip(top3, inv_vols):
                            new_holdings[t] = sw * (iv / total_inv)
                        continue

                # Fallback: equal weight within sector
                w = sw / len(top3)
                for t in top3:
                    new_holdings[t] = w

            # ── Concentration cap: clamp each position to MAX_POSITION_WEIGHT ─
            capped = {t: min(w, MAX_POSITION_WEIGHT) for t, w in new_holdings.items()}
            # Redistribute clipped weight proportionally to uncapped positions
            total_before = sum(new_holdings.values())
            total_after = sum(capped.values())
            clipped = total_before - total_after
            if clipped > 1e-6:
                uncapped = {t: w for t, w in capped.items() if w < MAX_POSITION_WEIGHT}
                if uncapped:
                    uncapped_total = sum(uncapped.values())
                    for t in uncapped:
                        capped[t] += clipped * (uncapped[t] / uncapped_total)
            new_holdings = capped

            # ── Update entry prices for new / re-entered positions ────────
            for t in new_holdings:
                if t not in current_holdings:  # new entry
                    if t in prices_to_date.columns:
                        ep = prices_to_date[t].dropna()
                        if not ep.empty:
                            entry_prices[t] = float(ep.iloc[-1])
            # Remove entry prices for exited positions
            for t in list(entry_prices.keys()):
                if t not in new_holdings:
                    del entry_prices[t]

            # ── Transaction costs ────────────────────────────────────────
            rebalance_cost = 0.0
            for t, new_w in new_holdings.items():
                old_w = current_holdings.get(t, 0.0)
                trade_value = abs(new_w - old_w) * nav
                price_t = prices_to_date[t].dropna().iloc[-1] if t in prices_to_date.columns else 100
                shares_traded = trade_value / price_t if price_t > 0 else 0
                rebalance_cost += trade_value * BACKTEST_SLIPPAGE
                rebalance_cost += shares_traded * BACKTEST_COMMISSION_PER_SHARE
            nav -= rebalance_cost

            current_holdings = new_holdings

        # ── Stop-loss check (daily) ──────────────────────────────────────
        if USE_STOP_LOSS and current_holdings and trade_date in all_prices.index:
            for ticker in list(current_holdings.keys()):
                if ticker not in entry_prices or ticker not in all_prices.columns:
                    continue
                curr_p = all_prices.loc[trade_date, ticker]
                ep = entry_prices[ticker]
                if pd.notna(curr_p) and ep > 0 and curr_p < ep * (1 - STOP_LOSS_PCT):
                    loss_pct = (curr_p / ep - 1) * 100
                    logger.debug(f"  STOP-LOSS {ticker} {loss_pct:.1f}% — exiting")
                    del current_holdings[ticker]
                    del entry_prices[ticker]
                    stopped_tickers.add(ticker)

        # Daily return
        if i > 0 and current_holdings:
            prev_date = trading_days[i - 1]
            daily_ret = 0.0
            for ticker, weight in current_holdings.items():
                if ticker in all_prices.columns:
                    curr_p = all_prices.loc[trade_date, ticker] if trade_date in all_prices.index else np.nan
                    prev_p = all_prices.loc[prev_date, ticker] if prev_date in all_prices.index else np.nan
                    if pd.notna(curr_p) and pd.notna(prev_p) and prev_p != 0:
                        daily_ret += weight * (curr_p / prev_p - 1)
            nav *= (1 + daily_ret)

        nav_records.append({"date": trade_date.isoformat(), "nav": float(nav)})
        positions_count.append(len(current_holdings))

    # ── 5. Metrics ───────────────────────────────────────────────────────────
    nav_series = pd.Series(
        [r["nav"] for r in nav_records],
        index=pd.to_datetime([r["date"] for r in nav_records])
    )
    metrics = calculate_all_metrics(nav_series)

    # ── 6. Benchmarks ────────────────────────────────────────────────────────
    logger.info("Fetching benchmark data")
    benchmark_data = fetch_all_benchmarks(start_date, end_date)
    benchmark_metrics: Dict[str, Dict] = {}
    for ticker, df in benchmark_data.items():
        if not df.empty:
            bm_prices = pd.Series(df["price"].values, index=pd.to_datetime(df["date"]))
            bm_prices = bm_prices.reindex(nav_series.index, method="ffill")
            bm_prices = bm_prices / bm_prices.iloc[0] * 100
            bm_m = calculate_all_metrics(bm_prices)
            benchmark_metrics[ticker] = bm_m

    # ── 7. Monthly returns ───────────────────────────────────────────────────
    from .metrics import monthly_returns as _monthly
    monthly_df = _monthly(nav_series)
    monthly_returns_json: Dict = {}
    if not monthly_df.empty:
        monthly_returns_json = {
            "years": [int(y) for y in monthly_df.index.tolist()],
            "months": [str(m) for m in monthly_df.columns.tolist()],
            "data": monthly_df.fillna(0).values.tolist()
        }

    final_nav = float(nav_records[-1]["nav"]) if nav_records else 100.0
    logger.info(f"Backtest complete. Final NAV={final_nav:.2f}, CAGR={metrics.get('cagr', 0):.2%}")

    return {
        "run_id": None,
        "start_date": start_date,
        "end_date": end_date,
        "rebalance_freq": rebalance_freq,
        "status": "completed",
        "nav_series": nav_records,
        "metrics": metrics,
        "benchmark_metrics": benchmark_metrics,
        "monthly_returns": monthly_returns_json,
        "total_trades": len(rebalance_dates) * 33,
        "final_nav": final_nav,
        "total_return": (final_nav / 100.0) - 1.0,
    }

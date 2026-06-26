"""
IBKR market data — historical bars and live quotes.

Purpose: replace yfinance for data where accuracy matters most — i.e. current
positions (where mismatch between Yahoo close and actual execution price
creates P&L reconciliation errors) and optionally short-list watchlists.

NOT used for bulk S&P 500 screening — IBKR's historical API is paced
(~60 req / 10 min per clientId), making it impractical for 500-ticker runs.
Keep yfinance for bulk backtest/screener; use IBKR for position-level data.

Pacing notes:
  * reqHistoricalData: ~6 req/min per contract safely; ib_insync spaces
    calls internally. For 33 positions this takes ~30s sequentially.
  * reqMktData (live quotes): requires market data subscription; paper
    accounts often return delayed/frozen data only.
"""
from __future__ import annotations
import logging
import time
from typing import Dict, List, Optional

import pandas as pd

from .gateway import get_ib, is_dry_run

logger = logging.getLogger(__name__)


def _qualify_stock(symbol: str):
    """Create and qualify a SMART-routed US stock contract."""
    from ib_insync import Stock
    ib = get_ib()
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)
    return contract


def fetch_historical_bars(
    ticker: str,
    duration: str = "1 Y",
    bar_size: str = "1 day",
    what_to_show: str = "TRADES",
    use_rth: bool = True,
) -> Optional[pd.DataFrame]:
    """
    Fetch historical OHLCV bars for a single ticker via IBKR.

    Args:
        ticker:       US stock symbol (SMART-routed).
        duration:     IB duration string: "1 Y", "6 M", "30 D", etc.
        bar_size:     "1 day", "1 hour", "5 mins", "1 min", etc.
        what_to_show: "TRADES" (actual fills — preferred for daily),
                      "MIDPOINT", "BID_ASK".
        use_rth:      True = regular trading hours only (standard for daily).

    Returns:
        DataFrame with DatetimeIndex and columns:
          Open, High, Low, Close, Volume, Average, BarCount
        Column naming matches yfinance convention so downstream code works
        drop-in (only Close + Volume are actually needed).
        Returns None on failure.
    """
    if is_dry_run():
        logger.debug(f"[IBKR MD] dry-run: skipping {ticker} historical fetch")
        return None

    ib = get_ib()
    if not ib or not ib.isConnected():
        raise RuntimeError("Not connected to IB Gateway. Call connect() first.")

    try:
        contract = _qualify_stock(ticker)
        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow=what_to_show,
            useRTH=use_rth,
            formatDate=1,
        )
        if not bars:
            logger.warning(f"[IBKR MD] {ticker}: no bars returned")
            return None

        rows = [
            {
                "Open":     b.open,
                "High":     b.high,
                "Low":      b.low,
                "Close":    b.close,
                "Volume":   b.volume,
                "Average":  b.average,
                "BarCount": b.barCount,
            }
            for b in bars
        ]
        idx = pd.DatetimeIndex([b.date for b in bars])
        df = pd.DataFrame(rows, index=idx)
        return df
    except Exception as e:
        logger.warning(f"[IBKR MD] {ticker} historical fetch failed: {e}")
        return None


def fetch_position_history(
    tickers: List[str],
    duration: str = "1 Y",
    bar_size: str = "1 day",
    pacing_sleep: float = 0.2,
) -> Dict[str, pd.DataFrame]:
    """
    Fetch historical bars for a list of tickers (e.g. current positions).

    ib_insync auto-paces internally, but we add a small sleep between
    requests to stay under IBKR's 60 req / 10 min soft limit.

    Args:
        tickers:      Usually your current open positions (~30 tickers).
        duration:     IB duration string (default 1 year for momentum calcs).
        bar_size:     "1 day" is standard.
        pacing_sleep: Seconds between requests (safety buffer).

    Returns:
        Dict[ticker, DataFrame]. Failed tickers are omitted (not exception).
    """
    if is_dry_run():
        logger.info("[IBKR MD] dry-run: returning empty history dict")
        return {}

    out: Dict[str, pd.DataFrame] = {}
    for i, t in enumerate(tickers, 1):
        df = fetch_historical_bars(t, duration=duration, bar_size=bar_size)
        if df is not None and not df.empty:
            out[t] = df
        if pacing_sleep and i < len(tickers):
            time.sleep(pacing_sleep)
    logger.info(
        f"[IBKR MD] Historical bars: {len(out)}/{len(tickers)} tickers "
        f"({duration} @ {bar_size})"
    )
    return out


def fetch_live_quotes(
    tickers: List[str],
    timeout: float = 3.0,
) -> Dict[str, float]:
    """
    Fetch last-trade prices for a list of tickers.

    Requires an active market data subscription; paper accounts typically
    return delayed/frozen data only. Falls back silently to None per ticker
    if no data is available within the timeout.

    Args:
        tickers:  Symbols to quote.
        timeout:  Seconds to wait per ticker for first tick.

    Returns:
        Dict[ticker, last_price]. Missing tickers are omitted.
    """
    if is_dry_run():
        logger.info("[IBKR MD] dry-run: returning empty quotes dict")
        return {}

    ib = get_ib()
    if not ib or not ib.isConnected():
        raise RuntimeError("Not connected to IB Gateway. Call connect() first.")

    quotes: Dict[str, float] = {}
    tickers_subs = []
    try:
        # Subscribe all at once — ib_insync handles concurrency
        for t in tickers:
            contract = _qualify_stock(t)
            sub = ib.reqMktData(contract, "", False, False)
            tickers_subs.append((t, sub))

        # Wait up to `timeout` seconds for first tick on each
        deadline = time.time() + timeout
        while time.time() < deadline:
            ib.sleep(0.1)
            all_ready = True
            for t, sub in tickers_subs:
                if t in quotes:
                    continue
                price = (
                    sub.last if (sub.last and sub.last > 0)
                    else (sub.close if (sub.close and sub.close > 0) else None)
                )
                if price:
                    quotes[t] = float(price)
                else:
                    all_ready = False
            if all_ready:
                break
    finally:
        # Clean up subscriptions to avoid wasting data-line slots
        for t, sub in tickers_subs:
            try:
                ib.cancelMktData(sub.contract)
            except Exception:
                pass

    missing = set(tickers) - set(quotes.keys())
    if missing:
        logger.warning(
            f"[IBKR MD] No live quote for {len(missing)} tickers "
            f"(may need market-data subscription): {sorted(missing)[:5]}..."
        )
    return quotes

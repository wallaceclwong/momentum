"""
Finnhub earnings surprises — more reliable than yfinance for historical EPS.

Free-tier API key: https://finnhub.io  (register → copy key → set
FINNHUB_API_KEY env var in .env)

Free tier limits: 60 requests/min, unlimited per day.
For 500 tickers this takes ~9 minutes on the free tier — fine for a
monthly rebalance run. Paid tier ($10-20/mo) removes the rate limit.

Endpoint: https://finnhub.io/api/v1/stock/earnings
Returns list of the last ~4-8 earnings reports with actual vs estimate EPS.
"""
from __future__ import annotations
import logging
import os
import time
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "").strip()
FINNHUB_BASE = "https://finnhub.io/api/v1"

# Rate limiting: free tier = 60/min → 1 req / sec is safe
_RATE_LIMIT_SLEEP = 1.05
_last_request_time = 0.0


def _rate_limit():
    """Sleep to stay under the 60/min free-tier limit."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _RATE_LIMIT_SLEEP:
        time.sleep(_RATE_LIMIT_SLEEP - elapsed)
    _last_request_time = time.time()


def is_finnhub_configured() -> bool:
    return bool(FINNHUB_API_KEY)


def fetch_earnings_finnhub(ticker: str, n: int = 2) -> List[Dict]:
    """
    Fetch the last N earnings reports (actual vs estimate) from Finnhub.

    Args:
        ticker: US stock symbol.
        n:      Number of most-recent reports to return (L1 = most recent).

    Returns:
        List of dicts — sorted most-recent first — with keys:
          {period (L1, L2, ...), date, eps_estimate, eps_actual, surprise_pct}
        Empty list if the ticker has no data or the API key is missing.
    """
    if not FINNHUB_API_KEY:
        return []

    _rate_limit()
    url = f"{FINNHUB_BASE}/stock/earnings"
    params = {"symbol": ticker, "token": FINNHUB_API_KEY}

    try:
        resp = requests.get(url, params=params, timeout=8)
        if resp.status_code == 429:
            logger.warning(f"[FINNHUB] Rate-limited on {ticker}, sleeping 10s")
            time.sleep(10)
            resp = requests.get(url, params=params, timeout=8)
        if resp.status_code != 200:
            logger.warning(
                f"[FINNHUB] {ticker}: HTTP {resp.status_code} — {resp.text[:100]}"
            )
            return []
        data = resp.json()
    except Exception as e:
        logger.warning(f"[FINNHUB] {ticker} request failed: {e}")
        return []

    if not isinstance(data, list) or not data:
        return []

    # Finnhub returns most-recent first. Keep only rows with actual+estimate.
    results: List[Dict] = []
    for i, row in enumerate(data[:n]):
        actual   = row.get("actual")
        estimate = row.get("estimate")
        if actual is None or estimate is None:
            continue

        # surprise % = (actual - estimate) / |estimate| * 100
        try:
            surprise_pct = (float(actual) - float(estimate)) / abs(float(estimate)) * 100 \
                if float(estimate) != 0 else None
        except (TypeError, ValueError, ZeroDivisionError):
            surprise_pct = None

        results.append({
            "period":       f"L{i + 1}",
            "date":         row.get("period"),  # YYYY-MM-DD of fiscal period
            "eps_actual":   actual,
            "eps_estimate": estimate,
            "surprise_pct": round(surprise_pct, 2) if surprise_pct is not None else None,
        })
    return results


def fetch_earnings_finnhub_batch(
    tickers: List[str],
    n: int = 2,
    progress_every: int = 50,
) -> Dict[str, List[Dict]]:
    """
    Batch wrapper — fetches earnings for each ticker sequentially under
    the free-tier rate limit. For 500 tickers expect ~9 minutes.

    Args:
        tickers:        Symbols to fetch.
        n:              Reports per ticker.
        progress_every: Log progress every N tickers.

    Returns:
        {ticker: [...]} — tickers with no data or errors are omitted.
    """
    if not FINNHUB_API_KEY:
        logger.warning(
            "[FINNHUB] FINNHUB_API_KEY not set — skipping Finnhub earnings. "
            "Register free at https://finnhub.io and add to .env"
        )
        return {}

    out: Dict[str, List[Dict]] = {}
    for i, t in enumerate(tickers, 1):
        data = fetch_earnings_finnhub(t, n=n)
        if data:
            out[t] = data
        if i % progress_every == 0:
            logger.info(f"[FINNHUB] Progress: {i}/{len(tickers)} tickers")

    logger.info(f"[FINNHUB] Fetched earnings for {len(out)}/{len(tickers)} tickers")
    return out

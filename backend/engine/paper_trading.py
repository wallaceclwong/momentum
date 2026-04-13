"""
Paper trading engine.
Records rebalance trades to DB and tracks live P&L via yfinance.
Works identically for both paper and live modes — only the order
execution layer differs (sandbox API vs production API).
"""
import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import yfinance as yf

from backend.db import SessionLocal, PaperPosition, PaperTrade

logger = logging.getLogger(__name__)

TRADING_MODE = os.getenv("TRADING_MODE", "paper")  # paper | live
INITIAL_CAPITAL = float(os.getenv("PAPER_CAPITAL", "100000"))


# ── Write side ────────────────────────────────────────────────

def record_rebalance(
    target_weights: Dict[str, float],
    ticker_to_sector: Dict[str, str],
    capital: float = INITIAL_CAPITAL,
    trading_mode: str = TRADING_MODE,
) -> str:
    """
    Record a full rebalance into paper_positions and paper_trades.
    Fetches current live prices to size positions.

    Args:
        target_weights: {ticker: weight} — must sum to ~1.0
        ticker_to_sector: {ticker: sector}
        capital: total portfolio value in USD
        trading_mode: 'paper' or 'live'

    Returns:
        rebalance_id (UUID string)
    """
    rebalance_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    tickers = list(target_weights.keys())

    # Fetch live prices for all tickers at once
    logger.info(f"Fetching live prices for {len(tickers)} tickers...")
    raw = yf.download(tickers, period="2d", interval="1d", progress=False, auto_adjust=True)
    prices: Dict[str, float] = {}
    for ticker in tickers:
        try:
            if len(tickers) == 1:
                price = float(raw["Close"].dropna().iloc[-1])
            else:
                price = float(raw["Close"][ticker].dropna().iloc[-1])
            prices[ticker] = price
        except Exception:
            logger.warning(f"Could not get price for {ticker}, skipping")

    db = SessionLocal()
    try:
        # Clear existing positions
        db.query(PaperPosition).delete()

        for ticker, weight in target_weights.items():
            price = prices.get(ticker)
            if not price:
                continue

            target_value = capital * weight
            shares = target_value / price
            sector = ticker_to_sector.get(ticker, "Unknown")

            # Record open position
            pos = PaperPosition(
                ticker=ticker,
                sector=sector,
                shares=round(shares, 6),
                entry_price=round(price, 4),
                entry_date=now,
                target_weight=weight,
                trading_mode=trading_mode,
            )
            db.add(pos)

            # Record trade log
            trade = PaperTrade(
                trade_date=now,
                action="BUY",
                ticker=ticker,
                sector=sector,
                shares=round(shares, 6),
                price=round(price, 4),
                total_value=round(target_value, 2),
                rebalance_id=rebalance_id,
                trading_mode=trading_mode,
            )
            db.add(trade)

        db.commit()
        logger.info(f"Recorded rebalance {rebalance_id}: {len(target_weights)} positions")
        return rebalance_id

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to record rebalance: {e}")
        raise
    finally:
        db.close()


# ── Read side ─────────────────────────────────────────────────

def get_live_portfolio(benchmark_tickers: List[str] = None) -> Dict:
    """
    Return current portfolio with live P&L.
    Also fetches benchmark prices for comparison.
    """
    if benchmark_tickers is None:
        benchmark_tickers = ["SPY", "SPMO", "QQQ"]

    db = SessionLocal()
    try:
        positions = db.query(PaperPosition).all()
        if not positions:
            return {"positions": [], "summary": None, "benchmarks": {}}

        tickers = [p.ticker for p in positions]
        all_fetch = tickers + benchmark_tickers

        # Fetch live prices
        raw = yf.download(all_fetch, period="2d", interval="1d", progress=False, auto_adjust=True)

        def get_price(ticker):
            try:
                close = raw["Close"]
                if hasattr(close, "columns"):
                    # MultiIndex or multi-ticker: close is a DataFrame
                    return float(close[ticker].dropna().iloc[-1])
                else:
                    # Single-ticker flat Series
                    return float(close.dropna().iloc[-1])
            except Exception:
                return None

        # Build position rows
        rows = []
        total_cost = 0.0
        total_value = 0.0

        for p in positions:
            current_price = get_price(p.ticker)
            if current_price is None:
                current_price = p.entry_price

            cost = p.shares * p.entry_price
            value = p.shares * current_price
            gain = value - cost
            gain_pct = (gain / cost * 100) if cost else 0

            rows.append({
                "ticker":        p.ticker,
                "sector":        p.sector,
                "shares":        round(p.shares, 4),
                "entry_price":   round(p.entry_price, 2),
                "current_price": round(current_price, 2),
                "cost_basis":    round(cost, 2),
                "market_value":  round(value, 2),
                "gain_loss":     round(gain, 2),
                "gain_loss_pct": round(gain_pct, 2),
                "target_weight": round((p.target_weight or 0) * 100, 2),
                "entry_date":    p.entry_date.isoformat() if p.entry_date else None,
            })
            total_cost += cost
            total_value += value

        total_gain = total_value - total_cost
        total_gain_pct = (total_gain / total_cost * 100) if total_cost else 0

        # Benchmark performance since first entry date
        first_entry = min(p.entry_date for p in positions)
        benchmarks = {}
        for bm in benchmark_tickers:
            try:
                bm_price_now = get_price(bm)
                bm_data = yf.download(bm, start=first_entry.strftime("%Y-%m-%d"),
                                      interval="1d",
                                      progress=False, auto_adjust=True)
                # Handle both flat and MultiIndex columns (yfinance version differences)
                close_col = bm_data["Close"]
                if hasattr(close_col, "columns"):
                    close_col = close_col.iloc[:, 0]
                close_series = close_col.dropna()
                bm_price_start = float(close_series.iloc[0])
                bm_return = ((bm_price_now - bm_price_start) / bm_price_start * 100) if bm_price_start else 0
                benchmarks[bm] = round(bm_return, 2)
            except Exception as e:
                logger.warning(f"Benchmark fetch failed for {bm}: {e}")
                benchmarks[bm] = None

        rows.sort(key=lambda x: x["gain_loss_pct"], reverse=True)

        return {
            "positions": rows,
            "summary": {
                "total_positions":  len(rows),
                "total_cost":       round(total_cost, 2),
                "total_value":      round(total_value, 2),
                "total_gain_loss":  round(total_gain, 2),
                "total_gain_pct":   round(total_gain_pct, 2),
                "trading_mode":     TRADING_MODE,
                "inception_date":   first_entry.isoformat(),
            },
            "benchmarks": benchmarks,
        }

    finally:
        db.close()


def get_trade_history(limit: int = 100) -> List[Dict]:
    """Return recent trade history."""
    db = SessionLocal()
    try:
        trades = (
            db.query(PaperTrade)
            .order_by(PaperTrade.trade_date.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "date":         t.trade_date.isoformat(),
                "action":       t.action,
                "ticker":       t.ticker,
                "sector":       t.sector,
                "shares":       round(t.shares, 4),
                "price":        round(t.price, 2),
                "total_value":  round(t.total_value, 2),
                "rebalance_id": t.rebalance_id,
                "mode":         t.trading_mode,
            }
            for t in trades
        ]
    finally:
        db.close()

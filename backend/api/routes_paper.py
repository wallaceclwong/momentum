"""
Paper (and live) portfolio API routes.
GET  /api/paper/portfolio   — live positions + P&L
GET  /api/paper/trades      — trade history
POST /api/paper/rebalance   — trigger a manual rebalance and record it
"""
import os
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks

from backend.engine.paper_trading import (
    get_live_portfolio,
    get_trade_history,
    record_rebalance,
    TRADING_MODE,
    INITIAL_CAPITAL,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/portfolio")
async def paper_portfolio():
    """Return current positions with live prices and P&L."""
    try:
        data = get_live_portfolio()
        return data
    except Exception as e:
        logger.error(f"Error fetching paper portfolio: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades")
async def paper_trades(limit: int = 100):
    """Return trade history."""
    try:
        return {"trades": get_trade_history(limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rebalance")
async def trigger_rebalance(background_tasks: BackgroundTasks):
    """
    Manually trigger a rebalance — runs screener, records trades to DB.
    Safe to call at any time (dry run of the monthly scheduler logic).
    """
    def _run():
        try:
            from backend.data.sp500 import get_ticker_to_sector, get_tickers_by_sector
            from backend.engine.portfolio import get_sector_etf_weights
            from backend.engine.momentum import calculate_momentum_for_tickers
            from backend.data.prices import fetch_price_history

            ticker_to_sector = get_ticker_to_sector()
            sector_to_tickers = get_tickers_by_sector()
            sector_weights = get_sector_etf_weights()
            all_tickers = list(ticker_to_sector.keys())

            price_data = fetch_price_history(all_tickers, period="6mo", interval="1d")
            momentum_data = calculate_momentum_for_tickers(price_data)

            target = {}
            for sector, tickers in sector_to_tickers.items():
                scores = [
                    (t, momentum_data[t]["composite_score"])
                    for t in tickers
                    if t in momentum_data and momentum_data[t].get("composite_score") is not None
                ]
                scores.sort(key=lambda x: x[1], reverse=True)
                top3 = [t for t, _ in scores[:3]]
                sw = sector_weights.get(sector, 0.0)
                if top3 and sw > 0:
                    w = sw / len(top3)
                    for t in top3:
                        target[t] = w

            record_rebalance(target, ticker_to_sector, capital=INITIAL_CAPITAL)
            logger.info(f"Manual rebalance complete: {len(target)} positions recorded")
        except Exception as e:
            logger.error(f"Background rebalance failed: {e}")

    background_tasks.add_task(_run)
    return {
        "status": "started",
        "message": "Rebalance running in background — check /api/paper/portfolio in ~30s",
        "trading_mode": TRADING_MODE,
    }

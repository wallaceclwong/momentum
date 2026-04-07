"""
Market regime filter.
Checks whether SPY is above or below its 200-day moving average.
"""
import logging
import pandas as pd
import yfinance as yf
from typing import Dict, Optional

from backend.config import REGIME_MA_DAYS, REGIME_BEAR_DEPLOYMENT

logger = logging.getLogger(__name__)


def get_regime(prices: Optional[pd.Series] = None) -> Dict:
    """
    Determine market regime from SPY price vs 200-day MA.

    Args:
        prices: Optional pre-loaded SPY price series (for backtesting).
                If None, fetches live data.

    Returns:
        {
            "bullish": bool,
            "spy_price": float,
            "spy_ma200": float,
            "deployment": float,   # 1.0 = fully invested, 0.5 = half
            "label": str,
        }
    """
    try:
        if prices is None:
            raw = yf.download("SPY", period="14mo", interval="1d",
                              progress=False, auto_adjust=True)
            if raw.empty:
                logger.warning("[REGIME] Could not fetch SPY data — assuming bullish")
                return _bullish_default()
            # Handle MultiIndex columns from yfinance
            if isinstance(raw.columns, pd.MultiIndex):
                prices = raw["Close"]["SPY"].dropna()
            else:
                prices = raw["Close"].dropna()
            prices = prices.squeeze()

        if len(prices) < REGIME_MA_DAYS + 1:
            logger.warning("[REGIME] Insufficient SPY history — assuming bullish")
            return _bullish_default()

        spy_price = float(prices.iloc[-1])
        ma200     = float(prices.iloc[-REGIME_MA_DAYS:].mean())
        bullish   = spy_price >= ma200
        deployment = 1.0 if bullish else REGIME_BEAR_DEPLOYMENT

        label = "BULL" if bullish else "BEAR"
        logger.info(f"[REGIME] {label}  SPY={spy_price:.2f}  MA200={ma200:.2f}  deploy={deployment:.0%}")

        return {
            "bullish":    bullish,
            "spy_price":  round(spy_price, 2),
            "spy_ma200":  round(ma200, 2),
            "deployment": deployment,
            "label":      label,
        }
    except Exception as e:
        logger.error(f"[REGIME] Error: {e} — assuming bullish")
        return _bullish_default()


def _bullish_default() -> Dict:
    return {"bullish": True, "spy_price": None, "spy_ma200": None,
            "deployment": 1.0, "label": "UNKNOWN"}

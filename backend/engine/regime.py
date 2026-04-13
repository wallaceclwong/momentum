"""
Market regime filter — graduated 5-state model.

States (deployment %):
  STRONG_BULL  : SPY > MA50 > MA200  AND  VIX < 20   →  100%
  BULL         : SPY > MA200         AND  VIX < 25   →   80%
  VOLATILE_BULL: SPY > MA200  but VIX 25–30          →   50%
  BEAR         : SPY < MA200         AND  VIX < 30   →   30%
  CRISIS       : SPY < MA200         AND  VIX >= 30  →   15%
"""
import logging
import pandas as pd
import yfinance as yf
from typing import Dict, Optional

from backend.config import (
    REGIME_MA_DAYS, REGIME_MA_SHORT,
    REGIME_VIX_HIGH, REGIME_VIX_EXTREME,
    REGIME_STRONG_BULL, REGIME_BULL, REGIME_VOLATILE_BULL,
    REGIME_BEAR, REGIME_CRISIS,
)

logger = logging.getLogger(__name__)


def _fetch_vix() -> Optional[float]:
    """Fetch current CBOE VIX level."""
    try:
        raw = yf.download("^VIX", period="5d", interval="1d",
                          progress=False, auto_adjust=True)
        if raw.empty:
            return None
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw["Close"].iloc[:, 0]
        else:
            close = raw["Close"]
        return float(close.dropna().iloc[-1])
    except Exception as e:
        logger.warning(f"[REGIME] VIX fetch failed: {e}")
        return None


def get_regime(
    prices: Optional[pd.Series] = None,
    vix: Optional[float] = None,
) -> Dict:
    """
    Determine market regime using SPY MA50/MA200 and VIX.

    Args:
        prices: Optional pre-loaded SPY price series (backtesting).
                If None, fetches live data.
        vix:    Optional pre-loaded VIX value (backtesting).
                If None and prices is None, fetches live VIX.

    Returns:
        {
            "label":      str,    e.g. "STRONG_BULL"
            "bullish":    bool,
            "spy_price":  float,
            "spy_ma50":   float,
            "spy_ma200":  float,
            "vix":        float | None,
            "deployment": float,  fraction of capital to deploy
        }
    """
    try:
        if prices is None:
            raw = yf.download("SPY", period="14mo", interval="1d",
                              progress=False, auto_adjust=True)
            if raw.empty:
                logger.warning("[REGIME] Could not fetch SPY — defaulting to BULL")
                return _default("BULL")
            prices = (
                raw["Close"]["SPY"].dropna()
                if isinstance(raw.columns, pd.MultiIndex)
                else raw["Close"].dropna()
            ).squeeze()

        if len(prices) < REGIME_MA_DAYS + 1:
            logger.warning("[REGIME] Insufficient SPY history — defaulting to BULL")
            return _default("BULL")

        spy_price = float(prices.iloc[-1])
        ma200 = float(prices.iloc[-REGIME_MA_DAYS:].mean())
        ma50  = float(prices.iloc[-REGIME_MA_SHORT:].mean()) if len(prices) >= REGIME_MA_SHORT else spy_price

        # Fetch live VIX only when not in backtest mode (prices=None originally)
        if vix is None:
            vix = _fetch_vix()

        label, deployment = _classify(spy_price, ma50, ma200, vix)
        bullish = spy_price >= ma200

        vix_str = f"{vix:.1f}" if vix else "N/A"
        logger.info(
            f"[REGIME] {label}  SPY={spy_price:.2f}  MA50={ma50:.2f}  "
            f"MA200={ma200:.2f}  VIX={vix_str}  deploy={deployment:.0%}"
        )

        return {
            "label":      label,
            "bullish":    bullish,
            "spy_price":  round(spy_price, 2),
            "spy_ma50":   round(ma50, 2),
            "spy_ma200":  round(ma200, 2),
            "vix":        round(vix, 2) if vix else None,
            "deployment": deployment,
        }

    except Exception as e:
        logger.error(f"[REGIME] Error: {e} — defaulting to BULL")
        return _default("BULL")


def _classify(
    spy: float, ma50: float, ma200: float, vix: Optional[float]
) -> tuple:
    """Map SPY + VIX state to (label, deployment)."""
    above_ma200 = spy >= ma200
    above_ma50  = spy >= ma50
    v = vix if vix is not None else 15.0  # assume calm if VIX unavailable

    if above_ma200 and above_ma50 and v < REGIME_VIX_HIGH:
        return "STRONG_BULL",   REGIME_STRONG_BULL
    if above_ma200 and v < 25:
        return "BULL",          REGIME_BULL
    if above_ma200 and v < REGIME_VIX_EXTREME:
        return "VOLATILE_BULL", REGIME_VOLATILE_BULL
    if not above_ma200 and v < REGIME_VIX_EXTREME:
        return "BEAR",          REGIME_BEAR
    return "CRISIS",            REGIME_CRISIS


def _default(label: str) -> Dict:
    deployment = {
        "STRONG_BULL":   REGIME_STRONG_BULL,
        "BULL":          REGIME_BULL,
        "VOLATILE_BULL": REGIME_VOLATILE_BULL,
        "BEAR":          REGIME_BEAR,
        "CRISIS":        REGIME_CRISIS,
    }.get(label, REGIME_BULL)
    return {
        "label": label, "bullish": label in ("STRONG_BULL", "BULL", "VOLATILE_BULL"),
        "spy_price": None, "spy_ma50": None, "spy_ma200": None,
        "vix": None, "deployment": deployment,
    }

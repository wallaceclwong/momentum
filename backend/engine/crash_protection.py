"""
Momentum crash protection — Barroso & Santa-Clara (2015).

Scales portfolio exposure inversely to recent realised portfolio volatility,
targeting a constant annualised vol. This shrinks position sizes before and
during momentum crashes (rapid reversals) — the primary unhedged risk of
pure momentum strategies.

Formula:  scale = min(1.0, TARGET_VOL / realized_vol_annualised)

The cap at 1.0 means we never lever up in calm markets.
"""
import pandas as pd
import numpy as np
import logging
from typing import Dict, Optional

from backend.config import CRASH_PROTECTION_TARGET_VOL, CRASH_PROTECTION_LOOKBACK

logger = logging.getLogger(__name__)


def compute_crash_scale(
    portfolio_weights: Dict[str, float],
    price_df: pd.DataFrame,
    lookback: int = None,
    target_vol: float = None,
) -> float:
    """
    Compute the volatility-scaling factor for the current portfolio.

    Args:
        portfolio_weights: {ticker: weight} of the CURRENT (not new) portfolio.
                           Used to compute realised portfolio returns.
        price_df:          DataFrame with at least (lookback+5) rows of price
                           history; columns are ticker symbols.
        lookback:          Days of history to estimate vol (default from config).
        target_vol:        Annualised vol target (default from config).

    Returns:
        Scalar in (0, 1]. Multiply regime deployment by this before sizing.
    """
    lookback    = lookback    or CRASH_PROTECTION_LOOKBACK
    target_vol  = target_vol  or CRASH_PROTECTION_TARGET_VOL

    if not portfolio_weights:
        return 1.0

    tickers = [t for t in portfolio_weights if t in price_df.columns]
    if not tickers:
        return 1.0

    prices = price_df[tickers].iloc[-(lookback + 2):]
    rets   = prices.pct_change().dropna()

    if len(rets) < max(5, lookback // 3):
        logger.debug("[CRASH] Insufficient history for vol estimate — scale=1.0")
        return 1.0

    w = pd.Series({t: portfolio_weights[t] for t in tickers})
    w = w / w.sum()

    port_rets    = (rets * w).sum(axis=1)
    realized_vol = float(port_rets.std() * (252 ** 0.5))

    if realized_vol <= 0:
        return 1.0

    scale = round(min(1.0, target_vol / realized_vol), 4)
    logger.info(
        f"[CRASH] realized_vol={realized_vol:.1%}  "
        f"target={target_vol:.1%}  scale={scale:.3f}"
    )
    return scale

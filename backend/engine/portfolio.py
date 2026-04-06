"""Portfolio allocation engine - applies sector ETF weights to picks."""
from typing import Dict, List
import yfinance as yf
import logging

from backend.config import SECTORS, SECTOR_TO_ETF

logger = logging.getLogger(__name__)


def get_sector_etf_weights() -> Dict[str, float]:
    """
    Fetch current sector ETF market cap weights.
    
    Uses the market cap of each sector ETF as a proxy for sector weight.
    In production, you might use actual S&P 500 sector weights from an index provider.
    
    Returns:
        Dict mapping sector_name -> weight (0-1, sum to ~1.0)
    """
    etf_market_caps = {}
    total_market_cap = 0
    
    for etf_ticker, sector_name in SECTORS.items():
        try:
            etf = yf.Ticker(etf_ticker)
            info = etf.info
            
            # Try to get market cap or AUM proxy
            market_cap = info.get("totalAssets") or info.get("marketCap")
            
            if market_cap:
                etf_market_caps[sector_name] = market_cap
                total_market_cap += market_cap
            else:
                # Fallback: use equal weight if data unavailable
                logger.warning(f"No market cap for {etf_ticker}, using equal weight")
                
        except Exception as e:
            logger.warning(f"Failed to fetch ETF data for {etf_ticker}: {e}")
    
    if not etf_market_caps or total_market_cap == 0:
        # Equal weights fallback
        logger.warning("Using equal sector weights due to data fetch failure")
        n_sectors = len(SECTORS)
        return {sector: 1.0 / n_sectors for sector in SECTORS.values()}
    
    # Normalize to percentages
    weights = {
        sector: cap / total_market_cap
        for sector, cap in etf_market_caps.items()
    }
    
    logger.info(f"Sector weights sum: {sum(weights.values()):.4f}")
    return weights


def allocate_portfolio(
    screener_results: Dict[str, List[Dict]],
    equal_sector_weight: bool = False
) -> List[Dict]:
    """
    Allocate capital to selected stocks using sector ETF weights.
    
    Each sector's budget is divided equally among its Top N picks.
    
    Args:
        screener_results: Output from screener.run_momentum_screener
        equal_sector_weight: If True, use equal weights (1/11 each sector)
                          If False, use live ETF market cap weights
    
    Returns:
        List of portfolio holdings with: ticker, sector, sector_weight, 
                                          position_weight, momentum_metrics
    """
    if equal_sector_weight:
        n_sectors = len([s for s in screener_results.values() if s])  # Only count sectors with picks
        sector_weights = {
            sector: 1.0 / n_sectors if n_sectors > 0 else 0
            for sector in screener_results.keys()
        }
    else:
        sector_weights = get_sector_etf_weights()
    
    portfolio = []
    
    for sector, picks in screener_results.items():
        if not picks:
            continue
        
        sector_budget = sector_weights.get(sector, 0)
        
        # Divide sector budget equally among top picks
        n_picks = len(picks)
        position_weight = sector_budget / n_picks if n_picks > 0 else 0
        
        for pick in picks:
            holding = {
                "ticker": pick["ticker"],
                "sector": sector,
                "sector_etf": pick.get("sector_etf"),
                "sector_weight": round(sector_budget * 100, 2),  # as %
                "position_weight": round(position_weight * 100, 2),  # as %
                "returns_4w": pick.get("returns", {}).get("4W"),
                "returns_13w": pick.get("returns", {}).get("13W"),
                "returns_26w": pick.get("returns", {}).get("26W"),
                "composite_score": pick.get("composite_score"),
                "l1_surprise": pick.get("l1_surprise"),
                "l2_surprise": pick.get("l2_surprise"),
            }
            portfolio.append(holding)
    
    # Normalize weights to ensure they sum to 100%
    total_weight = sum(h["position_weight"] for h in portfolio)
    if total_weight > 0 and abs(total_weight - 100) > 0.01:
        for holding in portfolio:
            holding["position_weight"] = round(
                holding["position_weight"] / total_weight * 100, 2
            )
    
    logger.info(f"Allocated portfolio with {len(portfolio)} positions")
    return portfolio


def get_portfolio_summary(portfolio: List[Dict]) -> Dict:
    """
    Generate summary statistics for the portfolio.
    
    Args:
        portfolio: Output from allocate_portfolio
    
    Returns:
        Summary dict with sector breakdown, avg returns, etc.
    """
    if not portfolio:
        return {"error": "Empty portfolio"}
    
    # Sector breakdown
    sector_counts = {}
    sector_weights = {}
    for holding in portfolio:
        sector = holding["sector"]
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        sector_weights[sector] = sector_weights.get(sector, 0) + holding["position_weight"]
    
    # Average returns
    avg_4w = sum(h["returns_4w"] or 0 for h in portfolio) / len(portfolio)
    avg_13w = sum(h["returns_13w"] or 0 for h in portfolio) / len(portfolio)
    avg_26w = sum(h["returns_26w"] or 0 for h in portfolio) / len(portfolio)
    
    return {
        "total_positions": len(portfolio),
        "sector_breakdown": sector_counts,
        "sector_weights": {s: round(w, 2) for s, w in sector_weights.items()},
        "avg_4w_return": round(avg_4w, 2),
        "avg_13w_return": round(avg_13w, 2),
        "avg_26w_return": round(avg_26w, 2),
    }

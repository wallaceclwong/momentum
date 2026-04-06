#!/usr/bin/env python3
"""
CLI entry point for S&P 500 Momentum Screener.

Usage:
    python run_screener.py

Outputs a clean table of top momentum picks by sector with sector ETF weights.
"""

import sys
import os

# Ensure project root is in sys.path for backend.* imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
from tabulate import tabulate

from backend.config import SECTORS, TOP_N_PER_SECTOR
from backend.engine.screener import run_momentum_screener, get_screener_summary
from backend.engine.portfolio import allocate_portfolio, get_portfolio_summary

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def format_return(val: float | None) -> str:
    """Format return value with color coding."""
    if val is None:
        return "N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.1f}%"


def format_surprise(val: float | None) -> str:
    """Format earnings surprise with color coding."""
    if val is None:
        return "N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.1f}%"


def print_results(portfolio: list, summary: dict):
    """Print screener results in a clean table format."""
    
    print("\n" + "=" * 100)
    print("S&P 500 SECTOR MOMENTUM SCREENER")
    print("=" * 100)
    print(f"Run Date: {summary.get('timestamp', 'N/A')}")
    print(f"Total Positions: {summary.get('total_positions', 0)}")
    print(f"Sectors with Picks: {summary.get('sectors_with_picks', 0)}/11")
    print(f"Avg Returns: 4W={summary.get('avg_4w_return', 0):.1f}% | "
          f"13W={summary.get('avg_13w_return', 0):.1f}% | "
          f"26W={summary.get('avg_26w_return', 0):.1f}%")
    print("=" * 100)
    
    # Group by sector for display
    from collections import defaultdict
    by_sector = defaultdict(list)
    for holding in portfolio:
        by_sector[holding["sector"]].append(holding)
    
    # Print each sector
    for sector_name in SECTORS.values():
        picks = by_sector.get(sector_name, [])
        if not picks:
            continue
        
        etf = picks[0].get("sector_etf", "N/A")
        sector_weight = picks[0].get("sector_weight", 0)
        
        print(f"\n🔹 {sector_name} ({etf}) — Sector Weight: {sector_weight:.1f}%")
        print("-" * 95)
        
        # Prepare table rows
        rows = []
        for pick in picks:
            rows.append([
                pick["ticker"],
                format_return(pick.get("returns_4w")),
                format_return(pick.get("returns_13w")),
                format_return(pick.get("returns_26w")),
                format_surprise(pick.get("l1_surprise")),
                format_surprise(pick.get("l2_surprise")),
                f"{pick.get('position_weight', 0):.1f}%",
            ])
        
        headers = ["Ticker", "4W", "13W", "26W", "L1 Surprise", "L2 Surprise", "Weight"]
        print(tabulate(rows, headers=headers, tablefmt="simple", stralign="right"))
    
    print("\n" + "=" * 100)
    print(f"Total Portfolio Weight: {sum(h.get('position_weight', 0) for h in portfolio):.1f}%")
    print("=" * 100)


def main():
    """Run the momentum screener."""
    logger.info("Starting S&P 500 Momentum Screener...")
    logger.info("Fetching data and calculating momentum (this may take a few minutes)...")
    
    try:
        # Run screener
        screener_results = run_momentum_screener(top_n=TOP_N_PER_SECTOR)
        
        # Generate screener summary
        screener_summary = get_screener_summary(screener_results)
        
        # Allocate portfolio
        portfolio = allocate_portfolio(
            screener_results,
            equal_sector_weight=False  # Use live ETF weights
        )
        
        # Generate portfolio summary
        portfolio_summary = get_portfolio_summary(portfolio)
        
        # Merge summaries for display
        display_summary = {
            **screener_summary,
            **portfolio_summary,
        }
        
        # Print results
        print_results(portfolio, display_summary)
        
        logger.info("Screener completed successfully!")
        return 0
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Screener failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

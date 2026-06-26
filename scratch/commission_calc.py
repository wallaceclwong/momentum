
import sys
import os
import pandas as pd
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(os.getcwd())))

from backend.data.sp500 import get_ticker_to_sector, get_tickers_by_sector
from backend.engine.portfolio import get_sector_etf_weights
from backend.engine.momentum import calculate_momentum_for_tickers
from backend.data.prices import fetch_price_history
from backend.config import USE_VOLATILITY_WEIGHTING, MAX_POSITION_WEIGHT, USE_EARNINGS_IN_SCREENER, EARNINGS_LOOKBACK
from backend.data.earnings import get_earnings_surprises_batch
from backend.engine.earnings_filter import filter_by_earnings_momentum

def calculate_ibkr_commission(capital=390000):
    print(f"--- Calculating IBKR Commissions for ${capital:,.0f} ---")
    
    # 1. Run Screener Logic (simplified from get_target_weights)
    ticker_to_sector = get_ticker_to_sector()
    sector_to_tickers = get_tickers_by_sector()
    sector_weights = get_sector_etf_weights()
    all_tickers = list(ticker_to_sector.keys())

    print("Fetching price data...")
    price_data = fetch_price_history(all_tickers, period="1y", interval="1d")
    
    earnings_data = {}
    if USE_EARNINGS_IN_SCREENER:
        print("Fetching earnings data...")
        try:
            earnings_data = get_earnings_surprises_batch(list(price_data.keys()), n=EARNINGS_LOOKBACK)
        except Exception as e:
            print(f"Earnings fetch failed: {e}")

    print("Calculating momentum...")
    momentum_data = calculate_momentum_for_tickers(price_data, earnings_data=earnings_data or None)

    target_weights = {}
    prices = {}
    
    for sector, tickers in sector_to_tickers.items():
        scores = [
            (t, momentum_data[t]["composite_score"])
            for t in tickers
            if t in momentum_data and momentum_data[t].get("composite_score") is not None
        ]
        scores.sort(key=lambda x: x[1], reverse=True)
        top6 = [t for t, _ in scores[:6]]
        
        if earnings_data:
            passed = filter_by_earnings_momentum(top6, earnings_data)
            top3 = passed[:3] if passed else top6[:3]
        else:
            top3 = top6[:3]
            
        sw = sector_weights.get(sector, 0.0)
        if not top3 or sw <= 0:
            continue

        if USE_VOLATILITY_WEIGHTING:
            vols = [momentum_data[t].get("volatility") for t in top3]
            if all(v is not None and v > 0 for v in vols):
                inv_vols = [1.0 / v for v in vols]
                total_inv = sum(inv_vols)
                for t, iv in zip(top3, inv_vols):
                    target_weights[t] = sw * (iv / total_inv)
                continue

        w = sw / len(top3)
        for t in top3:
            target_weights[t] = w

    # Concentration cap
    capped = {t: min(w, MAX_POSITION_WEIGHT) for t, w in target_weights.items()}
    # (Normalization logic omitted for brevity as it's a small adjustment)
    
    # Get current prices for share calculation
    for ticker in capped:
        if ticker in price_data:
            prices[ticker] = price_data[ticker]["Close"].iloc[-1]

    # 2. Commission Calculation
    total_fixed = 0
    total_tiered = 0
    total_shares = 0
    results = []

    for ticker, weight in capped.items():
        price = prices.get(ticker)
        if not price: continue
        
        pos_value = capital * weight
        shares = int(pos_value / price)
        if shares == 0: continue
        
        # IBKR Fixed: $0.005/share, min $1.0, max 1%
        fixed = max(1.0, shares * 0.005)
        fixed = min(fixed, pos_value * 0.01)
        
        # IBKR Tiered: $0.0035/share, min $0.35, plus ~ $0.0005 fees
        tiered = max(0.35, shares * 0.0035) + (shares * 0.0005) # approximation
        
        total_fixed += fixed
        total_tiered += tiered
        total_shares += shares
        
        results.append({
            "ticker": ticker,
            "value": pos_value,
            "shares": shares,
            "price": price,
            "fixed": fixed,
            "tiered": tiered
        })

    print(f"\nResults for {len(results)} positions:")
    print(f"Total Shares: {total_shares}")
    print(f"Total Portfolio Value: ${sum(r['value'] for r in results):,.2f}")
    print("-" * 40)
    print(f"Total IBKR Fixed Commission:  ${total_fixed:.2f}")
    print(f"Total IBKR Tiered Commission: ${total_tiered:.2f} (Estimated)")
    print("-" * 40)
    print(f"Cost basis effect: { (total_fixed/capital)*100:.3f}%")

if __name__ == "__main__":
    calculate_ibkr_commission(390000)

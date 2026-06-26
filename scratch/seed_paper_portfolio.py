
from backend.db import SessionLocal, PaperPosition, PaperTrade
from datetime import datetime

# The 33 picks from the report
picks = [
    ("SNDK", 71, 97.62, "Information Technology", 2.1),
    ("LITE", 98, 70.71, "Information Technology", 2.1),
    ("CIEN", 131, 52.75, "Information Technology", 2.1),
    ("VZ", 185, 60.65, "Communication Services", 3.4),
    ("SATS", 417, 26.88, "Communication Services", 3.4),
    ("LYV", 100, 111.45, "Communication Services", 3.4),
    ("ROST", 56, 153.22, "Consumer Discretionary", 2.6),
    ("TPR", 165, 51.98, "Consumer Discretionary", 2.6),
    ("SBUX", 92, 93.00, "Consumer Discretionary", 2.6),
    ("BG", 143, 85.38, "Consumer Staples", 3.7),
    ("TGT", 68, 178.50, "Consumer Staples", 3.7),
    ("CASY", 16, 741.84, "Consumer Staples", 3.7),
    ("VLO", 35, 235.54, "Energy", 2.5),
    ("TRGP", 34, 239.82, "Energy", 2.5),
    ("HAL", 219, 37.67, "Energy", 2.5),
    ("CBOE", 31, 305.44, "Financials", 2.9),
    ("CME", 32, 297.84, "Financials", 2.9),
    ("CB", 29, 329.34, "Financials", 2.9),
    ("MRNA", 220, 53.99, "Health Care", 3.6),
    ("JNJ", 50, 237.55, "Health Care", 3.6),
    ("MRK", 100, 117.74, "Health Care", 3.6),
    ("VRT", 29, 297.62, "Industrials", 2.7),
    ("FIX", 5, 1627.24, "Industrials", 2.7),
    ("PWR", 15, 585.68, "Industrials", 2.7),
    ("DOW", 228, 39.01, "Materials", 2.7),
    ("CF", 74, 120.17, "Materials", 2.7),
    ("LYB", 121, 73.23, "Materials", 2.7),
    ("IRM", 105, 113.12, "Real Estate", 3.6),
    ("VTR", 139, 84.87, "Real Estate", 3.6),
    ("DLR", 61, 194.54, "Real Estate", 3.6),
    ("EIX", 161, 71.38, "Utilities", 3.5),
    ("NEE", 127, 90.57, "Utilities", 3.5),
    ("AEP", 85, 134.80, "Utilities", 3.5),
]

db = SessionLocal()
try:
    print(f"Seeding {len(picks)} positions into paper portfolio...")
    now = datetime.now()
    rebalance_id = f"INITIAL_330K_{now.strftime('%Y%m%d')}"
    
    for ticker, shares, price, sector, weight in picks:
        # 1. Add Position
        pos = PaperPosition(
            ticker=ticker,
            shares=float(shares),
            entry_price=float(price),
            entry_date=now,
            sector=sector,
            target_weight=float(weight),
            trading_mode="paper"
        )
        db.add(pos)
        
        # 2. Record Trade for history
        trade = PaperTrade(
            ticker=ticker,
            action="BUY",
            shares=float(shares),
            price=float(price),
            total_value=float(shares * price),
            sector=sector,
            trade_date=now,
            rebalance_id=rebalance_id,
            trading_mode="paper"
        )
        db.add(trade)
    
    db.commit()
    print("Portfolio seeded successfully!")
finally:
    db.close()

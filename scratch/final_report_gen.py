
import yfinance as yf
import pandas as pd

tickers = [
    "SNDK", "LITE", "CIEN",
    "VZ", "SATS", "LYV",
    "ROST", "TPR", "SBUX",
    "BG", "TGT", "CASY",
    "VLO", "TRGP", "HAL",
    "CBOE", "CME", "CB",
    "MRNA", "JNJ", "MRK",
    "VRT", "FIX", "PWR",
    "DOW", "CF", "LYB",
    "IRM", "VTR", "DLR",
    "EIX", "NEE", "AEP"
]

# Weights from the report
weights = {
    "SNDK": 2.1, "LITE": 2.1, "CIEN": 2.1,
    "VZ": 3.4, "SATS": 3.4, "LYV": 3.4,
    "ROST": 2.6, "TPR": 2.6, "SBUX": 2.6,
    "BG": 3.7, "TGT": 3.7, "CASY": 3.7,
    "VLO": 2.5, "TRGP": 2.5, "HAL": 2.5,
    "CBOE": 2.9, "CME": 2.9, "CB": 2.9,
    "MRNA": 3.6, "JNJ": 3.6, "MRK": 3.6,
    "VRT": 2.7, "FIX": 2.7, "PWR": 2.7,
    "DOW": 2.7, "CF": 2.7, "LYB": 2.7,
    "IRM": 3.6, "VTR": 3.6, "DLR": 3.6,
    "EIX": 3.5, "NEE": 3.5, "AEP": 3.5
}

capital = 330000

print("Fetching prices...")
data = yf.download(tickers, period="5d", interval="1d", progress=False, auto_adjust=True)
prices = {t: data["Close"][t].dropna().iloc[-1] for t in tickers if t in data["Close"]}

report = []
total_val = 0
for t in tickers:
    p = prices.get(t)
    w = weights.get(t, 0) / 100
    if p:
        val = capital * w
        shares = int(val / p)
        total_val += (shares * p)
        report.append({
            "ticker": t,
            "shares": shares,
            "price": p,
            "value": shares * p,
            "weight": w * 100
        })

print("\n| Ticker | Shares | Price | Value | Weight |")
print("| :--- | :--- | :--- | :--- | :--- |")
for r in report:
    print(f"| {r['ticker']} | {r['shares']} | ${r['price']:.2f} | ${r['value']:,.2f} | {r['weight']:.1f}% |")

print(f"\nTotal Invested: ${total_val:,.2f}")

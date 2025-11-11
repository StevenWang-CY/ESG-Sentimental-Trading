"""
Debug script to examine price data structure
"""
import pandas as pd
import pickle
from datetime import datetime

# Load prices
with open('data/prices_2024-08-01_to_2024-10-01.pkl', 'rb') as f:
    prices = pickle.load(f)

print("="*60)
print("PRICE DATA STRUCTURE ANALYSIS")
print("="*60)

print(f"\nPrice data type: {type(prices)}")
print(f"Price data shape: {prices.shape}")
print(f"\nIndex type: {type(prices.index)}")
print(f"Is MultiIndex: {isinstance(prices.index, pd.MultiIndex)}")

if isinstance(prices.index, pd.MultiIndex):
    print(f"Index levels: {prices.index.names}")
    print(f"Index level 0 (dates): {len(prices.index.get_level_values(0).unique())} unique")
    print(f"Index level 1 (tickers): {prices.index.get_level_values(1).unique().tolist()}")
else:
    print(f"Index: {prices.index[:10]}")

print(f"\nColumns: {prices.columns.tolist()}")

print("\n" + "="*60)
print("SAMPLE PRICE DATA")
print("="*60)
print(prices.head(20))

print("\n" + "="*60)
print("CHECK SPECIFIC DATES")
print("="*60)

target_dates = [
    datetime(2024, 7, 12),
    datetime(2024, 8, 19),
    datetime(2024, 10, 2)
]

tickers = ['AVGO', 'AMD']

for ticker in tickers:
    print(f"\nTicker: {ticker}")
    for date in target_dates:
        print(f"  Date: {date}")
        try:
            if isinstance(prices.index, pd.MultiIndex):
                # Try to get price using MultiIndex
                ticker_data = prices.xs(ticker, level='ticker')
                if date in ticker_data.index:
                    price = ticker_data.loc[date, 'Close']
                    print(f"    Price (exact match): {price}")
                else:
                    # Try forward-fill (most recent past date)
                    past_dates = ticker_data.index[ticker_data.index <= date]
                    if len(past_dates) > 0:
                        nearest_date = past_dates.max()
                        price = ticker_data.loc[nearest_date, 'Close']
                        print(f"    Price (forward-fill from {nearest_date}): {price}")
                    else:
                        print(f"    No price data available (before first date)")
            else:
                if date in prices.index:
                    price = prices.loc[date, ticker]
                    print(f"    Price: {price}")
                else:
                    print(f"    Date not in index")
        except Exception as e:
            print(f"    ERROR: {e}")

print("\n" + "="*60)

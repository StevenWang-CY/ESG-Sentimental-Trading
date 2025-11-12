"""
Debug script to diagnose trade execution issue
"""
import pandas as pd
import pickle

# Load portfolio
portfolio = pd.read_csv('data/portfolio_2024-02-01_to_2025-11-10.csv')
portfolio['date'] = pd.to_datetime(portfolio['date'])

# Load prices
with open('data/prices_2024-02-01_to_2025-11-10.pkl', 'rb') as f:
    prices = pickle.load(f)

print("="*60)
print("DIAGNOSTIC: Date Alignment Check")
print("="*60)

# Get portfolio dates (rebalance dates)
portfolio_dates = sorted(portfolio['date'].unique())
print(f"\nPortfolio has {len(portfolio_dates)} unique signal dates")
print(f"Date range: {portfolio_dates[0]} to {portfolio_dates[-1]}")
print(f"\nFirst 10 signal dates:")
for i, date in enumerate(portfolio_dates[:10]):
    print(f"  {i+1}. {date}")

# Get price dates
if isinstance(prices.index, pd.MultiIndex):
    price_dates = sorted(prices.index.get_level_values(0).unique())
else:
    price_dates = sorted(prices.index.unique())

print(f"\nPrice data has {len(price_dates)} trading days")
print(f"Date range: {price_dates[0]} to {price_dates[-1]}")
print(f"\nFirst 10 price dates:")
for i, date in enumerate(price_dates[:10]):
    print(f"  {i+1}. {date}")

# Check overlap
matching_dates = [d for d in portfolio_dates if d in price_dates]
print(f"\n{'='*60}")
print(f"OVERLAP ANALYSIS")
print(f"{'='*60}")
print(f"Signal dates that exist in price data: {len(matching_dates)}/{len(portfolio_dates)}")

if len(matching_dates) == 0:
    print("\n⚠ CRITICAL: NO OVERLAP! This is why no trades execute.")
    print("\nChecking date types:")
    print(f"  Portfolio date type: {type(portfolio_dates[0])}")
    print(f"  Price date type: {type(price_dates[0])}")

    # Check if it's a timezone issue
    print(f"\n  Portfolio date sample: {portfolio_dates[0]}")
    print(f"  Price date sample: {price_dates[0]}")

    # Find nearest matches
    print(f"\nNearest price dates to first signal date:")
    target = portfolio_dates[0]
    for pd_date in price_dates[:20]:
        if abs((pd_date - target).days) < 7:
            print(f"  {pd_date} (diff: {(pd_date - target).days} days)")
else:
    print(f"\n✓ Found {len(matching_dates)} matching dates")
    print(f"\nMatching dates:")
    for i, date in enumerate(matching_dates[:10]):
        print(f"  {i+1}. {date}")

print("\n" + "="*60)

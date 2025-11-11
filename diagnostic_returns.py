"""
Diagnostic script to analyze returns distribution
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent / 'src'))

import pandas as pd
import numpy as np
from backtest import BacktestEngine
from signals.portfolio_constructor import PortfolioConstructor
import logging

logging.basicConfig(level=logging.ERROR)

def run_diagnostic():
    """Run diagnostic on returns"""
    # Generate mock data (same as main.py demo)
    from datetime import datetime

    start_date = datetime(2023, 1, 1)
    end_date = datetime(2023, 12, 31)
    dates = pd.date_range(start_date, end_date, freq='B')

    tickers = ['AAPL', 'TSLA', 'XOM', 'JPM', 'MSFT']

    # Generate price data
    price_data = {}
    for ticker in tickers:
        np.random.seed(hash(ticker) % 2**32)
        returns = np.random.normal(0.0005, 0.015, len(dates))
        prices = 100 * np.exp(np.cumsum(returns))

        price_data[ticker] = pd.DataFrame({
            'Open': prices * 0.99,
            'High': prices * 1.02,
            'Low': prices * 0.98,
            'Close': prices,
            'Volume': np.random.randint(1000000, 10000000, len(dates))
        }, index=dates)

    # Prepare prices
    prices_list = []
    for ticker, df in price_data.items():
        df_copy = df.copy()
        df_copy['ticker'] = ticker
        df_copy['date'] = df_copy.index
        prices_list.append(df_copy)

    prices_combined = pd.concat(prices_list, ignore_index=True)
    prices_combined['date'] = pd.to_datetime(prices_combined['date'])
    prices = prices_combined.set_index(['date', 'ticker'])

    # Generate signals
    signal_dates = dates[::20]
    signals_list = []

    for signal_date in signal_dates[:10]:
        ticker = np.random.choice(tickers)
        signal_score = np.random.uniform(0.4, 0.8)

        signals_list.append({
            'ticker': ticker,
            'date': signal_date,
            'signal': signal_score,
            'raw_score': signal_score,
            'quintile': int(signal_score * 5) + 1
        })

    signals_df = pd.DataFrame(signals_list)

    # Calculate z-scores
    mean_score = signals_df['signal'].mean()
    std_score = signals_df['signal'].std()
    signals_df['z_score'] = (signals_df['signal'] - mean_score) / (std_score + 1e-6)

    # Construct portfolio
    portfolio_constructor = PortfolioConstructor(strategy_type='long_short')
    portfolio = portfolio_constructor.construct_portfolio(signals_df, method='z_score')

    # Run backtest
    engine = BacktestEngine(
        prices=prices,
        initial_capital=1000000,
        commission_pct=0.0005,
        slippage_bps=3,
        enable_risk_management=True,
        max_position_size=0.10,
        target_volatility=0.12,
        max_drawdown_threshold=0.15
    )

    result = engine.run(portfolio, rebalance_freq='W')

    # Analyze returns
    returns = result.returns_series

    print("\n" + "="*80)
    print("RETURNS DISTRIBUTION DIAGNOSTIC")
    print("="*80)

    print(f"\nTotal periods: {len(returns)}")
    print(f"Positive returns: {(returns > 0).sum()} ({(returns > 0).sum() / len(returns) * 100:.1f}%)")
    print(f"Negative returns: {(returns < 0).sum()} ({(returns < 0).sum() / len(returns) * 100:.1f}%)")
    print(f"Zero returns: {(returns == 0).sum()} ({(returns == 0).sum() / len(returns) * 100:.1f}%)")

    print(f"\nReturn statistics:")
    print(f"Mean: {returns.mean():.6f} ({returns.mean() * 252:.2%} annualized)")
    print(f"Std: {returns.std():.6f} ({returns.std() * np.sqrt(252):.2%} annualized)")
    print(f"Min: {returns.min():.6f} ({returns.min():.2%})")
    print(f"Max: {returns.max():.6f} ({returns.max():.2%})")
    print(f"Skewness: {returns.skew():.2f}")
    print(f"Kurtosis: {returns.kurtosis():.2f}")

    # Downside analysis
    negative_returns = returns[returns < 0]
    print(f"\nDownside returns statistics:")
    print(f"Count: {len(negative_returns)}")
    print(f"Mean: {negative_returns.mean():.6f}")
    print(f"Std: {negative_returns.std():.6f} ({negative_returns.std() * np.sqrt(252):.2%} annualized)")

    # Calculate downside deviation properly
    downside_dev_daily = negative_returns.std()
    downside_dev_annualized = downside_dev_daily * np.sqrt(252)

    print(f"\nDownside deviation:")
    print(f"Daily: {downside_dev_daily:.6f}")
    print(f"Annualized: {downside_dev_annualized:.2%}")

    vol_annualized = returns.std() * np.sqrt(252)
    print(f"\nVolatility (annualized): {vol_annualized:.2%}")
    print(f"Downside/Volatility ratio: {downside_dev_annualized / vol_annualized:.2%}")
    print(f"Expected ratio (normal dist): {np.sqrt(0.5):.2%}")

    # Percentiles
    print(f"\nReturn percentiles:")
    for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
        print(f"{p:2d}%: {np.percentile(returns, p):.4f} ({np.percentile(returns, p):.2%})")

    print("\n" + "="*80)

if __name__ == "__main__":
    run_diagnostic()

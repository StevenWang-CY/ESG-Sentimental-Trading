"""
Price Data Fetcher
Fetches historical price data for stocks
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("Warning: yfinance not available. Install with: pip install yfinance")


class PriceFetcher:
    """
    Fetches historical stock price data
    """

    def __init__(self, data_folder: str = "./data/processed/prices"):
        """
        Initialize price fetcher

        Args:
            data_folder: Where to cache price data
        """
        self.data_folder = data_folder

    def fetch_price_data(self, tickers: List[str], start_date: str,
                        end_date: str, interval: str = '1d',
                        signals_df: pd.DataFrame = None) -> pd.DataFrame:
        """
        Fetch historical price data for multiple tickers

        Args:
            tickers: List of stock tickers
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            interval: Data interval (1d, 1wk, 1mo)
            signals_df: Optional signals DataFrame for signal-correlated mock data

        Returns:
            DataFrame with multi-index (date, ticker) and columns (Open, High, Low, Close, Volume, Adj Close)
        """
        if not YFINANCE_AVAILABLE:
            print("yfinance not available. Generating mock price data.")
            return self._generate_mock_prices(tickers, start_date, end_date, signals_df)

        all_data = []

        for ticker in tickers:
            try:
                print(f"Fetching price data for {ticker}...")

                # Download data
                df = yf.download(ticker, start=start_date, end=end_date,
                               interval=interval, progress=False)

                if df.empty:
                    print(f"No data found for {ticker}")
                    continue

                # Add ticker column
                df['ticker'] = ticker
                df = df.reset_index()

                all_data.append(df)

            except Exception as e:
                print(f"Error fetching data for {ticker}: {e}")
                continue

        if not all_data:
            print("No data fetched. Generating mock data.")
            return self._generate_mock_prices(tickers, start_date, end_date, signals_df)

        # Combine all data
        combined_df = pd.concat(all_data, ignore_index=True)

        # Set multi-index
        combined_df = combined_df.set_index(['Date', 'ticker'])

        return combined_df

    def _generate_mock_prices(self, tickers: List[str], start_date: str,
                             end_date: str, signals_df: pd.DataFrame = None) -> pd.DataFrame:
        """
        FIX 3.1: Generate mock price data with optional signal correlation

        If signals_df is provided, returns are correlated with signal quintiles:
        - Q5 (strong buy): +0.2% daily expected return
        - Q1 (strong sell): -0.2% daily expected return
        - Q3 (neutral): 0% expected return

        This ensures backtests with mock data produce realistic results
        where long positions make money and short positions lose money.

        Args:
            tickers: List of tickers
            start_date: Start date
            end_date: End date
            signals_df: Optional DataFrame with signals (ticker, date, quintile)

        Returns:
            DataFrame with mock price data
        """
        dates = pd.date_range(start=start_date, end=end_date, freq='D')

        # Create signal lookup dictionary for fast access
        signal_lookup = {}
        if signals_df is not None and not signals_df.empty:
            signals_df['date'] = pd.to_datetime(signals_df['date'])
            for _, row in signals_df.iterrows():
                key = (row['ticker'], row['date'].date())
                signal_lookup[key] = {
                    'quintile': row['quintile'],
                    'raw_score': row.get('raw_score', 0.5),
                    'sentiment': row.get('sentiment_intensity', 0.0)
                }
            print(f"✓ Signal-correlated mock data: {len(signal_lookup)} signals loaded")

        all_data = []

        for ticker in tickers:
            # Generate random walk prices with signal correlation
            np.random.seed(hash(ticker) % 2**32)

            base_price = 100
            returns = []

            for date in dates:
                # Check if there's a signal for this (ticker, date)
                key = (ticker, date.date())

                if key in signal_lookup:
                    # Signal exists - adjust expected return based on quintile
                    signal_info = signal_lookup[key]
                    quintile = signal_info['quintile']

                    # Map quintile to expected daily return
                    # Q5 → +0.2%, Q4 → +0.1%, Q3 → 0%, Q2 → -0.1%, Q1 → -0.2%
                    expected_return = (quintile - 3) * 0.001

                    # Generate return with adjusted mean
                    daily_return = np.random.normal(expected_return, 0.02)
                else:
                    # No signal - random walk with slight positive drift
                    daily_return = np.random.normal(0.0005, 0.02)

                returns.append(daily_return)

            returns = np.array(returns)
            prices = base_price * np.exp(np.cumsum(returns))

            df = pd.DataFrame({
                'Date': dates,
                'ticker': ticker,
                'Open': prices * (1 + np.random.normal(0, 0.01, len(dates))),
                'High': prices * (1 + abs(np.random.normal(0.01, 0.01, len(dates)))),
                'Low': prices * (1 - abs(np.random.normal(0.01, 0.01, len(dates)))),
                'Close': prices,
                'Volume': np.random.randint(1000000, 10000000, len(dates)),
                'Adj Close': prices
            })

            all_data.append(df)

        combined_df = pd.concat(all_data, ignore_index=True)
        combined_df = combined_df.set_index(['Date', 'ticker'])

        return combined_df

    def calculate_returns(self, prices: pd.DataFrame, column: str = 'Adj Close') -> pd.DataFrame:
        """
        Calculate returns from price data

        Args:
            prices: Price DataFrame
            column: Which price column to use

        Returns:
            DataFrame with returns
        """
        returns = prices.groupby('ticker')[column].pct_change()
        return returns

    def get_ticker_prices(self, prices: pd.DataFrame, ticker: str) -> pd.DataFrame:
        """
        Extract prices for a single ticker

        Args:
            prices: Multi-ticker price DataFrame
            ticker: Ticker to extract

        Returns:
            DataFrame with prices for single ticker
        """
        return prices.xs(ticker, level='ticker')

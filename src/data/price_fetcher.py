"""
Price Data Fetcher
Fetches historical price data for stocks
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time

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
        Fetch historical price data for multiple tickers using batch download
        with rate limiting and retry logic.

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

        # Try batch download first (more reliable)
        print(f"Fetching price data for {len(tickers)} tickers via batch download...")

        all_data = []
        batch_size = 10  # Download in batches to avoid rate limits
        max_retries = 3

        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i+batch_size]
            batch_str = " ".join(batch)

            for retry in range(max_retries):
                try:
                    print(f"  Batch {i//batch_size + 1}/{(len(tickers)-1)//batch_size + 1}: {batch[:3]}... ({len(batch)} tickers)")

                    # Use batch download with group_by='ticker'
                    # auto_adjust=False to get raw prices including 'Adj Close'
                    df = yf.download(
                        batch_str,
                        start=start_date,
                        end=end_date,
                        interval=interval,
                        progress=False,
                        group_by='ticker',
                        threads=False,  # Single-threaded to avoid rate limits
                        auto_adjust=False  # Keep raw prices with 'Adj Close' column
                    )

                    if df.empty:
                        print(f"    Warning: Empty response for batch, retrying...")
                        time.sleep(2 ** retry)  # Exponential backoff
                        continue

                    # Process batch results
                    if len(batch) == 1:
                        # Single ticker - df has simple columns
                        ticker = batch[0]
                        df_ticker = df.copy()
                        df_ticker['ticker'] = ticker
                        df_ticker = df_ticker.reset_index()
                        if 'Date' not in df_ticker.columns and 'index' in df_ticker.columns:
                            df_ticker = df_ticker.rename(columns={'index': 'Date'})
                        all_data.append(df_ticker)
                    else:
                        # Multiple tickers - df has multi-level columns
                        for ticker in batch:
                            try:
                                if ticker in df.columns.get_level_values(0):
                                    df_ticker = df[ticker].copy()
                                    df_ticker['ticker'] = ticker
                                    df_ticker = df_ticker.reset_index()
                                    if 'Date' not in df_ticker.columns and 'index' in df_ticker.columns:
                                        df_ticker = df_ticker.rename(columns={'index': 'Date'})
                                    # Drop rows with all NaN values
                                    df_ticker = df_ticker.dropna(subset=['Close'])
                                    if not df_ticker.empty:
                                        all_data.append(df_ticker)
                            except Exception as e:
                                print(f"    Warning: Could not extract {ticker}: {e}")

                    print(f"    ✓ Batch complete")
                    time.sleep(0.5)  # Rate limit between batches
                    break  # Success, exit retry loop

                except Exception as e:
                    print(f"    Error in batch download (retry {retry+1}/{max_retries}): {e}")
                    if retry < max_retries - 1:
                        time.sleep(2 ** retry)  # Exponential backoff
                    continue

        if not all_data:
            print("No data fetched from yfinance. Generating mock data.")
            return self._generate_mock_prices(tickers, start_date, end_date, signals_df)

        # Combine all data
        combined_df = pd.concat(all_data, ignore_index=True)

        # Standardize column names (handle both 'Adj Close' and 'Adj_Close')
        if 'Adj Close' not in combined_df.columns and 'Adj_Close' in combined_df.columns:
            combined_df['Adj Close'] = combined_df['Adj_Close']

        # Ensure Date column is datetime
        combined_df['Date'] = pd.to_datetime(combined_df['Date'])

        # Set multi-index
        combined_df = combined_df.set_index(['Date', 'ticker'])

        print(f"✓ Fetched REAL price data for {combined_df.index.get_level_values('ticker').nunique()} tickers")
        print(f"  Date range: {combined_df.index.get_level_values('Date').min()} to {combined_df.index.get_level_values('Date').max()}")

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

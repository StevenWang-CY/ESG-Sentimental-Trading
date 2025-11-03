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
                        end_date: str, interval: str = '1d') -> pd.DataFrame:
        """
        Fetch historical price data for multiple tickers

        Args:
            tickers: List of stock tickers
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            interval: Data interval (1d, 1wk, 1mo)

        Returns:
            DataFrame with multi-index (date, ticker) and columns (Open, High, Low, Close, Volume, Adj Close)
        """
        if not YFINANCE_AVAILABLE:
            print("yfinance not available. Generating mock price data.")
            return self._generate_mock_prices(tickers, start_date, end_date)

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
            return self._generate_mock_prices(tickers, start_date, end_date)

        # Combine all data
        combined_df = pd.concat(all_data, ignore_index=True)

        # Set multi-index
        combined_df = combined_df.set_index(['Date', 'ticker'])

        return combined_df

    def _generate_mock_prices(self, tickers: List[str], start_date: str,
                             end_date: str) -> pd.DataFrame:
        """
        Generate mock price data for testing
        """
        dates = pd.date_range(start=start_date, end=end_date, freq='D')

        all_data = []

        for ticker in tickers:
            # Generate random walk prices
            np.random.seed(hash(ticker) % 2**32)

            base_price = 100
            returns = np.random.normal(0.0005, 0.02, len(dates))
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

"""
Universe Fetcher
Fetches stock universes (NASDAQ-100, S&P 500, etc.)
"""

import pandas as pd
import requests
from typing import List, Dict, Optional
from datetime import datetime


class UniverseFetcher:
    """
    Fetches and manages stock universes
    """

    def __init__(self):
        """Initialize universe fetcher"""
        self.cache = {}

    def get_nasdaq100_tickers(self, as_of_date: Optional[datetime] = None) -> List[str]:
        """
        Get NASDAQ-100 constituent tickers

        Args:
            as_of_date: Date for historical constituents (not implemented yet)

        Returns:
            List of ticker symbols
        """
        # Check cache first
        if 'nasdaq100' in self.cache:
            return self.cache['nasdaq100']

        try:
            # Try to fetch from Wikipedia
            url = 'https://en.wikipedia.org/wiki/NASDAQ-100'
            tables = pd.read_html(url)

            # The NASDAQ-100 table is typically the 4th table
            for table in tables:
                if 'Ticker' in table.columns or 'Symbol' in table.columns:
                    ticker_col = 'Ticker' if 'Ticker' in table.columns else 'Symbol'
                    tickers = table[ticker_col].tolist()

                    # Clean tickers
                    tickers = [str(t).strip().upper() for t in tickers if pd.notna(t)]

                    # Remove any non-ticker entries
                    tickers = [t for t in tickers if t and len(t) <= 5 and t.isalpha()]

                    if len(tickers) > 50:  # Should have ~100 tickers
                        self.cache['nasdaq100'] = tickers
                        print(f"Fetched {len(tickers)} NASDAQ-100 tickers from Wikipedia")
                        return tickers

            # If Wikipedia fetch fails, use hardcoded list
            print("Warning: Could not fetch from Wikipedia, using hardcoded NASDAQ-100 list")
            return self._get_hardcoded_nasdaq100()

        except Exception as e:
            print(f"Error fetching NASDAQ-100: {e}")
            print("Using hardcoded NASDAQ-100 list")
            return self._get_hardcoded_nasdaq100()

    def _get_hardcoded_nasdaq100(self) -> List[str]:
        """
        Hardcoded NASDAQ-100 list (as of 2024)
        Fallback when web scraping fails
        """
        tickers = [
            # Mega-cap Tech
            'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'NVDA', 'TSLA',

            # Large Tech
            'AVGO', 'ORCL', 'CSCO', 'ADBE', 'CRM', 'INTC', 'AMD', 'QCOM', 'TXN',
            'AMAT', 'INTU', 'ISRG', 'MU', 'ADI', 'LRCX', 'KLAC', 'SNPS', 'CDNS',
            'MRVL', 'PANW', 'NXPI', 'MCHP', 'FTNT', 'DXCM', 'ANSS', 'CRWD',

            # Communications
            'NFLX', 'CMCSA', 'TMUS', 'CHTR', 'GILD', 'AMGN', 'VRTX', 'REGN',

            # Consumer
            'COST', 'SBUX', 'ABNB', 'BKNG', 'PYPL', 'ADSK', 'ADP', 'PAYX',
            'LULU', 'MELI', 'PDD', 'JD', 'DASH', 'CPRT', 'ODFL', 'VRSK',

            # Healthcare/Biotech
            'BIIB', 'ILMN', 'MRNA', 'ALGN', 'IDXX', 'SGEN', 'SIRI',

            # Others
            'NTES', 'PCAR', 'MNST', 'WDAY', 'ROST', 'DLTR', 'FAST', 'WBD',
            'EXC', 'XEL', 'EA', 'CTSH', 'EBAY', 'TEAM', 'CTAS', 'DDOG',
            'ZS', 'ENPH', 'LCID', 'ZM', 'RIVN', 'COIN', 'KDP', 'FANG',
            'GEHC', 'ON', 'CEG', 'CCEP', 'CDW', 'TTWO', 'GFS', 'SMCI'
        ]

        self.cache['nasdaq100'] = tickers
        return tickers

    def get_sp500_tickers(self) -> List[str]:
        """
        Get S&P 500 constituent tickers

        Returns:
            List of ticker symbols
        """
        if 'sp500' in self.cache:
            return self.cache['sp500']

        try:
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            tables = pd.read_html(url)
            df = tables[0]
            tickers = df['Symbol'].tolist()

            # Clean tickers
            tickers = [str(t).replace('.', '-').strip() for t in tickers]

            self.cache['sp500'] = tickers
            print(f"Fetched {len(tickers)} S&P 500 tickers")
            return tickers

        except Exception as e:
            print(f"Error fetching S&P 500: {e}")
            return []

    def filter_by_criteria(self, tickers: List[str],
                           min_market_cap: Optional[float] = None,
                           min_avg_volume: Optional[float] = None,
                           exclude_sectors: Optional[List[str]] = None) -> List[str]:
        """
        Filter tickers by various criteria

        Args:
            tickers: List of ticker symbols
            min_market_cap: Minimum market cap in USD
            min_avg_volume: Minimum average daily volume
            exclude_sectors: Sectors to exclude

        Returns:
            Filtered list of tickers
        """
        try:
            import yfinance as yf

            filtered = []
            print(f"Filtering {len(tickers)} tickers...")

            for ticker in tickers:
                try:
                    stock = yf.Ticker(ticker)
                    info = stock.info

                    # Market cap filter
                    if min_market_cap:
                        market_cap = info.get('marketCap', 0)
                        if market_cap < min_market_cap:
                            continue

                    # Volume filter
                    if min_avg_volume:
                        avg_volume = info.get('averageVolume', 0)
                        if avg_volume < min_avg_volume:
                            continue

                    # Sector filter
                    if exclude_sectors:
                        sector = info.get('sector', '')
                        if sector in exclude_sectors:
                            continue

                    filtered.append(ticker)

                except Exception as e:
                    print(f"Warning: Could not filter {ticker}: {e}")
                    continue

            print(f"Filtered to {len(filtered)} tickers")
            return filtered

        except ImportError:
            print("Warning: yfinance not available for filtering")
            return tickers

    def get_ticker_info(self, ticker: str) -> Dict:
        """
        Get basic information about a ticker

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dictionary with ticker information
        """
        try:
            import yfinance as yf
            stock = yf.Ticker(ticker)
            info = stock.info

            return {
                'ticker': ticker,
                'name': info.get('longName', ''),
                'sector': info.get('sector', ''),
                'industry': info.get('industry', ''),
                'market_cap': info.get('marketCap', 0),
                'avg_volume': info.get('averageVolume', 0),
                'currency': info.get('currency', 'USD')
            }
        except Exception as e:
            print(f"Error getting info for {ticker}: {e}")
            return {'ticker': ticker, 'error': str(e)}

    def save_universe(self, tickers: List[str], filename: str):
        """
        Save universe to CSV file

        Args:
            tickers: List of ticker symbols
            filename: Output filename
        """
        df = pd.DataFrame({'ticker': tickers})
        df.to_csv(filename, index=False)
        print(f"Saved {len(tickers)} tickers to {filename}")

    def load_universe(self, filename: str) -> List[str]:
        """
        Load universe from CSV file

        Args:
            filename: Input filename

        Returns:
            List of ticker symbols
        """
        df = pd.read_csv(filename)
        tickers = df['ticker'].tolist()
        print(f"Loaded {len(tickers)} tickers from {filename}")
        return tickers

    def get_esg_sensitive_nasdaq100(self, sensitivity: str = 'HIGH') -> List[str]:
        """
        Get ESG-sensitive NASDAQ-100 stocks

        Args:
            sensitivity: 'VERY HIGH', 'HIGH', 'MEDIUM', 'ALL'

        Returns:
            List of ESG-sensitive ticker symbols
        """
        from .esg_universe import ESGSensitiveUniverse

        esg_universe = ESGSensitiveUniverse()
        tickers = esg_universe.get_esg_sensitive_nasdaq100(sensitivity)

        print(f"\n✓ Fetched {len(tickers)} ESG-sensitive NASDAQ-100 stocks")
        print(f"  Sensitivity threshold: {sensitivity}")

        # Print breakdown
        esg_universe.print_universe_summary(tickers)

        return tickers

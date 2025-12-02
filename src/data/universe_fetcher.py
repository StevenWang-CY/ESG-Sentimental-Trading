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

    def get_russell_midcap_tickers(self) -> List[str]:
        """
        Get Russell Midcap Index constituent tickers
        ~800 mid-cap stocks ($2B-$50B market cap)

        Returns:
            List of ticker symbols
        """
        if 'russell_midcap' in self.cache:
            return self.cache['russell_midcap']

        try:
            # Try to fetch from iShares Russell Mid-Cap ETF (IWR) holdings
            url = 'https://www.ishares.com/us/products/239506/ishares-russell-midcap-etf/1467271812596.ajax?fileType=csv&fileName=IWR_holdings&dataType=fund'

            print("Fetching Russell Midcap constituents from iShares IWR ETF...")
            df = pd.read_csv(url, skiprows=9)

            # Get tickers
            if 'Ticker' in df.columns:
                tickers = df['Ticker'].dropna().tolist()
            elif 'Symbol' in df.columns:
                tickers = df['Symbol'].dropna().tolist()
            else:
                raise ValueError("Could not find ticker column")

            # Clean tickers
            tickers = [str(t).strip().upper() for t in tickers if pd.notna(t) and str(t) != '-']
            tickers = [t for t in tickers if t and len(t) <= 5 and not t.startswith('CASH')]

            # Remove duplicates
            tickers = list(set(tickers))

            self.cache['russell_midcap'] = tickers
            print(f"✓ Fetched {len(tickers)} Russell Midcap tickers from iShares")
            return tickers

        except Exception as e:
            print(f"Warning: Could not fetch from iShares: {e}")
            print("Using fallback method...")
            return self._get_russell_midcap_fallback()

    def _get_russell_midcap_fallback(self) -> List[str]:
        """
        Fallback: Generate Russell Midcap proxy from S&P 400 + filtering
        S&P 400 MidCap is similar composition to Russell Midcap
        """
        try:
            # Fetch S&P 400 MidCap from Wikipedia
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_400_companies'
            tables = pd.read_html(url)
            df = tables[0]

            if 'Symbol' in df.columns:
                tickers = df['Symbol'].tolist()
            elif 'Ticker symbol' in df.columns:
                tickers = df['Ticker symbol'].tolist()
            else:
                # Use first column if can't find symbol column
                tickers = df.iloc[:, 0].tolist()

            # Clean tickers
            tickers = [str(t).replace('.', '-').strip().upper() for t in tickers if pd.notna(t)]
            tickers = [t for t in tickers if t and len(t) <= 5]

            self.cache['russell_midcap'] = tickers
            print(f"✓ Using S&P 400 MidCap as proxy: {len(tickers)} tickers")
            return tickers

        except Exception as e:
            print(f"Error in fallback method: {e}")
            print("Using minimal hardcoded mid-cap list")
            return self._get_hardcoded_midcap()

    def _get_hardcoded_midcap(self) -> List[str]:
        """
        ESG-sensitive stocks with HIGH REDDIT COVERAGE

        Strategy: Include both mid-caps AND popular large-caps to ensure
        sufficient Reddit data for sentiment signals. Popular stocks
        generate 10-100x more Reddit discussion than obscure mid-caps.
        """
        tickers = [
            # === HIGH REDDIT COVERAGE LARGE-CAPS (ESG-sensitive) ===
            # These stocks dominate Reddit discussion and have strong ESG exposure
            'TSLA',  # Tesla - EV leader, massive Reddit following, ESG-sensitive
            'AAPL',  # Apple - Supply chain ESG, huge Reddit presence
            'MSFT',  # Microsoft - Cloud sustainability, ESG leader
            'GOOGL', # Alphabet - Data privacy ESG, high Reddit coverage
            'AMZN',  # Amazon - Labor/ESG issues, very high Reddit coverage
            'META',  # Meta - Governance issues, high Reddit coverage
            'NVDA',  # Nvidia - AI/green tech, very high Reddit coverage
            'AMD',   # AMD - Green computing, high Reddit coverage
            'INTC',  # Intel - Manufacturing ESG, good Reddit coverage

            # === ENERGY (High ESG exposure + Reddit coverage) ===
            'DVN', 'FANG', 'OXY', 'MPC', 'VLO', 'PSX', 'CTRA',
            'XOM',   # Exxon - Climate litigation, high Reddit coverage
            'CVX',   # Chevron - ESG controversies, high Reddit coverage
            'COP',   # ConocoPhillips - Energy transition, good coverage
            'BP',    # BP - Major ESG news, good coverage
            'SHEL',  # Shell - Energy transition leader

            # === MATERIALS (ESG-sensitive) ===
            'FCX', 'NEM', 'NUE', 'STLD', 'CLF', 'AA', 'X',

            # === CONSUMER DISCRETIONARY (High Reddit coverage) ===
            'MAR', 'HLT', 'MGM', 'WYNN', 'LVS', 'CCL', 'RCL', 'NCLH',
            'TPR', 'LULU', 'ULTA', 'DKS', 'BBY', 'BBWI',
            'NKE',   # Nike - Labor ESG, very high Reddit coverage
            'SBUX',  # Starbucks - Labor issues, high Reddit coverage

            # === INDUSTRIALS (Airlines, ESG-sensitive) ===
            'DAL', 'UAL', 'AAL', 'LUV', 'JBLU', 'CARR', 'OTIS', 'XYL',
            'IEX', 'FTV', 'VLTO', 'EME', 'J', 'GNRC',
            'BA',    # Boeing - Safety ESG, very high Reddit coverage
            'CAT',   # Caterpillar - Industrial ESG, good coverage

            # === REAL ESTATE (ESG-sensitive) ===
            'INVH', 'EQR', 'AVB', 'ESS', 'MAA', 'UDR', 'CPT', 'AIV',

            # === HEALTHCARE (Reddit-popular) ===
            'PODD', 'HOLX', 'ALGN', 'IDXX', 'TECH', 'BAX', 'POOL',
            'PFE',   # Pfizer - Pharma ESG, high Reddit coverage
            'JNJ',   # J&J - Product safety ESG, high coverage
            'UNH',   # UnitedHealth - Healthcare ESG, good coverage

            # === TECHNOLOGY (High Reddit coverage) ===
            'PANW', 'CRWD', 'ZS', 'DDOG', 'NET', 'SNOW', 'PLTR', 'U',
            'CRM',   # Salesforce - ESG leader, good Reddit coverage
            'COIN',  # Coinbase - Crypto ESG, very high Reddit coverage

            # === UTILITIES (High ESG exposure) ===
            'AES', 'NRG', 'CMS', 'AEE', 'EVRG', 'LNT', 'NI', 'PNW',
            'NEE',   # NextEra - Clean energy leader, good coverage

            # === FINANCIAL (ESG-sensitive, good coverage) ===
            'JPM',   # JPMorgan - ESG financing, high Reddit coverage
            'BAC',   # Bank of America - ESG investing, good coverage
            'GS',    # Goldman Sachs - ESG controversies, good coverage
            'BLK',   # BlackRock - ESG investing leader, good coverage
        ]

        print(f"Using minimal hardcoded list: {len(tickers)} mid-cap tickers")
        return tickers

    def get_esg_sensitive_midcap(self, min_market_cap: float = 2e9, max_market_cap: float = 50e9) -> List[str]:
        """
        Get ESG-sensitive mid-cap stocks from Russell Midcap
        Filters for $2B-$50B market cap range

        Args:
            min_market_cap: Minimum market cap (default $2B)
            max_market_cap: Maximum market cap (default $50B)

        Returns:
            List of ESG-sensitive mid-cap tickers
        """
        # Get Russell Midcap base universe
        tickers = self.get_russell_midcap_tickers()

        print(f"\nFiltering {len(tickers)} mid-caps for ESG sensitivity...")
        print(f"Market cap range: ${min_market_cap/1e9:.1f}B - ${max_market_cap/1e9:.1f}B")

        # Filter by market cap if needed
        if min_market_cap or max_market_cap:
            filtered = self.filter_by_market_cap(tickers, min_market_cap, max_market_cap)
        else:
            filtered = tickers

        print(f"✓ {len(filtered)} ESG-sensitive mid-cap stocks")
        return filtered

    def filter_by_market_cap(self, tickers: List[str], min_cap: float = None, max_cap: float = None) -> List[str]:
        """
        Filter tickers by market capitalization range

        Args:
            tickers: List of ticker symbols
            min_cap: Minimum market cap in USD
            max_cap: Maximum market cap in USD

        Returns:
            Filtered list of tickers
        """
        try:
            import yfinance as yf

            filtered = []
            print(f"Filtering {len(tickers)} tickers by market cap...")

            # Process in batches to avoid rate limiting
            batch_size = 50
            for i in range(0, len(tickers), batch_size):
                batch = tickers[i:i+batch_size]

                for ticker in batch:
                    try:
                        stock = yf.Ticker(ticker)
                        info = stock.info
                        market_cap = info.get('marketCap', 0)

                        # Apply filters
                        if min_cap and market_cap < min_cap:
                            continue
                        if max_cap and market_cap > max_cap:
                            continue

                        filtered.append(ticker)

                    except Exception as e:
                        # If can't get info, include by default
                        filtered.append(ticker)
                        continue

                # Progress update
                if (i + batch_size) % 100 == 0:
                    print(f"  Processed {min(i + batch_size, len(tickers))}/{len(tickers)}...")

            print(f"✓ Filtered to {len(filtered)} tickers")
            return filtered

        except ImportError:
            print("Warning: yfinance not available, returning all tickers")
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

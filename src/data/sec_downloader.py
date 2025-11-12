"""
SEC Filing Downloader
Downloads and manages SEC EDGAR filings (8-K, 10-K, 10-Q)
"""

import os
import time
from datetime import datetime
from typing import List, Dict, Optional
import pandas as pd
from pathlib import Path

try:
    from sec_edgar_downloader import Downloader
    SEC_DOWNLOADER_AVAILABLE = True
except ImportError:
    SEC_DOWNLOADER_AVAILABLE = False
    print("Warning: sec-edgar-downloader not available. Install with: pip install sec-edgar-downloader")


class SECDownloader:
    """
    Downloads SEC filings from EDGAR database
    """

    def __init__(self, company_name: str = "ESGQuantResearch", email: str = "research@example.com",
                 download_folder: str = "./data/raw/sec_filings"):
        """
        Initialize SEC downloader

        Args:
            company_name: Your company name (required by SEC)
            email: Your email (required by SEC)
            download_folder: Where to save downloaded filings
        """
        self.company_name = company_name
        self.email = email
        self.download_folder = Path(download_folder)
        self.download_folder.mkdir(parents=True, exist_ok=True)

        if SEC_DOWNLOADER_AVAILABLE:
            self.downloader = Downloader(company_name, email, str(self.download_folder))
        else:
            self.downloader = None

    def fetch_filings(self, tickers: List[str], filing_type: str = '8-K',
                     start_date: str = None, end_date: str = None,
                     limit: int = None) -> List[Dict]:
        """
        Download SEC filings for given tickers

        Args:
            tickers: List of stock tickers
            filing_type: Type of filing (8-K, 10-K, 10-Q)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            limit: Maximum number of filings per ticker

        Returns:
            List of filing metadata dictionaries
        """
        if not SEC_DOWNLOADER_AVAILABLE:
            print("SEC downloader not available. Returning mock data.")
            return self._generate_mock_filings(tickers, filing_type, start_date, end_date)

        filings_metadata = []

        for ticker in tickers:
            try:
                print(f"Downloading {filing_type} filings for {ticker}...")

                # Download filings
                after_date = start_date if start_date else "2020-01-01"
                before_date = end_date if end_date else datetime.now().strftime("%Y-%m-%d")

                self.downloader.get(
                    filing_type,
                    ticker,
                    after=after_date,
                    before=before_date,
                    limit=limit
                )

                # Get metadata of downloaded files
                ticker_folder = self.download_folder / "sec-edgar-filings" / ticker / filing_type
                if ticker_folder.exists():
                    for filing_folder in ticker_folder.iterdir():
                        if filing_folder.is_dir():
                            for file_path in filing_folder.glob("*.txt"):
                                # CRITICAL FIX: Extract filing date from accession number or filing metadata
                                # Accession format: 0001140361-24-038601 (year is in middle segment)
                                filing_date = self._extract_filing_date(file_path, filing_folder.name)

                                # FIX 1.1: Strict date filtering to prevent wrong-dated data
                                # Filter out filings outside [start_date, end_date] window
                                if start_date or end_date:
                                    try:
                                        filing_dt = datetime.strptime(filing_date, '%Y-%m-%d')

                                        # Check if filing is before start date
                                        if start_date:
                                            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                                            if filing_dt < start_dt:
                                                print(f"  ↳ Filtered: {ticker} filing from {filing_date} (before {start_date})")
                                                continue

                                        # Check if filing is after end date
                                        if end_date:
                                            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                                            if filing_dt > end_dt:
                                                print(f"  ↳ Filtered: {ticker} filing from {filing_date} (after {end_date})")
                                                continue
                                    except ValueError as e:
                                        print(f"  ⚠ Warning: Invalid date format for {ticker} filing: {filing_date}")
                                        continue

                                filings_metadata.append({
                                    'ticker': ticker,
                                    'filing_type': filing_type,
                                    'file_path': str(file_path),
                                    'accession_number': filing_folder.name,
                                    'date': filing_date,  # ADDED: Filing date for event detection
                                    'download_date': datetime.now().strftime("%Y-%m-%d")
                                })

                # Rate limiting (SEC requires 10 requests per second max)
                time.sleep(0.15)

            except Exception as e:
                print(f"Error downloading filings for {ticker}: {e}")
                continue

        return filings_metadata

    def _extract_filing_date(self, file_path, accession_number: str) -> str:
        """
        Extract filing date from SEC filing metadata

        Args:
            file_path: Path to the SEC filing file
            accession_number: Filing accession number

        Returns:
            Filing date in YYYY-MM-DD format
        """
        try:
            # Try to extract from filing content (most accurate)
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(5000)  # Read first 5KB (header contains date)

                # Look for FILED AS OF DATE or FILING DATE
                import re

                # Pattern 1: FILED AS OF DATE:        20240801
                match = re.search(r'FILED AS OF DATE:\s*(\d{8})', content)
                if match:
                    date_str = match.group(1)
                    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

                # Pattern 2: FILING DATE in SGML header
                match = re.search(r'<FILING-DATE>(\d{8})', content)
                if match:
                    date_str = match.group(1)
                    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

                # Pattern 3: CONFORMED PERIOD OF REPORT
                match = re.search(r'CONFORMED PERIOD OF REPORT:\s*(\d{8})', content)
                if match:
                    date_str = match.group(1)
                    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

        except Exception as e:
            print(f"Warning: Could not extract filing date from {file_path}: {e}")

        # Fallback: Use file modification date
        try:
            from pathlib import Path
            file_mod_time = Path(file_path).stat().st_mtime
            mod_date = datetime.fromtimestamp(file_mod_time)
            return mod_date.strftime("%Y-%m-%d")
        except:
            # Last resort: Use current date
            return datetime.now().strftime("%Y-%m-%d")

    def _generate_mock_filings(self, tickers: List[str], filing_type: str,
                               start_date: str, end_date: str) -> List[Dict]:
        """
        Generate mock filing data for testing when SEC API is not available
        """
        mock_filings = []

        for ticker in tickers:
            # Generate 3 mock filings per ticker
            for i in range(3):
                date = pd.date_range(start=start_date or "2023-01-01",
                                    end=end_date or "2023-12-31",
                                    periods=3)[i]

                mock_filings.append({
                    'ticker': ticker,
                    'filing_type': filing_type,
                    'file_path': f'mock_filing_{ticker}_{i}.txt',
                    'date': date.strftime("%Y-%m-%d"),
                    'text': self._generate_mock_filing_text(ticker, filing_type),
                    'accession_number': f'0000000000-00-00000{i}'
                })

        return mock_filings

    def _generate_mock_filing_text(self, ticker: str, filing_type: str) -> str:
        """Generate mock filing text for testing"""
        mock_texts = {
            'environmental': [
                f"{ticker} announced a major environmental fine of $5 million from the EPA for pollution violations.",
                f"{ticker} disclosed emissions reduction targets and renewable energy investments.",
                f"{ticker} reported an oil spill incident requiring environmental remediation."
            ],
            'social': [
                f"{ticker} facing discrimination lawsuit from former employees.",
                f"{ticker} announced data breach affecting 1 million customers.",
                f"{ticker} implementing new diversity initiative and fair wage increases."
            ],
            'governance': [
                f"{ticker} under SEC investigation for accounting irregularities.",
                f"{ticker} disclosed insider trading allegations against executives.",
                f"{ticker} announced board diversity improvements and anti-corruption policies."
            ]
        }

        # Return a random ESG event
        import random
        category = random.choice(list(mock_texts.keys()))
        return random.choice(mock_texts[category])

    def get_filing_metadata_df(self, filings: List[Dict]) -> pd.DataFrame:
        """
        Convert filing metadata to DataFrame

        Args:
            filings: List of filing metadata dictionaries

        Returns:
            DataFrame with filing metadata
        """
        return pd.DataFrame(filings)

"""
SEC Filing Downloader
Downloads and manages SEC EDGAR filings (8-K, 10-K, 10-Q)
"""

import logging
import os
import re
import time
import zlib
from datetime import datetime
from typing import List, Dict, Optional
import numpy as np
import pandas as pd
from pathlib import Path

from src.utils.config_loader import load_environment
from src.utils.provenance import REAL, MOCK, EMPTY, tag, is_mock, DataUnavailableError

logger = logging.getLogger(__name__)

# Effective email values that look like unconfigured placeholders. Using one of
# these as the EDGAR User-Agent risks SEC rate-limiting/throttling.
_PLACEHOLDER_EMAIL_RE = re.compile(r"example\.com|your_email", re.IGNORECASE)

try:
    from sec_edgar_downloader import Downloader
    SEC_DOWNLOADER_AVAILABLE = True
except ImportError:
    SEC_DOWNLOADER_AVAILABLE = False
    logger.warning(
        "sec-edgar-downloader not available. Install with: pip install sec-edgar-downloader"
    )


class SECDownloader:
    """
    Downloads SEC filings from EDGAR database
    """

    def __init__(self, company_name: str = "ESGQuantResearch", email: str = "research@example.com",
                 download_folder: str = "./data/raw/sec_filings", use_mock: bool = False):
        """
        Initialize SEC downloader

        Args:
            company_name: Your company name (required by SEC)
            email: Your email (required by SEC). SEC_EDGAR_USER_EMAIL in the
                environment overrides this if set.
            download_folder: Where to save downloaded filings
            use_mock: If True (intentional demo/test mode), fetch_filings returns
                synthetic data stamped MOCK. In production (use_mock=False) the
                fetcher never fabricates data and fails closed instead.
        """
        self.company_name = company_name
        self.use_mock = use_mock

        # INFRA-06: allow an environment override for the EDGAR User-Agent email,
        # and warn loudly (without hard-exiting) if the effective email looks like
        # an unconfigured placeholder that risks SEC throttling.
        load_environment()
        env_email = os.environ.get("SEC_EDGAR_USER_EMAIL")
        if env_email and env_email.strip():
            email = env_email.strip()
        self.email = email
        if _PLACEHOLDER_EMAIL_RE.search(self.email or ""):
            logger.warning(
                "SEC EDGAR User-Agent email '%s' looks like a placeholder; SEC may "
                "throttle or block requests. Set SEC_EDGAR_USER_EMAIL (or config "
                "data.sec.email) to a real contact email.",
                self.email,
            )

        self.download_folder = Path(download_folder)
        self.download_folder.mkdir(parents=True, exist_ok=True)

        if SEC_DOWNLOADER_AVAILABLE:
            self.downloader = Downloader(company_name, self.email, str(self.download_folder))
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
        # use_mock=True is an intentional demo/test mode: return synthetic data
        # (stamped MOCK by _generate_mock_filings). This path stays.
        if self.use_mock:
            logger.warning(
                "SECDownloader.use_mock=True: returning synthetic mock filings "
                "(NOT real SEC data)."
            )
            return self._generate_mock_filings(tickers, filing_type, start_date, end_date)

        # Production (use_mock=False): never auto-fall back to mock data. If the
        # downloader library/client is unavailable, fail closed.
        if not SEC_DOWNLOADER_AVAILABLE or self.downloader is None:
            raise DataUnavailableError(
                "sec-edgar-downloader is not installed/initialized; cannot fetch "
                "real SEC filings. Install it, or construct SECDownloader(use_mock=True) "
                "for an explicit demo run."
            )

        filings_metadata = []

        for ticker in tickers:
            try:
                logger.info(f"Downloading {filing_type} filings for {ticker}...")

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
                                # DATA-08: extract the authoritative FILING date from
                                # the SGML header. Returns None when undated; we then
                                # drop the filing (the downstream date_validator also
                                # excludes undated filings).
                                filing_date = self._extract_filing_date(file_path, filing_folder.name)

                                if filing_date is None:
                                    logger.warning(
                                        "Dropping undated %s filing for %s (accession %s): "
                                        "no authoritative FILED AS OF DATE / FILING-DATE "
                                        "in header (%s)",
                                        filing_type, ticker, filing_folder.name, file_path,
                                    )
                                    continue

                                # Strict date filtering to prevent wrong-dated data:
                                # filter out filings outside [start_date, end_date].
                                if start_date or end_date:
                                    try:
                                        filing_dt = datetime.strptime(filing_date, '%Y-%m-%d')

                                        # Check if filing is before start date
                                        if start_date:
                                            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                                            if filing_dt < start_dt:
                                                logger.info(f"Filtered: {ticker} filing from {filing_date} (before {start_date})")
                                                continue

                                        # Check if filing is after end date
                                        if end_date:
                                            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                                            if filing_dt > end_dt:
                                                logger.info(f"Filtered: {ticker} filing from {filing_date} (after {end_date})")
                                                continue
                                    except ValueError:
                                        logger.warning(f"Invalid date format for {ticker} filing: {filing_date}")
                                        continue

                                filings_metadata.append({
                                    'ticker': ticker,
                                    'filing_type': filing_type,
                                    'file_path': str(file_path),
                                    'accession_number': filing_folder.name,
                                    'date': filing_date,  # Filing date for event detection
                                    'download_date': datetime.now().strftime("%Y-%m-%d")
                                })

                # Rate limiting (SEC requires 10 requests per second max)
                time.sleep(0.15)

            except Exception as e:
                # SOFT no-data: one ticker's download failed mid-loop. Log and
                # continue rather than fabricating rows. The overall fetch is not
                # aborted because other tickers may still yield real data.
                logger.warning(f"Error downloading {filing_type} filings for {ticker}: {e}")
                continue

        return filings_metadata

    def _extract_filing_date(self, file_path, accession_number: str) -> Optional[str]:
        """
        Extract the authoritative FILING date from a downloaded SEC filing.

        DATA-08: only the true filing-DATE header is used as a source --
        ``FILED AS OF DATE`` / ``<FILING-DATE>`` from the SGML header of the
        downloaded full-submission file. ``CONFORMED PERIOD OF REPORT`` is NOT
        used: it is the reporting-period END, not the filing date.

        On any failure (unreadable file, header absent/unparseable) this returns
        ``None`` -- it deliberately does NOT fall back to the file modification
        time or ``datetime.now()``, both of which fabricate a plausible-but-wrong
        date. An undated filing is treated as excluded by the caller (and the
        downstream date_validator), so it never enters the backtest mis-dated.

        Args:
            file_path: Path to the SEC filing file
            accession_number: Filing accession number (for diagnostics)

        Returns:
            Filing date in ``YYYY-MM-DD`` format, or ``None`` if undated.
        """
        try:
            # Read the header (first 5KB contains the SGML header with dates).
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(5000)
        except Exception as e:
            logger.warning(
                "Could not read SEC filing %s (accession %s) to extract filing date: %s",
                file_path, accession_number, e,
            )
            return None

        # Pattern 1: FILED AS OF DATE:        20240801  (authoritative filing date)
        match = re.search(r'FILED AS OF DATE:\s*(\d{8})', content)
        if match:
            date_str = match.group(1)
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

        # Pattern 2: <FILING-DATE>20240801  (authoritative filing date in SGML header)
        match = re.search(r'<FILING-DATE>(\d{8})', content)
        if match:
            date_str = match.group(1)
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

        # No authoritative filing-DATE header found. Do NOT fall back to mtime or
        # now(); return None so the caller drops this filing as undated.
        return None

    def _generate_mock_filings(self, tickers: List[str], filing_type: str,
                               start_date: str, end_date: str) -> List[Dict]:
        """
        Generate mock filing data for demo/test mode.

        Only reachable when ``use_mock=True`` (an explicit, intentional demo/test
        mode). Each row carries ``provenance='mock'`` so that converting the list
        to a DataFrame via :meth:`get_filing_metadata_df` stamps the frame MOCK.
        """
        mock_filings = []

        # Spread mock filing dates across BUSINESS days only, so synthetic event
        # dates land on the trading-day calendar the backtest rebalance grid uses
        # (calendar-spaced dates can fall on weekends/holidays and never match a
        # rebalance date, yielding a degenerate zero-trade demo backtest).
        bdays = pd.bdate_range(start=start_date or "2023-01-01",
                               end=end_date or "2023-12-31")
        if len(bdays) < 3:
            bdays = pd.bdate_range(start=start_date or "2023-01-01", periods=3)
        date_positions = [0, len(bdays) // 2, len(bdays) - 1]

        for ticker in tickers:
            # Generate 3 mock filings per ticker on distinct business days.
            for i in range(3):
                date = bdays[date_positions[i]]

                mock_filings.append({
                    'ticker': ticker,
                    'filing_type': filing_type,
                    'file_path': f'mock_filing_{ticker}_{i}.txt',
                    'date': date.strftime("%Y-%m-%d"),
                    'text': self._generate_mock_filing_text(ticker, filing_type, seed_key=f"{ticker}_{i}"),
                    'accession_number': f'0000000000-00-00000{i}',
                    'provenance': MOCK,
                })

        return mock_filings

    def _generate_mock_filing_text(self, ticker: str, filing_type: str, seed_key: str = "") -> str:
        """Generate deterministic mock filing text for demo/test mode."""
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

        # Deterministic local RNG (no global state mutation, stable across processes).
        rng = np.random.default_rng(zlib.crc32(str(seed_key or ticker).encode()))
        categories = list(mock_texts.keys())
        category = categories[int(rng.integers(0, len(categories)))]
        # Build a representative multi-sentence 8-K body so the rule-based event
        # detector (which scores on keyword density) reliably fires in demo mode,
        # mirroring a real material-event filing rather than a one-line stub.
        body = " ".join(mock_texts[category])
        return (
            f"Item 8.01 Other Events. {body} "
            f"The company is cooperating with regulators and disclosed the material "
            f"ESG impact, governance review, and sustainability and compliance "
            f"remediation steps in this current report."
        )

    def get_filing_metadata_df(self, filings: List[Dict]) -> pd.DataFrame:
        """
        Convert filing metadata to DataFrame, preserving data provenance.

        Args:
            filings: List of filing metadata dictionaries

        Returns:
            DataFrame with filing metadata, stamped REAL/MOCK/EMPTY.
        """
        df = pd.DataFrame(filings)
        if df.empty:
            return tag(df, EMPTY, source="sec_edgar")
        # Mock rows carry a 'provenance' marker (see _generate_mock_filings).
        if 'provenance' in df.columns and (df['provenance'] == MOCK).any():
            return tag(df, MOCK, source="sec_edgar")
        return tag(df, REAL, source="sec_edgar")

"""
Fama-French Factor Data
Downloads and manages Fama-French factor data from Ken French's data library
"""

import logging

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional

from src.utils.provenance import REAL, MOCK, tag, DataUnavailableError

logger = logging.getLogger(__name__)

try:
    import pandas_datareader as pdr
    DATAREADER_AVAILABLE = True
except ImportError:
    DATAREADER_AVAILABLE = False
    logger.warning("pandas_datareader not available. Install with: pip install pandas-datareader")


class FamaFrenchFactors:
    """
    Downloads and manages Fama-French factor data
    """

    def __init__(self, data_folder: str = "./data/processed/factors",
                 use_mock: bool = False):
        """
        Initialize Fama-French factor loader

        Args:
            data_folder: Where to cache factor data
            use_mock: When True, intentionally return synthetic (demo/test)
                factor data stamped MOCK. When False (production default),
                a download/dependency failure raises DataUnavailableError
                instead of silently fabricating data.
        """
        self.data_folder = data_folder
        self.use_mock = use_mock
        self.factors = None

    def load_ff_factors(self, start_date: str, end_date: str,
                       frequency: str = 'daily') -> pd.DataFrame:
        """
        Download Fama-French 5 factors + Momentum

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            frequency: 'daily' or 'monthly'

        Returns:
            DataFrame with factors: Mkt-RF, SMB, HML, RMW, CMA, Mom, RF
        """
        if self.use_mock:
            logger.warning("use_mock=True: generating SYNTHETIC mock factor data (demo mode).")
            mock_df = self._generate_mock_factors(start_date, end_date, frequency)
            return tag(mock_df, MOCK, "ff_mock")

        if not DATAREADER_AVAILABLE:
            raise DataUnavailableError(
                "FamaFrenchFactors: pandas_datareader is not installed but "
                "use_mock=False. Install pandas-datareader (pip install "
                "pandas-datareader) or construct FamaFrenchFactors(use_mock=True) "
                "for a labelled demo run."
            )

        try:
            # Download Fama-French 5 Factors
            if frequency == 'daily':
                dataset_name = 'F-F_Research_Data_5_Factors_2x3_daily'
            else:
                dataset_name = 'F-F_Research_Data_5_Factors_2x3'

            print(f"Downloading Fama-French 5 factors ({frequency})...")
            ff5 = pdr.DataReader(dataset_name, 'famafrench', start_date, end_date)[0]

            # Download Momentum Factor
            if frequency == 'daily':
                mom_dataset = 'F-F_Momentum_Factor_daily'
            else:
                mom_dataset = 'F-F_Momentum_Factor'

            print(f"Downloading Momentum factor ({frequency})...")
            mom = pdr.DataReader(mom_dataset, 'famafrench', start_date, end_date)[0]

            # Merge factors
            factors = ff5.join(mom)

            # Convert from percentages to decimals
            factors = factors / 100

            # Rename Mom column if needed
            if 'Mom   ' in factors.columns:
                factors = factors.rename(columns={'Mom   ': 'Mom'})

            self.factors = factors

            print(f"Successfully loaded {len(factors)} periods of factor data")
            print(f"Factors: {list(factors.columns)}")

            return tag(factors, REAL, "famafrench")

        except Exception as e:
            logger.error(f"Error downloading Fama-French factors: {e}")
            raise DataUnavailableError(
                f"FamaFrenchFactors: failed to download Fama-French factors "
                f"({frequency}, {start_date} to {end_date}) and use_mock=False. "
                f"Refusing to fabricate factor data on a production run."
            ) from e

    def _generate_mock_factors(self, start_date: str, end_date: str,
                               frequency: str = 'daily') -> pd.DataFrame:
        """
        Generate mock factor data for testing
        """
        if frequency == 'daily':
            # Business days to match the trading-day calendar of (mock) prices.
            dates = pd.date_range(start=start_date, end=end_date, freq='B')
        else:
            dates = pd.date_range(start=start_date, end=end_date, freq='M')

        # Local deterministic generator (no global RNG mutation); only
        # reachable on the explicit mock path.
        rng = np.random.default_rng(42)
        n = len(dates)

        # Generate realistic factor returns
        mock_factors = pd.DataFrame({
            'Mkt-RF': rng.normal(0.0003, 0.01, n),  # Market excess return
            'SMB': rng.normal(0.0001, 0.005, n),     # Size factor
            'HML': rng.normal(0.0001, 0.005, n),     # Value factor
            'RMW': rng.normal(0.0001, 0.004, n),     # Profitability
            'CMA': rng.normal(0.0001, 0.003, n),     # Investment
            'Mom': rng.normal(0.0002, 0.006, n),     # Momentum
            'RF': np.full(n, 0.02 / 252)                   # Risk-free rate (~2% annual)
        }, index=dates)

        self.factors = mock_factors

        return mock_factors

    def get_factor_returns(self, start_date: Optional[str] = None,
                          end_date: Optional[str] = None) -> pd.DataFrame:
        """
        Get factor returns for a specific date range

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            Filtered factor DataFrame
        """
        if self.factors is None:
            raise ValueError("Factors not loaded. Call load_ff_factors() first.")

        factors = self.factors.copy()

        if start_date:
            factors = factors[factors.index >= start_date]
        if end_date:
            factors = factors[factors.index <= end_date]

        return factors

    def get_market_return(self) -> pd.Series:
        """Get market excess return (Mkt-RF)"""
        if self.factors is None:
            raise ValueError("Factors not loaded.")
        return self.factors['Mkt-RF']

    def get_risk_free_rate(self) -> pd.Series:
        """Get risk-free rate"""
        if self.factors is None:
            raise ValueError("Factors not loaded.")
        return self.factors['RF']

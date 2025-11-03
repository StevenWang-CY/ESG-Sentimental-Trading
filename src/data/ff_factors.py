"""
Fama-French Factor Data
Downloads and manages Fama-French factor data from Ken French's data library
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional

try:
    import pandas_datareader as pdr
    DATAREADER_AVAILABLE = True
except ImportError:
    DATAREADER_AVAILABLE = False
    print("Warning: pandas_datareader not available. Install with: pip install pandas-datareader")


class FamaFrenchFactors:
    """
    Downloads and manages Fama-French factor data
    """

    def __init__(self, data_folder: str = "./data/processed/factors"):
        """
        Initialize Fama-French factor loader

        Args:
            data_folder: Where to cache factor data
        """
        self.data_folder = data_folder
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
        if not DATAREADER_AVAILABLE:
            print("pandas_datareader not available. Generating mock factor data.")
            return self._generate_mock_factors(start_date, end_date, frequency)

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

            return factors

        except Exception as e:
            print(f"Error downloading Fama-French factors: {e}")
            print("Generating mock factor data instead.")
            return self._generate_mock_factors(start_date, end_date, frequency)

    def _generate_mock_factors(self, start_date: str, end_date: str,
                               frequency: str = 'daily') -> pd.DataFrame:
        """
        Generate mock factor data for testing
        """
        if frequency == 'daily':
            dates = pd.date_range(start=start_date, end=end_date, freq='D')
        else:
            dates = pd.date_range(start=start_date, end=end_date, freq='M')

        np.random.seed(42)
        n = len(dates)

        # Generate realistic factor returns
        mock_factors = pd.DataFrame({
            'Mkt-RF': np.random.normal(0.0003, 0.01, n),  # Market excess return
            'SMB': np.random.normal(0.0001, 0.005, n),     # Size factor
            'HML': np.random.normal(0.0001, 0.005, n),     # Value factor
            'RMW': np.random.normal(0.0001, 0.004, n),     # Profitability
            'CMA': np.random.normal(0.0001, 0.003, n),     # Investment
            'Mom': np.random.normal(0.0002, 0.006, n),     # Momentum
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

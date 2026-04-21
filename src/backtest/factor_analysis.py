"""
Factor Analysis
Performs Fama-French factor regression to prove alpha.

Academic references:
- Fama, E. & French, K. (1993) "Common risk factors in the returns on stocks
  and bonds", Journal of Financial Economics.
- Fama, E. & French, K. (2015) "A five-factor asset pricing model", JFE.
- Carhart, M. (1997) "On persistence in mutual fund performance", Journal of Finance.
- Newey, W.K. & West, K.D. (1987) "A Simple, Positive Semi-Definite,
  Heteroskedasticity and Autocorrelation Consistent Covariance Matrix",
  Econometrica. HAC estimators are required when residuals exhibit
  heteroskedasticity or serial correlation (as typical in event-driven
  strategies with overlapping positions).
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional

try:
    import statsmodels.api as sm
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False
    print("Warning: statsmodels not available. Factor analysis will be limited.")
    print("Install with: pip install statsmodels")


class FactorAnalysis:
    """
    Performs factor attribution analysis using Fama-French factors
    """

    def __init__(self, hac_lags: Optional[int] = None):
        """Initialize factor analysis.

        Args:
            hac_lags: Newey-West HAC lag length. If None, defaults to the
                automatic rule-of-thumb floor(4 * (n/100)^(2/9)) which is
                the standard bandwidth from Newey-West (1994). Set to 0
                to use classical (non-HAC) OLS standard errors.
        """
        self.factors = None
        self.hac_lags = hac_lags

    def load_factors(self, factors_df: pd.DataFrame):
        """
        Load factor data

        Args:
            factors_df: DataFrame with factor returns
        """
        self.factors = factors_df

    def run_regression(self, strategy_returns: pd.Series) -> Dict:
        """
        Run Fama-French factor regression

        Regression: R_p - R_f = α + β_mkt(R_mkt - R_f) + β_smb(SMB) +
                                  β_hml(HML) + β_rmw(RMW) + β_cma(CMA) + β_mom(MOM) + ε

        Args:
            strategy_returns: Series of strategy returns

        Returns:
            Dictionary with regression results
        """
        if not STATSMODELS_AVAILABLE:
            return self._simple_alpha_calculation(strategy_returns)

        if self.factors is None:
            print("Warning: Factors not loaded. Using simple alpha calculation.")
            return self._simple_alpha_calculation(strategy_returns)

        # Align dates
        merged = pd.concat([strategy_returns, self.factors], axis=1, join='inner')
        merged = merged.dropna()

        if len(merged) < 30:
            print(f"Warning: Only {len(merged)} overlapping periods. Results may be unreliable.")
            return self._simple_alpha_calculation(strategy_returns)

        # Prepare regression variables
        strategy_col = strategy_returns.name if strategy_returns.name else 'returns'

        # Dependent variable: Excess returns
        if 'RF' in merged.columns:
            y = merged[strategy_col] - merged['RF']
        else:
            y = merged[strategy_col]

        # Independent variables: Factor returns
        factor_cols = []
        for col in ['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA', 'Mom']:
            if col in merged.columns:
                factor_cols.append(col)

        if not factor_cols:
            print("Warning: No factors found. Using simple alpha calculation.")
            return self._simple_alpha_calculation(strategy_returns)

        X = merged[factor_cols]
        X = sm.add_constant(X)  # Add intercept (this is alpha)

        # Run OLS regression with Newey-West HAC standard errors
        # (robust to heteroskedasticity + autocorrelation of unknown form).
        try:
            n_obs = len(merged)
            if self.hac_lags is None:
                # Newey-West (1994) automatic bandwidth rule of thumb.
                # Ensures at least 1 lag for small samples.
                nw_lags = max(1, int(np.floor(4 * (n_obs / 100.0) ** (2.0 / 9.0))))
            else:
                nw_lags = int(self.hac_lags)

            ols_model = sm.OLS(y, X)
            if nw_lags > 0:
                model = ols_model.fit(
                    cov_type='HAC',
                    cov_kwds={'maxlags': nw_lags},
                )
                cov_type_used = f'HAC (Newey-West, lags={nw_lags})'
            else:
                model = ols_model.fit()
                cov_type_used = 'Classical OLS'

            # Extract results — t-stats and p-values now use HAC covariance
            alpha_daily = model.params['const']
            alpha_annual = alpha_daily * 252
            alpha_tstat = model.tvalues['const']
            alpha_pvalue = model.pvalues['const']

            # 95% CI for annualized alpha based on HAC standard errors
            alpha_se_daily = model.bse['const']
            alpha_se_annual = alpha_se_daily * 252
            ci_low = alpha_annual - 1.96 * alpha_se_annual
            ci_high = alpha_annual + 1.96 * alpha_se_annual

            # Extract betas with their HAC t-stats
            betas = {}
            beta_tstats = {}
            for col in factor_cols:
                if col in model.params:
                    betas[col] = model.params[col]
                    beta_tstats[col] = model.tvalues[col]

            return {
                'alpha_annual': alpha_annual,
                'alpha_daily': alpha_daily,
                'alpha_tstat': alpha_tstat,
                'alpha_pvalue': alpha_pvalue,
                'alpha_se_annual': alpha_se_annual,
                'alpha_ci_95_low': ci_low,
                'alpha_ci_95_high': ci_high,
                'betas': betas,
                'beta_tstats': beta_tstats,
                'r_squared': model.rsquared,
                'adj_r_squared': model.rsquared_adj,
                'n_observations': n_obs,
                'cov_type': cov_type_used,
                'nw_lags': nw_lags,
                'residuals': model.resid,
                'full_summary': model.summary()
            }

        except Exception as e:
            print(f"Error in regression: {e}")
            return self._simple_alpha_calculation(strategy_returns)

    def _simple_alpha_calculation(self, strategy_returns: pd.Series) -> Dict:
        """
        Simple alpha calculation without factor regression

        Args:
            strategy_returns: Series of strategy returns

        Returns:
            Dictionary with simple alpha metrics
        """
        if strategy_returns.empty:
            return {
                'alpha_annual': 0.0,
                'alpha_daily': 0.0,
                'alpha_tstat': 0.0,
                'alpha_pvalue': 1.0,
                'betas': {},
                'r_squared': 0.0,
                'n_observations': 0
            }

        # Calculate simple metrics
        mean_daily_return = strategy_returns.mean()
        std_daily_return = strategy_returns.std()

        # Annualize
        alpha_annual = mean_daily_return * 252
        alpha_daily = mean_daily_return

        # T-statistic
        n = len(strategy_returns)
        alpha_tstat = mean_daily_return / (std_daily_return / np.sqrt(n)) if std_daily_return > 0 else 0

        # P-value (two-tailed test)
        from scipy import stats
        alpha_pvalue = 2 * (1 - stats.t.cdf(abs(alpha_tstat), n - 1))

        return {
            'alpha_annual': alpha_annual,
            'alpha_daily': alpha_daily,
            'alpha_tstat': alpha_tstat,
            'alpha_pvalue': alpha_pvalue,
            'betas': {'market': 0.0},
            'r_squared': 0.0,
            'n_observations': n
        }

    def interpret_results(self, results: Dict) -> str:
        """
        Provide human-readable interpretation of regression results

        Args:
            results: Regression results dictionary

        Returns:
            Formatted interpretation string
        """
        alpha = results['alpha_annual']
        tstat = results['alpha_tstat']
        pval = results['alpha_pvalue']

        cov_type = results.get('cov_type', 'Classical OLS')
        ci_low = results.get('alpha_ci_95_low')
        ci_high = results.get('alpha_ci_95_high')
        ci_str = (
            f"95% CI: [{ci_low*100:.2f}%, {ci_high*100:.2f}%]\n"
            if ci_low is not None and ci_high is not None else ""
        )

        interpretation = f"""
FACTOR REGRESSION RESULTS
========================

Annualized Alpha: {alpha*100:.2f}%
T-Statistic: {tstat:.2f}
P-Value: {pval:.4f}
Std Error: {cov_type}
{ci_str}N Observations: {results.get('n_observations', 0)}

"""

        # Statistical significance
        if pval < 0.01:
            interpretation += "✓ HIGHLY SIGNIFICANT (p < 0.01): Strong evidence of alpha.\n"
        elif pval < 0.05:
            interpretation += "✓ SIGNIFICANT (p < 0.05): Evidence of alpha.\n"
        elif pval < 0.10:
            interpretation += "~ MARGINALLY SIGNIFICANT (p < 0.10): Weak evidence of alpha.\n"
        else:
            interpretation += "✗ NOT SIGNIFICANT: No evidence of alpha beyond factor exposure.\n"

        # R-squared
        if 'r_squared' in results:
            interpretation += f"\nR-squared: {results['r_squared']:.3f} "
            interpretation += f"({results['r_squared']*100:.1f}% of returns explained by factors)\n"

        # Factor loadings
        if 'betas' in results and results['betas']:
            interpretation += "\nFactor Loadings (Betas):\n"
            for factor, beta in results['betas'].items():
                interpretation += f"  {factor:15s}: {beta:7.3f}\n"

        return interpretation

    def calculate_information_ratio(self, strategy_returns: pd.Series,
                                   benchmark_returns: pd.Series) -> float:
        """
        Calculate Information Ratio

        Args:
            strategy_returns: Strategy returns
            benchmark_returns: Benchmark returns

        Returns:
            Information ratio
        """
        # Align returns
        merged = pd.concat([strategy_returns, benchmark_returns], axis=1, join='inner')
        merged.columns = ['strategy', 'benchmark']

        # Calculate active returns
        active_returns = merged['strategy'] - merged['benchmark']

        # Information ratio
        if active_returns.std() == 0:
            return 0.0

        ir = np.sqrt(252) * active_returns.mean() / active_returns.std()
        return ir

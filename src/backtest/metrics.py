"""
Performance Metrics
Calculates portfolio performance metrics

Academic references:
- Lo, A. (2002) "The Statistics of Sharpe Ratios", Financial Analysts Journal.
  Provides autocorrelation-adjusted annualization factor η(q) that corrects
  the naive sqrt(q) scaling when daily returns exhibit serial dependence.
- Bailey, D.H. & Lopez de Prado, M. (2014) "The Deflated Sharpe Ratio",
  Journal of Portfolio Management. Corrects for multiple testing selection bias
  and non-normal return distributions (skewness, kurtosis).
- Bailey, D.H. & Lopez de Prado, M. (2012) "The Sharpe Ratio Efficient Frontier",
  Journal of Risk. Probabilistic Sharpe Ratio (PSR).
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from scipy import stats


class PerformanceAnalyzer:
    """
    Generates comprehensive performance tear sheet
    """

    def __init__(self, backtest_result):
        """
        Initialize performance analyzer

        Args:
            backtest_result: BacktestResult object
        """
        self.result = backtest_result
        self.returns = backtest_result.returns_series

    def generate_tear_sheet(self) -> Dict:
        """
        Generate comprehensive performance metrics

        Returns:
            Dictionary with all performance metrics
        """
        if self.returns.empty:
            return self._get_empty_metrics()

        return {
            'returns': self._calculate_return_metrics(),
            'risk': self._calculate_risk_metrics(),
            'trading': self._calculate_trading_metrics(),
            'summary': self._calculate_summary_metrics()
        }

    def _calculate_return_metrics(self) -> Dict:
        """Calculate return-based metrics"""
        total_return = self.result.get_total_return()
        n_periods = len(self.returns)

        # Annualization factor (assuming daily returns)
        periods_per_year = 252

        cagr = self._calculate_cagr()
        # FIXED: Use CAGR for annualized return (geometric compounding)
        # Old: annualized_return = self.returns.mean() * periods_per_year (arithmetic)
        # New: Use CAGR which properly accounts for compounding
        annualized_return = cagr
        annualized_vol = self.returns.std() * np.sqrt(periods_per_year)

        sharpe_naive = self._calculate_sharpe_ratio()
        sharpe_lo = self._calculate_sharpe_ratio_lo_adjusted()
        psr = self._calculate_probabilistic_sharpe(sr_benchmark=0.0)
        dsr = self._calculate_deflated_sharpe(n_trials=1)

        return {
            'total_return': total_return,
            'cagr': cagr,
            'annualized_return': annualized_return,
            'annualized_volatility': annualized_vol,
            'sharpe_ratio': sharpe_naive,
            'sharpe_ratio_lo_adjusted': sharpe_lo,
            'probabilistic_sharpe': psr,
            'deflated_sharpe': dsr,
            'sortino_ratio': self._calculate_sortino_ratio(),
            'calmar_ratio': self._calculate_calmar_ratio()
        }

    def _calculate_risk_metrics(self) -> Dict:
        """Calculate risk metrics"""
        # CRITICAL: Annualize downside deviation for consistency with volatility
        downside_dev_daily = self._calculate_downside_deviation()
        downside_dev_annualized = downside_dev_daily * np.sqrt(252)

        return {
            'max_drawdown': self._calculate_max_drawdown(),
            'avg_drawdown': self._calculate_avg_drawdown(),
            'var_95': self._calculate_var(0.95),
            'cvar_95': self._calculate_cvar(0.95),
            'downside_deviation': downside_dev_annualized,  # FIXED: Now annualized
            'volatility': self.returns.std() * np.sqrt(252)
        }

    def _calculate_trading_metrics(self) -> Dict:
        """Calculate trading-related metrics"""
        if self.result.trades.empty:
            return {
                'num_trades': 0,
                'win_rate': 0.0,
                'avg_trade': 0.0,
                'turnover': 0.0
            }

        trades = self.result.trades

        return {
            'num_trades': len(trades),
            'avg_trade_size': trades['value'].abs().mean() if 'value' in trades.columns else 0,
            'total_traded': trades['value'].abs().sum() if 'value' in trades.columns else 0,
            'turnover': self._calculate_turnover()
        }

    def _calculate_summary_metrics(self) -> Dict:
        """Calculate summary metrics"""
        return {
            'initial_capital': self.result.initial_capital,
            'final_value': self.result.get_final_value(),
            'total_return_pct': self.result.get_total_return() * 100,
            'n_periods': len(self.returns),
            'start_date': self.returns.index[0] if not self.returns.empty else None,
            'end_date': self.returns.index[-1] if not self.returns.empty else None
        }

    def _calculate_cagr(self) -> float:
        """Calculate Compound Annual Growth Rate"""
        if self.returns.empty:
            return 0.0

        total_return = self.result.get_total_return()
        n_years = len(self.returns) / 252  # Assuming daily returns

        if n_years == 0:
            return 0.0

        cagr = (1 + total_return) ** (1 / n_years) - 1
        return cagr

    def _calculate_sharpe_ratio(self, risk_free_rate: float = 0.02) -> float:
        """
        Calculate Sharpe Ratio (naive sqrt(q) annualization — assumes IID returns)

        Formula: Sharpe = sqrt(252) * E[R - Rf] / std(R - Rf)
        where R is portfolio return and Rf is risk-free rate

        WARNING: This assumes daily returns are IID. When returns are
        autocorrelated (as is typical for event-driven strategies with
        overlapping holding periods), prefer the Lo (2002)-adjusted
        Sharpe ratio.
        """
        if self.returns.empty:
            return 0.0

        excess_returns = self.returns - (risk_free_rate / 252)

        if excess_returns.std() == 0:
            return 0.0

        sharpe = np.sqrt(252) * excess_returns.mean() / excess_returns.std()
        return sharpe

    def _calculate_sharpe_ratio_lo_adjusted(
        self,
        risk_free_rate: float = 0.02,
        q: int = 252,
        max_lag: int = 20,
    ) -> float:
        """
        Calculate autocorrelation-adjusted Sharpe Ratio (Lo 2002).

        Naive sqrt(q) annualization overstates SR when returns exhibit
        positive autocorrelation. Lo (2002) provides a scaling factor:

            eta(q) = q / sqrt( q + 2 * sum_{k=1}^{q-1} (q - k) * rho_k )

        where rho_k is the k-th autocorrelation coefficient.

        Adjusted annualized SR = eta(q) * (E[R - Rf] / std(R - Rf))

        In practice, we truncate the sum at max_lag (default 20) since
        higher-order autocorrelations are typically negligible.

        Reference: Lo, A. (2002) "The Statistics of Sharpe Ratios",
        Financial Analysts Journal, 58(4), 36-52.
        """
        if self.returns.empty or len(self.returns) < max_lag + 2:
            return 0.0

        excess_returns = self.returns - (risk_free_rate / 252)
        daily_std = excess_returns.std()
        if daily_std == 0:
            return 0.0

        daily_sr = excess_returns.mean() / daily_std

        # Compute autocorrelations up to max_lag (truncation)
        effective_lag = min(max_lag, len(excess_returns) - 2)
        rho_sum = 0.0
        for k in range(1, effective_lag + 1):
            rho_k = excess_returns.autocorr(lag=k)
            if pd.isna(rho_k):
                rho_k = 0.0
            # Lo (2002) approximation: weight = (q - k) ≈ q(1 - k/q)
            rho_sum += (q - k) * rho_k

        denominator = q + 2.0 * rho_sum
        if denominator <= 0:
            # Autocorrelation structure prevents adjustment;
            # fall back to naive annualization.
            return np.sqrt(q) * daily_sr

        eta_q = q / np.sqrt(denominator)
        return eta_q * daily_sr

    def _calculate_probabilistic_sharpe(
        self,
        sr_benchmark: float = 0.0,
        risk_free_rate: float = 0.02,
    ) -> float:
        """
        Probabilistic Sharpe Ratio (PSR) - Bailey & Lopez de Prado (2012).

        PSR = Pr(SR_true > SR_benchmark | observed SR)

        Accounts for non-normality (skewness and kurtosis) of returns.
        PSR > 0.95 is typically required to reject the null that the
        strategy's true Sharpe is <= benchmark at the 5% significance level.

        Formula:
            PSR = Φ( (SR_hat - SR_b) * sqrt(n-1) /
                    sqrt(1 - γ3·SR_hat + ((γ4-1)/4)·SR_hat²) )

        where Φ is the standard normal CDF, γ3 is skew, γ4 is kurtosis
        (non-excess), and SR_hat is the observed (non-annualized) Sharpe.

        Reference: Bailey, D.H. & Lopez de Prado, M. (2012)
        "The Sharpe Ratio Efficient Frontier", Journal of Risk, 15(2).
        """
        if self.returns.empty or len(self.returns) < 30:
            return 0.0

        excess_returns = self.returns - (risk_free_rate / 252)
        n = len(excess_returns)
        std = excess_returns.std()
        if std == 0:
            return 0.0

        sr_hat = excess_returns.mean() / std  # Non-annualized (daily)

        # Convert benchmark to daily scale to match sr_hat
        sr_b_daily = sr_benchmark / np.sqrt(252)

        skew = stats.skew(excess_returns.dropna(), bias=False)
        kurt = stats.kurtosis(excess_returns.dropna(), fisher=False, bias=False)  # Non-excess

        # Denominator must be positive
        denom_sq = 1.0 - skew * sr_hat + ((kurt - 1.0) / 4.0) * (sr_hat ** 2)
        if denom_sq <= 0:
            return 0.0

        z = (sr_hat - sr_b_daily) * np.sqrt(n - 1) / np.sqrt(denom_sq)
        return float(stats.norm.cdf(z))

    def _calculate_deflated_sharpe(
        self,
        n_trials: int = 1,
        risk_free_rate: float = 0.02,
    ) -> float:
        """
        Deflated Sharpe Ratio (DSR) - Bailey & Lopez de Prado (2014).

        DSR corrects PSR for multiple-testing selection bias. When a
        strategy is chosen from N candidate backtests, the observed SR
        is upwardly biased (selection-biased maximum of N variates).

        The deflated benchmark SR is:
            SR_b = sqrt(V) * ((1 - γ)·Φ⁻¹(1 - 1/N) + γ·Φ⁻¹(1 - 1/(N·e)))

        where V is the variance of SRs across trials (here approximated
        as 1/(n-1) for a single-trial case) and γ is the Euler-Mascheroni
        constant (≈0.5772). DSR = PSR(SR_b).

        For n_trials=1, DSR ≡ PSR(0) (no selection bias correction).

        Reference: Bailey, D.H. & Lopez de Prado, M. (2014)
        "The Deflated Sharpe Ratio", Journal of Portfolio Management, 40(5).
        """
        if self.returns.empty or len(self.returns) < 30:
            return 0.0

        if n_trials <= 1:
            return self._calculate_probabilistic_sharpe(
                sr_benchmark=0.0,
                risk_free_rate=risk_free_rate,
            )

        # Expected max of N SRs under null (no skill): order statistic approximation
        euler_mascheroni = 0.5772156649
        max_z = (
            (1.0 - euler_mascheroni) * stats.norm.ppf(1.0 - 1.0 / n_trials) +
            euler_mascheroni * stats.norm.ppf(1.0 - 1.0 / (n_trials * np.e))
        )

        # Approximate variance of SR estimate across trials:
        # Bailey & Lopez de Prado (2014) eq. 7 — for unknown cross-trial variance,
        # use sample-based plugin: V ≈ (1/(n-1)) * (1 - γ3·SR + ((γ4-1)/4)·SR²)
        excess = self.returns - (risk_free_rate / 252)
        n = len(excess)
        std = excess.std()
        if std == 0:
            return 0.0
        sr_hat_daily = excess.mean() / std
        skew = stats.skew(excess.dropna(), bias=False)
        kurt = stats.kurtosis(excess.dropna(), fisher=False, bias=False)
        variance_component = 1.0 - skew * sr_hat_daily + ((kurt - 1.0) / 4.0) * (sr_hat_daily ** 2)
        variance_component = max(variance_component, 1e-6)
        v_sr = variance_component / (n - 1)

        sr_b_daily = np.sqrt(v_sr) * max_z

        # Convert benchmark to annualized to match PSR input convention
        sr_b_annual = sr_b_daily * np.sqrt(252)

        return self._calculate_probabilistic_sharpe(
            sr_benchmark=sr_b_annual,
            risk_free_rate=risk_free_rate,
        )

    def _calculate_sortino_ratio(self, risk_free_rate: float = 0.02) -> float:
        """
        Calculate Sortino Ratio

        Formula: Sortino = sqrt(252) * E[R - Rf] / downside_std(R - Rf)
        Uses downside deviation of excess returns (only negative excess returns)
        """
        if self.returns.empty:
            return 0.0

        excess_returns = self.returns - (risk_free_rate / 252)
        downside_std = self._calculate_downside_deviation(returns=excess_returns, threshold=0)

        if downside_std == 0:
            return 0.0

        sortino = np.sqrt(252) * excess_returns.mean() / downside_std
        return sortino

    def _calculate_calmar_ratio(self) -> float:
        """Calculate Calmar Ratio (CAGR / Max Drawdown)"""
        max_dd = abs(self._calculate_max_drawdown())

        if max_dd == 0:
            return 0.0

        cagr = self._calculate_cagr()
        return cagr / max_dd

    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown"""
        if self.returns.empty:
            return 0.0

        cumulative = (1 + self.returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        return drawdown.min()

    def _calculate_avg_drawdown(self) -> float:
        """Calculate average drawdown"""
        if self.returns.empty:
            return 0.0

        cumulative = (1 + self.returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        return drawdown[drawdown < 0].mean()

    def _calculate_downside_deviation(self, returns: pd.Series = None, threshold: float = 0) -> float:
        """
        Calculate downside deviation (DAILY, not annualized)

        Args:
            returns: Returns series to use (default: self.returns)
            threshold: Threshold below which returns are considered "downside" (default: 0)

        Returns:
            DAILY downside deviation (for Sortino, multiply by sqrt(252) to annualize)
        """
        if returns is None:
            returns = self.returns

        if returns.empty:
            return 0.0

        downside_returns = returns[returns < threshold]

        if len(downside_returns) == 0:
            return 0.0

        return downside_returns.std()

    def _calculate_var(self, confidence: float = 0.95) -> float:
        """Calculate Value at Risk"""
        if self.returns.empty:
            return 0.0

        return np.percentile(self.returns, (1 - confidence) * 100)

    def _calculate_cvar(self, confidence: float = 0.95) -> float:
        """Calculate Conditional Value at Risk (Expected Shortfall)"""
        if self.returns.empty:
            return 0.0

        var = self._calculate_var(confidence)
        return self.returns[self.returns <= var].mean()

    def _calculate_turnover(self) -> float:
        """Calculate portfolio turnover"""
        if self.result.trades.empty:
            return 0.0

        total_traded = self.result.trades['value'].abs().sum()
        avg_portfolio_value = self.result.portfolio_values['value'].mean()

        if avg_portfolio_value == 0:
            return 0.0

        return total_traded / avg_portfolio_value

    def _get_empty_metrics(self) -> Dict:
        """Return empty metrics when no data"""
        return {
            'returns': {
                'total_return': 0.0,
                'cagr': 0.0,
                'annualized_return': 0.0,
                'annualized_volatility': 0.0,
                'sharpe_ratio': 0.0,
                'sharpe_ratio_lo_adjusted': 0.0,
                'probabilistic_sharpe': 0.0,
                'deflated_sharpe': 0.0,
                'sortino_ratio': 0.0,
                'calmar_ratio': 0.0
            },
            'risk': {
                'max_drawdown': 0.0,
                'avg_drawdown': 0.0,
                'var_95': 0.0,
                'cvar_95': 0.0,
                'downside_deviation': 0.0,
                'volatility': 0.0
            },
            'trading': {
                'num_trades': 0,
                'avg_trade_size': 0.0,
                'total_traded': 0.0,
                'turnover': 0.0
            },
            'summary': {
                'initial_capital': self.result.initial_capital,
                'final_value': self.result.initial_capital,
                'total_return_pct': 0.0,
                'n_periods': 0,
                'start_date': None,
                'end_date': None
            }
        }

    def _validate_metrics(self, metrics: Dict) -> list:
        """
        Validate metrics and return warnings for unrealistic values

        Returns:
            List of warning messages
        """
        warnings = []

        returns = metrics['returns']
        risk = metrics['risk']

        # Check for unrealistically high Sortino ratio
        if returns['sortino_ratio'] > 5.0:
            warnings.append(
                f"⚠ Sortino ratio ({returns['sortino_ratio']:.2f}) > 5.0 suggests:\n"
                f"   - Very few downside returns (unrealistic for real markets)\n"
                f"   - Possible overfitting or mock data with perfect signals\n"
                f"   - Real-world expectation: 1.5-3.0 for good strategies"
            )

        # Check for unrealistically high Calmar ratio
        if returns['calmar_ratio'] > 10.0:
            warnings.append(
                f"⚠ Calmar ratio ({returns['calmar_ratio']:.2f}) > 10.0 suggests:\n"
                f"   - Max drawdown is too small for the returns\n"
                f"   - Real-world expectation: 2-5 for excellent strategies\n"
                f"   - Current: {returns['cagr']:.1%} CAGR / {abs(risk['max_drawdown']):.1%} max DD"
            )

        # Check for unrealistically low max drawdown
        max_dd_abs = abs(risk['max_drawdown'])
        if max_dd_abs < 0.05 and max_dd_abs > 0:
            warnings.append(
                f"⚠ Max drawdown ({max_dd_abs:.2%}) < 5% is unrealistic:\n"
                f"   - Real strategies typically see 10-30% drawdowns\n"
                f"   - With {risk['volatility']:.1%} volatility, expect {risk['volatility']*0.5:.1%}-{risk['volatility']*1.0:.1%} drawdown\n"
                f"   - This suggests mock data or look-ahead bias"
            )

        # Check for unrealistically low downside deviation relative to volatility
        if risk['volatility'] > 0 and risk['downside_deviation'] > 0:
            dd_ratio = risk['downside_deviation'] / risk['volatility']
            if dd_ratio < 0.3:  # Downside dev should be 50-100% of volatility for normal distributions
                warnings.append(
                    f"⚠ Downside deviation ({risk['downside_deviation']:.1%}) is only {dd_ratio:.0%} of volatility:\n"
                    f"   - Suggests highly asymmetric returns (too few negative returns)\n"
                    f"   - Real strategies: downside dev ≈ 50-100% of total volatility\n"
                    f"   - This indicates unrealistic price behavior"
                )

        # Check for unrealistically high CAGR
        if returns['cagr'] > 0.50:  # > 50% annualized
            warnings.append(
                f"⚠ CAGR ({returns['cagr']:.1%}) > 50% is exceptional:\n"
                f"   - Very few strategies sustain this long-term\n"
                f"   - Real hedge funds: 10-30% CAGR is excellent\n"
                f"   - Consider if backtest has look-ahead bias or overfitting"
            )

        # Lo-adjusted vs naive Sharpe: flag large autocorrelation-driven inflation
        naive_sr = returns.get('sharpe_ratio', 0.0)
        lo_sr = returns.get('sharpe_ratio_lo_adjusted', 0.0)
        if naive_sr > 0 and lo_sr > 0:
            inflation = naive_sr / lo_sr if lo_sr != 0 else float('inf')
            if inflation > 1.25:
                warnings.append(
                    f"⚠ Naive Sharpe ({naive_sr:.2f}) is {inflation:.2f}× the "
                    f"Lo (2002) autocorrelation-adjusted Sharpe ({lo_sr:.2f}):\n"
                    f"   - Returns exhibit positive serial correlation\n"
                    f"   - Use lo_adjusted Sharpe for reporting to mitigate bias"
                )

        # PSR: require high confidence that SR > 0
        psr = returns.get('probabilistic_sharpe', 0.0)
        if 0 < psr < 0.95:
            warnings.append(
                f"⚠ Probabilistic Sharpe ({psr:.2%}) < 95%:\n"
                f"   - Cannot reject SR=0 at 5% significance level\n"
                f"   - Consider more data or selection-bias adjustments"
            )

        return warnings

    def print_tear_sheet(self):
        """Print formatted tear sheet with validation warnings"""
        metrics = self.generate_tear_sheet()

        print("\n" + "="*60)
        print("PERFORMANCE TEAR SHEET")
        print("="*60)

        print("\nRETURN METRICS:")
        print("-"*60)
        for key, value in metrics['returns'].items():
            if isinstance(value, float):
                # Ratios should NOT be formatted as percentages
                if key in ['sharpe_ratio', 'sharpe_ratio_lo_adjusted', 'probabilistic_sharpe', 'deflated_sharpe', 'sortino_ratio', 'calmar_ratio']:
                    print(f"{key:30s}: {value:10.2f}")
                else:
                    print(f"{key:30s}: {value:10.2%}")

        print("\nRISK METRICS:")
        print("-"*60)
        for key, value in metrics['risk'].items():
            if isinstance(value, float):
                print(f"{key:30s}: {value:10.2%}")

        print("\nTRADING METRICS:")
        print("-"*60)
        for key, value in metrics['trading'].items():
            print(f"{key:30s}: {value:10,.2f}")

        print("\nSUMMARY:")
        print("-"*60)
        for key, value in metrics['summary'].items():
            if isinstance(value, float):
                print(f"{key:30s}: {value:10,.2f}")
            else:
                print(f"{key:30s}: {value}")

        print("="*60)

        # Validate metrics and print warnings
        warnings = self._validate_metrics(metrics)
        if warnings:
            print("\n" + "!"*60)
            print("METRIC VALIDATION WARNINGS")
            print("!"*60)
            for warning in warnings:
                print(f"\n{warning}")
            print("\n" + "!"*60)

        print()

    def save_tear_sheet(self, filepath: str):
        """Save formatted tear sheet to file"""
        metrics = self.generate_tear_sheet()

        with open(filepath, 'w') as f:
            f.write("="*60 + "\n")
            f.write("PERFORMANCE TEAR SHEET\n")
            f.write("="*60 + "\n")

            f.write("\nRETURN METRICS:\n")
            f.write("-"*60 + "\n")
            for key, value in metrics['returns'].items():
                if isinstance(value, float):
                    if key in ['sharpe_ratio', 'sharpe_ratio_lo_adjusted', 'probabilistic_sharpe', 'deflated_sharpe', 'sortino_ratio', 'calmar_ratio']:
                        f.write(f"{key:30s}: {value:10.2f}\n")
                    else:
                        f.write(f"{key:30s}: {value:10.2%}\n")

            f.write("\nRISK METRICS:\n")
            f.write("-"*60 + "\n")
            for key, value in metrics['risk'].items():
                if isinstance(value, float):
                    f.write(f"{key:30s}: {value:10.2%}\n")

            f.write("\nTRADING METRICS:\n")
            f.write("-"*60 + "\n")
            for key, value in metrics['trading'].items():
                f.write(f"{key:30s}: {value:10,.2f}\n")

            f.write("\nSUMMARY:\n")
            f.write("-"*60 + "\n")
            for key, value in metrics['summary'].items():
                if isinstance(value, float):
                    f.write(f"{key:30s}: {value:10,.2f}\n")
                else:
                    f.write(f"{key:30s}: {value}\n")

            f.write("="*60 + "\n")

            # Validate metrics and write warnings
            warnings = self._validate_metrics(metrics)
            if warnings:
                f.write("\n" + "!"*60 + "\n")
                f.write("METRIC VALIDATION WARNINGS\n")
                f.write("!"*60 + "\n")
                for warning in warnings:
                    f.write(f"\n{warning}\n")
                f.write("\n" + "!"*60 + "\n")

            f.write("\n")

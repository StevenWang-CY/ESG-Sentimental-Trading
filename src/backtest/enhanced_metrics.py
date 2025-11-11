"""
Enhanced Performance Metrics (Institutional-Grade)
Comprehensive metrics meeting quantitative finance industry standards
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, List, Tuple
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime


class EnhancedPerformanceAnalyzer:
    """
    Institutional-grade performance analysis with comprehensive metrics,
    benchmark comparison, and visualization suite
    """

    def __init__(self, backtest_result, benchmark_returns: Optional[pd.Series] = None):
        """
        Initialize enhanced performance analyzer

        Args:
            backtest_result: BacktestResult object
            benchmark_returns: Optional benchmark returns (e.g., SPY) for comparison
        """
        self.result = backtest_result
        self.returns = backtest_result.returns_series
        self.benchmark_returns = benchmark_returns

        # Extract trades and positions
        self.trades = backtest_result.trades if hasattr(backtest_result, 'trades') else pd.DataFrame()
        self.positions = backtest_result.positions if hasattr(backtest_result, 'positions') else pd.DataFrame()

    def generate_comprehensive_tearsheet(self) -> Dict:
        """
        Generate institutional-grade comprehensive tear sheet

        Returns:
            Dictionary with all performance, risk, trading, and benchmark metrics
        """
        if self.returns.empty:
            return self._get_empty_metrics()

        metrics = {
            'returns': self._calculate_return_metrics(),
            'risk': self._calculate_risk_metrics(),
            'trading': self._calculate_enhanced_trading_metrics(),
            'trade_analysis': self._calculate_trade_analysis(),
            'benchmark': self._calculate_benchmark_metrics() if self.benchmark_returns is not None else {},
            'summary': self._calculate_summary_metrics(),
            'monthly_breakdown': self._calculate_monthly_breakdown(),
            'validation': self._run_validation_checks()
        }

        # Run sanity checks and log warnings
        sanity_warnings = self._validate_metric_sanity(metrics)
        if sanity_warnings:
            metrics['validation']['sanity_warnings'] = sanity_warnings
            import warnings
            for warning_msg in sanity_warnings:
                warnings.warn(f"Metric sanity check: {warning_msg}")

        return metrics

    # ==================== RETURN METRICS ====================

    def _calculate_return_metrics(self) -> Dict:
        """Calculate comprehensive return-based metrics"""
        total_return = self.result.get_total_return()
        n_periods = len(self.returns)
        periods_per_year = 252

        cagr = self._calculate_cagr()
        annualized_return = self.returns.mean() * periods_per_year
        annualized_vol = self.returns.std() * np.sqrt(periods_per_year)

        return {
            'total_return': total_return,
            'cagr': cagr,
            'annualized_return': annualized_return,
            'annualized_volatility': annualized_vol,
            'sharpe_ratio': self._calculate_sharpe_ratio(),
            'sortino_ratio': self._calculate_sortino_ratio(),
            'calmar_ratio': self._calculate_calmar_ratio(),
            'best_day': self.returns.max(),
            'worst_day': self.returns.min(),
            'positive_days_pct': (self.returns > 0).sum() / len(self.returns) if len(self.returns) > 0 else 0
        }

    def _calculate_cagr(self) -> float:
        """Calculate Compound Annual Growth Rate"""
        if self.returns.empty:
            return 0.0

        total_return = self.result.get_total_return()
        n_years = len(self.returns) / 252

        if n_years == 0:
            return 0.0

        cagr = (1 + total_return) ** (1 / n_years) - 1
        return cagr

    def _calculate_sharpe_ratio(self, risk_free_rate: float = 0.02) -> float:
        """
        Calculate Sharpe Ratio
        Formula: Sharpe = sqrt(252) * E[R - Rf] / std(R - Rf)

        NOTE: Returns a ratio (not percentage). Typical range: -3 to +5
        Values > 4 may indicate look-ahead bias or data errors.
        """
        if self.returns.empty:
            return 0.0

        excess_returns = self.returns - (risk_free_rate / 252)

        if excess_returns.std() == 0:
            return 0.0

        sharpe = np.sqrt(252) * excess_returns.mean() / excess_returns.std()

        # Validation: Warn if Sharpe seems unrealistic
        if abs(sharpe) > 10:
            import warnings
            warnings.warn(f"Sharpe ratio {sharpe:.2f} is extremely high/low. Check for data errors or look-ahead bias.")

        return sharpe

    def _calculate_sortino_ratio(self, risk_free_rate: float = 0.02) -> float:
        """
        Calculate Sortino Ratio
        Formula: Sortino = sqrt(252) * E[R - Rf] / downside_std(R - Rf)

        NOTE: Returns a ratio (not percentage). Typically 1-3 for good strategies.
        """
        if self.returns.empty:
            return 0.0

        excess_returns = self.returns - (risk_free_rate / 252)
        downside_std = self._calculate_downside_deviation(returns=excess_returns, threshold=0)

        if downside_std == 0:
            return 0.0

        sortino = np.sqrt(252) * excess_returns.mean() / downside_std

        # Validation: Warn if Sortino seems unrealistic
        if abs(sortino) > 10:
            import warnings
            warnings.warn(f"Sortino ratio {sortino:.2f} is extremely high/low. Check for data errors.")

        return sortino

    def _calculate_calmar_ratio(self) -> float:
        """
        Calculate Calmar Ratio (CAGR / Max Drawdown)

        NOTE: Returns a ratio (not percentage). Typical range: -5 to +10
        Values > 10 may indicate unrealistic performance.
        """
        max_dd = abs(self._calculate_max_drawdown())

        if max_dd == 0:
            return 0.0

        cagr = self._calculate_cagr()
        calmar = cagr / max_dd

        # Validation: Warn if Calmar seems unrealistic
        if abs(calmar) > 20:
            import warnings
            warnings.warn(f"Calmar ratio {calmar:.2f} is extremely high/low. Check for data errors.")

        return calmar

    # ==================== RISK METRICS ====================

    def _calculate_risk_metrics(self) -> Dict:
        """Calculate comprehensive risk metrics"""
        # CRITICAL: Annualize downside deviation for consistency with volatility
        # Sortino uses daily downside dev internally (with sqrt(252) factor)
        # But for display, downside dev should be annualized like volatility
        downside_dev_daily = self._calculate_downside_deviation()
        downside_dev_annualized = downside_dev_daily * np.sqrt(252)

        metrics = {
            'max_drawdown': self._calculate_max_drawdown(),
            'avg_drawdown': self._calculate_avg_drawdown(),
            'var_95': self._calculate_var(0.95),
            'cvar_95': self._calculate_cvar(0.95),
            'var_99': self._calculate_var(0.99),  # NEW
            'cvar_99': self._calculate_cvar(0.99),  # NEW
            'downside_deviation': downside_dev_annualized,  # FIXED: Now annualized
            'volatility': self.returns.std() * np.sqrt(252),
            'max_consecutive_losses': self._calculate_max_consecutive_losses(),  # NEW
            'max_consecutive_wins': self._calculate_max_consecutive_wins(),  # NEW
            'skewness': self.returns.skew(),  # NEW
            'kurtosis': self.returns.kurtosis(),  # NEW
        }

        return metrics

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
        Calculate downside deviation
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

    def _calculate_max_consecutive_losses(self) -> int:
        """Calculate maximum consecutive losing days"""
        if self.returns.empty:
            return 0

        losses = self.returns < 0
        consecutive = 0
        max_consecutive = 0

        for loss in losses:
            if loss:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 0

        return max_consecutive

    def _calculate_max_consecutive_wins(self) -> int:
        """Calculate maximum consecutive winning days"""
        if self.returns.empty:
            return 0

        wins = self.returns > 0
        consecutive = 0
        max_consecutive = 0

        for win in wins:
            if win:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 0

        return max_consecutive

    # ==================== ENHANCED TRADING METRICS ====================

    def _calculate_enhanced_trading_metrics(self) -> Dict:
        """Calculate comprehensive trading metrics"""
        if self.trades.empty:
            return {
                'num_trades': 0,
                'win_rate': 0.0,
                'profit_factor': 0.0,
                'avg_trade': 0.0,
                'turnover': 0.0
            }

        # Calculate returns per trade (requires positions data)
        trade_returns = self._calculate_trade_returns()

        metrics = {
            'num_trades': len(self.trades),
            'win_rate': self._calculate_win_rate(trade_returns),  # NEW
            'profit_factor': self._calculate_profit_factor(trade_returns),  # NEW
            'avg_trade_size': self.trades['value'].abs().mean() if 'value' in self.trades.columns else 0,
            'total_traded': self.trades['value'].abs().sum() if 'value' in self.trades.columns else 0,
            'turnover': self._calculate_turnover()
        }

        return metrics

    def _calculate_trade_returns(self) -> List[float]:
        """
        Calculate return for each closed trade

        Returns:
            List of trade returns (P&L as percentage of entry value)
        """
        if self.trades.empty:
            return []

        trade_returns = []

        # Group trades by ticker to track position entries and exits
        for ticker in self.trades['ticker'].unique():
            ticker_trades = self.trades[self.trades['ticker'] == ticker].sort_values('date')

            position = 0  # Current position size
            entry_price = 0
            entry_value = 0

            for _, trade in ticker_trades.iterrows():
                shares = trade['shares']
                price = trade['price']

                # Opening a new position (from 0)
                if position == 0 and shares != 0:
                    position = shares
                    entry_price = price
                    entry_value = abs(shares * price)

                # Adding to existing position (same direction)
                elif (position > 0 and shares > 0) or (position < 0 and shares < 0):
                    # Average in
                    total_shares = position + shares
                    entry_price = ((position * entry_price) + (shares * price)) / total_shares
                    position = total_shares
                    entry_value = abs(position * entry_price)

                # Closing entire position
                elif (position > 0 and shares < 0 and abs(shares) >= position) or \
                     (position < 0 and shares > 0 and abs(shares) >= abs(position)):

                    # Calculate P&L
                    if position > 0:  # Long position
                        pnl = position * (price - entry_price)
                    else:  # Short position
                        pnl = abs(position) * (entry_price - price)

                    # Return as percentage of entry value
                    if entry_value > 0:
                        trade_return = pnl / entry_value
                        trade_returns.append(trade_return)

                    # Reset position
                    position = 0
                    entry_price = 0
                    entry_value = 0

                # Partial close
                elif (position > 0 and shares < 0) or (position < 0 and shares > 0):
                    # Calculate P&L for closed portion
                    closed_shares = abs(shares)

                    if position > 0:  # Long position
                        pnl = closed_shares * (price - entry_price)
                    else:  # Short position
                        pnl = closed_shares * (entry_price - price)

                    # Return as percentage of closed portion's entry value
                    closed_value = closed_shares * entry_price
                    if closed_value > 0:
                        trade_return = pnl / closed_value
                        trade_returns.append(trade_return)

                    # Update remaining position
                    position = position + shares  # shares is negative for close

        return trade_returns

    def _calculate_win_rate(self, trade_returns: List[float]) -> float:
        """
        Calculate win rate (percentage of profitable trades)

        Args:
            trade_returns: List of trade returns

        Returns:
            Win rate as decimal (0-1)
        """
        if not trade_returns:
            return 0.0

        winning_trades = sum(1 for r in trade_returns if r > 0)
        total_trades = len(trade_returns)

        return winning_trades / total_trades if total_trades > 0 else 0.0

    def _calculate_profit_factor(self, trade_returns: List[float]) -> float:
        """
        Calculate profit factor (Gross Profit / Gross Loss)

        Args:
            trade_returns: List of trade returns

        Returns:
            Profit factor
        """
        if not trade_returns:
            return 0.0

        gross_profit = sum(r for r in trade_returns if r > 0)
        gross_loss = abs(sum(r for r in trade_returns if r < 0))

        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0

        return gross_profit / gross_loss

    def _calculate_turnover(self) -> float:
        """Calculate portfolio turnover"""
        if self.result.trades.empty:
            return 0.0

        total_traded = self.result.trades['value'].abs().sum()
        avg_portfolio_value = self.result.portfolio_values['value'].mean()

        if avg_portfolio_value == 0:
            return 0.0

        return total_traded / avg_portfolio_value

    # ==================== TRADE ANALYSIS ====================

    def _calculate_trade_analysis(self) -> Dict:
        """
        Calculate detailed trade analysis metrics
        """
        trade_returns = self._calculate_trade_returns()

        if not trade_returns:
            return {
                'avg_trade_return': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'largest_win': 0.0,
                'largest_loss': 0.0,
                'win_loss_ratio': 0.0,
                'avg_trade_duration': 0.0
            }

        winning_trades = [r for r in trade_returns if r > 0]
        losing_trades = [r for r in trade_returns if r < 0]

        return {
            'avg_trade_return': np.mean(trade_returns),
            'avg_win': np.mean(winning_trades) if winning_trades else 0.0,
            'avg_loss': np.mean(losing_trades) if losing_trades else 0.0,
            'largest_win': max(trade_returns) if trade_returns else 0.0,
            'largest_loss': min(trade_returns) if trade_returns else 0.0,
            'win_loss_ratio': (np.mean(winning_trades) / abs(np.mean(losing_trades))) if (winning_trades and losing_trades) else 0.0,
            'avg_trade_duration': self._calculate_avg_trade_duration()
        }

    def _calculate_avg_trade_duration(self) -> float:
        """Calculate average trade holding period in days"""
        if self.trades.empty or len(self.trades) < 2:
            return 0.0

        # Group by ticker and calculate duration between entry and exit
        durations = []

        for ticker in self.trades['ticker'].unique():
            ticker_trades = self.trades[self.trades['ticker'] == ticker].sort_values('date')

            for i in range(0, len(ticker_trades)-1, 2):
                if i+1 < len(ticker_trades):
                    entry_date = ticker_trades.iloc[i]['date']
                    exit_date = ticker_trades.iloc[i+1]['date']
                    duration = (exit_date - entry_date).days
                    durations.append(duration)

        return np.mean(durations) if durations else 0.0

    # ==================== BENCHMARK COMPARISON ====================

    def _calculate_benchmark_metrics(self) -> Dict:
        """
        Calculate benchmark-relative metrics (Alpha, Beta, Information Ratio)

        Requires benchmark_returns to be provided
        """
        if self.benchmark_returns is None or self.returns.empty:
            return {}

        # Align returns
        aligned_returns, aligned_benchmark = self.returns.align(self.benchmark_returns, join='inner')

        if len(aligned_returns) < 2:
            return {}

        return {
            'alpha': self._calculate_alpha(aligned_returns, aligned_benchmark),
            'beta': self._calculate_beta(aligned_returns, aligned_benchmark),
            'information_ratio': self._calculate_information_ratio(aligned_returns, aligned_benchmark),
            'tracking_error': self._calculate_tracking_error(aligned_returns, aligned_benchmark),
            'benchmark_correlation': aligned_returns.corr(aligned_benchmark)
        }

    def _calculate_beta(self, returns: pd.Series, benchmark_returns: pd.Series) -> float:
        """
        Calculate beta (systematic risk)

        Formula: Beta = Cov(R_p, R_b) / Var(R_b)
        """
        if len(returns) < 2 or len(benchmark_returns) < 2:
            return 0.0

        covariance = returns.cov(benchmark_returns)
        benchmark_variance = benchmark_returns.var()

        if benchmark_variance == 0:
            return 0.0

        return covariance / benchmark_variance

    def _calculate_alpha(self, returns: pd.Series, benchmark_returns: pd.Series, risk_free_rate: float = 0.02) -> float:
        """
        Calculate Jensen's Alpha

        Formula: Alpha = R_p - [R_f + Beta * (R_b - R_f)]
        """
        if len(returns) < 2:
            return 0.0

        beta = self._calculate_beta(returns, benchmark_returns)

        # Annualized returns
        portfolio_return = returns.mean() * 252
        benchmark_return = benchmark_returns.mean() * 252

        # Jensen's Alpha
        alpha = portfolio_return - (risk_free_rate + beta * (benchmark_return - risk_free_rate))

        return alpha

    def _calculate_information_ratio(self, returns: pd.Series, benchmark_returns: pd.Series) -> float:
        """
        Calculate Information Ratio

        Formula: IR = (R_p - R_b) / Tracking_Error
        """
        if len(returns) < 2:
            return 0.0

        excess_returns = returns - benchmark_returns
        tracking_error = excess_returns.std() * np.sqrt(252)

        if tracking_error == 0:
            return 0.0

        information_ratio = (excess_returns.mean() * 252) / tracking_error

        return information_ratio

    def _calculate_tracking_error(self, returns: pd.Series, benchmark_returns: pd.Series) -> float:
        """Calculate tracking error (annualized std of excess returns)"""
        if len(returns) < 2:
            return 0.0

        excess_returns = returns - benchmark_returns
        return excess_returns.std() * np.sqrt(252)

    # ==================== MONTHLY BREAKDOWN ====================

    def _calculate_monthly_breakdown(self) -> pd.DataFrame:
        """Calculate monthly returns breakdown"""
        if self.returns.empty:
            return pd.DataFrame()

        # Ensure returns has datetime index
        returns_copy = self.returns.copy()
        if not isinstance(returns_copy.index, pd.DatetimeIndex):
            returns_copy.index = pd.to_datetime(returns_copy.index)

        # Calculate monthly returns
        monthly = (1 + returns_copy).resample('M').prod() - 1

        # Create year-month pivot
        monthly_pivot = monthly.to_frame('return')
        monthly_pivot['year'] = monthly_pivot.index.year
        monthly_pivot['month'] = monthly_pivot.index.month

        pivot = monthly_pivot.pivot_table(values='return', index='year', columns='month')

        return pivot

    # ==================== VALIDATION CHECKS ====================

    def _validate_metric_sanity(self, metrics: Dict) -> List[str]:
        """
        Check if calculated metrics pass sanity tests

        Returns:
            List of warning messages (empty if all checks pass)
        """
        warnings = []

        # Check Sharpe ratio
        sharpe = metrics['returns'].get('sharpe_ratio', 0)
        if abs(sharpe) > 10:
            warnings.append(f"Sharpe ratio {sharpe:.2f} is unrealistic (typical: -3 to +5)")

        # Check Sortino ratio
        sortino = metrics['returns'].get('sortino_ratio', 0)
        if abs(sortino) > 10:
            warnings.append(f"Sortino ratio {sortino:.2f} is unrealistic (typical: -3 to +5)")

        # Check Sortino/Sharpe ratio consistency
        if sharpe != 0 and sortino != 0:
            sortino_sharpe_ratio = abs(sortino / sharpe)
            if sortino_sharpe_ratio > 5:
                warnings.append(f"Sortino/Sharpe ratio {sortino_sharpe_ratio:.1f}x is too high (typical: 1.2-2.0x). "
                               f"Check downside deviation calculation.")

        # Check Calmar ratio
        calmar = metrics['returns'].get('calmar_ratio', 0)
        if abs(calmar) > 20:
            warnings.append(f"Calmar ratio {calmar:.2f} is unrealistic (typical: -5 to +10)")

        # Check win rate
        win_rate = metrics['trading'].get('win_rate', 0)
        if win_rate > 0.90:
            warnings.append(f"Win rate {win_rate:.1%} is suspiciously high (typical: 40-70%)")

        # Check profit factor
        profit_factor = metrics['trading'].get('profit_factor', 0)
        if profit_factor > 10 and profit_factor != float('inf'):
            warnings.append(f"Profit factor {profit_factor:.2f} is suspiciously high (typical: 1.2-3.0)")

        # Check volatility
        vol = metrics['risk'].get('volatility', 0)
        if vol < 0.01:
            warnings.append(f"Volatility {vol:.2%} is unrealistically low (typical: 10-50%)")

        # Check downside deviation vs volatility
        downside_dev = metrics['risk'].get('downside_deviation', 0)
        if vol > 0:
            dd_vol_ratio = downside_dev / vol
            # For normal distribution, ratio should be ~0.707 (sqrt(0.5))
            # Allow range of 0.4 to 0.9
            if dd_vol_ratio < 0.4:
                warnings.append(f"Downside deviation {downside_dev:.2%} is too low vs volatility {vol:.2%} "
                               f"(ratio: {dd_vol_ratio:.1%}, expected: ~70%). Possible data issues.")
            elif dd_vol_ratio > 0.9:
                warnings.append(f"Downside deviation {downside_dev:.2%} is too high vs volatility {vol:.2%} "
                               f"(ratio: {dd_vol_ratio:.1%}, expected: ~70%). Very negative skew.")

        # Check drawdown vs volatility
        max_dd = abs(metrics['risk'].get('max_drawdown', 0))
        if vol > 0:
            # Rule of thumb: max DD should be at least 2x volatility over a year
            expected_min_dd = vol * 2
            if max_dd < expected_min_dd and metrics['summary'].get('n_periods', 0) > 100:
                warnings.append(f"Max drawdown {max_dd:.2%} is unrealistically low for volatility {vol:.2%}. "
                               f"Expected at least {expected_min_dd:.2%}. Possible look-ahead bias.")

        return warnings

    def _run_validation_checks(self) -> Dict:
        """
        Run validation checks for common quant errors (red flags)

        Returns:
            Dictionary with validation results
        """
        checks = {}

        # Check 1: Suspiciously high Sharpe ratio
        sharpe = self._calculate_sharpe_ratio()
        checks['high_sharpe_flag'] = sharpe > 4.0
        checks['sharpe_status'] = 'WARNING' if sharpe > 4.0 else 'OK'

        # Check 2: Unrealistic max drawdown with high returns
        max_dd = abs(self._calculate_max_drawdown())
        total_return = self.result.get_total_return()
        checks['unrealistic_dd_flag'] = max_dd < 0.05 and total_return > 0.20
        checks['drawdown_status'] = 'WARNING' if checks['unrealistic_dd_flag'] else 'OK'

        # Check 3: Win rate check
        trade_returns = self._calculate_trade_returns()
        if trade_returns:
            win_rate = self._calculate_win_rate(trade_returns)
            checks['high_win_rate_flag'] = win_rate > 0.80
            checks['win_rate_status'] = 'WARNING' if win_rate > 0.80 else 'OK'
        else:
            checks['win_rate_status'] = 'N/A'

        # Overall status
        flags = sum([
            checks.get('high_sharpe_flag', False),
            checks.get('unrealistic_dd_flag', False),
            checks.get('high_win_rate_flag', False)
        ])

        checks['overall_status'] = 'PASS' if flags == 0 else 'REVIEW REQUIRED'
        checks['num_red_flags'] = flags

        return checks

    # ==================== VISUALIZATION ====================

    def plot_equity_curve_with_drawdown(self, save_path: Optional[str] = None):
        """Plot equity curve with drawdown overlay"""
        if self.returns.empty:
            print("No returns data to plot")
            return

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), gridspec_kw={'height_ratios': [3, 1]})

        # Equity curve
        cumulative = (1 + self.returns).cumprod()
        cumulative.plot(ax=ax1, label='Strategy', linewidth=2)

        if self.benchmark_returns is not None:
            aligned_returns, aligned_benchmark = self.returns.align(self.benchmark_returns, join='inner')
            benchmark_cumulative = (1 + aligned_benchmark).cumprod()
            benchmark_cumulative.plot(ax=ax1, label='Benchmark', linewidth=2, alpha=0.7)

        ax1.set_title('Equity Curve', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Date')
        ax1.set_ylabel('Cumulative Return')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # Drawdown
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        drawdown.plot(ax=ax2, color='red', linewidth=2)
        ax2.fill_between(drawdown.index, drawdown.values, 0, alpha=0.3, color='red')
        ax2.set_title('Drawdown', fontsize=14, fontweight='bold')
        ax2.set_xlabel('Date')
        ax2.set_ylabel('Drawdown')
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Saved equity curve to {save_path}")
        else:
            plt.show()

    def plot_monthly_returns_heatmap(self, save_path: Optional[str] = None):
        """Plot monthly returns heatmap"""
        monthly_pivot = self._calculate_monthly_breakdown()

        if monthly_pivot.empty:
            print("No monthly data to plot")
            return

        plt.figure(figsize=(12, 6))
        sns.heatmap(monthly_pivot * 100, annot=True, fmt='.1f', cmap='RdYlGn', center=0,
                   cbar_kws={'label': 'Return (%)'})
        plt.title('Monthly Returns Heatmap', fontsize=14, fontweight='bold')
        plt.xlabel('Month')
        plt.ylabel('Year')

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Saved heatmap to {save_path}")
        else:
            plt.show()

    def plot_returns_distribution(self, save_path: Optional[str] = None):
        """Plot returns distribution histogram"""
        if self.returns.empty:
            print("No returns data to plot")
            return

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

        # Histogram
        self.returns.hist(bins=50, ax=ax1, edgecolor='black', alpha=0.7)
        ax1.axvline(self.returns.mean(), color='red', linestyle='--', linewidth=2, label=f'Mean: {self.returns.mean():.4f}')
        ax1.axvline(self.returns.median(), color='green', linestyle='--', linewidth=2, label=f'Median: {self.returns.median():.4f}')
        ax1.set_title('Returns Distribution', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Daily Return')
        ax1.set_ylabel('Frequency')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # Q-Q plot
        from scipy import stats
        stats.probplot(self.returns, dist="norm", plot=ax2)
        ax2.set_title('Q-Q Plot (Normal Distribution)', fontsize=14, fontweight='bold')
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Saved distribution plot to {save_path}")
        else:
            plt.show()

    def plot_rolling_sharpe(self, window: int = 63, save_path: Optional[str] = None):
        """Plot rolling Sharpe ratio (default: 3-month window)"""
        if self.returns.empty or len(self.returns) < window:
            print(f"Insufficient data for rolling Sharpe (need at least {window} days)")
            return

        rolling_sharpe = self.returns.rolling(window).apply(
            lambda x: np.sqrt(252) * x.mean() / x.std() if x.std() > 0 else 0
        )

        plt.figure(figsize=(14, 6))
        rolling_sharpe.plot(linewidth=2)
        plt.axhline(y=0, color='black', linestyle='-', linewidth=1, alpha=0.3)
        plt.axhline(y=1.0, color='green', linestyle='--', linewidth=1, alpha=0.5, label='Sharpe = 1.0')
        plt.axhline(y=2.0, color='blue', linestyle='--', linewidth=1, alpha=0.5, label='Sharpe = 2.0')
        plt.title(f'Rolling Sharpe Ratio ({window}-day window)', fontsize=14, fontweight='bold')
        plt.xlabel('Date')
        plt.ylabel('Sharpe Ratio')
        plt.legend()
        plt.grid(True, alpha=0.3)

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Saved rolling Sharpe to {save_path}")
        else:
            plt.show()

    # ==================== SUMMARY PRINTING ====================

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

    def _get_empty_metrics(self) -> Dict:
        """Return empty metrics when no data"""
        return {
            'returns': {}, 'risk': {}, 'trading': {},
            'trade_analysis': {}, 'benchmark': {},
            'summary': {'initial_capital': self.result.initial_capital},
            'validation': {'overall_status': 'N/A'}
        }

    def print_comprehensive_tearsheet(self):
        """Print formatted comprehensive tear sheet"""
        metrics = self.generate_comprehensive_tearsheet()

        print("\n" + "="*80)
        print("COMPREHENSIVE PERFORMANCE TEAR SHEET (INSTITUTIONAL-GRADE)")
        print("="*80)

        # Returns
        print("\nRETURN METRICS:")
        print("-"*80)
        for key, value in metrics['returns'].items():
            if isinstance(value, float):
                # Ratios should NOT be formatted as percentages
                if key in ['sharpe_ratio', 'sortino_ratio', 'calmar_ratio']:
                    print(f"{key:30s}: {value:10.2f}")
                else:
                    print(f"{key:30s}: {value:10.2%}")

        # Risk
        print("\nRISK METRICS:")
        print("-"*80)
        for key, value in metrics['risk'].items():
            if isinstance(value, (int, float)):
                if isinstance(value, int):
                    print(f"{key:30s}: {value:10d}")
                # Skewness and Kurtosis should NOT be formatted as percentages
                elif key in ['skewness', 'kurtosis']:
                    print(f"{key:30s}: {value:10.2f}")
                else:
                    print(f"{key:30s}: {value:10.2%}")

        # Trading
        print("\nTRADING METRICS:")
        print("-"*80)
        for key, value in metrics['trading'].items():
            if isinstance(value, (int, float)):
                if key in ['win_rate', 'profit_factor']:
                    print(f"{key:30s}: {value:10.2f}")
                else:
                    print(f"{key:30s}: {value:10,.2f}")

        # Trade Analysis
        if metrics['trade_analysis']:
            print("\nTRADE ANALYSIS:")
            print("-"*80)
            for key, value in metrics['trade_analysis'].items():
                if isinstance(value, float):
                    if key.endswith('_duration'):
                        print(f"{key:30s}: {value:10.1f} days")
                    else:
                        print(f"{key:30s}: {value:10.2%}")

        # Benchmark
        if metrics['benchmark']:
            print("\nBENCHMARK COMPARISON:")
            print("-"*80)
            for key, value in metrics['benchmark'].items():
                if isinstance(value, float):
                    print(f"{key:30s}: {value:10.4f}")

        # Validation
        print("\nVALIDATION CHECKS:")
        print("-"*80)
        validation = metrics['validation']
        print(f"{'Overall Status':30s}: {validation['overall_status']}")
        print(f"{'Red Flags':30s}: {validation['num_red_flags']}")
        print(f"{'Sharpe Check':30s}: {validation['sharpe_status']}")
        print(f"{'Drawdown Check':30s}: {validation['drawdown_status']}")
        if 'win_rate_status' in validation:
            print(f"{'Win Rate Check':30s}: {validation['win_rate_status']}")

        # Summary
        print("\nSUMMARY:")
        print("-"*80)
        for key, value in metrics['summary'].items():
            if isinstance(value, float):
                print(f"{key:30s}: {value:10,.2f}")
            else:
                print(f"{key:30s}: {value}")

        print("="*80 + "\n")

"""
Performance Metrics
Calculates portfolio performance metrics
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional


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
        annualized_return = self.returns.mean() * periods_per_year
        annualized_vol = self.returns.std() * np.sqrt(periods_per_year)

        return {
            'total_return': total_return,
            'cagr': cagr,
            'annualized_return': annualized_return,
            'annualized_volatility': annualized_vol,
            'sharpe_ratio': self._calculate_sharpe_ratio(),
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
        Calculate Sharpe Ratio

        Formula: Sharpe = sqrt(252) * E[R - Rf] / std(R - Rf)
        where R is portfolio return and Rf is risk-free rate
        """
        if self.returns.empty:
            return 0.0

        excess_returns = self.returns - (risk_free_rate / 252)

        if excess_returns.std() == 0:
            return 0.0

        sharpe = np.sqrt(252) * excess_returns.mean() / excess_returns.std()
        return sharpe

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

    def print_tear_sheet(self):
        """Print formatted tear sheet"""
        metrics = self.generate_tear_sheet()

        print("\n" + "="*60)
        print("PERFORMANCE TEAR SHEET")
        print("="*60)

        print("\nRETURN METRICS:")
        print("-"*60)
        for key, value in metrics['returns'].items():
            if isinstance(value, float):
                # Ratios should NOT be formatted as percentages
                if key in ['sharpe_ratio', 'sortino_ratio', 'calmar_ratio']:
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

        print("="*60 + "\n")

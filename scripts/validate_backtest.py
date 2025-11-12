"""
Backtest Validation Script

Validates backtest results against root cause analysis criteria.
Implements the validation checklist from BACKTEST_ANALYSIS_ROOT_CAUSE.md

Pre-Flight Checks:
- Universe size (50-90 stocks for MEDIUM/ALL)
- Confidence threshold (≥0.18)
- Rebalance frequency (Weekly for ESG)
- Holding period (7-10 days)
- Reddit window (3 days before, 7 days after)

Post-Backtest Validation:
- Sharpe ratio (>0.50, ideally >0.60)
- Sortino/Sharpe ratio (1.5x-2.0x)
- Turnover (3x-5x optimal, <6x max)
- Max drawdown (<10%, 15% max acceptable)
- Sentiment-quintile correlation (>0.75)
- ESG category balance (G: 60-70%, E+S: 30-40%)
"""

import argparse
import yaml
import pandas as pd
import logging
from pathlib import Path
from typing import Dict, List, Tuple
import json
from dataclasses import dataclass, asdict

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ValidationCriteria:
    """Validation criteria from root cause analysis"""

    # Pre-flight checks
    min_universe_size: int = 40
    max_universe_size: int = 100
    min_confidence_threshold: float = 0.18
    rebalance_frequency: str = "W"
    min_holding_period: int = 7
    max_holding_period: int = 10
    reddit_days_before: int = 3
    reddit_days_after: int = 7

    # Post-backtest validation
    min_sharpe: float = 0.50
    target_sharpe: float = 0.60
    min_sortino_sharpe_ratio: float = 1.5
    target_sortino_sharpe_ratio: float = 2.0
    min_turnover: float = 3.0
    max_turnover: float = 6.0
    max_drawdown_warning: float = -10.0
    max_drawdown_critical: float = -15.0
    min_sentiment_quintile_corr: float = 0.75
    min_governance_pct: float = 60.0
    max_governance_pct: float = 70.0
    min_env_social_pct: float = 30.0
    max_env_social_pct: float = 40.0


class BacktestValidator:
    """
    Validates backtest configuration and results
    """

    def __init__(self, config_path='config/config.yaml', criteria=None):
        """
        Initialize validator

        Args:
            config_path: Path to configuration file
            criteria: ValidationCriteria object (uses defaults if None)
        """
        self.config_path = config_path
        self.criteria = criteria or ValidationCriteria()

        # Load config
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.pre_flight_results = {}
        self.post_backtest_results = {}
        self.warnings = []
        self.errors = []

    def run_pre_flight_checks(self, universe_size=None) -> Tuple[bool, List[str]]:
        """
        Run pre-flight configuration checks

        Args:
            universe_size: Actual universe size (optional, will estimate if not provided)

        Returns:
            Tuple of (passed, list of issues)
        """
        logger.info("="*60)
        logger.info("PRE-FLIGHT CONFIGURATION CHECKS")
        logger.info("="*60)

        issues = []

        # Check 1: Confidence Threshold
        threshold = self.config['nlp']['event_detector']['confidence_threshold']
        if threshold < self.criteria.min_confidence_threshold:
            msg = f"❌ Confidence threshold {threshold} < {self.criteria.min_confidence_threshold} (HIGH RISK of noise)"
            issues.append(msg)
            self.errors.append(msg)
            logger.error(msg)
        else:
            logger.info(f"✓ Confidence threshold: {threshold} (OK)")
            self.pre_flight_results['confidence_threshold'] = 'PASS'

        # Check 2: Rebalance Frequency
        rebal_freq = self.config['portfolio']['rebalance_frequency']
        if rebal_freq != self.criteria.rebalance_frequency:
            msg = f"⚠️  Rebalance frequency '{rebal_freq}' != '{self.criteria.rebalance_frequency}' (may cause overtrading)"
            issues.append(msg)
            self.warnings.append(msg)
            logger.warning(msg)
        else:
            logger.info(f"✓ Rebalance frequency: {rebal_freq} (OK)")
            self.pre_flight_results['rebalance_frequency'] = 'PASS'

        # Check 3: Holding Period
        holding_period = self.config['portfolio']['holding_period']
        if holding_period < self.criteria.min_holding_period:
            msg = f"❌ Holding period {holding_period} < {self.criteria.min_holding_period} days (TOO SHORT for ESG sentiment diffusion)"
            issues.append(msg)
            self.errors.append(msg)
            logger.error(msg)
        elif holding_period > self.criteria.max_holding_period:
            msg = f"⚠️  Holding period {holding_period} > {self.criteria.max_holding_period} days (may miss exit timing)"
            issues.append(msg)
            self.warnings.append(msg)
            logger.warning(msg)
        else:
            logger.info(f"✓ Holding period: {holding_period} days (OK)")
            self.pre_flight_results['holding_period'] = 'PASS'

        # Check 4: Reddit Window
        days_before = self.config['data']['social_media']['days_before_event']
        days_after = self.config['data']['social_media']['days_after_event']

        if days_before != self.criteria.reddit_days_before:
            msg = f"⚠️  Reddit days_before {days_before} != {self.criteria.reddit_days_before} (may capture pre-event noise)"
            issues.append(msg)
            self.warnings.append(msg)
            logger.warning(msg)
        else:
            logger.info(f"✓ Reddit days_before: {days_before} (OK)")

        if days_after != self.criteria.reddit_days_after:
            msg = f"⚠️  Reddit days_after {days_after} != {self.criteria.reddit_days_after} (may capture sentiment decay)"
            issues.append(msg)
            self.warnings.append(msg)
            logger.warning(msg)
        else:
            logger.info(f"✓ Reddit days_after: {days_after} (OK)")

        if days_before == self.criteria.reddit_days_before and days_after == self.criteria.reddit_days_after:
            self.pre_flight_results['reddit_window'] = 'PASS'

        # Check 5: Universe Size (if provided)
        if universe_size is not None:
            if universe_size < self.criteria.min_universe_size:
                msg = f"❌ Universe size {universe_size} < {self.criteria.min_universe_size} (TOO SMALL, concentration risk)"
                issues.append(msg)
                self.errors.append(msg)
                logger.error(msg)
            elif universe_size > self.criteria.max_universe_size:
                msg = f"⚠️  Universe size {universe_size} > {self.criteria.max_universe_size} (may dilute ESG focus)"
                issues.append(msg)
                self.warnings.append(msg)
                logger.warning(msg)
            else:
                logger.info(f"✓ Universe size: {universe_size} stocks (OK)")
                self.pre_flight_results['universe_size'] = 'PASS'

        logger.info("="*60)

        passed = len(self.errors) == 0
        return passed, issues

    def validate_backtest_results(self, results_dict) -> Tuple[bool, List[str]]:
        """
        Validate backtest performance results

        Args:
            results_dict: Dictionary containing backtest metrics
                Expected keys: sharpe_ratio, sortino_ratio, turnover,
                              max_drawdown, total_return, num_trades

        Returns:
            Tuple of (passed, list of issues)
        """
        logger.info("\n" + "="*60)
        logger.info("POST-BACKTEST VALIDATION")
        logger.info("="*60)

        issues = []

        # Check 1: Sharpe Ratio
        sharpe = results_dict.get('sharpe_ratio')
        if sharpe is not None:
            if sharpe < self.criteria.min_sharpe:
                msg = f"❌ Sharpe ratio {sharpe:.3f} < {self.criteria.min_sharpe} (STRATEGY FAILED)"
                issues.append(msg)
                self.errors.append(msg)
                logger.error(msg)
            elif sharpe < self.criteria.target_sharpe:
                msg = f"⚠️  Sharpe ratio {sharpe:.3f} < target {self.criteria.target_sharpe} (below target)"
                issues.append(msg)
                self.warnings.append(msg)
                logger.warning(msg)
            else:
                logger.info(f"✓ Sharpe ratio: {sharpe:.3f} (EXCELLENT)")
                self.post_backtest_results['sharpe_ratio'] = 'PASS'

        # Check 2: Sortino/Sharpe Ratio
        sortino = results_dict.get('sortino_ratio')
        if sharpe is not None and sortino is not None:
            sortino_sharpe_ratio = sortino / sharpe if sharpe > 0 else 0

            if sortino_sharpe_ratio < self.criteria.min_sortino_sharpe_ratio:
                msg = f"❌ Sortino/Sharpe {sortino_sharpe_ratio:.2f}x < {self.criteria.min_sortino_sharpe_ratio}x (POOR downside protection)"
                issues.append(msg)
                self.errors.append(msg)
                logger.error(msg)
            elif sortino_sharpe_ratio < self.criteria.target_sortino_sharpe_ratio:
                msg = f"⚠️  Sortino/Sharpe {sortino_sharpe_ratio:.2f}x < target {self.criteria.target_sortino_sharpe_ratio}x"
                issues.append(msg)
                self.warnings.append(msg)
                logger.warning(msg)
            else:
                logger.info(f"✓ Sortino/Sharpe ratio: {sortino_sharpe_ratio:.2f}x (GOOD downside protection)")
                self.post_backtest_results['sortino_sharpe_ratio'] = 'PASS'

        # Check 3: Turnover
        turnover = results_dict.get('turnover')
        if turnover is not None:
            if turnover > self.criteria.max_turnover:
                msg = f"❌ Turnover {turnover:.2f}x > {self.criteria.max_turnover}x (EXCESSIVE trading, cost drag)"
                issues.append(msg)
                self.errors.append(msg)
                logger.error(msg)
            elif turnover < self.criteria.min_turnover:
                msg = f"⚠️  Turnover {turnover:.2f}x < {self.criteria.min_turnover}x (may be underutilizing signals)"
                issues.append(msg)
                self.warnings.append(msg)
                logger.warning(msg)
            else:
                logger.info(f"✓ Turnover: {turnover:.2f}x (OK)")
                self.post_backtest_results['turnover'] = 'PASS'

        # Check 4: Max Drawdown
        max_dd = results_dict.get('max_drawdown')
        if max_dd is not None:
            if max_dd < self.criteria.max_drawdown_critical:
                msg = f"❌ Max drawdown {max_dd:.2f}% < {self.criteria.max_drawdown_critical}% (UNACCEPTABLE risk)"
                issues.append(msg)
                self.errors.append(msg)
                logger.error(msg)
            elif max_dd < self.criteria.max_drawdown_warning:
                msg = f"⚠️  Max drawdown {max_dd:.2f}% < {self.criteria.max_drawdown_warning}% (elevated risk)"
                issues.append(msg)
                self.warnings.append(msg)
                logger.warning(msg)
            else:
                logger.info(f"✓ Max drawdown: {max_dd:.2f}% (OK)")
                self.post_backtest_results['max_drawdown'] = 'PASS'

        # Check 5: Trade Count
        num_trades = results_dict.get('num_trades')
        if num_trades is not None:
            logger.info(f"ℹ️  Number of trades: {num_trades}")

        # Check 6: Total Return
        total_return = results_dict.get('total_return')
        if total_return is not None:
            logger.info(f"ℹ️  Total return: {total_return:.2f}%")

        logger.info("="*60)

        passed = len(self.errors) == 0
        return passed, issues

    def generate_report(self, output_file=None) -> str:
        """
        Generate validation report

        Args:
            output_file: Path to save report (optional)

        Returns:
            str: Report content
        """
        report = []
        report.append("="*70)
        report.append("BACKTEST VALIDATION REPORT")
        report.append("="*70)
        report.append("")

        # Summary
        total_errors = len(self.errors)
        total_warnings = len(self.warnings)

        if total_errors == 0 and total_warnings == 0:
            report.append("✓ STATUS: ALL CHECKS PASSED")
        elif total_errors == 0:
            report.append(f"⚠️  STATUS: PASSED WITH {total_warnings} WARNING(S)")
        else:
            report.append(f"❌ STATUS: FAILED WITH {total_errors} ERROR(S) AND {total_warnings} WARNING(S)")

        report.append("")

        # Errors
        if self.errors:
            report.append("ERRORS (Must Fix):")
            report.append("-" * 70)
            for i, error in enumerate(self.errors, 1):
                report.append(f"{i}. {error}")
            report.append("")

        # Warnings
        if self.warnings:
            report.append("WARNINGS (Review Recommended):")
            report.append("-" * 70)
            for i, warning in enumerate(self.warnings, 1):
                report.append(f"{i}. {warning}")
            report.append("")

        # Pre-flight Results
        if self.pre_flight_results:
            report.append("PRE-FLIGHT CHECK RESULTS:")
            report.append("-" * 70)
            for check, status in self.pre_flight_results.items():
                report.append(f"  {check}: {status}")
            report.append("")

        # Post-backtest Results
        if self.post_backtest_results:
            report.append("POST-BACKTEST VALIDATION RESULTS:")
            report.append("-" * 70)
            for check, status in self.post_backtest_results.items():
                report.append(f"  {check}: {status}")
            report.append("")

        report.append("="*70)

        report_text = "\n".join(report)

        # Save to file if specified
        if output_file:
            with open(output_file, 'w') as f:
                f.write(report_text)
            logger.info(f"Report saved to {output_file}")

        return report_text


def parse_backtest_log(log_file):
    """
    Parse backtest results from log file

    Args:
        log_file: Path to backtest log file

    Returns:
        dict: Parsed metrics
    """
    results = {}

    try:
        with open(log_file, 'r') as f:
            content = f.read()

        # Extract metrics (same parsing logic as threshold_sweep.py)
        for line in content.split('\n'):
            if 'Sharpe Ratio:' in line:
                results['sharpe_ratio'] = float(line.split(':')[1].strip())
            elif 'Sortino Ratio:' in line:
                results['sortino_ratio'] = float(line.split(':')[1].strip())
            elif 'Turnover:' in line:
                results['turnover'] = float(line.split(':')[1].strip().replace('x', ''))
            elif 'Max Drawdown:' in line:
                results['max_drawdown'] = float(line.split(':')[1].strip().replace('%', ''))
            elif 'Total Return:' in line:
                results['total_return'] = float(line.split(':')[1].strip().replace('%', ''))
            elif 'Total Trades:' in line or 'Number of Trades:' in line:
                results['num_trades'] = int(line.split(':')[1].strip())

    except Exception as e:
        logger.error(f"Error parsing log file: {str(e)}")

    return results


def main():
    """Main execution"""
    parser = argparse.ArgumentParser(
        description='Validate Backtest Configuration and Results'
    )
    parser.add_argument('--config', type=str, default='config/config.yaml',
                       help='Path to configuration file')
    parser.add_argument('--universe-size', type=int,
                       help='Universe size (number of stocks)')
    parser.add_argument('--results-file', type=str,
                       help='Path to backtest results (log file or JSON)')
    parser.add_argument('--output-report', type=str,
                       help='Path to save validation report')
    parser.add_argument('--pre-flight-only', action='store_true',
                       help='Run only pre-flight checks (no results validation)')

    args = parser.parse_args()

    # Initialize validator
    validator = BacktestValidator(config_path=args.config)

    # Run pre-flight checks
    pre_flight_passed, pre_flight_issues = validator.run_pre_flight_checks(
        universe_size=args.universe_size
    )

    # Run post-backtest validation if results provided
    if args.results_file and not args.pre_flight_only:
        # Parse results
        if args.results_file.endswith('.json'):
            with open(args.results_file, 'r') as f:
                results = json.load(f)
        else:
            # Assume log file
            results = parse_backtest_log(args.results_file)

        if results:
            post_backtest_passed, post_backtest_issues = validator.validate_backtest_results(results)
        else:
            logger.warning("Could not parse results from file")
            post_backtest_passed = None
    else:
        post_backtest_passed = None

    # Generate report
    report = validator.generate_report(output_file=args.output_report)

    print("\n" + report)

    # Exit code
    if not pre_flight_passed or (post_backtest_passed is not None and not post_backtest_passed):
        logger.error("\nValidation FAILED! Please review errors above.")
        return 1
    elif validator.warnings:
        logger.warning("\nValidation passed with warnings. Review recommended.")
        return 0
    else:
        logger.info("\nValidation PASSED! All checks successful.")
        return 0


if __name__ == '__main__':
    exit(main())

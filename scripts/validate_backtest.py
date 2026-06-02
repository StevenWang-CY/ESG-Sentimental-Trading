"""
Backtest Validation Script

Validates backtest results against the canonical strategy runtime contract.

The producer of truth is the canonical FLAT run JSON written by
``run_production.py`` to ``results/runs/run_{start}_{end}_{githash}.json``.
That file is a flat metrics dict (NOT the nested PerformanceAnalyzer tear
sheet), so this validator reads the flat keys directly. Critical units:

* ``max_drawdown_pct`` -- percent, negative (used for percent thresholds)
* ``total_return_pct`` -- percent (used for return thresholds)
* ``turnover``         -- annualized turnover (read directly)
* ``sharpe_ratio`` / ``sortino_ratio`` -- read directly

Pre-Flight Checks (canonical params, sourced from strategy_config where
available):
- Universe size (40-100 stocks)
- Confidence threshold (>= 0.25)
- Rebalance frequency (Weekly for ESG)
- Holding period (up to 49 days)
- Social window (10 days before, 3 days after)

Post-Backtest Validation:
- Sharpe ratio (>0.50, ideally >0.60)
- Sortino/Sharpe ratio (1.5x-2.0x)
- Turnover (annualized; ceiling consistent with weekly long/short book)
- Max drawdown (percent, negative)
"""

import argparse
import yaml
import pandas as pd
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
from dataclasses import dataclass, asdict

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Default location of the canonical FLAT run JSON written by run_production.py.
RUNS_DIR = Path('results/runs')


@dataclass
class ValidationCriteria:
    """Validation criteria for the canonical strategy runtime contract.

    Pre-flight literals default to the canonical strategy spec (confidence
    0.25, holding period up to 49 days, social window 10 before / 3 after).
    Use :meth:`from_strategy_spec` to derive these from a loaded config so the
    validator never drifts from ``src.utils.strategy_config``.
    """

    # Pre-flight checks (canonical)
    min_universe_size: int = 40
    max_universe_size: int = 100
    min_confidence_threshold: float = 0.25
    rebalance_frequency: str = "W"
    min_holding_period: int = 7
    max_holding_period: int = 49
    reddit_days_before: int = 10
    reddit_days_after: int = 3

    # Post-backtest validation
    min_sharpe: float = 0.50
    target_sharpe: float = 0.60
    min_sortino_sharpe_ratio: float = 1.5
    target_sortino_sharpe_ratio: float = 2.0
    # Turnover is now ANNUALIZED (sum of per-rebalance book turnover over a
    # year). A weekly-rebalanced dollar-neutral long/short book can turn over a
    # large fraction of the book each of ~52 rebalances, so the annualized
    # ceiling is far higher than the legacy per-period 6x. < min => signals are
    # under-utilized; > max => excessive trading / cost drag.
    min_turnover: float = 2.0
    max_turnover: float = 52.0
    max_drawdown_warning: float = -10.0
    max_drawdown_critical: float = -15.0
    min_sentiment_quintile_corr: float = 0.75
    min_governance_pct: float = 60.0
    max_governance_pct: float = 70.0
    min_env_social_pct: float = 30.0
    max_env_social_pct: float = 40.0

    @classmethod
    def from_strategy_spec(cls, config: Dict) -> "ValidationCriteria":
        """Build criteria from a loaded config via the canonical strategy spec.

        Falls back to the canonical literal defaults if the spec cannot be
        loaded so the validator stays importable and usable without the spec.
        """
        criteria = cls()
        try:
            from src.utils.strategy_config import load_strategy_spec

            spec = load_strategy_spec(config)
            criteria.min_confidence_threshold = float(spec.event_confidence_threshold)
            criteria.rebalance_frequency = str(spec.portfolio.rebalance_frequency)
            criteria.max_holding_period = int(spec.portfolio.holding_period)
            criteria.reddit_days_before = int(spec.social_window.days_before_event)
            criteria.reddit_days_after = int(spec.social_window.days_after_event)
        except Exception as e:  # pragma: no cover - defensive fallback
            logger.warning(
                "Could not derive criteria from strategy_config (%s); "
                "using canonical literal defaults.", e
            )
        return criteria


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

        # Load config
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        # Derive canonical criteria from the loaded config (strategy_config)
        # unless the caller supplied an explicit ValidationCriteria.
        self.criteria = criteria or ValidationCriteria.from_strategy_spec(self.config)

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

    @staticmethod
    def _drawdown_pct(results_dict) -> Optional[float]:
        """Read max drawdown as a PERCENT (negative).

        The canonical FLAT run JSON carries ``max_drawdown_pct`` (percent,
        negative) and ``max_drawdown`` (fraction, negative). Prefer the percent
        key; if only the fraction is present, scale it to percent. The
        dashboard log-parsing path already stores a percent value under
        ``max_drawdown`` -- a value already in the percent range (|x| > 1) is
        treated as percent and passed through unchanged.
        """
        if results_dict.get('max_drawdown_pct') is not None:
            return float(results_dict['max_drawdown_pct'])
        raw = results_dict.get('max_drawdown')
        if raw is None:
            return None
        raw = float(raw)
        # A genuine drawdown fraction is in (-1, 0]; anything outside is already
        # expressed in percent.
        return raw if abs(raw) > 1.0 else raw * 100.0

    @staticmethod
    def _total_return_pct(results_dict) -> Optional[float]:
        """Read total return as a PERCENT.

        Prefer the canonical ``total_return_pct``; if only the fraction
        ``total_return`` is present, scale to percent. A bare value already in
        the percent range (|x| > 1) is treated as percent.
        """
        if results_dict.get('total_return_pct') is not None:
            return float(results_dict['total_return_pct'])
        raw = results_dict.get('total_return')
        if raw is None:
            return None
        raw = float(raw)
        return raw if abs(raw) > 1.0 else raw * 100.0

    def validate_backtest_results(self, results_dict) -> Tuple[bool, List[str]]:
        """
        Validate backtest performance results against the canonical FLAT dict.

        Args:
            results_dict: Flat metrics dict as written to
                ``results/runs/run_*.json`` by ``run_production.py``. Read keys:
                sharpe_ratio, sortino_ratio (direct), turnover (annualized,
                direct), max_drawdown_pct (percent, negative),
                total_return_pct (percent), num_trades. Fraction-only inputs are
                tolerated and scaled to percent for the percent thresholds.

        Returns:
            Tuple of (passed, list of issues)
        """
        logger.info("\n" + "="*60)
        logger.info("POST-BACKTEST VALIDATION")
        logger.info("="*60)

        issues = []

        # Check 1: Sharpe Ratio (read directly)
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

        # Check 4: Max Drawdown (percent, negative)
        max_dd = self._drawdown_pct(results_dict)
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

        # Check 6: Total Return (percent)
        total_return = self._total_return_pct(results_dict)
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


def find_latest_run_json(runs_dir: Path = RUNS_DIR) -> Optional[Path]:
    """Return the newest ``run_*.json`` under ``runs_dir`` (by mtime), or None."""
    runs_dir = Path(runs_dir)
    if not runs_dir.exists():
        return None
    candidates = sorted(
        runs_dir.glob('run_*.json'),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def load_run_json(results_file: Path) -> Dict:
    """Load the canonical FLAT run JSON written by run_production.py."""
    with open(results_file, 'r') as f:
        return json.load(f)


def parse_tear_sheet(tearsheet_file) -> Dict:
    """Parse a metrics.py tear sheet (.txt) into the FLAT metrics dict.

    metrics.py ``save_tear_sheet`` writes left-justified ``snake_case`` keys
    (``f"{key:30s}: {value}"``), so anchor on EXACT snake_case key equality
    (``line.split(':')[0].strip() == 'sharpe_ratio'``) rather than the
    Title-Case labels no producer emits. Ratios are plain floats; risk metrics
    (``max_drawdown``) and returns (``total_return``) are written as percent via
    ``{value:10.2%}`` (e.g. ``-15.00%``) and the trailing ``%`` is stripped.
    """
    results: Dict = {}
    # Map of tear-sheet snake_case key -> (flat key, transform)
    ratio_keys = {'sharpe_ratio', 'sortino_ratio', 'calmar_ratio'}
    try:
        with open(tearsheet_file, 'r') as f:
            content = f.read()

        for line in content.split('\n'):
            if ':' not in line:
                continue
            key = line.split(':')[0].strip()
            value = line.split(':', 1)[1].strip()

            try:
                if key in ratio_keys:
                    results[key] = float(value)
                elif key == 'turnover':
                    # Trading metric: plain number (may carry a trailing 'x')
                    results['turnover'] = float(value.replace('x', '').replace(',', ''))
                elif key == 'num_trades':
                    results['num_trades'] = int(float(value.replace(',', '')))
                elif key == 'max_drawdown':
                    # percent-formatted fraction, e.g. '-15.00%'
                    results['max_drawdown_pct'] = float(value.replace('%', '').replace(',', ''))
                elif key == 'total_return':
                    results['total_return_pct'] = float(value.replace('%', '').replace(',', ''))
            except ValueError:
                continue

    except Exception as e:
        logger.error(f"Error parsing tear sheet {tearsheet_file}: {str(e)}")

    return results


def load_results(results_file: Optional[str]) -> Dict:
    """Load backtest metrics, preferring the canonical FLAT run JSON.

    Resolution order:
      1. ``results_file`` ending in ``.json``  -> canonical FLAT run JSON.
      2. ``results_file`` ending in ``.txt``   -> parse metrics.py tear sheet.
      3. ``results_file`` is None              -> newest ``results/runs/*.json``.
    """
    if results_file:
        path = Path(results_file)
        if path.suffix == '.json':
            logger.info(f"Loading canonical run JSON: {path}")
            return load_run_json(path)
        if path.suffix == '.txt':
            logger.info(f"Parsing tear sheet: {path}")
            return parse_tear_sheet(path)
        logger.warning(f"Unrecognized results file extension: {path.suffix}")
        return {}

    latest = find_latest_run_json()
    if latest is None:
        logger.warning(
            "No --results-file given and no results/runs/run_*.json found."
        )
        return {}
    logger.info(f"Using newest canonical run JSON: {latest}")
    return load_run_json(latest)


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
                       help='Path to backtest results: canonical run JSON '
                            '(results/runs/run_*.json) or a metrics.py tear '
                            'sheet .txt. If omitted, the newest '
                            'results/runs/run_*.json is used.')
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

    # Run post-backtest validation unless pre-flight-only. When no explicit
    # --results-file is given, fall back to the newest canonical run JSON.
    if not args.pre_flight_only:
        results = load_results(args.results_file)

        if results:
            post_backtest_passed, post_backtest_issues = validator.validate_backtest_results(results)
        else:
            logger.warning("No backtest results available to validate.")
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

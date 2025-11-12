"""
Threshold Sweep Analysis for ESG Event Detection
Runs multiple backtests with different confidence thresholds to find optimal balance
between signal quality and quantity.

Based on Root Cause Analysis findings:
- Threshold 0.20 (MEDIUM) → 58 events, 0.70 Sharpe (EXCELLENT)
- Threshold 0.15 (HIGH) → 99 events, 0.04 Sharpe (CATASTROPHIC)
- Goal: Find optimal threshold that maximizes Sharpe while achieving >50 trades
"""

import argparse
import yaml
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from datetime import datetime
import json
import sys
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ThresholdSweep:
    """
    Orchestrates threshold sweep analysis
    """

    def __init__(self,
                 thresholds,
                 start_date,
                 end_date,
                 esg_sensitivity='MEDIUM',
                 config_path='config/config.yaml',
                 results_dir='results/threshold_sweep',
                 parallel=False,
                 max_workers=4):
        """
        Initialize threshold sweep

        Args:
            thresholds: List of confidence thresholds to test
            start_date: Backtest start date (YYYY-MM-DD)
            end_date: Backtest end date (YYYY-MM-DD)
            esg_sensitivity: ESG universe sensitivity (MEDIUM, HIGH, ALL)
            config_path: Path to config.yaml
            results_dir: Directory to save results
            parallel: Whether to run backtests in parallel
            max_workers: Maximum parallel workers
        """
        self.thresholds = thresholds
        self.start_date = start_date
        self.end_date = end_date
        self.esg_sensitivity = esg_sensitivity
        self.config_path = config_path
        self.results_dir = Path(results_dir)
        self.parallel = parallel
        self.max_workers = max_workers

        # Create results directory
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Load original config
        with open(config_path, 'r') as f:
            self.base_config = yaml.safe_load(f)

    def run_single_backtest(self, threshold):
        """
        Run backtest for a single threshold value

        Args:
            threshold: Confidence threshold to test

        Returns:
            dict: Backtest results
        """
        logger.info(f"Running backtest with threshold {threshold}...")

        # Create temporary config with modified threshold
        temp_config = self.base_config.copy()
        temp_config['nlp']['event_detector']['confidence_threshold'] = threshold

        # Save temporary config
        temp_config_path = self.results_dir / f"config_threshold_{threshold}.yaml"
        with open(temp_config_path, 'w') as f:
            yaml.dump(temp_config, f)

        # Run backtest
        cmd = [
            'python', 'run_production.py',
            '--config', str(temp_config_path),
            '--esg-sensitivity', self.esg_sensitivity,
            '--start-date', self.start_date,
            '--end-date', self.end_date
        ]

        log_file = self.results_dir / f"backtest_threshold_{threshold}.log"

        try:
            with open(log_file, 'w') as f:
                result = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=3600  # 1 hour timeout per backtest
                )

            if result.returncode == 0:
                logger.info(f"✓ Threshold {threshold} completed successfully")
                # Parse results from log file
                metrics = self._parse_backtest_results(log_file)
                metrics['threshold'] = threshold
                metrics['status'] = 'success'
                return metrics
            else:
                logger.error(f"✗ Threshold {threshold} failed with return code {result.returncode}")
                return {'threshold': threshold, 'status': 'failed'}

        except subprocess.TimeoutExpired:
            logger.error(f"✗ Threshold {threshold} timed out after 1 hour")
            return {'threshold': threshold, 'status': 'timeout'}
        except Exception as e:
            logger.error(f"✗ Threshold {threshold} raised exception: {str(e)}")
            return {'threshold': threshold, 'status': 'error', 'error': str(e)}

    def _parse_backtest_results(self, log_file):
        """
        Parse backtest results from log file

        Args:
            log_file: Path to log file

        Returns:
            dict: Parsed metrics
        """
        metrics = {}

        try:
            with open(log_file, 'r') as f:
                log_content = f.read()

            # Extract key metrics using string parsing
            # Look for performance summary section

            # Total Return
            if 'Total Return:' in log_content:
                for line in log_content.split('\n'):
                    if 'Total Return:' in line:
                        value = line.split(':')[1].strip().replace('%', '')
                        metrics['total_return'] = float(value)
                        break

            # Sharpe Ratio
            if 'Sharpe Ratio:' in log_content:
                for line in log_content.split('\n'):
                    if 'Sharpe Ratio:' in line:
                        value = line.split(':')[1].strip()
                        metrics['sharpe_ratio'] = float(value)
                        break

            # Sortino Ratio
            if 'Sortino Ratio:' in log_content:
                for line in log_content.split('\n'):
                    if 'Sortino Ratio:' in line:
                        value = line.split(':')[1].strip()
                        metrics['sortino_ratio'] = float(value)
                        break

            # Max Drawdown
            if 'Max Drawdown:' in log_content:
                for line in log_content.split('\n'):
                    if 'Max Drawdown:' in line:
                        value = line.split(':')[1].strip().replace('%', '')
                        metrics['max_drawdown'] = float(value)
                        break

            # Volatility
            if 'Volatility:' in log_content:
                for line in log_content.split('\n'):
                    if 'Volatility:' in line and 'Ann' not in line:
                        value = line.split(':')[1].strip().replace('%', '')
                        metrics['volatility'] = float(value)
                        break

            # Turnover
            if 'Turnover:' in log_content:
                for line in log_content.split('\n'):
                    if 'Turnover:' in line:
                        value = line.split(':')[1].strip().replace('x', '')
                        metrics['turnover'] = float(value)
                        break

            # Number of trades
            if 'Total Trades:' in log_content or 'Number of Trades:' in log_content:
                for line in log_content.split('\n'):
                    if 'Total Trades:' in line or 'Number of Trades:' in line:
                        value = line.split(':')[1].strip()
                        metrics['num_trades'] = int(value)
                        break

            # Number of ESG events detected
            if 'ESG events detected:' in log_content or 'Events detected:' in log_content:
                for line in log_content.split('\n'):
                    if 'ESG events detected:' in line or 'Events detected:' in line:
                        value = line.split(':')[1].strip()
                        metrics['num_events'] = int(value)
                        break

        except Exception as e:
            logger.warning(f"Error parsing metrics from {log_file}: {str(e)}")

        return metrics

    def run_sweep(self):
        """
        Run threshold sweep analysis

        Returns:
            pd.DataFrame: Results dataframe
        """
        logger.info("="*60)
        logger.info("THRESHOLD SWEEP ANALYSIS")
        logger.info("="*60)
        logger.info(f"Thresholds to test: {self.thresholds}")
        logger.info(f"Date range: {self.start_date} to {self.end_date}")
        logger.info(f"ESG Sensitivity: {self.esg_sensitivity}")
        logger.info(f"Parallel execution: {self.parallel}")
        logger.info("="*60)

        results = []

        if self.parallel:
            # Run backtests in parallel
            logger.info(f"Running {len(self.thresholds)} backtests in parallel (max {self.max_workers} workers)...")

            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self.run_single_backtest, threshold): threshold
                    for threshold in self.thresholds
                }

                for future in as_completed(futures):
                    threshold = futures[future]
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        logger.error(f"Threshold {threshold} generated exception: {str(e)}")
                        results.append({'threshold': threshold, 'status': 'exception', 'error': str(e)})
        else:
            # Run backtests sequentially
            logger.info(f"Running {len(self.thresholds)} backtests sequentially...")

            for threshold in self.thresholds:
                result = self.run_single_backtest(threshold)
                results.append(result)

        # Convert to DataFrame
        df = pd.DataFrame(results)
        df = df.sort_values('threshold')

        # Calculate signal quality metric (Sharpe per signal)
        if 'sharpe_ratio' in df.columns and 'num_events' in df.columns:
            df['sharpe_per_signal'] = df['sharpe_ratio'] / df['num_events']

        # Save results
        results_file = self.results_dir / 'threshold_sweep_results.csv'
        df.to_csv(results_file, index=False)
        logger.info(f"Results saved to {results_file}")

        # Print summary
        logger.info("\n" + "="*60)
        logger.info("THRESHOLD SWEEP RESULTS SUMMARY")
        logger.info("="*60)
        logger.info(df.to_string(index=False))
        logger.info("="*60)

        return df

    def generate_plots(self, df):
        """
        Generate analysis plots

        Args:
            df: Results dataframe
        """
        logger.info("Generating analysis plots...")

        # Set style
        sns.set_style("whitegrid")
        plt.rcParams['figure.figsize'] = (15, 10)

        # Create figure with subplots
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('Threshold Sweep Analysis: Signal Quality vs. Quantity Trade-off',
                     fontsize=16, fontweight='bold')

        # Filter successful runs
        df_success = df[df['status'] == 'success'].copy()

        if len(df_success) == 0:
            logger.warning("No successful backtests to plot!")
            return

        # Plot 1: Sharpe Ratio vs Threshold
        ax1 = axes[0, 0]
        ax1.plot(df_success['threshold'], df_success['sharpe_ratio'],
                marker='o', linewidth=2, markersize=8, color='#2E86AB')
        ax1.axhline(y=0.60, color='green', linestyle='--', alpha=0.5, label='Target (0.60)')
        ax1.axhline(y=0.50, color='orange', linestyle='--', alpha=0.5, label='Min Acceptable (0.50)')
        ax1.set_xlabel('Confidence Threshold', fontsize=12)
        ax1.set_ylabel('Sharpe Ratio', fontsize=12)
        ax1.set_title('Sharpe Ratio vs. Confidence Threshold', fontsize=13, fontweight='bold')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # Plot 2: Number of Trades vs Threshold
        ax2 = axes[0, 1]
        ax2.plot(df_success['threshold'], df_success['num_trades'],
                marker='s', linewidth=2, markersize=8, color='#A23B72')
        ax2.axhline(y=50, color='red', linestyle='--', alpha=0.5, label='Target (50 trades)')
        ax2.set_xlabel('Confidence Threshold', fontsize=12)
        ax2.set_ylabel('Number of Trades', fontsize=12)
        ax2.set_title('Trade Count vs. Confidence Threshold', fontsize=13, fontweight='bold')
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        # Plot 3: Signal Quality Metric (Sharpe per Signal)
        ax3 = axes[0, 2]
        if 'sharpe_per_signal' in df_success.columns:
            ax3.plot(df_success['threshold'], df_success['sharpe_per_signal'],
                    marker='^', linewidth=2, markersize=8, color='#F18F01')
            ax3.set_xlabel('Confidence Threshold', fontsize=12)
            ax3.set_ylabel('Sharpe / # Signals', fontsize=12)
            ax3.set_title('Signal Quality Metric (Sharpe per Signal)', fontsize=13, fontweight='bold')
            ax3.grid(True, alpha=0.3)

        # Plot 4: Total Return vs Threshold
        ax4 = axes[1, 0]
        ax4.plot(df_success['threshold'], df_success['total_return'],
                marker='D', linewidth=2, markersize=8, color='#006E90')
        ax4.set_xlabel('Confidence Threshold', fontsize=12)
        ax4.set_ylabel('Total Return (%)', fontsize=12)
        ax4.set_title('Total Return vs. Confidence Threshold', fontsize=13, fontweight='bold')
        ax4.grid(True, alpha=0.3)

        # Plot 5: Sortino Ratio vs Threshold
        ax5 = axes[1, 1]
        ax5.plot(df_success['threshold'], df_success['sortino_ratio'],
                marker='v', linewidth=2, markersize=8, color='#BC4B51')
        ax5.axhline(y=1.20, color='green', linestyle='--', alpha=0.5, label='Target (1.20)')
        ax5.set_xlabel('Confidence Threshold', fontsize=12)
        ax5.set_ylabel('Sortino Ratio', fontsize=12)
        ax5.set_title('Sortino Ratio vs. Confidence Threshold', fontsize=13, fontweight='bold')
        ax5.legend()
        ax5.grid(True, alpha=0.3)

        # Plot 6: Turnover vs Threshold
        ax6 = axes[1, 2]
        ax6.plot(df_success['threshold'], df_success['turnover'],
                marker='p', linewidth=2, markersize=8, color='#8B2635')
        ax6.axhline(y=5.0, color='orange', linestyle='--', alpha=0.5, label='Max Recommended (5x)')
        ax6.set_xlabel('Confidence Threshold', fontsize=12)
        ax6.set_ylabel('Turnover (x)', fontsize=12)
        ax6.set_title('Turnover vs. Confidence Threshold', fontsize=13, fontweight='bold')
        ax6.legend()
        ax6.grid(True, alpha=0.3)

        plt.tight_layout()

        # Save plot
        plot_file = self.results_dir / 'threshold_sweep_analysis.png'
        plt.savefig(plot_file, dpi=300, bbox_inches='tight')
        logger.info(f"Plots saved to {plot_file}")

        plt.close()

        # Create summary plot: Sharpe vs Trades (the key trade-off)
        fig, ax = plt.subplots(figsize=(10, 7))

        scatter = ax.scatter(df_success['num_trades'], df_success['sharpe_ratio'],
                           c=df_success['threshold'], cmap='viridis',
                           s=200, alpha=0.7, edgecolors='black', linewidth=1.5)

        # Add threshold labels
        for _, row in df_success.iterrows():
            ax.annotate(f"{row['threshold']:.2f}",
                       (row['num_trades'], row['sharpe_ratio']),
                       xytext=(5, 5), textcoords='offset points',
                       fontsize=9, fontweight='bold')

        # Add target zones
        ax.axhline(y=0.60, color='green', linestyle='--', alpha=0.3, label='Sharpe Target (0.60)')
        ax.axvline(x=50, color='red', linestyle='--', alpha=0.3, label='Trade Target (50)')

        # Highlight optimal zone
        ax.fill_between([50, df_success['num_trades'].max()], 0.60, df_success['sharpe_ratio'].max(),
                       alpha=0.1, color='green', label='Optimal Zone')

        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label('Confidence Threshold', fontsize=12)

        ax.set_xlabel('Number of Trades', fontsize=13, fontweight='bold')
        ax.set_ylabel('Sharpe Ratio', fontsize=13, fontweight='bold')
        ax.set_title('Signal Quality vs. Quantity Trade-off\n(Goal: Top-Right Quadrant)',
                    fontsize=14, fontweight='bold')
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        tradeoff_file = self.results_dir / 'quality_vs_quantity_tradeoff.png'
        plt.savefig(tradeoff_file, dpi=300, bbox_inches='tight')
        logger.info(f"Trade-off plot saved to {tradeoff_file}")

        plt.close()

    def find_optimal_threshold(self, df, min_trades=50, min_sharpe=0.60):
        """
        Find optimal threshold balancing quality and quantity

        Args:
            df: Results dataframe
            min_trades: Minimum number of trades required
            min_sharpe: Minimum Sharpe ratio required

        Returns:
            float: Optimal threshold
        """
        logger.info("\n" + "="*60)
        logger.info("FINDING OPTIMAL THRESHOLD")
        logger.info("="*60)

        # Filter successful runs
        df_success = df[df['status'] == 'success'].copy()

        # Find candidates that meet both criteria
        candidates = df_success[
            (df_success['num_trades'] >= min_trades) &
            (df_success['sharpe_ratio'] >= min_sharpe)
        ]

        if len(candidates) > 0:
            # Choose the one with highest Sharpe ratio
            optimal = candidates.loc[candidates['sharpe_ratio'].idxmax()]
            logger.info(f"✓ OPTIMAL THRESHOLD FOUND: {optimal['threshold']}")
            logger.info(f"  - Trades: {optimal['num_trades']}")
            logger.info(f"  - Sharpe: {optimal['sharpe_ratio']:.3f}")
            logger.info(f"  - Return: {optimal['total_return']:.2f}%")
            return optimal['threshold']
        else:
            # No perfect candidate, find best compromise
            logger.warning("No threshold meets both criteria. Finding best compromise...")

            # Normalize metrics to [0, 1] and compute weighted score
            df_success['norm_trades'] = df_success['num_trades'] / min_trades
            df_success['norm_sharpe'] = df_success['sharpe_ratio'] / min_sharpe

            # Weighted score: 60% Sharpe, 40% Trades (quality > quantity)
            df_success['score'] = 0.6 * df_success['norm_sharpe'] + 0.4 * df_success['norm_trades']

            optimal = df_success.loc[df_success['score'].idxmax()]
            logger.info(f"⚠ COMPROMISE THRESHOLD: {optimal['threshold']}")
            logger.info(f"  - Trades: {optimal['num_trades']} (target: {min_trades})")
            logger.info(f"  - Sharpe: {optimal['sharpe_ratio']:.3f} (target: {min_sharpe})")
            logger.info(f"  - Return: {optimal['total_return']:.2f}%")
            logger.info(f"  - Composite Score: {optimal['score']:.3f}")
            return optimal['threshold']


def main():
    """Main execution"""
    parser = argparse.ArgumentParser(
        description='Threshold Sweep Analysis for ESG Event Detection'
    )
    parser.add_argument('--thresholds', type=float, nargs='+',
                       default=[0.15, 0.16, 0.17, 0.18, 0.19, 0.20, 0.22, 0.25],
                       help='Confidence thresholds to test')
    parser.add_argument('--start-date', type=str, required=True,
                       help='Backtest start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, required=True,
                       help='Backtest end date (YYYY-MM-DD)')
    parser.add_argument('--esg-sensitivity', type=str, default='MEDIUM',
                       choices=['MEDIUM', 'HIGH', 'ALL'],
                       help='ESG universe sensitivity')
    parser.add_argument('--parallel', action='store_true',
                       help='Run backtests in parallel')
    parser.add_argument('--max-workers', type=int, default=4,
                       help='Maximum parallel workers')
    parser.add_argument('--config', type=str, default='config/config.yaml',
                       help='Path to configuration file')
    parser.add_argument('--results-dir', type=str, default='results/threshold_sweep',
                       help='Directory to save results')

    args = parser.parse_args()

    # Run threshold sweep
    sweep = ThresholdSweep(
        thresholds=args.thresholds,
        start_date=args.start_date,
        end_date=args.end_date,
        esg_sensitivity=args.esg_sensitivity,
        config_path=args.config,
        results_dir=args.results_dir,
        parallel=args.parallel,
        max_workers=args.max_workers
    )

    # Execute sweep
    results_df = sweep.run_sweep()

    # Generate plots
    sweep.generate_plots(results_df)

    # Find optimal threshold
    optimal_threshold = sweep.find_optimal_threshold(results_df)

    logger.info("\n" + "="*60)
    logger.info("THRESHOLD SWEEP COMPLETE!")
    logger.info("="*60)
    logger.info(f"Results saved to: {sweep.results_dir}")
    logger.info(f"Recommended threshold: {optimal_threshold}")
    logger.info("="*60)


if __name__ == '__main__':
    main()

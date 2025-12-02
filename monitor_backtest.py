#!/usr/bin/env python3
"""
Real-Time Backtest Progress Monitor
Visualizes the progress of the ESG trading strategy backtest in real-time.
"""

import re
import time
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

try:
    from rich.console import Console
    from rich.live import Live
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    from rich.panel import Panel
    from rich.layout import Layout
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Installing rich library for better visualization...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "rich"], check=True)
    from rich.console import Console
    from rich.live import Live
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    from rich.panel import Panel
    from rich.layout import Layout
    from rich import box


class BacktestMonitor:
    """Real-time monitor for ESG backtest progress."""

    def __init__(self, log_path: str = "logs/esg_strategy.log"):
        self.log_path = Path(log_path)
        self.console = Console()

        # Phase definitions with expected counts and time estimates
        self.phases = {
            'universe': {'name': 'Stock Universe', 'total': 1, 'time_est': 1},
            'filings': {'name': 'SEC Filings', 'total': 172, 'time_est': 15},
            'prices': {'name': 'Price Data', 'total': 172, 'time_est': 10},
            'factors': {'name': 'Fama-French Factors', 'total': 1, 'time_est': 1},
            'events_reddit': {'name': 'Events & Reddit Analysis', 'total': None, 'time_est': 35},
            'signals': {'name': 'Signal Generation', 'total': None, 'time_est': 2},
            'portfolio': {'name': 'Portfolio Construction', 'total': None, 'time_est': 2},
            'backtest': {'name': 'Backtesting', 'total': None, 'time_est': 10},
            'performance': {'name': 'Performance Analysis', 'total': None, 'time_est': 2},
            'factor_analysis': {'name': 'Factor Analysis', 'total': None, 'time_est': 2}
        }

        # Progress tracking
        self.current_phase = None
        self.phase_progress = defaultdict(lambda: {'current': 0, 'total': None, 'status': ''})
        self.start_time = None
        self.phase_start_times = {}
        self.completed_phases = set()
        self.total_filings = 0
        self.total_events = 0
        self.errors = []

    def extract_timestamp(self, line: str) -> datetime:
        """Extract timestamp from log line."""
        try:
            timestamp_str = line.split(' - ')[0].strip()
            return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        except:
            return datetime.now()

    def parse_log_line(self, line: str):
        """Parse a log line and update progress."""

        # Detect new backtest run - reset everything
        if "ESG EVENT-DRIVEN ALPHA STRATEGY - PRODUCTION RUN" in line:
            # Reset all tracking for new run
            self.start_time = self.extract_timestamp(line)
            self.current_phase = None
            self.phase_progress = defaultdict(lambda: {'current': 0, 'total': None, 'status': ''})
            self.phase_start_times = {}
            self.completed_phases = set()
            self.total_filings = 0
            self.total_events = 0
            self.errors = []
            return

        # Universe phase
        if ">>> STEP 1: FETCHING STOCK UNIVERSE" in line:
            self.current_phase = 'universe'
            self.phase_start_times['universe'] = self.extract_timestamp(line)
        elif "Universe: " in line and "tickers" in line:
            match = re.search(r'Universe: (\d+) tickers', line)
            if match:
                count = int(match.group(1))
                self.phases['filings']['total'] = count
                self.phases['prices']['total'] = count
                self.phase_progress['universe']['current'] = 1
                self.phase_progress['universe']['total'] = 1
                self.completed_phases.add('universe')

        # SEC Filings phase
        elif ">>> STEP 2: DOWNLOADING SEC FILINGS" in line:
            self.current_phase = 'filings'
            self.phase_start_times['filings'] = self.extract_timestamp(line)
        elif re.search(r'Downloading filings for \w+ \((\d+)/(\d+)\)', line):
            match = re.search(r'Downloading filings for (\w+) \((\d+)/(\d+)\)', line)
            if match:
                ticker = match.group(1)
                current = int(match.group(2))
                total = int(match.group(3))
                self.phase_progress['filings']['current'] = current
                self.phase_progress['filings']['total'] = total
                self.phase_progress['filings']['status'] = f"Downloading {ticker}"
        elif "Saved filings to" in line:
            match = re.search(r'(\d+) filings', line)
            if match:
                self.total_filings = int(match.group(1))
            self.completed_phases.add('filings')

        # Price data phase
        elif ">>> STEP 3: FETCHING PRICE DATA" in line:
            self.current_phase = 'prices'
            self.phase_start_times['prices'] = self.extract_timestamp(line)
        elif re.search(r'Fetching prices for \w+ \((\d+)/(\d+)\)', line):
            match = re.search(r'Fetching prices for (\w+) \((\d+)/(\d+)\)', line)
            if match:
                ticker = match.group(1)
                current = int(match.group(2))
                total = int(match.group(3))
                self.phase_progress['prices']['current'] = current
                self.phase_progress['prices']['total'] = total
                self.phase_progress['prices']['status'] = f"Fetching {ticker}"
        elif "Saved prices to" in line:
            self.completed_phases.add('prices')

        # Fama-French factors phase
        elif ">>> STEP 4: LOADING FAMA-FRENCH FACTORS" in line:
            self.current_phase = 'factors'
            self.phase_start_times['factors'] = self.extract_timestamp(line)
            self.phase_progress['factors']['current'] = 1
            self.phase_progress['factors']['total'] = 1
        elif "Loaded Fama-French" in line or ("STEP 5:" in line and self.current_phase == 'factors'):
            self.completed_phases.add('factors')

        # Events & Reddit analysis phase (combined STEP 5)
        elif ">>> STEP 5: EVENT DETECTION & REDDIT SENTIMENT ANALYSIS" in line:
            self.current_phase = 'events_reddit'
            self.phase_start_times['events_reddit'] = self.extract_timestamp(line)
        elif self.current_phase == 'events_reddit':
            if "Fetching Reddit data around" in line:
                match = re.search(r'around (\d{4}-\d{2}-\d{2})', line)
                if match:
                    date = match.group(1)
                    self.phase_progress['events_reddit']['status'] = f"Reddit data {date}"
            elif "Detected" in line and "ESG events with Reddit reactions" in line:
                match = re.search(r'Detected (\d+) ESG events', line)
                if match:
                    count = int(match.group(1))
                    self.total_events = count
                    self.phase_progress['events_reddit']['current'] = count
                    self.phase_progress['events_reddit']['total'] = count
                    self.phase_progress['events_reddit']['status'] = f"{count} events detected"
            elif ">>> STEP 6:" in line:
                self.completed_phases.add('events_reddit')

        # Signal generation phase
        elif ">>> STEP 6: SIGNAL GENERATION" in line:
            self.current_phase = 'signals'
            self.phase_start_times['signals'] = self.extract_timestamp(line)
        elif "Generated" in line and "signals" in line:
            self.completed_phases.add('signals')

        # Portfolio construction phase
        elif ">>> STEP 7: PORTFOLIO CONSTRUCTION" in line:
            self.current_phase = 'portfolio'
            self.phase_start_times['portfolio'] = self.extract_timestamp(line)
        elif "Portfolio constructed" in line or ">>> STEP 8:" in line:
            if self.current_phase == 'portfolio':
                self.completed_phases.add('portfolio')

        # Backtesting phase
        elif ">>> STEP 8: BACKTESTING" in line:
            self.current_phase = 'backtest'
            self.phase_start_times['backtest'] = self.extract_timestamp(line)
        elif "Backtest complete" in line or ">>> STEP 9:" in line:
            if self.current_phase == 'backtest':
                self.completed_phases.add('backtest')

        # Performance Analysis phase
        elif ">>> STEP 9: PERFORMANCE ANALYSIS" in line:
            self.current_phase = 'performance'
            self.phase_start_times['performance'] = self.extract_timestamp(line)
        elif "Tearsheet saved to" in line or ">>> STEP 10:" in line:
            if self.current_phase == 'performance':
                self.completed_phases.add('performance')

        # Factor Analysis phase
        elif ">>> STEP 10: FACTOR ANALYSIS" in line:
            self.current_phase = 'factor_analysis'
            self.phase_start_times['factor_analysis'] = self.extract_timestamp(line)
        elif "Factor analysis complete" in line or "All steps complete" in line:
            if self.current_phase == 'factor_analysis':
                self.completed_phases.add('factor_analysis')

        # Error tracking
        if "Error" in line or "ERROR" in line:
            # Extract ticker from error message if possible
            match = re.search(r'Error.*?(\w+):', line)
            if match and match.group(1) not in [e.split(':')[0] for e in self.errors]:
                self.errors.append(f"{match.group(1)}: {line.split('Error')[-1].strip()[:50]}")

    def generate_display(self) -> Table:
        """Generate the rich display table."""

        # Main layout
        layout = Table(show_header=False, box=box.ROUNDED, border_style="cyan", padding=(0, 1))
        layout.add_column(justify="left", ratio=1)

        # Header
        header = Table(show_header=False, box=None, padding=(0, 1))
        header.add_column(justify="center", style="bold cyan")
        header.add_row("🚀 ESG TRADING STRATEGY - BACKTEST MONITOR 🚀")
        header.add_row(f"Started: {self.start_time.strftime('%H:%M:%S') if self.start_time else 'N/A'}")
        layout.add_row(header)

        # Overall Progress
        overall_progress = Table(show_header=True, box=box.SIMPLE, padding=(0, 1))
        overall_progress.add_column("Phase", style="cyan", width=20)
        overall_progress.add_column("Status", justify="center", width=12)
        overall_progress.add_column("Progress", width=40)
        overall_progress.add_column("Time", justify="right", width=10)

        for phase_key, phase_info in self.phases.items():
            phase_name = phase_info['name']
            progress = self.phase_progress[phase_key]

            # Status emoji
            if phase_key in self.completed_phases:
                status = "✅ Done"
                status_style = "green"
            elif phase_key == self.current_phase:
                status = "🔄 Running"
                status_style = "yellow"
            else:
                status = "⏳ Pending"
                status_style = "dim"

            # Progress bar
            if progress['total'] and progress['total'] > 0:
                pct = (progress['current'] / progress['total']) * 100
                bar_length = 30
                filled = int(bar_length * progress['current'] / progress['total'])
                bar = "█" * filled + "░" * (bar_length - filled)
                progress_text = f"{bar} {progress['current']}/{progress['total']} ({pct:.1f}%)"
            elif phase_key in self.completed_phases:
                progress_text = "█" * 30 + " 100%"
            else:
                progress_text = "░" * 30 + " 0%"

            # Time
            if phase_key in self.phase_start_times:
                elapsed = (datetime.now() - self.phase_start_times[phase_key]).total_seconds() / 60
                time_text = f"{elapsed:.1f}m"
            elif phase_key in self.completed_phases:
                time_text = "✓"
            else:
                time_text = f"~{phase_info['time_est']}m"

            overall_progress.add_row(
                phase_name,
                f"[{status_style}]{status}[/{status_style}]",
                progress_text,
                time_text
            )

        layout.add_row(overall_progress)

        # Current Activity
        if self.current_phase:
            activity = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
            activity.add_column(style="yellow")

            phase_name = self.phases[self.current_phase]['name']
            status = self.phase_progress[self.current_phase].get('status', 'Processing...')
            activity.add_row(f"[bold]Current:[/bold] {phase_name} - {status}")

            layout.add_row(activity)

        # Statistics
        stats = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
        stats.add_column(justify="left", style="cyan")
        stats.add_column(justify="right", style="white")

        stats.add_row("Total Filings", f"{self.total_filings:,}" if self.total_filings else "N/A")
        stats.add_row("Total Events", f"{self.total_events:,}" if self.total_events else "N/A")
        stats.add_row("Errors", f"[red]{len(self.errors)}[/red]" if self.errors else "[green]0[/green]")

        if self.start_time:
            elapsed = datetime.now() - self.start_time
            stats.add_row("Elapsed Time", str(elapsed).split('.')[0])

            # Estimate remaining time
            completed = len(self.completed_phases)
            total_phases = len(self.phases)
            if completed > 0:
                avg_time = elapsed.total_seconds() / completed
                remaining_phases = total_phases - completed
                est_remaining = timedelta(seconds=avg_time * remaining_phases)
                stats.add_row("Est. Remaining", str(est_remaining).split('.')[0])

        layout.add_row(stats)

        # Errors (if any)
        if self.errors:
            error_table = Table(show_header=True, box=box.SIMPLE, padding=(0, 1))
            error_table.add_column("Recent Errors", style="red")
            for error in self.errors[-5:]:  # Show last 5 errors
                error_table.add_row(error)
            layout.add_row(error_table)

        # Footer
        footer = Table(show_header=False, box=None, padding=(0, 0))
        footer.add_column(justify="center", style="dim")
        footer.add_row("Press Ctrl+C to exit")
        layout.add_row(footer)

        return layout

    def tail_log(self):
        """Tail the log file and parse new lines."""
        if not self.log_path.exists():
            self.console.print(f"[red]Error: Log file not found at {self.log_path}[/red]")
            self.console.print("[yellow]Waiting for log file to be created...[/yellow]")

            # Wait for log file to be created
            while not self.log_path.exists():
                time.sleep(1)

        with open(self.log_path, 'r') as f:
            # Read existing lines
            for line in f:
                self.parse_log_line(line)

            # Continue tailing
            while True:
                line = f.readline()
                if line:
                    self.parse_log_line(line)
                else:
                    # Check if all phases are complete
                    if len(self.completed_phases) >= len(self.phases) - 1:  # -1 because some phases might be skipped
                        break
                    time.sleep(0.5)

    def run(self):
        """Run the monitor with live display."""
        self.console.clear()

        try:
            with Live(self.generate_display(), refresh_per_second=2, console=self.console) as live:
                # Start tailing in a way that updates the display
                if not self.log_path.exists():
                    self.console.print(f"[yellow]Waiting for log file: {self.log_path}[/yellow]")
                    while not self.log_path.exists():
                        time.sleep(1)

                with open(self.log_path, 'r') as f:
                    # Read existing lines
                    for line in f:
                        self.parse_log_line(line)

                    live.update(self.generate_display())

                    # Continue tailing
                    last_update = time.time()
                    while True:
                        line = f.readline()
                        if line:
                            self.parse_log_line(line)

                            # Update display every 0.5 seconds
                            if time.time() - last_update > 0.5:
                                live.update(self.generate_display())
                                last_update = time.time()
                        else:
                            # Update display even if no new lines
                            live.update(self.generate_display())

                            # Check if complete
                            if 'analysis' in self.completed_phases or 'backtest' in self.completed_phases:
                                time.sleep(2)  # Show final state for 2 seconds
                                break

                            time.sleep(0.5)

            # Final message
            self.console.print("\n[bold green]✅ Backtest Complete![/bold green]")
            if self.total_events:
                self.console.print(f"[cyan]Total Events Detected: {self.total_events:,}[/cyan]")
            if self.errors:
                self.console.print(f"[yellow]Warnings/Errors: {len(self.errors)}[/yellow]")

            self.console.print(f"\n[bold]Check results at:[/bold] results/tear_sheets/")

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Monitor stopped by user[/yellow]")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Monitor ESG trading strategy backtest progress in real-time"
    )
    parser.add_argument(
        '--log-file',
        default='logs/esg_strategy.log',
        help='Path to log file (default: logs/esg_strategy.log)'
    )

    args = parser.parse_args()

    monitor = BacktestMonitor(log_path=args.log_file)
    monitor.run()


if __name__ == '__main__':
    main()

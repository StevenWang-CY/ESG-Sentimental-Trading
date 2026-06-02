#!/usr/bin/env python3
"""
Real-Time Backtest Progress Monitor
Visualizes the progress of the ESG trading strategy backtest in real-time.
"""

import re
import json
import time
import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

# Optional dependency: rich provides the live TUI. We NEVER install packages as
# an import side-effect -- if rich is missing we print an actionable message and
# the monitor falls back to plain stdout (or exits cleanly from main()).
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
    Console = Live = Table = box = None  # sentinels for type checks / fallback


class BacktestMonitor:
    """Real-time monitor for ESG backtest progress."""

    def __init__(self, log_path: str = "logs/esg_strategy.log",
                 runs_dir: str = "results/runs"):
        self.log_path = Path(log_path)
        self.runs_dir = Path(runs_dir)
        self.console = Console() if RICH_AVAILABLE else None

        # True once we have matched at least one recognized log/run marker; used
        # to surface a visible warning when the log format has drifted and the
        # monitor recognizes nothing.
        self.saw_known_marker = False

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
        """Parse a log line and update progress.

        Phase markers are matched on SOURCE-AGNOSTIC prefixes (e.g.
        ``'>>> STEP 5: EVENT DETECTION &'``, ``'ESG events with'``,
        ``'periods of factor data'``, ``'Saved tear sheet to'``) rather than
        literal data-source names (REDDIT / 'Loaded Fama-French' /
        'Portfolio constructed' / 'Factor analysis complete'), so the monitor
        keeps working when the underlying social/factor source changes.
        """

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
            self.saw_known_marker = True
            return

        # Universe phase
        if ">>> STEP 1: FETCHING STOCK UNIVERSE" in line:
            self.current_phase = 'universe'
            self.phase_start_times['universe'] = self.extract_timestamp(line)
            self.saw_known_marker = True
        elif "Universe: " in line and "tickers" in line:
            match = re.search(r'Universe: (\d+) tickers', line)
            if match:
                count = int(match.group(1))
                self.phases['filings']['total'] = count
                self.phases['prices']['total'] = count
                self.phase_progress['universe']['current'] = 1
                self.phase_progress['universe']['total'] = 1
                self.completed_phases.add('universe')
                self.saw_known_marker = True

        # SEC Filings phase
        elif ">>> STEP 2: DOWNLOADING SEC FILINGS" in line:
            self.current_phase = 'filings'
            self.phase_start_times['filings'] = self.extract_timestamp(line)
            self.saw_known_marker = True
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
            self.saw_known_marker = True
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

        # Factor data phase (STEP 4). Source-agnostic: match the STEP 4 prefix,
        # and complete on the source-neutral 'periods of factor data' summary
        # line (or arrival of STEP 5) instead of a 'Loaded Fama-French' literal.
        elif ">>> STEP 4:" in line:
            self.current_phase = 'factors'
            self.phase_start_times['factors'] = self.extract_timestamp(line)
            self.phase_progress['factors']['current'] = 1
            self.phase_progress['factors']['total'] = 1
            self.saw_known_marker = True
        elif "periods of factor data" in line:
            self.completed_phases.add('factors')

        # Event detection & social sentiment phase (combined STEP 5).
        # Source-agnostic: anchor on the STEP 5 prefix rather than a social
        # source name. A STEP 5 start implies STEP 4 (factors) finished.
        elif ">>> STEP 5: EVENT DETECTION &" in line:
            if self.current_phase == 'factors':
                self.completed_phases.add('factors')
            self.current_phase = 'events_reddit'
            self.phase_start_times['events_reddit'] = self.extract_timestamp(line)
            self.saw_known_marker = True

        # Signal generation phase. A STEP 6 start completes the events phase.
        elif ">>> STEP 6: SIGNAL GENERATION" in line:
            if self.current_phase == 'events_reddit':
                self.completed_phases.add('events_reddit')
            self.current_phase = 'signals'
            self.phase_start_times['signals'] = self.extract_timestamp(line)
            self.saw_known_marker = True
        elif "Generated" in line and "signals" in line:
            if self.current_phase == 'signals':
                self.completed_phases.add('signals')

        # Portfolio construction phase. Source-agnostic completion: arrival of
        # STEP 8 marks portfolio done (no 'Portfolio constructed' literal).
        elif ">>> STEP 7: PORTFOLIO CONSTRUCTION" in line:
            if self.current_phase == 'signals':
                self.completed_phases.add('signals')
            self.current_phase = 'portfolio'
            self.phase_start_times['portfolio'] = self.extract_timestamp(line)
            self.saw_known_marker = True

        # Backtesting phase. A STEP 8 start completes portfolio.
        elif ">>> STEP 8: BACKTESTING" in line:
            if self.current_phase == 'portfolio':
                self.completed_phases.add('portfolio')
            self.current_phase = 'backtest'
            self.phase_start_times['backtest'] = self.extract_timestamp(line)
            self.saw_known_marker = True
        elif "Backtest complete" in line:
            if self.current_phase == 'backtest':
                self.completed_phases.add('backtest')

        # Performance Analysis phase. A STEP 9 start completes backtest;
        # completion anchors on the emitted 'Saved tear sheet to' line.
        elif ">>> STEP 9: PERFORMANCE ANALYSIS" in line:
            if self.current_phase == 'backtest':
                self.completed_phases.add('backtest')
            self.current_phase = 'performance'
            self.phase_start_times['performance'] = self.extract_timestamp(line)
            self.saw_known_marker = True
        elif "Saved tear sheet to" in line or "Tearsheet saved to" in line:
            if self.current_phase == 'performance':
                self.completed_phases.add('performance')

        # Factor Analysis phase. A STEP 10 start completes performance;
        # completion anchors on the source-neutral final marker.
        elif ">>> STEP 10: FACTOR ANALYSIS" in line:
            if self.current_phase == 'performance':
                self.completed_phases.add('performance')
            self.current_phase = 'factor_analysis'
            self.phase_start_times['factor_analysis'] = self.extract_timestamp(line)
            self.saw_known_marker = True
        elif "All steps complete" in line or "PRODUCTION RUN COMPLETE" in line:
            if self.current_phase == 'factor_analysis':
                self.completed_phases.add('factor_analysis')

        # Within-phase progress for the event/social phase. Handled as a
        # NON-consuming block (after the STEP-start elif chain) so STEP markers
        # always take priority and are never swallowed.
        if self.current_phase == 'events_reddit':
            if "Fetching" in line and "data around" in line:
                match = re.search(r'around (\d{4}-\d{2}-\d{2})', line)
                if match:
                    self.phase_progress['events_reddit']['status'] = f"Social data {match.group(1)}"
            elif "ESG events with" in line:
                match = re.search(r'(\d+) ESG events', line)
                if match:
                    count = int(match.group(1))
                    self.total_events = count
                    self.phase_progress['events_reddit']['current'] = count
                    self.phase_progress['events_reddit']['total'] = count
                    self.phase_progress['events_reddit']['status'] = f"{count} events detected"

        # Error tracking
        if "Error" in line or "ERROR" in line:
            # Extract ticker from error message if possible
            match = re.search(r'Error.*?(\w+):', line)
            if match and match.group(1) not in [e.split(':')[0] for e in self.errors]:
                self.errors.append(f"{match.group(1)}: {line.split('Error')[-1].strip()[:50]}")

    def latest_run_json(self):
        """Return the newest ``results/runs/run_*.json`` path, or None.

        The canonical run JSON written by run_production.py is the preferred
        source of completion/progress when present.
        """
        if not self.runs_dir.exists():
            return None
        candidates = sorted(
            self.runs_dir.glob('run_*.json'),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return candidates[0] if candidates else None

    def apply_run_json(self) -> bool:
        """Fold the newest canonical run JSON into progress, if present.

        A completed run JSON means the whole pipeline finished, so all phases
        are marked done and headline counts are pulled from the flat metrics.
        Returns True if a run JSON was found and applied.
        """
        run_json = self.latest_run_json()
        if run_json is None:
            return False

        try:
            with open(run_json, 'r') as f:
                data = json.load(f)
        except Exception as e:
            logger.warning("Could not read run JSON %s: %s", run_json, e)
            return False

        self.saw_known_marker = True
        status = data.get('status', 'COMPLETE')

        # A COMPLETE/FACTOR_ANALYSIS_INVALID run has produced final metrics; mark
        # every tracked phase as done so the display reflects completion.
        if status in ('COMPLETE', 'FACTOR_ANALYSIS_INVALID'):
            self.completed_phases.update(self.phases.keys())
            for key in self.phases:
                progress = self.phase_progress[key]
                if progress.get('total') is None:
                    progress['total'] = 1
                    progress['current'] = 1

        num_trades = data.get('num_trades')
        if num_trades:
            try:
                self.total_events = int(num_trades)
            except (TypeError, ValueError):
                pass

        return True

    def warn_if_no_markers(self) -> None:
        """Emit a VISIBLE warning if no recognized markers were ever seen.

        This makes log-format drift (the failure mode where the monitor parses
        a producer that emits different labels) detectable instead of silently
        showing an all-pending screen.
        """
        if self.saw_known_marker:
            return
        message = (
            "WARNING: no matching log lines seen. The monitor recognized no "
            "known phase markers in the log or any results/runs/*.json. The log "
            "format may have drifted, or the run has not started emitting "
            "progress yet."
        )
        if RICH_AVAILABLE and self.console is not None:
            self.console.print(f"[bold yellow]{message}[/bold yellow]")
        else:
            print(message)
        logger.warning(message)

    def render_plain(self) -> str:
        """Plain-text rendering used when rich is unavailable."""
        lines = []
        lines.append("=" * 60)
        lines.append("ESG TRADING STRATEGY - BACKTEST MONITOR")
        started = self.start_time.strftime('%H:%M:%S') if self.start_time else 'N/A'
        lines.append(f"Started: {started}")
        lines.append("=" * 60)

        for phase_key, phase_info in self.phases.items():
            progress = self.phase_progress[phase_key]
            if phase_key in self.completed_phases:
                status = "DONE"
            elif phase_key == self.current_phase:
                status = "RUNNING"
            else:
                status = "PENDING"

            if progress.get('total') and progress['total'] > 0:
                pct = (progress['current'] / progress['total']) * 100
                detail = f"{progress['current']}/{progress['total']} ({pct:.0f}%)"
            elif phase_key in self.completed_phases:
                detail = "100%"
            else:
                detail = "0%"

            lines.append(f"  [{status:8s}] {phase_info['name']:28s} {detail}")

        lines.append("-" * 60)
        lines.append(f"  Total Filings : {self.total_filings or 'N/A'}")
        lines.append(f"  Total Events  : {self.total_events or 'N/A'}")
        lines.append(f"  Errors        : {len(self.errors)}")
        lines.append("=" * 60)
        return "\n".join(lines)

    def run_plain(self) -> None:
        """Fallback monitor loop without rich: tail log and print snapshots."""
        if not self.apply_run_json():
            if not self.log_path.exists():
                print(f"Waiting for log file: {self.log_path}")
                while not self.log_path.exists():
                    time.sleep(1)

            with open(self.log_path, 'r') as f:
                for line in f:
                    self.parse_log_line(line)

                print(self.render_plain())
                last_update = time.time()
                while True:
                    line = f.readline()
                    if line:
                        self.parse_log_line(line)
                        if time.time() - last_update > 1.0:
                            print(self.render_plain())
                            last_update = time.time()
                    else:
                        # Run JSON appearing means the run finished.
                        if self.apply_run_json():
                            break
                        if len(self.completed_phases) >= len(self.phases) - 1:
                            break
                        time.sleep(0.5)

        print(self.render_plain())
        self.warn_if_no_markers()
        print("\nBacktest monitor finished. Check results at: results/tear_sheets/")

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
            msg = f"Log file not found at {self.log_path}; waiting for it to be created..."
            if RICH_AVAILABLE and self.console is not None:
                self.console.print(f"[red]{msg}[/red]")
            else:
                print(msg)

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
        """Run the monitor with live display (rich) or plain fallback."""
        if not RICH_AVAILABLE:
            self.run_plain()
            return

        self.console.clear()

        # Prefer the canonical run JSON when a completed run is already on disk.
        if self.apply_run_json():
            self.console.print(self.generate_display())
            self.warn_if_no_markers()
            self.console.print("\n[bold green]✅ Backtest Complete![/bold green]")
            self.console.print("\n[bold]Check results at:[/bold] results/tear_sheets/")
            return

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
                            # A canonical run JSON appearing means the run is done.
                            if self.apply_run_json():
                                live.update(self.generate_display())
                                time.sleep(1)
                                break

                            # Update display even if no new lines
                            live.update(self.generate_display())

                            # Check if complete
                            if 'factor_analysis' in self.completed_phases or 'backtest' in self.completed_phases:
                                time.sleep(2)  # Show final state for 2 seconds
                                break

                            time.sleep(0.5)

            # Final message
            self.warn_if_no_markers()
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
    parser.add_argument(
        '--runs-dir',
        default='results/runs',
        help='Directory of canonical run JSONs (default: results/runs)'
    )
    parser.add_argument(
        '--plain',
        action='store_true',
        help='Force plain-text output even if rich is installed'
    )

    args = parser.parse_args()

    if not RICH_AVAILABLE:
        print(
            "Note: the 'rich' library is not installed, so this monitor will "
            "use plain-text output.\n"
            "      For the live dashboard, install it with:  pip install rich\n"
        )

    monitor = BacktestMonitor(log_path=args.log_file, runs_dir=args.runs_dir)
    if args.plain:
        monitor.run_plain()
    else:
        monitor.run()


if __name__ == '__main__':
    main()

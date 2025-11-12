"""
FIX 7.1: Comprehensive Date Validation Module

Centralizes all date filtering and validation logic to prevent recurring bugs
where data from wrong dates appears in backtests (e.g., 2024 data in 2025 backtest).

This module provides:
- Strict date filtering for filings, events, signals
- Look-ahead bias detection
- Comprehensive logging and statistics
- Fail-fast validation to catch bugs early

Usage:
    validator = DateValidator('2024-01-01', '2024-12-31')
    valid_filings = validator.validate_filings(filings)
    valid_events = validator.validate_events(events)
    valid_signals = validator.validate_signals(signals)
    validator.print_summary()
"""

from datetime import datetime
from typing import List, Dict, Union
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class DateValidator:
    """
    Comprehensive date validation and filtering
    """

    def __init__(self, start_date: str, end_date: str, strict_mode: bool = True):
        """
        Initialize date validator

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            strict_mode: If True, raises errors on validation failures.
                        If False, only logs warnings.
        """
        self.start_date = start_date
        self.end_date = end_date
        self.strict_mode = strict_mode

        # Parse dates
        try:
            self.start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            self.end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError as e:
            raise ValueError(f"Invalid date format. Expected YYYY-MM-DD. Error: {e}")

        if self.start_dt > self.end_dt:
            raise ValueError(f"Start date {start_date} is after end date {end_date}")

        # Statistics tracking
        self.stats = {
            'filings_total': 0,
            'filings_filtered': 0,
            'filings_invalid_format': 0,
            'events_total': 0,
            'events_filtered': 0,
            'events_invalid_format': 0,
            'signals_total': 0,
            'signals_filtered': 0,
            'signals_invalid_format': 0,
            'look_ahead_violations': 0
        }

        # Detailed error tracking
        self.filtered_items = {
            'filings': [],
            'events': [],
            'signals': []
        }

    def validate_filings(self, filings: List[Dict]) -> List[Dict]:
        """
        Filter filings to only include those within date range

        Args:
            filings: List of filing dictionaries with 'date' field

        Returns:
            List of valid filings within date range
        """
        self.stats['filings_total'] = len(filings)
        valid_filings = []

        for filing in filings:
            try:
                filing_date_str = filing.get('date')

                if not filing_date_str:
                    logger.warning(f"Filing missing 'date' field: {filing.get('ticker', 'UNKNOWN')}")
                    self.stats['filings_invalid_format'] += 1
                    self.filtered_items['filings'].append({
                        'ticker': filing.get('ticker', 'UNKNOWN'),
                        'date': 'MISSING',
                        'reason': 'Missing date field'
                    })
                    continue

                filing_date = datetime.strptime(filing_date_str, '%Y-%m-%d')

                if self.start_dt <= filing_date <= self.end_dt:
                    valid_filings.append(filing)
                else:
                    self.stats['filings_filtered'] += 1
                    self.filtered_items['filings'].append({
                        'ticker': filing.get('ticker', 'UNKNOWN'),
                        'date': filing_date_str,
                        'reason': f'Outside range [{self.start_date}, {self.end_date}]'
                    })

            except ValueError as e:
                logger.warning(f"Invalid date format in filing: {filing.get('date')}")
                self.stats['filings_invalid_format'] += 1
                self.filtered_items['filings'].append({
                    'ticker': filing.get('ticker', 'UNKNOWN'),
                    'date': filing.get('date', 'INVALID'),
                    'reason': f'Invalid format: {e}'
                })

        # Alert if too many filtered
        if self.stats['filings_filtered'] > 0:
            pct_filtered = (self.stats['filings_filtered'] / self.stats['filings_total']) * 100
            logger.warning(f"DateValidator: Filtered {self.stats['filings_filtered']}/{self.stats['filings_total']} "
                          f"filings ({pct_filtered:.1f}%) outside date range")

            if pct_filtered > 10:
                msg = (f"CRITICAL: {pct_filtered:.1f}% of filings were outside date range! "
                      f"This suggests upstream data fetching bug.")
                if self.strict_mode:
                    raise ValueError(msg)
                else:
                    logger.error(msg)

        return valid_filings

    def validate_events(self, events: List[Dict]) -> List[Dict]:
        """
        Filter events to only include those within date range

        Args:
            events: List of event dictionaries with 'date' field

        Returns:
            List of valid events within date range
        """
        self.stats['events_total'] = len(events)
        valid_events = []

        for event in events:
            try:
                # Handle both datetime objects and strings
                event_date = event.get('date')

                if isinstance(event_date, datetime):
                    event_date_dt = event_date
                    event_date_str = event_date.strftime('%Y-%m-%d')
                elif isinstance(event_date, str):
                    event_date_dt = datetime.strptime(event_date, '%Y-%m-%d')
                    event_date_str = event_date
                else:
                    logger.warning(f"Event has invalid date type: {type(event_date)}")
                    self.stats['events_invalid_format'] += 1
                    self.filtered_items['events'].append({
                        'ticker': event.get('ticker', 'UNKNOWN'),
                        'date': str(event_date),
                        'reason': f'Invalid date type: {type(event_date)}'
                    })
                    continue

                if self.start_dt <= event_date_dt <= self.end_dt:
                    valid_events.append(event)
                else:
                    self.stats['events_filtered'] += 1
                    self.filtered_items['events'].append({
                        'ticker': event.get('ticker', 'UNKNOWN'),
                        'date': event_date_str,
                        'reason': f'Outside range [{self.start_date}, {self.end_date}]'
                    })

            except (ValueError, AttributeError) as e:
                logger.warning(f"Invalid date in event: {event.get('date')}")
                self.stats['events_invalid_format'] += 1
                self.filtered_items['events'].append({
                    'ticker': event.get('ticker', 'UNKNOWN'),
                    'date': str(event.get('date', 'INVALID')),
                    'reason': f'Invalid format: {e}'
                })

        return valid_events

    def validate_signals(self, signals: Union[List[Dict], pd.DataFrame]) -> Union[List[Dict], pd.DataFrame]:
        """
        Filter signals to only include those within date range

        Args:
            signals: List of signal dicts or DataFrame with 'date' column

        Returns:
            Filtered signals (same type as input)
        """
        if isinstance(signals, pd.DataFrame):
            return self._validate_signals_df(signals)
        else:
            return self._validate_signals_list(signals)

    def _validate_signals_list(self, signals: List[Dict]) -> List[Dict]:
        """Validate signals in list format"""
        self.stats['signals_total'] = len(signals)
        valid_signals = []

        for signal in signals:
            try:
                signal_date = signal.get('date')

                if isinstance(signal_date, datetime):
                    signal_date_dt = signal_date
                    signal_date_str = signal_date.strftime('%Y-%m-%d')
                elif isinstance(signal_date, str):
                    signal_date_dt = datetime.strptime(signal_date, '%Y-%m-%d')
                    signal_date_str = signal_date
                else:
                    logger.warning(f"Signal has invalid date type: {type(signal_date)}")
                    self.stats['signals_invalid_format'] += 1
                    continue

                if self.start_dt <= signal_date_dt <= self.end_dt:
                    valid_signals.append(signal)
                else:
                    self.stats['signals_filtered'] += 1
                    self.filtered_items['signals'].append({
                        'ticker': signal.get('ticker', 'UNKNOWN'),
                        'date': signal_date_str,
                        'reason': f'Outside range [{self.start_date}, {self.end_date}]'
                    })

            except (ValueError, AttributeError) as e:
                logger.warning(f"Invalid date in signal: {signal.get('date')}")
                self.stats['signals_invalid_format'] += 1

        return valid_signals

    def _validate_signals_df(self, signals_df: pd.DataFrame) -> pd.DataFrame:
        """Validate signals in DataFrame format"""
        self.stats['signals_total'] = len(signals_df)

        # Ensure date column is datetime
        signals_df['date'] = pd.to_datetime(signals_df['date'])

        # Filter by date range
        mask = (signals_df['date'] >= self.start_dt) & (signals_df['date'] <= self.end_dt)
        valid_signals_df = signals_df[mask].copy()

        # Track filtered signals
        filtered_df = signals_df[~mask]
        self.stats['signals_filtered'] = len(filtered_df)

        for _, row in filtered_df.iterrows():
            self.filtered_items['signals'].append({
                'ticker': row.get('ticker', 'UNKNOWN'),
                'date': row['date'].strftime('%Y-%m-%d'),
                'reason': f'Outside range [{self.start_date}, {self.end_date}]'
            })

        return valid_signals_df

    def assert_no_future_data(self, data_date: Union[str, datetime],
                              reference_date: Union[str, datetime],
                              context: str = ""):
        """
        Assert that data_date is not in the future relative to reference_date

        This prevents look-ahead bias in backtests.

        Args:
            data_date: Date of the data being used
            reference_date: Reference date (e.g., backtest current date)
            context: Description of what's being validated

        Raises:
            ValueError: If look-ahead bias detected and strict_mode=True
        """
        # Parse dates
        if isinstance(data_date, str):
            data_dt = datetime.strptime(data_date, '%Y-%m-%d')
        else:
            data_dt = data_date

        if isinstance(reference_date, str):
            ref_dt = datetime.strptime(reference_date, '%Y-%m-%d')
        else:
            ref_dt = reference_date

        # Check for look-ahead bias
        if data_dt > ref_dt:
            self.stats['look_ahead_violations'] += 1
            msg = (f"LOOK-AHEAD BIAS DETECTED: {context}\n"
                  f"  Data date: {data_dt.strftime('%Y-%m-%d')}\n"
                  f"  Reference date: {ref_dt.strftime('%Y-%m-%d')}\n"
                  f"  Difference: {(data_dt - ref_dt).days} days in future")

            if self.strict_mode:
                raise ValueError(msg)
            else:
                logger.error(msg)

    def print_summary(self):
        """Print comprehensive validation summary"""
        print("\n" + "=" * 60)
        print("DATE VALIDATION SUMMARY")
        print("=" * 60)
        print(f"Date Range: {self.start_date} to {self.end_date}")
        print(f"Strict Mode: {self.strict_mode}")
        print()

        # Filings
        print("FILINGS:")
        print(f"  Total: {self.stats['filings_total']}")
        print(f"  Valid: {self.stats['filings_total'] - self.stats['filings_filtered'] - self.stats['filings_invalid_format']}")
        print(f"  Filtered (out of range): {self.stats['filings_filtered']}")
        print(f"  Invalid format: {self.stats['filings_invalid_format']}")

        if self.stats['filings_filtered'] > 0:
            print(f"\n  Sample filtered filings:")
            for item in self.filtered_items['filings'][:3]:
                print(f"    - {item['ticker']}: {item['date']} ({item['reason']})")

        # Events
        print("\nEVENTS:")
        print(f"  Total: {self.stats['events_total']}")
        print(f"  Valid: {self.stats['events_total'] - self.stats['events_filtered'] - self.stats['events_invalid_format']}")
        print(f"  Filtered (out of range): {self.stats['events_filtered']}")
        print(f"  Invalid format: {self.stats['events_invalid_format']}")

        if self.stats['events_filtered'] > 0:
            print(f"\n  Sample filtered events:")
            for item in self.filtered_items['events'][:3]:
                print(f"    - {item['ticker']}: {item['date']} ({item['reason']})")

        # Signals
        print("\nSIGNALS:")
        print(f"  Total: {self.stats['signals_total']}")
        print(f"  Valid: {self.stats['signals_total'] - self.stats['signals_filtered'] - self.stats['signals_invalid_format']}")
        print(f"  Filtered (out of range): {self.stats['signals_filtered']}")
        print(f"  Invalid format: {self.stats['signals_invalid_format']}")

        if self.stats['signals_filtered'] > 0:
            print(f"\n  Sample filtered signals:")
            for item in self.filtered_items['signals'][:3]:
                print(f"    - {item['ticker']}: {item['date']} ({item['reason']})")

        # Look-ahead bias
        print("\nLOOK-AHEAD BIAS:")
        print(f"  Violations detected: {self.stats['look_ahead_violations']}")

        # Overall status
        print("\n" + "-" * 60)
        total_filtered = (self.stats['filings_filtered'] + self.stats['events_filtered'] +
                         self.stats['signals_filtered'])
        total_invalid = (self.stats['filings_invalid_format'] + self.stats['events_invalid_format'] +
                        self.stats['signals_invalid_format'])

        if total_filtered == 0 and total_invalid == 0 and self.stats['look_ahead_violations'] == 0:
            print("✓ VALIDATION PASSED: All data within date range")
        else:
            print(f"⚠ VALIDATION WARNINGS:")
            if total_filtered > 0:
                print(f"  - {total_filtered} items filtered due to date range")
            if total_invalid > 0:
                print(f"  - {total_invalid} items with invalid date format")
            if self.stats['look_ahead_violations'] > 0:
                print(f"  - {self.stats['look_ahead_violations']} look-ahead bias violations")

        print("=" * 60 + "\n")

    def get_stats(self) -> Dict:
        """
        Get validation statistics

        Returns:
            Dictionary with validation stats
        """
        return self.stats.copy()


def validate_date_range(data: Union[List[Dict], pd.DataFrame],
                        start_date: str, end_date: str,
                        date_field: str = 'date') -> Union[List[Dict], pd.DataFrame]:
    """
    Convenience function to validate date range

    Args:
        data: List of dicts or DataFrame
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        date_field: Name of date field

    Returns:
        Filtered data within date range
    """
    validator = DateValidator(start_date, end_date, strict_mode=False)

    if isinstance(data, pd.DataFrame):
        return validator._validate_signals_df(data)
    else:
        # Assume it's signals-like data
        return validator._validate_signals_list(data)

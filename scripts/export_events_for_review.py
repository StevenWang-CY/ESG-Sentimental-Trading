"""
Export ESG Events for Manual Quality Review

Exports events detected at different confidence thresholds to CSV for manual review.
Focuses on comparing high-confidence (e.g. 0.25+) vs lower-confidence events to
validate whether a lower threshold introduces noise.

This script is wired against the REAL component interfaces:

* ``UniverseFetcher()`` (no constructor args) ->
  ``get_esg_sensitive_nasdaq100(sensitivity)`` -> list of tickers.
* ``SECDownloader(company_name=, email=, download_folder=)`` ->
  ``fetch_filings(tickers, filing_type, start_date, end_date, limit=)`` ->
  list of filing metadata dicts (``ticker``, ``filing_type``, ``file_path``,
  ``accession_number``, ``date``).
* ``SECFilingParser().extract_text(filing_path)`` -> text string.
* ``TextCleaner().clean_for_sentiment_analysis(text)`` -> cleaned text.
* ``ESGEventDetector().detect_event(text, threshold)`` -> detection dict
  (``has_event``, ``category`` (E/S/G), ``category_full``, ``sentiment``,
  ``confidence``, ``matched_keywords``, ``num_matches``).

Use ``--limit N`` to cap the number of tickers / filings per ticker for a quick
dry run.
"""

import argparse
import yaml
import pandas as pd
import logging
from pathlib import Path
from datetime import datetime
import sys

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.data import SECDownloader, UniverseFetcher
from src.preprocessing import SECFilingParser, TextCleaner
from src.nlp import ESGEventDetector

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Map the detector's category_full to the capitalized labels used in the
# comparison / breakdown reporting.
_CATEGORY_LABELS = {
    'environmental': 'Environmental',
    'social': 'Social',
    'governance': 'Governance',
}


class EventExporter:
    """
    Export ESG events for manual review
    """

    def __init__(self,
                 start_date,
                 end_date,
                 universe_sensitivity='MEDIUM',
                 thresholds=(0.20, 0.25),
                 config_path='config/config.yaml',
                 limit=None):
        """
        Initialize event exporter

        Args:
            start_date: Start date for event detection (YYYY-MM-DD)
            end_date: End date for event detection (YYYY-MM-DD)
            universe_sensitivity: Universe sensitivity level
            thresholds: List of thresholds to test
            config_path: Path to config file
            limit: Optional cap on number of tickers (and filings per ticker)
                for a quick dry run.
        """
        self.start_date = start_date
        self.end_date = end_date
        self.universe_sensitivity = universe_sensitivity
        self.thresholds = list(thresholds)
        self.config_path = config_path
        self.limit = limit

        # Load config
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

    def fetch_universe(self):
        """
        Fetch the ESG-sensitive NASDAQ-100 stock universe.

        Returns:
            list: List of ticker symbols
        """
        logger.info(f"Fetching universe with sensitivity: {self.universe_sensitivity}")

        fetcher = UniverseFetcher()
        tickers = fetcher.get_esg_sensitive_nasdaq100(self.universe_sensitivity)

        if self.limit:
            tickers = tickers[:self.limit]
            logger.info(f"--limit applied: using first {len(tickers)} tickers")

        logger.info(f"Universe contains {len(tickers)} stocks: {tickers[:10]}...")

        return tickers

    def download_filings(self, tickers):
        """
        Download SEC filings for tickers.

        Args:
            tickers: List of ticker symbols

        Returns:
            list: List of filing metadata dicts (one per downloaded filing)
        """
        logger.info(f"Downloading SEC filings from {self.start_date} to {self.end_date}...")

        sec_cfg = self.config['data']['sec']
        downloader = SECDownloader(
            company_name=sec_cfg['company_name'],
            email=sec_cfg['email'],
            download_folder=sec_cfg['download_folder']
        )

        # Canonical trading trigger is the 8-K; use the first configured type.
        filing_types = sec_cfg.get('filing_types', ['8-K'])
        filing_type = filing_types[0] if filing_types else '8-K'

        filings = downloader.fetch_filings(
            tickers=tickers,
            filing_type=filing_type,
            start_date=self.start_date,
            end_date=self.end_date,
            limit=self.limit
        )

        logger.info(f"Total filings downloaded: {len(filings)}")

        return filings

    def detect_events_at_threshold(self, filings, threshold):
        """
        Detect ESG events at a specific confidence threshold.

        Args:
            filings: List of filing metadata dicts (from ``download_filings``)
            threshold: Confidence threshold

        Returns:
            pd.DataFrame: Detected events
        """
        logger.info(f"\nDetecting events with threshold {threshold}...")

        # Initialize components (real interfaces)
        parser = SECFilingParser()
        cleaner = TextCleaner()
        detector = ESGEventDetector()

        events = []

        for filing in filings:
            file_path = filing.get('file_path')
            ticker = filing.get('ticker', 'UNKNOWN')

            if not file_path:
                continue

            try:
                # Extract raw text from the filing
                raw_text = parser.extract_text(file_path)

                if not raw_text:
                    continue

                # Clean text for downstream NLP
                clean_text = cleaner.clean_for_sentiment_analysis(raw_text)

                if not clean_text:
                    continue

                # Detect ESG events
                detection = detector.detect_event(clean_text, threshold=threshold)

                if detection.get('has_event'):
                    category_full = detection.get('category_full', 'unknown')
                    matched = detection.get('matched_keywords', [])

                    event = {
                        'ticker': ticker,
                        'date': filing.get('date', 'unknown'),
                        'filing_type': filing.get('filing_type', 'unknown'),
                        'category': _CATEGORY_LABELS.get(category_full, category_full),
                        'sentiment': detection.get('sentiment', 'unknown'),
                        'confidence': detection.get('confidence', 0.0),
                        'keywords_matched': ', '.join(matched),
                        'num_keywords': len(matched),
                        'text_length': len(clean_text),
                        'file_path': str(file_path),
                        'accession_number': filing.get('accession_number', ''),
                    }

                    # Event summary (first 500 chars of cleaned text)
                    event['summary'] = (
                        clean_text[:500] + '...' if len(clean_text) > 500 else clean_text
                    )

                    events.append(event)

            except Exception as e:
                logger.warning(f"Error processing {file_path}: {str(e)}")
                continue

        df = pd.DataFrame(events)

        if len(df) > 0:
            df = df.sort_values(['confidence', 'date'], ascending=[False, True])
            logger.info(f"  Detected {len(df)} events")
            logger.info(f"  Confidence range: [{df['confidence'].min():.3f}, {df['confidence'].max():.3f}]")
            logger.info("  Category breakdown:")
            logger.info(df['category'].value_counts().to_string())
        else:
            logger.warning("  No events detected!")

        return df

    def compare_thresholds(self, events_dict):
        """
        Compare events detected at different thresholds.

        Args:
            events_dict: Dictionary mapping threshold to events DataFrame

        Returns:
            pd.DataFrame: Comparison analysis
        """
        logger.info("\n" + "="*60)
        logger.info("THRESHOLD COMPARISON ANALYSIS")
        logger.info("="*60)

        comparison = []

        for threshold, df in events_dict.items():
            stats = {
                'threshold': threshold,
                'total_events': len(df),
                'avg_confidence': df['confidence'].mean() if len(df) > 0 else 0,
                'median_confidence': df['confidence'].median() if len(df) > 0 else 0,
                'min_confidence': df['confidence'].min() if len(df) > 0 else 0,
                'max_confidence': df['confidence'].max() if len(df) > 0 else 0,
            }

            # Category breakdown
            if len(df) > 0:
                cat_counts = df['category'].value_counts()
                stats['environmental_pct'] = (cat_counts.get('Environmental', 0) / len(df)) * 100
                stats['social_pct'] = (cat_counts.get('Social', 0) / len(df)) * 100
                stats['governance_pct'] = (cat_counts.get('Governance', 0) / len(df)) * 100
            else:
                stats['environmental_pct'] = 0
                stats['social_pct'] = 0
                stats['governance_pct'] = 0

            comparison.append(stats)

        comp_df = pd.DataFrame(comparison)
        comp_df = comp_df.sort_values('threshold')

        logger.info("\n" + comp_df.to_string(index=False))
        logger.info("="*60)

        return comp_df

    def identify_marginal_events(self, high_threshold_events, low_threshold_events):
        """
        Identify events only captured by the lower threshold (marginal events).

        Args:
            high_threshold_events: Events at the higher threshold
            low_threshold_events: Events at the lower threshold

        Returns:
            pd.DataFrame: Marginal events (only in the lower threshold)
        """
        logger.info("\n" + "="*60)
        logger.info("IDENTIFYING MARGINAL EVENTS")
        logger.info("="*60)

        empty_columns = [
            'ticker', 'date', 'filing_type', 'category', 'sentiment',
            'confidence', 'keywords_matched', 'num_keywords', 'text_length',
            'file_path', 'accession_number', 'summary', 'event_id'
        ]

        # Nothing captured at the lower threshold -> no marginal events.
        if low_threshold_events is None or len(low_threshold_events) == 0:
            logger.info("Low threshold produced no events; no marginal events.")
            return pd.DataFrame(columns=empty_columns)

        high = high_threshold_events.copy() if high_threshold_events is not None else pd.DataFrame()
        low = low_threshold_events.copy()

        def _event_id(frame):
            return (
                frame['ticker'].astype(str) + '_' +
                frame['date'].astype(str) + '_' +
                frame['filing_type'].astype(str)
            )

        low['event_id'] = _event_id(low)
        high_event_ids = set(_event_id(high)) if len(high) > 0 else set()

        marginal_mask = ~low['event_id'].isin(high_event_ids)
        marginal_events = low[marginal_mask].copy()

        logger.info(f"High threshold events: {len(high)}")
        logger.info(f"Low threshold events: {len(low)}")
        logger.info(f"Marginal events (only in low threshold): {len(marginal_events)}")

        if len(marginal_events) > 0:
            logger.info("\nMarginal Events Statistics:")
            logger.info(f"  Avg confidence: {marginal_events['confidence'].mean():.3f}")
            logger.info(f"  Confidence range: [{marginal_events['confidence'].min():.3f}, {marginal_events['confidence'].max():.3f}]")
            logger.info("  Category breakdown:")
            logger.info(marginal_events['category'].value_counts().to_string())

        logger.info("="*60)

        return marginal_events

    def export_to_csv(self, events_dict, marginal_events, output_dir='results/event_review'):
        """
        Export events to CSV files.

        Args:
            events_dict: Dictionary of events by threshold
            marginal_events: DataFrame of marginal events
            output_dir: Output directory
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Export events for each threshold
        for threshold, df in events_dict.items():
            filename = output_path / f'events_threshold_{threshold}_{timestamp}.csv'
            df.to_csv(filename, index=False)
            logger.info(f"Exported {len(df)} events to {filename}")

        # Export marginal events (the critical ones to review)
        if len(marginal_events) > 0:
            marginal_file = output_path / f'marginal_events_REVIEW_REQUIRED_{timestamp}.csv'
            marginal_events.to_csv(marginal_file, index=False)
            logger.info(f"\n⚠️  IMPORTANT: {len(marginal_events)} marginal events exported for manual review:")
            logger.info(f"   {marginal_file}")
            logger.info("\nThese are events captured ONLY by the lower threshold.")
            logger.info("Please review to determine if they are:")
            logger.info("  1. Material ESG events (true positives)")
            logger.info("  2. Routine disclosures (false positives / noise)")
            logger.info("  3. Generic keyword mentions (false positives / noise)")

        # Export comparison summary
        comparison_file = output_path / f'threshold_comparison_{timestamp}.txt'
        with open(comparison_file, 'w') as f:
            f.write("="*60 + "\n")
            f.write("ESG EVENT DETECTION - THRESHOLD COMPARISON\n")
            f.write("="*60 + "\n\n")
            f.write(f"Date Range: {self.start_date} to {self.end_date}\n")
            f.write(f"Universe: {self.universe_sensitivity}\n")
            f.write(f"Thresholds Tested: {self.thresholds}\n\n")

            for threshold, df in events_dict.items():
                f.write(f"\nThreshold {threshold}:\n")
                f.write(f"  Total Events: {len(df)}\n")
                if len(df) > 0:
                    f.write(f"  Avg Confidence: {df['confidence'].mean():.3f}\n")
                    f.write("  Category Breakdown:\n")
                    f.write(df['category'].value_counts().to_string() + "\n")

            if len(marginal_events) > 0:
                f.write("\n" + "="*60 + "\n")
                f.write("MARGINAL EVENTS ANALYSIS\n")
                f.write("="*60 + "\n")
                f.write(f"Marginal events (captured only by lower threshold): {len(marginal_events)}\n")
                f.write(f"Average confidence: {marginal_events['confidence'].mean():.3f}\n")
                f.write(f"Confidence range: [{marginal_events['confidence'].min():.3f}, {marginal_events['confidence'].max():.3f}]\n")

        logger.info(f"Comparison summary saved to {comparison_file}")


def main():
    """Main execution"""
    parser = argparse.ArgumentParser(
        description='Export ESG Events for Manual Quality Review'
    )
    parser.add_argument('--start-date', type=str, required=True,
                       help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, required=True,
                       help='End date (YYYY-MM-DD)')
    parser.add_argument('--esg-sensitivity', type=str, default='MEDIUM',
                       choices=['VERY HIGH', 'HIGH', 'MEDIUM', 'ALL'],
                       help='ESG universe sensitivity')
    parser.add_argument('--thresholds', type=float, nargs='+',
                       default=[0.20, 0.25],
                       help='Confidence thresholds to compare')
    parser.add_argument('--config', type=str, default='config/config.yaml',
                       help='Path to configuration file')
    parser.add_argument('--output-dir', type=str, default='results/event_review',
                       help='Output directory for CSV files')
    parser.add_argument('--limit', type=int, default=None,
                       help='Cap tickers (and filings per ticker) for a quick '
                            'dry run')

    args = parser.parse_args()

    # Initialize exporter
    exporter = EventExporter(
        start_date=args.start_date,
        end_date=args.end_date,
        universe_sensitivity=args.esg_sensitivity,
        thresholds=args.thresholds,
        config_path=args.config,
        limit=args.limit,
    )

    # Fetch universe
    tickers = exporter.fetch_universe()

    # Download filings
    filings = exporter.download_filings(tickers)

    # Detect events at each threshold
    events_dict = {}
    for threshold in args.thresholds:
        events_df = exporter.detect_events_at_threshold(filings, threshold)
        events_dict[threshold] = events_df

    # Compare thresholds
    exporter.compare_thresholds(events_dict)

    # Identify marginal events (captured only by the lower threshold)
    thresholds_sorted = sorted(args.thresholds)
    if len(thresholds_sorted) >= 2:
        marginal_events = exporter.identify_marginal_events(
            events_dict[thresholds_sorted[-1]],  # Highest threshold
            events_dict[thresholds_sorted[0]]     # Lowest threshold
        )
    else:
        marginal_events = pd.DataFrame()

    # Export to CSV
    exporter.export_to_csv(events_dict, marginal_events, args.output_dir)

    logger.info("\n" + "="*60)
    logger.info("EVENT EXPORT COMPLETE!")
    logger.info("="*60)
    logger.info(f"Files saved to: {args.output_dir}")
    logger.info("\nNext Steps:")
    logger.info("1. Review the marginal events CSV to determine signal quality")
    logger.info("2. Categorize events as Material/Routine/Noise")
    logger.info("3. Use findings to validate optimal confidence threshold")
    logger.info("="*60)


if __name__ == '__main__':
    main()

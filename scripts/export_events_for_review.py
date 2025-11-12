"""
Export ESG Events for Manual Quality Review

Exports events detected at different confidence thresholds to CSV for manual review.
Focuses on comparing high-confidence (0.20+) vs low-confidence (0.15-0.19) events
to validate root cause analysis finding that lower threshold introduces noise.
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


class EventExporter:
    """
    Export ESG events for manual review
    """

    def __init__(self,
                 start_date,
                 end_date,
                 universe_sensitivity='MEDIUM',
                 thresholds=[0.15, 0.20],
                 config_path='config/config.yaml'):
        """
        Initialize event exporter

        Args:
            start_date: Start date for event detection (YYYY-MM-DD)
            end_date: End date for event detection (YYYY-MM-DD)
            universe_sensitivity: Universe sensitivity level
            thresholds: List of thresholds to test
            config_path: Path to config file
        """
        self.start_date = start_date
        self.end_date = end_date
        self.universe_sensitivity = universe_sensitivity
        self.thresholds = thresholds
        self.config_path = config_path

        # Load config
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

    def fetch_universe(self):
        """
        Fetch stock universe

        Returns:
            list: List of ticker symbols
        """
        logger.info(f"Fetching universe with sensitivity: {self.universe_sensitivity}")

        fetcher = UniverseFetcher(
            index='nasdaq100',
            esg_sensitivity=self.universe_sensitivity
        )

        tickers = fetcher.get_tickers()
        logger.info(f"Universe contains {len(tickers)} stocks: {tickers[:10]}...")

        return tickers

    def download_filings(self, tickers):
        """
        Download SEC filings for tickers

        Args:
            tickers: List of ticker symbols

        Returns:
            dict: Mapping of ticker to filing paths
        """
        logger.info(f"Downloading SEC filings from {self.start_date} to {self.end_date}...")

        downloader = SECDownloader(
            company_name=self.config['data']['sec']['company_name'],
            email=self.config['data']['sec']['email'],
            download_folder=self.config['data']['sec']['download_folder']
        )

        filing_paths = {}

        for ticker in tickers:
            try:
                paths = downloader.download(
                    ticker=ticker,
                    filing_types=self.config['data']['sec']['filing_types'],
                    after_date=self.start_date,
                    before_date=self.end_date
                )
                filing_paths[ticker] = paths
                logger.info(f"  {ticker}: {len(paths)} filings downloaded")
            except Exception as e:
                logger.warning(f"  {ticker}: Error downloading - {str(e)}")
                filing_paths[ticker] = []

        total_filings = sum(len(paths) for paths in filing_paths.values())
        logger.info(f"Total filings downloaded: {total_filings}")

        return filing_paths

    def detect_events_at_threshold(self, filing_paths, threshold):
        """
        Detect ESG events at specific confidence threshold

        Args:
            filing_paths: Dictionary mapping tickers to filing paths
            threshold: Confidence threshold

        Returns:
            pd.DataFrame: Detected events
        """
        logger.info(f"\nDetecting events with threshold {threshold}...")

        # Initialize components
        parser = SECFilingParser()
        cleaner = TextCleaner()
        detector = ESGEventDetector(confidence_threshold=threshold)

        events = []

        for ticker, paths in filing_paths.items():
            for filing_path in paths:
                try:
                    # Parse filing
                    filing_data = parser.parse(filing_path)

                    if not filing_data or 'text' not in filing_data:
                        continue

                    # Clean text
                    clean_text = cleaner.clean(filing_data['text'])

                    # Detect ESG events
                    detection_result = detector.detect(clean_text)

                    if detection_result['has_event']:
                        # Extract event details
                        event = {
                            'ticker': ticker,
                            'date': filing_data.get('filing_date', 'unknown'),
                            'filing_type': filing_data.get('filing_type', 'unknown'),
                            'category': detection_result['category'],
                            'confidence': detection_result['confidence'],
                            'keywords_matched': ', '.join(detection_result.get('matched_keywords', [])),
                            'num_keywords': len(detection_result.get('matched_keywords', [])),
                            'text_length': len(clean_text),
                            'filing_path': str(filing_path)
                        }

                        # Extract event summary (first 500 chars of relevant section)
                        event['summary'] = clean_text[:500] + '...' if len(clean_text) > 500 else clean_text

                        events.append(event)

                except Exception as e:
                    logger.warning(f"Error processing {filing_path}: {str(e)}")
                    continue

        df = pd.DataFrame(events)

        if len(df) > 0:
            df = df.sort_values(['confidence', 'date'], ascending=[False, True])
            logger.info(f"  Detected {len(df)} events")
            logger.info(f"  Confidence range: [{df['confidence'].min():.3f}, {df['confidence'].max():.3f}]")
            logger.info(f"  Category breakdown:")
            logger.info(df['category'].value_counts().to_string())
        else:
            logger.warning("  No events detected!")

        return df

    def compare_thresholds(self, events_dict):
        """
        Compare events detected at different thresholds

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
        Identify events only captured by lower threshold (marginal events)

        Args:
            high_threshold_events: Events detected at high threshold (e.g., 0.20)
            low_threshold_events: Events detected at low threshold (e.g., 0.15)

        Returns:
            pd.DataFrame: Marginal events (only in low threshold)
        """
        logger.info("\n" + "="*60)
        logger.info("IDENTIFYING MARGINAL EVENTS")
        logger.info("="*60)

        # Create unique identifiers for events
        high_threshold_events['event_id'] = (
            high_threshold_events['ticker'] + '_' +
            high_threshold_events['date'].astype(str) + '_' +
            high_threshold_events['filing_type']
        )

        low_threshold_events['event_id'] = (
            low_threshold_events['ticker'] + '_' +
            low_threshold_events['date'].astype(str) + '_' +
            low_threshold_events['filing_type']
        )

        # Find marginal events (in low but not in high)
        high_event_ids = set(high_threshold_events['event_id'])
        marginal_mask = ~low_threshold_events['event_id'].isin(high_event_ids)
        marginal_events = low_threshold_events[marginal_mask].copy()

        logger.info(f"High threshold (0.20) events: {len(high_threshold_events)}")
        logger.info(f"Low threshold (0.15) events: {len(low_threshold_events)}")
        logger.info(f"Marginal events (only in 0.15): {len(marginal_events)}")

        if len(marginal_events) > 0:
            logger.info("\nMarginal Events Statistics:")
            logger.info(f"  Avg confidence: {marginal_events['confidence'].mean():.3f}")
            logger.info(f"  Confidence range: [{marginal_events['confidence'].min():.3f}, {marginal_events['confidence'].max():.3f}]")
            logger.info(f"  Category breakdown:")
            logger.info(marginal_events['category'].value_counts().to_string())

        logger.info("="*60)

        return marginal_events

    def export_to_csv(self, events_dict, marginal_events, output_dir='results/event_review'):
        """
        Export events to CSV files

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

        # Export marginal events (the critical ones to review!)
        if len(marginal_events) > 0:
            marginal_file = output_path / f'marginal_events_REVIEW_REQUIRED_{timestamp}.csv'
            marginal_events.to_csv(marginal_file, index=False)
            logger.info(f"\n⚠️  IMPORTANT: {len(marginal_events)} marginal events exported for manual review:")
            logger.info(f"   {marginal_file}")
            logger.info("\nThese are events captured ONLY by the lower threshold (0.15).")
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
                    f.write(f"  Category Breakdown:\n")
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
                       choices=['MEDIUM', 'HIGH', 'ALL'],
                       help='ESG universe sensitivity')
    parser.add_argument('--thresholds', type=float, nargs='+',
                       default=[0.15, 0.20],
                       help='Confidence thresholds to compare')
    parser.add_argument('--config', type=str, default='config/config.yaml',
                       help='Path to configuration file')
    parser.add_argument('--output-dir', type=str, default='results/event_review',
                       help='Output directory for CSV files')

    args = parser.parse_args()

    # Initialize exporter
    exporter = EventExporter(
        start_date=args.start_date,
        end_date=args.end_date,
        universe_sensitivity=args.esg_sensitivity,
        thresholds=args.thresholds,
        config_path=args.config
    )

    # Fetch universe
    tickers = exporter.fetch_universe()

    # Download filings
    filing_paths = exporter.download_filings(tickers)

    # Detect events at each threshold
    events_dict = {}
    for threshold in args.thresholds:
        events_df = exporter.detect_events_at_threshold(filing_paths, threshold)
        events_dict[threshold] = events_df

    # Compare thresholds
    comparison = exporter.compare_thresholds(events_dict)

    # Identify marginal events (captured only by lower threshold)
    if 0.20 in events_dict and 0.15 in events_dict:
        marginal_events = exporter.identify_marginal_events(
            events_dict[0.20],
            events_dict[0.15]
        )
    else:
        # Use the two thresholds provided
        thresholds_sorted = sorted(args.thresholds)
        marginal_events = exporter.identify_marginal_events(
            events_dict[thresholds_sorted[-1]],  # Highest threshold
            events_dict[thresholds_sorted[0]]     # Lowest threshold
        )

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

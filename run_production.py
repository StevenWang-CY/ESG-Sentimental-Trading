"""
Production Runner for ESG Event-Driven Alpha Strategy
Runs on real NASDAQ-100 stocks with real social media data (Reddit/Twitter)

INTELLIGENT CACHING SYSTEM (3-Tier Architecture):
===============================================
1. IMMUTABLE DATA CACHE (never invalidate):
   - SEC filings: data/filings_{universe}_{dates}_n{count}.pkl
   - Historical prices (>60 days): data/prices_{universe}_{dates}_n{count}.pkl

2. CONFIG-DEPENDENT CACHE (invalidate on config change):
   - Events: data/events_{universe}_{dates}_{config_hash}.pkl
   - Social media: data/social_media/{source}_{ticker}_{date}_d{before}_{after}_max{n}.pkl

3. TIME-FRESH CACHE (invalidate by age):
   - Recent prices (<60 days): Refresh if >24 hours old

Cache Control:
   --use-cache: Use cached data when available (default: True)
   --force-refresh: Force refresh all data (ignore cache)
   --clear-cache: Delete all cached data before running
"""

import argparse
import yaml
import logging
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import sys

# Import project modules
from src.utils.logging_config import setup_logging
from src.utils.cache_manager import compute_config_hash, is_cache_fresh, build_cache_key
from src.data import SECDownloader, PriceFetcher, FamaFrenchFactors, TwitterFetcher, RedditFetcher
from src.data.universe_fetcher import UniverseFetcher
from src.preprocessing import SECFilingParser, TextCleaner
from src.nlp import ESGEventDetector, FinancialSentimentAnalyzer, ReactionFeatureExtractor
from src.signals import ESGSignalGenerator, PortfolioConstructor
from src.backtest import BacktestEngine, PerformanceAnalyzer, FactorAnalysis


def load_config(config_path: str = 'config/config.yaml'):
    """Load configuration from YAML file"""
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config


def validate_social_media_config(config):
    """Validate social media API configuration (Reddit or Twitter)"""
    social_media_config = config.get('data', {}).get('social_media', {})
    source = social_media_config.get('source', 'reddit').lower()

    if source == 'reddit':
        reddit_config = config.get('data', {}).get('reddit', {})

        if reddit_config.get('use_mock', True):
            print("\n" + "="*60)
            print("INFO: Running in MOCK DATA mode (Reddit)")
            print("="*60)
            print("To use real Reddit data:")
            print("1. Get Reddit API credentials from reddit.com/prefs/apps")
            print("2. Set 'use_mock: false' in config/config.yaml")
            print("3. Add your Reddit client_id and client_secret to config/config.yaml")
            print("4. See ALTERNATIVE_DATA_SOURCES.md for instructions")
            print("="*60 + "\n")
            return False, 'reddit'

        client_id = reddit_config.get('client_id', '')
        client_secret = reddit_config.get('client_secret', '')
        if not client_id or not client_secret:
            print("\n" + "="*60)
            print("ERROR: No Reddit API credentials configured")
            print("="*60)
            print("Please add your Reddit API credentials to config/config.yaml")
            print("See ALTERNATIVE_DATA_SOURCES.md for setup instructions")
            print("="*60 + "\n")
            sys.exit(1)

        return True, 'reddit'

    else:  # twitter
        twitter_config = config.get('data', {}).get('twitter', {})

        if twitter_config.get('use_mock', True):
            print("\n" + "="*60)
            print("WARNING: Running in MOCK DATA mode (Twitter)")
            print("="*60)
            print("To use real Twitter data:")
            print("1. Set 'use_mock: false' in config/config.yaml")
            print("2. Add your Twitter Bearer Token to config/config.yaml")
            print("3. See ALTERNATIVE_DATA_SOURCES.md for instructions")
            print("="*60 + "\n")
            return False, 'twitter'

        bearer_token = twitter_config.get('bearer_token', '')
        if not bearer_token or bearer_token == '':
            print("\n" + "="*60)
            print("ERROR: No Twitter Bearer Token configured")
            print("="*60)
            print("Please add your Twitter API Bearer Token to config/config.yaml")
            print("See ALTERNATIVE_DATA_SOURCES.md for setup instructions")
            print("="*60 + "\n")
            sys.exit(1)

        return True, 'twitter'


def main():
    """Main execution function for production run"""

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='ESG Event-Driven Alpha Strategy - Production Run'
    )
    parser.add_argument('--config', type=str, default='config/config.yaml',
                       help='Path to configuration file')
    parser.add_argument('--start-date', type=str, required=True,
                       help='Start date (YYYY-MM-DD), e.g., 2024-09-01')
    parser.add_argument('--end-date', type=str, required=True,
                       help='End date (YYYY-MM-DD), e.g., 2024-09-30')
    parser.add_argument('--universe', type=str, default='esg_nasdaq100',
                       choices=['nasdaq100', 'esg_nasdaq100', 'sp500', 'russell_midcap', 'esg_midcap', 'custom'],
                       help='Stock universe to use (esg_nasdaq100 recommended for ESG strategy)')
    parser.add_argument('--esg-sensitivity', type=str, default='HIGH',
                       choices=['VERY HIGH', 'HIGH', 'MEDIUM', 'ALL'],
                       help='ESG sensitivity threshold (for esg_nasdaq100/esg_midcap universe)')
    parser.add_argument('--tickers', type=str, nargs='*',
                       help='Specific tickers (if universe=custom)')
    parser.add_argument('--max-tickers', type=int, default=None,
                       help='Limit number of tickers to process')
    parser.add_argument('--save-data', action='store_true',
                       help='Save intermediate data to disk')
    parser.add_argument('--use-cache', action='store_true', default=True,
                       help='Use cached data when available (default: True)')
    parser.add_argument('--force-refresh', action='store_true',
                       help='Force refresh all data (ignore cache)')
    parser.add_argument('--clear-cache', action='store_true',
                       help='Delete all cached data before running')
    parser.add_argument('--force-real-social-media', action='store_true',
                       help='Force real social media API (override mock mode)')
    parser.add_argument('--social-source', type=str, choices=['reddit', 'twitter'],
                       help='Override social media source (reddit or twitter)')

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Handle cache clearing if requested
    if args.clear_cache:
        from src.utils.cache_manager import clear_cache
        data_dir = Path('data')
        cleared = clear_cache(data_dir)
        print(f"Cleared {cleared} cache files from {data_dir}")
        if not args.force_refresh:
            # If only clearing cache, exit
            return

    # Setup logging
    logger = setup_logging(
        log_level=config['logging']['level'],
        log_file=config['logging'].get('log_file')
    )

    # Print banner
    logger.info("="*60)
    logger.info("ESG EVENT-DRIVEN ALPHA STRATEGY - PRODUCTION RUN")
    logger.info("="*60)
    logger.info(f"Universe: {args.universe.upper()}")
    logger.info(f"Date Range: {args.start_date} to {args.end_date}")
    logger.info(f"Config: {args.config}")
    logger.info("="*60)

    # Validate dates
    try:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d')

        if end_date <= start_date:
            logger.error("End date must be after start date")
            sys.exit(1)

        if (end_date - start_date).days > 365:
            logger.warning("Date range > 1 year. This may take a long time.")

    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        logger.error("Please use YYYY-MM-DD format")
        sys.exit(1)

    # Override social media source if specified
    if args.social_source:
        config['data']['social_media']['source'] = args.social_source

    # Validate social media configuration
    if args.force_real_social_media:
        source = config['data']['social_media'].get('source', 'reddit')
        if source == 'reddit':
            config['data']['reddit']['use_mock'] = False
        else:
            config['data']['twitter']['use_mock'] = False

    use_real_data, social_source = validate_social_media_config(config)

    # Step 1: Get stock universe
    logger.info("\n>>> STEP 1: FETCHING STOCK UNIVERSE")
    universe_fetcher = UniverseFetcher()

    if args.universe == 'esg_nasdaq100':
        logger.info(f"Using ESG-SENSITIVE NASDAQ-100 (sensitivity: {args.esg_sensitivity})")
        logger.info("This universe focuses on companies most affected by ESG events")
        tickers = universe_fetcher.get_esg_sensitive_nasdaq100(args.esg_sensitivity)
    elif args.universe == 'nasdaq100':
        logger.info("Using full NASDAQ-100 (all stocks)")
        tickers = universe_fetcher.get_nasdaq100_tickers()
    elif args.universe == 'sp500':
        tickers = universe_fetcher.get_sp500_tickers()
    elif args.universe == 'russell_midcap':
        logger.info("Using Russell Midcap Index (~400-800 mid-cap stocks)")
        logger.info("This universe targets $2B-$50B market cap with higher ESG sensitivity")
        tickers = universe_fetcher.get_russell_midcap_tickers()
    elif args.universe == 'esg_midcap':
        logger.info(f"Using ESG-SENSITIVE Russell Midcap (market cap: $2B-$50B)")
        logger.info("This universe focuses on mid-caps most affected by ESG events")
        tickers = universe_fetcher.get_esg_sensitive_midcap(
            min_market_cap=2e9,  # $2B minimum
            max_market_cap=50e9  # $50B maximum
        )
    elif args.universe == 'custom' and args.tickers:
        tickers = args.tickers
    else:
        logger.error("Invalid universe or no tickers specified for custom")
        sys.exit(1)

    # Limit tickers if requested
    if args.max_tickers:
        original_count = len(tickers)
        tickers = tickers[:args.max_tickers]
        logger.info(f"Limited to {len(tickers)} tickers (from {original_count})")

    logger.info(f"Universe: {len(tickers)} tickers")
    logger.info(f"Sample: {tickers[:10]}")

    # Save universe
    if args.save_data:
        universe_file = f"data/universe_{args.universe}_{args.start_date}.csv"
        universe_fetcher.save_universe(tickers, universe_file)

    # Step 2: Download SEC filings
    logger.info("\n>>> STEP 2: DOWNLOADING SEC FILINGS")

    # Build cache key for SEC filings (immutable data - no config hash needed)
    filings_cache_file = Path('data') / build_cache_key(
        data_type='filings',
        universe=args.universe,
        start_date=args.start_date,
        end_date=args.end_date,
        ticker_count=len(tickers)
    )

    # Try to load from cache
    if filings_cache_file.exists() and args.use_cache and not args.force_refresh:
        logger.info(f"✓ Loading cached SEC filings from {filings_cache_file.name}")
        all_filings = pd.read_pickle(filings_cache_file)
        logger.info(f"Loaded {len(all_filings)} cached SEC filings")
    else:
        # Download from SEC EDGAR
        if args.force_refresh:
            logger.info("Force refresh enabled - downloading fresh data from SEC EDGAR")
        else:
            logger.info("No cache found - downloading from SEC EDGAR")

        sec_downloader = SECDownloader(
            company_name=config['data']['sec']['company_name'],
            email=config['data']['sec']['email']
        )

        all_filings = []
        for i, ticker in enumerate(tickers):
            logger.info(f"Downloading filings for {ticker} ({i+1}/{len(tickers)})...")

            filings = sec_downloader.fetch_filings(
                tickers=[ticker],
                filing_type='8-K',  # Focus on 8-K for material events
                start_date=args.start_date,
                end_date=args.end_date
            )

            all_filings.extend(filings)

            # Rate limiting (SEC allows 10 requests/second)
            if i < len(tickers) - 1:
                import time
                time.sleep(0.1)

        logger.info(f"Downloaded {len(all_filings)} SEC filings")

        # Save to cache if requested
        if args.save_data or args.use_cache:
            filings_cache_file.parent.mkdir(parents=True, exist_ok=True)
            pd.to_pickle(all_filings, filings_cache_file)
            logger.info(f"Saved filings to {filings_cache_file.name}")

    # Step 3: Fetch price data
    logger.info("\n>>> STEP 3: FETCHING PRICE DATA")

    # Extend date range for returns calculation
    extended_start = (start_date - timedelta(days=30)).strftime('%Y-%m-%d')
    extended_end = (end_date + timedelta(days=30)).strftime('%Y-%m-%d')

    # Build cache key for price data (time-sensitive for recent data)
    prices_cache_file = Path('data') / build_cache_key(
        data_type='prices',
        universe=args.universe,
        start_date=args.start_date,
        end_date=args.end_date,
        ticker_count=len(tickers)
    )

    # Try to load from cache (check freshness for recent data)
    if (prices_cache_file.exists() and args.use_cache and not args.force_refresh and
        is_cache_fresh(prices_cache_file, args.end_date, max_age_days=60)):
        logger.info(f"✓ Loading cached price data from {prices_cache_file.name}")
        prices = pd.read_pickle(prices_cache_file)
        logger.info(f"Loaded {len(prices)} rows of cached price data")
    else:
        # Fetch from yfinance
        if args.force_refresh:
            logger.info("Force refresh enabled - fetching fresh price data from yfinance")
        elif not prices_cache_file.exists():
            logger.info("No cache found - fetching from yfinance")
        else:
            logger.info("Cache stale - fetching fresh price data from yfinance")

        price_fetcher = PriceFetcher()
        prices = price_fetcher.fetch_price_data(
            tickers=tickers,
            start_date=extended_start,
            end_date=extended_end
        )

        logger.info(f"Fetched price data: {len(prices)} rows")

        # Save to cache if requested
        if args.save_data or args.use_cache:
            prices_cache_file.parent.mkdir(parents=True, exist_ok=True)
            prices.to_pickle(prices_cache_file)
            logger.info(f"Saved prices to {prices_cache_file.name}")

    # Step 4: Load Fama-French factors
    logger.info("\n>>> STEP 4: LOADING FAMA-FRENCH FACTORS")
    ff_factors = FamaFrenchFactors()
    factors = ff_factors.load_ff_factors(
        start_date=extended_start,
        end_date=extended_end,
        frequency='daily'
    )
    logger.info(f"Loaded {len(factors)} periods of factor data")

    # Step 5: Event Detection & Sentiment Analysis
    source_name = "Reddit" if social_source == 'reddit' else "Twitter"
    logger.info(f"\n>>> STEP 5: EVENT DETECTION & {source_name.upper()} SENTIMENT ANALYSIS")

    # Compute config hash for events cache (depends on NLP parameters)
    nlp_config_keys = [
        'nlp.event_detector.confidence_threshold',
        'nlp.event_detector.type',
        'nlp.sentiment_analyzer.model',
        'data.social_media.days_before_event',
        'data.social_media.days_after_event',
        'data.social_media.max_posts_per_ticker'
    ]
    nlp_hash = compute_config_hash(config, nlp_config_keys)

    # Build cache key for events (config-dependent)
    events_cache_file = Path('data') / build_cache_key(
        data_type='events',
        universe=args.universe,
        start_date=args.start_date,
        end_date=args.end_date,
        config_hash=nlp_hash
    )

    # Try to load from cache
    if events_cache_file.exists() and args.use_cache and not args.force_refresh:
        logger.info(f"✓ Loading cached events from {events_cache_file.name}")
        logger.info(f"  Config hash: {nlp_hash} (NLP parameters unchanged)")
        events_data = pd.read_pickle(events_cache_file)
        logger.info(f"Loaded {len(events_data)} cached ESG events")
    else:
        # Process events from scratch
        if args.force_refresh:
            logger.info("Force refresh enabled - detecting events from scratch")
        elif not events_cache_file.exists():
            logger.info(f"No cache found (config hash: {nlp_hash}) - detecting events")
        else:
            logger.info("Config changed - re-detecting events with new parameters")

        # Initialize NLP components
        filing_parser = SECFilingParser()
        text_cleaner = TextCleaner()
        event_detector = ESGEventDetector()
        sentiment_analyzer = FinancialSentimentAnalyzer()
        feature_extractor = ReactionFeatureExtractor(sentiment_analyzer)

        # Initialize social media fetcher (Reddit or Twitter)
        social_media_config = config['data']['social_media']

        if social_source == 'reddit':
            reddit_config = config['data']['reddit']
            social_media_fetcher = RedditFetcher(
                client_id=reddit_config.get('client_id'),
                client_secret=reddit_config.get('client_secret'),
                user_agent=reddit_config.get('user_agent', 'ESG Sentiment Trading Bot 1.0'),
                use_mock=reddit_config.get('use_mock', True)
            )
        else:  # twitter
            twitter_config = config['data']['twitter']
            social_media_fetcher = TwitterFetcher(
                bearer_token=twitter_config.get('bearer_token') if not twitter_config.get('use_mock') else None,
                use_mock=twitter_config.get('use_mock', True)
            )

        if use_real_data:
            logger.info(f"✓ Using REAL {source_name} API")
        else:
            logger.info(f"⚠ Using MOCK {source_name} data")

        events_data = []

        # FIX 1.2: Defensive date filtering (second layer of defense)
        # Filter out any filings that somehow got through with wrong dates
        original_count = len(all_filings)
        start_dt = datetime.strptime(args.start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(args.end_date, '%Y-%m-%d')

        valid_filings = []
        filtered_out = []

        for filing in all_filings:
            try:
                filing_date = datetime.strptime(filing.get('date', args.start_date), '%Y-%m-%d')

                if start_dt <= filing_date <= end_dt:
                    valid_filings.append(filing)
                else:
                    filtered_out.append((filing['ticker'], filing.get('date', 'UNKNOWN')))
            except ValueError as e:
                logger.warning(f"⚠ Invalid date format in filing: {filing.get('date')}")
                filtered_out.append((filing['ticker'], filing.get('date', 'INVALID')))

        # Log filtering statistics
        filtered_count = len(filtered_out)
        if filtered_count > 0:
            logger.warning(f"⚠ Filtered {filtered_count}/{original_count} filings outside date range:")
            for ticker, date in filtered_out[:5]:  # Show first 5
                logger.warning(f"  - {ticker}: {date}")
            if filtered_count > 5:
                logger.warning(f"  ... and {filtered_count - 5} more")

            # Alert if >10% filtered (indicates upstream bug)
            if filtered_count / original_count > 0.10:
                logger.error(f"⚠⚠⚠ WARNING: {filtered_count/original_count*100:.1f}% of filings were outside date range!")
                logger.error(f"    This suggests the SEC downloader may not be filtering correctly.")
                logger.error(f"    Expected: {args.start_date} to {args.end_date}")

        all_filings = valid_filings  # Replace with filtered list
        logger.info(f"Valid filings for event detection: {len(all_filings)}")

        for i, filing in enumerate(all_filings):
            logger.info(f"Processing filing {i+1}/{len(all_filings)}: {filing['ticker']}...")

            try:
                # Extract and clean text
                if 'text' in filing:
                    text = filing['text']
                else:
                    text = filing_parser.extract_text(filing['file_path'])

                text = text_cleaner.clean_for_sentiment_analysis(text)

                # Detect ESG events
                event_result = event_detector.detect_event(text)

                if event_result['has_event']:
                    logger.info(f"  ✓ ESG Event detected: {event_result['category']} "
                              f"(confidence: {event_result['confidence']:.2f})")

                    # Fetch social media data
                    event_date = datetime.strptime(filing.get('date', args.start_date), '%Y-%m-%d')

                    # Build per-event cache for social media posts
                    days_before = social_media_config.get('days_before_event', 3)
                    days_after = social_media_config.get('days_after_event', 7)
                    max_results = social_media_config.get('max_posts_per_ticker', 100)

                    social_cache_dir = Path('data/social_media')
                    social_cache_dir.mkdir(parents=True, exist_ok=True)
                    social_cache_file = social_cache_dir / f"{social_source}_{filing['ticker']}_{event_date.date()}_d{days_before}_{days_after}_max{max_results}.pkl"

                    # Try to load from cache
                    if social_cache_file.exists() and args.use_cache and not args.force_refresh:
                        logger.info(f"  ✓ Loading cached {source_name} data from {social_cache_file.name}")
                        posts_df = pd.read_pickle(social_cache_file)
                    else:
                        # Fetch from API
                        logger.info(f"  Fetching {source_name} data around {event_date.date()}...")
                        posts_df = social_media_fetcher.fetch_tweets_for_event(
                            ticker=filing['ticker'],
                            event_date=event_date,
                            keywords=social_media_config.get('esg_keywords', []),
                            days_before=days_before,
                            days_after=days_after,
                            max_results=max_results
                        )

                        # Save to cache
                        if args.save_data or args.use_cache:
                            posts_df.to_pickle(social_cache_file)

                    # Extract reaction features (handle missing Reddit data gracefully)
                    if posts_df.empty:
                        logger.warning(f"  ⚠ No {source_name} posts found for {filing['ticker']}, using neutral sentiment")
                        # ADVANCED FALLBACK: Hybrid FinBERT + Keyword Sentiment
                        # 1. Try FinBERT on relevant text
                        # 2. If FinBERT is Neutral (0.0) but Keywords are Strong, use Keywords
                        # This handles "boring legalese" that actually contains a negative event
                        
                        fallback_intensity = 0.0
                        finbert_used = False
                        
                        if sentiment_analyzer:
                            relevant_text = filing_parser.extract_esg_relevant_sections(text)
                            filing_text_snippet = relevant_text[:1000] 
                            sentiment_result = sentiment_analyzer.analyze_single(filing_text_snippet)
                            finbert_score = sentiment_analyzer.score_to_numeric(sentiment_result)
                            
                            if abs(finbert_score) > 0.01:
                                fallback_intensity = finbert_score
                                finbert_used = True
                                logger.warning(f"  ⚠ No {source_name} posts found for {filing['ticker']}, using FinBERT on filing text: {finbert_score:.3f}")
                        
                        # If FinBERT was neutral or unavailable, check event keywords
                        if not finbert_used or abs(fallback_intensity) < 0.01:
                            event_sentiment = event_result.get('sentiment', 'neutral')
                            if event_sentiment == 'positive':
                                fallback_intensity = 0.5
                                logger.warning(f"  ⚠ No {source_name} posts found for {filing['ticker']}, FinBERT neutral, using event sentiment: {event_sentiment} ({fallback_intensity})")
                            elif event_sentiment == 'negative':
                                fallback_intensity = -0.5
                                logger.warning(f"  ⚠ No {source_name} posts found for {filing['ticker']}, FinBERT neutral, using event sentiment: {event_sentiment} ({fallback_intensity})")
                            elif finbert_used:
                                logger.warning(f"  ⚠ No {source_name} posts found for {filing['ticker']}, FinBERT and Event both neutral")
                        
                        reaction_features = {
                            'intensity': fallback_intensity,
                            'volume_ratio': 1.0,  # Baseline volume
                            'duration_days': 0,  # No reaction duration
                            'n_tweets': 0,  # No posts
                            'max_sentiment': fallback_intensity,  # Use hybrid score
                            'polarization': 0.0  # No disagreement
                        }
                    else:
                        # Extract features from available social media data
                        reaction_features = feature_extractor.extract_features(posts_df, event_date)

                    logger.info(f"  Posts: {reaction_features['n_tweets']}, "
                              f"Intensity: {reaction_features['intensity']:.3f}, "
                              f"Volume: {reaction_features['volume_ratio']:.2f}x")

                    events_data.append({
                        'ticker': filing['ticker'],
                        'date': event_date,
                        'event_features': event_result,
                        'reaction_features': reaction_features
                    })

            except Exception as e:
                logger.error(f"  Error processing filing: {e}")
                continue

        logger.info(f"\nDetected {len(events_data)} ESG events with {source_name} reactions")

        # Save to cache if requested
        if args.save_data or args.use_cache:
            events_cache_file.parent.mkdir(parents=True, exist_ok=True)
            pd.to_pickle(events_data, events_cache_file)
            logger.info(f"Saved events to {events_cache_file.name} (hash: {nlp_hash})")

    if len(events_data) == 0:
        logger.warning("No events detected. Cannot generate signals.")
        logger.info("\nPossible reasons:")
        logger.info("- No 8-K filings in date range")
        logger.info("- Events didn't meet confidence threshold")
        logger.info(f"- No {source_name} activity for detected events")
        return

    # Step 6: Signal Generation
    logger.info("\n>>> STEP 6: SIGNAL GENERATION")

    # Load quality filter thresholds from config (ROOT CAUSE FIX Dec 2025)
    quality_filters = config.get('signals', {}).get('quality_filters', {})
    min_intensity = quality_filters.get('min_intensity', 0.05)
    min_volume_ratio = quality_filters.get('min_volume_ratio', 1.2)
    min_posts = quality_filters.get('min_posts', 5)  # NEW: Minimum posts required
    require_social_data = quality_filters.get('require_social_data', True)  # NEW: Require social validation

    logger.info(f"Quality Filters (ROOT CAUSE FIX - Dec 2025):")
    logger.info(f"  Min intensity: {min_intensity}")
    logger.info(f"  Min volume ratio: {min_volume_ratio}x")
    logger.info(f"  Min posts: {min_posts} (excludes events with sparse social data)")
    logger.info(f"  Require social data: {require_social_data} (excludes events without Reddit coverage)")

    signal_generator = ESGSignalGenerator()

    # ROOT CAUSE FIX: Pass new quality parameters to signal generation
    # This filters out noise signals from events without social media validation
    signals_df = signal_generator.generate_signals_batch(
        events_data,
        min_posts=min_posts,
        require_social_data=require_social_data
    )

    if signals_df.empty:
        logger.warning("No trading signals generated after quality filtering.")
        logger.info("Possible fixes:")
        logger.info("  - Lower min_posts threshold in config")
        logger.info("  - Set require_social_data: false (not recommended)")
        logger.info("  - Expand Reddit search window")
        return

    logger.info(f"Generated {len(signals_df)} trading signals")
    logger.info(f"Quintile distribution: {signals_df['quintile'].value_counts().sort_index().to_dict()}")

    if args.save_data:
        signals_file = f"data/signals_{args.start_date}_to_{args.end_date}.csv"
        signals_df.to_csv(signals_file, index=False)
        logger.info(f"Saved signals to {signals_file}")

    # Step 7: Portfolio Construction
    logger.info("\n>>> STEP 7: PORTFOLIO CONSTRUCTION")

    portfolio_constructor = PortfolioConstructor(
        strategy_type=config['portfolio']['strategy_type']
    )

    portfolio = portfolio_constructor.construct_portfolio(
        signals_df,
        method=config['portfolio']['method'],
        balance_long_short=config.get('signals', {}).get('quality_filters', {}).get('balance_long_short', False)
    )

    stats = portfolio_constructor.get_portfolio_statistics(portfolio)
    logger.info(f"Portfolio: {stats['n_long']} long, {stats['n_short']} short positions")
    logger.info(f"Net exposure: {stats['net_exposure']:.2%}")
    logger.info(f"Gross exposure: {stats['gross_exposure']:.2%}")

    if stats['n_positions'] == 0:
        logger.warning("No positions in portfolio. Cannot run backtest.")
        return

    if args.save_data:
        portfolio_file = f"data/portfolio_{args.start_date}_to_{args.end_date}.csv"
        portfolio.to_csv(portfolio_file, index=False)
        logger.info(f"Saved portfolio to {portfolio_file}")

    # Step 8: Backtesting
    logger.info("\n>>> STEP 8: BACKTESTING")
    
    # Run backtest
    logger.info("\n>>> STEP 8: BACKTESTING")

    backtest_engine = BacktestEngine(
        prices=prices,
        initial_capital=config['backtest']['initial_capital'],
        commission_pct=config['backtest']['commission_pct'],
        slippage_bps=config['backtest']['slippage_bps'],
        balance_long_short=config.get('signals', {}).get('quality_filters', {}).get('balance_long_short', False)
    )

    results = backtest_engine.run(
        signals=portfolio,
        rebalance_freq=config['portfolio']['rebalance_frequency'],
        holding_period=config['portfolio']['holding_period']
    )

    logger.info(f"Backtest complete!")
    logger.info(f"Final value: ${results.get_final_value():,.2f}")
    logger.info(f"Total return: {results.get_total_return()*100:.2f}%")

    # Step 9: Performance Analysis
    logger.info("\n>>> STEP 9: PERFORMANCE ANALYSIS")

    perf_analyzer = PerformanceAnalyzer(results)
    perf_analyzer.print_tear_sheet()

    # Save tear sheet
    if args.save_data:
        tearsheet_file = f"results/tear_sheets/tearsheet_{args.start_date}_to_{args.end_date}.txt"
        Path("results/tear_sheets").mkdir(parents=True, exist_ok=True)
        perf_analyzer.save_tear_sheet(tearsheet_file)
        logger.info(f"\nSaved tear sheet to {tearsheet_file}")

    # Step 10: Factor Analysis
    logger.info("\n>>> STEP 10: FACTOR ANALYSIS")

    try:
        factor_analyzer = FactorAnalysis()
        factor_analyzer.load_factors(factors)  # Load factors first
        factor_results = factor_analyzer.run_regression(
            results.get_daily_returns()  # Pass returns as positional argument
        )

        logger.info("\n" + "="*60)
        logger.info("FAMA-FRENCH FACTOR REGRESSION")
        logger.info("="*60)
        logger.info(f"Annualized Alpha: {factor_results['alpha_annualized']*100:.2f}%")
        logger.info(f"T-Statistic: {factor_results['alpha_tstat']:.2f}")
        logger.info(f"P-Value: {factor_results['alpha_pvalue']:.4f}")

        if factor_results['alpha_pvalue'] < 0.05:
            logger.info("\n✓ SIGNIFICANT ALPHA (p < 0.05)")
        else:
            logger.info("\n⚠ Alpha not statistically significant")

        logger.info("\nFactor Loadings:")
        for factor, coef in factor_results['coefficients'].items():
            if factor != 'alpha':
                logger.info(f"  {factor}: {coef:.3f}")

        if args.save_data:
            factor_file = f"results/factor_analysis/factors_{args.start_date}_to_{args.end_date}.pkl"
            Path("results/factor_analysis").mkdir(parents=True, exist_ok=True)
            pd.to_pickle(factor_results, factor_file)
            logger.info(f"\nSaved factor analysis to {factor_file}")

    except Exception as e:
        logger.error(f"Factor analysis failed: {e}")

    # Final summary
    logger.info("\n" + "="*60)
    logger.info("PRODUCTION RUN COMPLETE")
    logger.info("="*60)
    logger.info(f"Events detected: {len(events_data)}")
    logger.info(f"Signals generated: {len(signals_df)}")
    logger.info(f"Portfolio positions: {stats['n_positions']}")
    logger.info(f"Final return: {results.get_total_return()*100:.2f}%")
    logger.info("="*60)


if __name__ == '__main__':
    main()

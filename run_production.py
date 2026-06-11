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
import json
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import sys

# Import project modules
from src.utils.logging_config import setup_logging
from src.utils.strategy_config import load_strategy_spec
from src.utils.date_validator import DateValidator
from src.utils.cache_manager import (
    compute_config_hash, is_cache_fresh, build_cache_key,
    is_cache_trusted, mark_cache_provenance,
)
from src.utils.config_loader import load_config as _load_config_env, resolve_credential
from src.utils.provenance import guard_real, get_provenance, DataUnavailableError, REAL
from src.data import SECDownloader, PriceFetcher, FamaFrenchFactors, TwitterFetcher, RedditFetcher, ArcticShiftFetcher, GDELTFetcher, StockTwitsFetcher, MultiSourceFetcher
from src.data.universe_fetcher import UniverseFetcher
from src.preprocessing import SECFilingParser, TextCleaner
from src.nlp import ESGEventDetector, FinancialSentimentAnalyzer, ReactionFeatureExtractor
from src.signals import ESGSignalGenerator, PortfolioConstructor
from src.signals.signal_generator import WeightDerivationMethod
from src.backtest import BacktestEngine, PerformanceAnalyzer, FactorAnalysis


def load_config(config_path: str = 'config/config.yaml'):
    """Load configuration from YAML.

    Delegates to ``src.utils.config_loader.load_config`` which loads ``.env``
    and expands ``${ENV_VAR}`` placeholders so credentials resolve correctly
    (a bare ``yaml.safe_load`` used to leave the literal ``${REDDIT_CLIENT_ID}``
    string in place, defeating the credential gate).
    """
    return _load_config_env(config_path)


def _git_commit() -> str:
    """Return the current short git commit hash, or 'nogit' if unavailable."""
    try:
        out = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True, text=True, timeout=5,
        )
        commit = out.stdout.strip()
        return commit or 'nogit'
    except Exception:
        return 'nogit'


def _write_equity_csv(results, path: Path, benchmark_returns=None) -> int:
    """Persist the per-period equity / returns / drawdown / exposure series.

    This is the time series the dashboard plots (equity curve, underwater
    drawdown, rolling exposure). run_production previously persisted only the
    scalar tear sheet, so no series existed to chart. Returns the row count.
    """
    equity = results.get_equity_curve()
    if equity is None or equity.empty:
        return 0
    daily_ret = results.get_daily_returns()
    drawdown = results.get_drawdown_series()
    exposure = results.get_exposure_series()

    df = pd.DataFrame({'equity': equity})
    df.index.name = 'date'
    df['daily_return'] = daily_ret.reindex(df.index) if daily_ret is not None else 0.0
    df['drawdown'] = drawdown.reindex(df.index) if drawdown is not None else 0.0
    if exposure is not None and not exposure.empty:
        df['gross_exposure'] = exposure['gross_exposure'].reindex(df.index)
        df['net_exposure'] = exposure['net_exposure'].reindex(df.index)
    if benchmark_returns is not None and len(benchmark_returns) > 0:
        bench = benchmark_returns.reindex(df.index).fillna(0.0)
        df['benchmark_cum'] = (1.0 + bench).cumprod()

    path.parent.mkdir(parents=True, exist_ok=True)
    df.reset_index().to_csv(path, index=False)
    return len(df)


def validate_social_media_config(config):
    """Validate social media API configuration (Reddit, Twitter, or Arctic Shift)"""
    social_media_config = config.get('data', {}).get('social_media', {})
    source = social_media_config.get('source', 'arctic_shift').lower()

    if source == 'multi_source':
        # Multi-source needs no credentials - combines free APIs
        multi_config = config.get('data', {}).get('multi_source', {})
        sources = multi_config.get('sources', ['arctic_shift', 'gdelt', 'stocktwits'])
        print("\n" + "="*60)
        print("Using MULTI-SOURCE data fusion (no credentials required)")
        print("="*60)
        print(f"Active sources: {', '.join(sources)}")
        print("  - Arctic Shift: Historical Reddit data")
        print("  - GDELT: Global news articles")
        print("  - StockTwits: Stock social media")
        print("="*60 + "\n")
        return True, 'multi_source'

    elif source == 'arctic_shift':
        # Arctic Shift needs no credentials - always valid
        print("\n" + "="*60)
        print("Using Arctic Shift API (no credentials required)")
        print("="*60)
        print("Free access to archived Reddit data for research.")
        print("API: https://arctic-shift.photon-reddit.com")
        print("="*60 + "\n")
        return True, 'arctic_shift'

    elif source == 'gdelt':
        print("\n" + "="*60)
        print("Using GDELT DOC API (no credentials required)")
        print("="*60)
        print("Free access to global news articles from 2015+.")
        print("API: https://api.gdeltproject.org/api/v2/doc/doc")
        print("="*60 + "\n")
        return True, 'gdelt'

    elif source == 'stocktwits':
        print("\n" + "="*60)
        print("Using StockTwits API (no credentials required)")
        print("="*60)
        print("Free access to stock social media with sentiment.")
        print("Note: Only returns recent messages (no historical date filtering)")
        print("="*60 + "\n")
        return True, 'stocktwits'

    elif source == 'reddit':
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

        # Resolve credentials the same way RedditFetcher does: treat an
        # unexpanded ${...} placeholder or empty value as unset and fall back
        # to the environment (.env already loaded by load_config).
        client_id = resolve_credential(reddit_config.get('client_id'), 'REDDIT_CLIENT_ID')
        client_secret = resolve_credential(reddit_config.get('client_secret'), 'REDDIT_CLIENT_SECRET')
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

        bearer_token = resolve_credential(twitter_config.get('bearer_token'), 'TWITTER_BEARER_TOKEN')
        if not bearer_token:
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
    parser.add_argument('--social-source', type=str, choices=['reddit', 'twitter', 'arctic_shift', 'gdelt', 'stocktwits', 'multi_source'],
                       help='Override social media source (multi_source, arctic_shift, gdelt, stocktwits, reddit, twitter)')
    parser.add_argument('--allow-mock', action='store_true',
                       help='DEMO ONLY: permit synthetic/mock data when real sources are '
                            'unavailable. Default False = fail-closed (a real run aborts rather '
                            'than fabricating data). Runs are tagged with data provenance.')
    parser.add_argument('--seed', type=int, default=42,
                       help='RNG seed recorded in run metadata for reproducibility')

    args = parser.parse_args()
    # Fail-closed by default: production never fabricates data. Mock generation
    # is reachable ONLY behind the explicit --allow-mock flag (clearly a demo).
    allow_mock = args.allow_mock

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

    # Recompute canonical runtime spec after CLI overrides
    strategy_spec = load_strategy_spec(config)

    # Validate social media configuration
    if args.force_real_social_media:
        source = config['data']['social_media'].get('source', 'arctic_shift')
        if source == 'arctic_shift':
            config['data'].setdefault('arctic_shift', {})['use_mock'] = False
        elif source == 'reddit':
            config['data']['reddit']['use_mock'] = False
        else:
            config['data']['twitter']['use_mock'] = False

    strategy_spec = load_strategy_spec(config)
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

    # Read canonical filing types from the shared strategy spec
    filing_types = strategy_spec.filing_types
    filing_type_suffix = '_'.join(ft.replace('-', '') for ft in sorted(filing_types))

    # Build cache key for SEC filings (includes filing types for cache invalidation)
    filings_cache_file = Path('data') / build_cache_key(
        data_type=f'filings_{filing_type_suffix}',
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
            email=config['data']['sec']['email'],
            use_mock=allow_mock,
        )

        all_filings = []
        logger.info(f"Filing types to download: {filing_types}")
        for i, ticker in enumerate(tickers):
            for filing_type in filing_types:
                logger.info(f"Downloading {filing_type} for {ticker} ({i+1}/{len(tickers)})...")

                filings = sec_downloader.fetch_filings(
                    tickers=[ticker],
                    filing_type=filing_type,
                    start_date=args.start_date,
                    end_date=args.end_date
                )

                all_filings.extend(filings)

            # Rate limiting (SEC allows 10 requests/second)
            if i < len(tickers) - 1:
                import time
                time.sleep(0.1)

        logger.info(f"Downloaded {len(all_filings)} SEC filings across {filing_types}")

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

    # Try to load from cache (check freshness AND data provenance for recent data).
    # is_cache_trusted refuses legacy marker-less caches and any mock-tagged cache,
    # so a single outage that once wrote synthetic prices can never poison future runs.
    if (prices_cache_file.exists() and args.use_cache and not args.force_refresh and
        is_cache_fresh(prices_cache_file, args.end_date, max_age_days=60) and
        is_cache_trusted(prices_cache_file)):
        logger.info(f"✓ Loading cached price data from {prices_cache_file.name}")
        prices = pd.read_pickle(prices_cache_file)
        logger.info(f"Loaded {len(prices)} rows of cached price data")
    else:
        # Fetch from yfinance
        if args.force_refresh:
            logger.info("Force refresh enabled - fetching fresh price data from yfinance")
        elif not prices_cache_file.exists():
            logger.info("No cache found - fetching from yfinance")
        elif not is_cache_trusted(prices_cache_file):
            logger.info("Cached prices lack a real-data provenance marker - refetching from yfinance")
        else:
            logger.info("Cache stale - fetching fresh price data from yfinance")

        price_fetcher = PriceFetcher(use_mock=allow_mock)
        prices = price_fetcher.fetch_price_data(
            tickers=tickers,
            start_date=extended_start,
            end_date=extended_end
        )

        # Fail closed: never backtest on synthetic/empty prices on a real run.
        if not allow_mock:
            guard_real(prices, 'STEP 3: price data')
        logger.info(f"Fetched price data: {len(prices)} rows (provenance={get_provenance(prices)})")

        # Save to cache if requested. Only cache REAL data, and stamp provenance
        # so the cache is trustworthy on the next run.
        if (args.save_data or args.use_cache) and get_provenance(prices) == REAL:
            prices_cache_file.parent.mkdir(parents=True, exist_ok=True)
            prices.to_pickle(prices_cache_file)
            mark_cache_provenance(prices_cache_file, REAL)
            logger.info(f"Saved prices to {prices_cache_file.name}")

    # Step 4: Load Fama-French factors
    logger.info("\n>>> STEP 4: LOADING FAMA-FRENCH FACTORS")
    ff_factors = FamaFrenchFactors(use_mock=allow_mock)
    factors = ff_factors.load_ff_factors(
        start_date=extended_start,
        end_date=extended_end,
        frequency='daily'
    )
    # Fail closed: the alpha/factor regression must never run on synthetic factors.
    if not allow_mock:
        guard_real(factors, 'STEP 4: Fama-French factors')
    logger.info(f"Loaded {len(factors)} periods of factor data (provenance={get_provenance(factors)})")

    # Step 5: Event Detection & Sentiment Analysis
    source_name = {
        'reddit': 'Reddit', 'twitter': 'Twitter', 'arctic_shift': 'Arctic Shift',
        'gdelt': 'GDELT', 'stocktwits': 'StockTwits', 'multi_source': 'Multi-Source',
    }.get(social_source, social_source)
    logger.info(f"\n>>> STEP 5: EVENT DETECTION & {source_name.upper()} SENTIMENT ANALYSIS")

    date_validator = DateValidator(args.start_date, args.end_date, strict_mode=False)
    sentiment_analyzer = FinancialSentimentAnalyzer(
        model_name=strategy_spec.sentiment.model_name,
        mode=strategy_spec.sentiment.mode,
        batch_size=strategy_spec.sentiment.batch_size,
        strict=strategy_spec.sentiment.strict,
    )
    logger.info(
        "Sentiment analyzer initialized: requested=%s active=%s",
        sentiment_analyzer.requested_mode,
        sentiment_analyzer.active_mode,
    )
    expected_sentiment_mode = strategy_spec.sentiment.mode.lower()
    if sentiment_analyzer.active_mode != expected_sentiment_mode:
        raise RuntimeError(
            "Canonical production sentiment mode is unavailable: "
            f"requested={expected_sentiment_mode}, active={sentiment_analyzer.active_mode}"
        )
    feature_extractor = ReactionFeatureExtractor(sentiment_analyzer)

    # Compute config hash for events cache (depends on NLP parameters)
    nlp_config_keys = [
        'nlp.event_detector.confidence_threshold',
        'nlp.event_detector.type',
        'nlp.sentiment_analyzer.mode',
        'nlp.sentiment_analyzer.model',
        'nlp.sentiment_analyzer.strict',
        'data.social_media.source',
        'data.social_media.days_before_event',
        'data.social_media.days_after_event',
        'data.social_media.max_posts_per_ticker',
        'data.multi_source.sources',
        'data.sec.filing_types'
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
        events_data = date_validator.validate_events(events_data)
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

        # Initialize social media fetcher (Arctic Shift, Reddit, or Twitter)
        social_media_config = config['data']['social_media']

        if social_source == 'multi_source':
            multi_config = config['data'].get('multi_source', {})
            arctic_config = config['data'].get('arctic_shift', {})
            gdelt_config = config['data'].get('gdelt', {})
            stocktwits_config = config['data'].get('stocktwits', {})
            social_media_fetcher = MultiSourceFetcher(
                sources=multi_config.get('sources', ['arctic_shift', 'gdelt', 'stocktwits']),
                enable_sentiment=True,
                arctic_shift_config=arctic_config,
                gdelt_config=gdelt_config,
                stocktwits_config=stocktwits_config,
                sentiment_mode=strategy_spec.sentiment.mode,
                sentiment_model_name=strategy_spec.sentiment.model_name,
                strict_sentiment=strategy_spec.sentiment.strict,
                use_mock=allow_mock,
            )
        elif social_source == 'arctic_shift':
            arctic_config = config['data'].get('arctic_shift', {})
            social_media_fetcher = ArcticShiftFetcher(
                use_mock=allow_mock,
                subreddits=arctic_config.get('subreddits', None),
                request_timeout=arctic_config.get('request_timeout', 15),
                sentiment_mode=strategy_spec.sentiment.mode,
                sentiment_model_name=strategy_spec.sentiment.model_name,
                strict_sentiment=strategy_spec.sentiment.strict,
            )
        elif social_source == 'gdelt':
            gdelt_config = config['data'].get('gdelt', {})
            social_media_fetcher = GDELTFetcher(
                use_mock=allow_mock,
                request_timeout=gdelt_config.get('request_timeout', 30),
                max_articles=gdelt_config.get('max_articles', 50),
                sentiment_mode=strategy_spec.sentiment.mode,
                sentiment_model_name=strategy_spec.sentiment.model_name,
                strict_sentiment=strategy_spec.sentiment.strict,
            )
        elif social_source == 'stocktwits':
            stocktwits_config = config['data'].get('stocktwits', {})
            social_media_fetcher = StockTwitsFetcher(
                use_mock=allow_mock,
                request_timeout=stocktwits_config.get('request_timeout', 15),
                max_pages=stocktwits_config.get('max_pages', 5),
                sentiment_mode=strategy_spec.sentiment.mode,
                sentiment_model_name=strategy_spec.sentiment.model_name,
                strict_sentiment=strategy_spec.sentiment.strict,
            )
        elif social_source == 'reddit':
            reddit_config = config['data']['reddit']
            social_media_fetcher = RedditFetcher(
                client_id=resolve_credential(reddit_config.get('client_id'), 'REDDIT_CLIENT_ID'),
                client_secret=resolve_credential(reddit_config.get('client_secret'), 'REDDIT_CLIENT_SECRET'),
                user_agent=reddit_config.get('user_agent', 'ESG Sentiment Trading Bot 1.0'),
                use_mock=allow_mock,
                sentiment_mode=strategy_spec.sentiment.mode,
                sentiment_model_name=strategy_spec.sentiment.model_name,
                strict_sentiment=strategy_spec.sentiment.strict,
            )
        else:  # twitter
            twitter_config = config['data']['twitter']
            social_media_fetcher = TwitterFetcher(
                bearer_token=resolve_credential(twitter_config.get('bearer_token'), 'TWITTER_BEARER_TOKEN'),
                use_mock=allow_mock,
            )

        if use_real_data:
            logger.info(f"✓ Using REAL {source_name} API")
        else:
            logger.info(f"⚠ Using MOCK {source_name} data")

        events_data = []

        # Extract confidence threshold from config (fixes bug where config value was ignored)
        confidence_threshold = strategy_spec.event_confidence_threshold

        # Filing-type-specific thresholds:
        # 8-K filings report MATERIAL EVENTS (new information) → use config threshold
        # 10-K/10-Q filings are PERIODIC REPORTS that always contain ESG boilerplate in
        # Risk Factors and MD&A sections. A confidence of 0.25 (3 keyword matches) is trivially
        # easy to hit in a 100-page annual report without any actual ESG event occurring.
        # Require 6+ keyword matches (confidence 0.60) to filter boilerplate from real events.
        confidence_threshold_periodic = max(confidence_threshold * 2.4, 0.60)

        logger.info(f"Event detection confidence thresholds:")
        logger.info(f"  8-K (material events): {confidence_threshold}")
        logger.info(f"  10-K/10-Q (periodic reports): {confidence_threshold_periodic}")

        all_filings = date_validator.validate_filings(all_filings)
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

                # For 10-K/10-Q: extract ESG-relevant sections only (Risk Factors, MD&A)
                # to avoid detecting keywords in boilerplate text across 100+ pages.
                # For 8-K: use full text (entire filing is about the material event).
                filing_type = filing.get('filing_type', '8-K')
                if filing_type in ('10-K', '10-Q'):
                    text = filing_parser.extract_esg_relevant_sections(text, filing_type)
                    effective_threshold = confidence_threshold_periodic
                else:
                    effective_threshold = confidence_threshold

                # Detect ESG events with filing-type-appropriate threshold
                event_result = event_detector.detect_event(text, threshold=effective_threshold)

                if event_result['has_event']:
                    logger.info(f"  ✓ ESG Event detected: {event_result['category']} "
                              f"(confidence: {event_result['confidence']:.2f})")

                    # Fetch social media data
                    event_date = datetime.strptime(filing.get('date', args.start_date), '%Y-%m-%d')

                    # Build per-event cache for social media posts
                    days_before = strategy_spec.social_window.days_before_event
                    days_after = strategy_spec.social_window.days_after_event
                    max_results = strategy_spec.social_window.max_posts_per_ticker

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
                        logger.warning(
                            "  ⚠ No %s posts found for %s; using neutral non-tradable reaction features",
                            source_name,
                            filing['ticker'],
                        )
                        reaction_features = feature_extractor._get_default_features()
                    else:
                        # Extract features from available social media data
                        reaction_features = feature_extractor.extract_features(posts_df, event_date)

                    # Add multi-source agreement metrics (boosts confidence)
                    if hasattr(social_media_fetcher, 'last_source_metrics'):
                        source_metrics = social_media_fetcher.last_source_metrics
                        reaction_features['n_sources'] = source_metrics.get('n_sources', 1)
                        reaction_features['source_agreement'] = source_metrics.get('source_agreement', 0.0)

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

        events_data = date_validator.validate_events(events_data)
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
    min_intensity = strategy_spec.signal.min_intensity
    min_volume_ratio = strategy_spec.signal.min_volume_ratio
    min_posts = strategy_spec.signal.min_posts
    require_social_data = strategy_spec.signal.require_social_data
    min_confidence = strategy_spec.signal.min_confidence

    logger.info("Quality Filters (canonical strategy spec):")
    logger.info(f"  Min intensity: {min_intensity}")
    logger.info(f"  Min volume ratio: {min_volume_ratio}x")
    logger.info(f"  Min posts: {min_posts}")
    logger.info(f"  Require social data: {require_social_data}")
    logger.info(f"  Min confidence: {min_confidence}")
    logger.info(
        "  Weight method: %s | Lookback: %s | Weights: %s",
        strategy_spec.signal.weight_derivation_method,
        strategy_spec.signal.lookback_window,
        strategy_spec.signal.weights,
    )

    signal_generator = ESGSignalGenerator(
        lookback_window=strategy_spec.signal.lookback_window,
        weights=strategy_spec.signal.weights,
        weight_method=WeightDerivationMethod.from_string(
            strategy_spec.signal.weight_derivation_method
        ),
    )

    # ROOT CAUSE FIX: Pass new quality parameters to signal generation
    # This filters out noise signals from events without social media validation
    signals_df = signal_generator.generate_signals_batch(
        events_data,
        min_posts=min_posts,
        require_social_data=require_social_data,
        min_volume_ratio=min_volume_ratio,
        min_intensity=min_intensity,
        min_confidence=min_confidence,
    )
    signals_df = date_validator.validate_signals(signals_df)

    if signals_df.empty:
        logger.warning("No trading signals generated after quality filtering.")
        logger.info("Possible fixes:")
        logger.info("  - Lower min_posts threshold in config")
        logger.info("  - Set require_social_data: false (not recommended)")
        logger.info("  - Expand Reddit search window")
        return

    logger.info(f"Generated {len(signals_df)} trading signals")
    logger.info(f"Quintile distribution: {signals_df['quintile'].value_counts().sort_index().to_dict()}")

    # Always persist signals so the dashboard / run record can read them.
    signals_file = f"data/signals_{args.start_date}_to_{args.end_date}.csv"
    Path('data').mkdir(parents=True, exist_ok=True)
    signals_df.to_csv(signals_file, index=False)
    logger.info(f"Saved signals to {signals_file}")

    # Step 7: Portfolio Construction
    logger.info("\n>>> STEP 7: PORTFOLIO CONSTRUCTION")

    portfolio_constructor = PortfolioConstructor(
        strategy_type=strategy_spec.portfolio.strategy_type,
        selection_balance=strategy_spec.portfolio.selection_balance,
        exposure_model=strategy_spec.portfolio.exposure_model,
        gross_exposure_target=strategy_spec.portfolio.gross_exposure_target,
    )

    # Rolling window: accumulate non-expired signals at each rebalance date
    # window_days = holding_period ensures signal lifetime matches position lifetime
    window_days = strategy_spec.portfolio.holding_period
    rebalance_freq = strategy_spec.portfolio.rebalance_frequency

    portfolio = portfolio_constructor.construct_portfolio(
        signals_df,
        method=strategy_spec.portfolio.method,
        selection_balance=strategy_spec.portfolio.selection_balance,
        exposure_model=strategy_spec.portfolio.exposure_model,
        window_days=window_days,
        rebalance_freq=rebalance_freq,
    )
    portfolio = portfolio_constructor.apply_position_limits(
        portfolio,
        max_position=strategy_spec.portfolio.max_position,
    )

    stats = portfolio_constructor.get_portfolio_statistics(portfolio)
    logger.info(f"Portfolio: {stats['n_long']} long, {stats['n_short']} short positions")
    logger.info(f"Net exposure: {stats['net_exposure']:.2%}")
    logger.info(f"Gross exposure: {stats['gross_exposure']:.2%}")

    if stats['n_positions'] == 0:
        logger.warning("No positions in portfolio. Cannot run backtest.")
        return

    # Always persist the portfolio so the dashboard holdings / proposed-orders
    # views and the run record can read it.
    portfolio_file = f"data/portfolio_{args.start_date}_to_{args.end_date}.csv"
    Path('data').mkdir(parents=True, exist_ok=True)
    portfolio.to_csv(portfolio_file, index=False)
    logger.info(f"Saved portfolio to {portfolio_file}")

    # Run backtest
    logger.info("\n>>> STEP 8: BACKTESTING")

    cash_benchmark_returns = None
    if strategy_spec.risk.cash_overlay_enabled:
        try:
            import yfinance as yf
            if isinstance(prices.index, pd.MultiIndex):
                price_dates = prices.index.get_level_values(0)
            else:
                price_dates = prices.index
            price_start = price_dates.min()
            price_end = price_dates.max()

            spy_data = yf.download(
                'SPY',
                start=price_start - pd.Timedelta(days=5),
                end=price_end + pd.Timedelta(days=5),
                progress=False,
                auto_adjust=True,
            )
            if isinstance(spy_data.columns, pd.MultiIndex):
                spy_data.columns = spy_data.columns.get_level_values(0)
            spy_returns = spy_data['Close'].pct_change().dropna()
            cash_benchmark_returns = spy_returns
            logger.info(f"Cash overlay enabled: SPY ({len(spy_returns)} daily returns)")
            logger.info(
                "  SPY period: %s to %s",
                spy_returns.index[0].date(),
                spy_returns.index[-1].date(),
            )
        except Exception as e:
            logger.warning(f"Could not download SPY for cash overlay: {e}")
            logger.warning("Cash overlay disabled for this run")
    else:
        logger.info("Cash overlay disabled in canonical baseline config")

    backtest_engine = BacktestEngine(
        prices=prices,
        initial_capital=config['backtest']['initial_capital'],
        commission_pct=config['backtest']['commission_pct'],
        slippage_bps=config['backtest']['slippage_bps'],
        enable_risk_management=strategy_spec.risk.enabled,
        max_position_size=strategy_spec.risk.max_position_size,
        target_volatility=strategy_spec.risk.target_volatility,
        max_drawdown_threshold=strategy_spec.risk.max_drawdown_threshold,
        adaptive_drawdown_thresholds=strategy_spec.risk.adaptive_thresholds,
        leverage_limit=strategy_spec.risk.leverage_limit,
        balance_long_short=(strategy_spec.portfolio.exposure_model == 'dollar_neutral'),
        cash_benchmark_returns=cash_benchmark_returns,
        regime_aware_equitization=strategy_spec.risk.regime_aware_equitization,
        bear_equitization_pct=strategy_spec.risk.bear_equitization_pct,
        sma_lookback=strategy_spec.risk.sma_lookback,
    )

    results = backtest_engine.run(
        signals=portfolio,
        rebalance_freq=strategy_spec.portfolio.rebalance_frequency,
        holding_period=strategy_spec.portfolio.holding_period,
    )

    logger.info(f"Backtest complete!")
    logger.info(f"Final value: ${results.get_final_value():,.2f}")
    logger.info(f"Total return: {results.get_total_return()*100:.2f}%")

    # Persist the per-period equity / returns / drawdown / exposure series so the
    # dashboard can plot the equity curve, underwater drawdown, and exposure.
    equity_file = f"data/equity_{args.start_date}_to_{args.end_date}.csv"
    equity_rows = _write_equity_csv(results, Path(equity_file), benchmark_returns=cash_benchmark_returns)
    logger.info(f"Saved equity series ({equity_rows} rows) to {equity_file}")

    # Step 9: Performance Analysis
    logger.info("\n>>> STEP 9: PERFORMANCE ANALYSIS")

    perf_analyzer = PerformanceAnalyzer(results)
    perf_analyzer.print_tear_sheet()

    # Canonical FLAT metrics dict (single source of truth for the run JSON,
    # the dashboard, and the post-backtest validator).
    flat_metrics = perf_analyzer.flatten()

    # Always save the tear sheet (small, per-run, needed by the dashboard).
    tearsheet_file = f"results/tear_sheets/tearsheet_{args.start_date}_to_{args.end_date}.txt"
    Path("results/tear_sheets").mkdir(parents=True, exist_ok=True)
    perf_analyzer.save_tear_sheet(tearsheet_file)
    logger.info(f"\nSaved tear sheet to {tearsheet_file}")

    # Step 10: Factor Analysis
    logger.info("\n>>> STEP 10: FACTOR ANALYSIS")

    factor_status = 'COMPLETE'
    factor_record = {}
    try:
        factor_analyzer = FactorAnalysis()
        factor_analyzer.load_factors(factors)  # Load factors first
        factor_results = factor_analyzer.run_regression(
            results.get_daily_returns()  # Pass returns as positional argument
        )

        logger.info("\n" + "="*60)
        logger.info("FAMA-FRENCH FACTOR REGRESSION")
        logger.info("="*60)
        logger.info(f"Annualized Alpha: {factor_results['alpha_annual']*100:.2f}%")
        logger.info(f"Alpha SE (annual): {factor_results.get('alpha_se_annual', 0.0)*100:.2f}%")
        logger.info(
            f"Alpha 95% CI: [{factor_results.get('alpha_ci_95_low', 0.0)*100:.2f}%, "
            f"{factor_results.get('alpha_ci_95_high', 0.0)*100:.2f}%]"
        )
        logger.info(f"T-Statistic ({factor_results.get('cov_type', 'OLS')}): {factor_results['alpha_tstat']:.2f}")
        logger.info(f"P-Value: {factor_results['alpha_pvalue']:.4f}")
        if 'nw_lags' in factor_results:
            logger.info(f"Newey-West Lags: {factor_results['nw_lags']}")

        if factor_results['alpha_pvalue'] < 0.05:
            logger.info("\n✓ SIGNIFICANT ALPHA (p < 0.05)")
        else:
            logger.info("\n⚠ Alpha not statistically significant")

        logger.info("\nFactor Loadings:")
        beta_tstats = factor_results.get('beta_tstats', {})
        for factor, coef in factor_results.get('betas', {}).items():
            tstat_str = f" (t={beta_tstats[factor]:.2f})" if factor in beta_tstats else ""
            logger.info(f"  {factor}: {coef:.3f}{tstat_str}")
        logger.info(f"R²: {factor_results.get('r_squared', 0.0):.3f} "
                    f"(adj: {factor_results.get('adj_r_squared', 0.0):.3f}), "
                    f"N={factor_results.get('n_observations', 0)}")

        # Serializable factor block for the run JSON (drop residuals/summary objects).
        factor_record = {
            'alpha_annual': float(factor_results.get('alpha_annual', 0.0)),
            'alpha_tstat': float(factor_results.get('alpha_tstat', 0.0)),
            'alpha_pvalue': float(factor_results.get('alpha_pvalue', 1.0)),
            'betas': {k: float(v) for k, v in factor_results.get('betas', {}).items()},
            'r_squared': float(factor_results.get('r_squared', 0.0)),
            'cov_type': factor_results.get('cov_type', 'OLS'),
            'nw_lags': factor_results.get('nw_lags'),
            'n_observations': int(factor_results.get('n_observations', 0)),
            'factors_provenance': get_provenance(factors),
        }

        if args.save_data:
            factor_file = f"results/factor_analysis/factors_{args.start_date}_to_{args.end_date}.pkl"
            Path("results/factor_analysis").mkdir(parents=True, exist_ok=True)
            pd.to_pickle(factor_results, factor_file)
            logger.info(f"\nSaved factor analysis to {factor_file}")

    except Exception as e:
        # Surface (do not swallow) failures in the headline-claim stage: mark the
        # run status invalid so the final summary and exit code reflect it.
        factor_status = 'FACTOR_ANALYSIS_INVALID'
        logger.error(f"Factor analysis failed: {e}", exc_info=True)

    # Post-backtest validation against the canonical FLAT metrics (DRIFT-01 fix:
    # the validator now reads the flat run record, not the nested tear sheet).
    validation_passed = True
    validation_issues = []
    try:
        from scripts.validate_backtest import BacktestValidator
        validator = BacktestValidator(config_path=args.config)
        pre_ok, pre_issues = validator.run_pre_flight_checks(universe_size=len(tickers))
        post_ok, post_issues = validator.validate_backtest_results(flat_metrics)
        validation_passed = bool(pre_ok and post_ok)
        validation_issues = list(pre_issues) + list(post_issues)
    except Exception as e:
        logger.warning(f"Post-backtest validation could not run: {e}")
        validation_passed = False
        validation_issues = [f"validator_error: {e}"]

    # Overall run status (drives the summary banner and process exit code).
    if factor_status == 'FACTOR_ANALYSIS_INVALID':
        status = 'FACTOR_ANALYSIS_INVALID'
    elif not validation_passed:
        status = 'VALIDATION_FAILED'
    else:
        status = 'COMPLETE'

    # Write the canonical machine-readable per-run record (single source of
    # truth for the dashboard, validators, and reproducibility).
    git_commit = _git_commit()
    run_id = f"run_{args.start_date}_to_{args.end_date}_{git_commit}"
    run_record = {
        'schema_version': 1,
        'run_id': run_id,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'status': status,
        'git_commit': git_commit,
        'cli_args': {k: v for k, v in vars(args).items()},
        'seed': args.seed,
        'allow_mock': allow_mock,
        'universe': args.universe,
        'start_date': args.start_date,
        'end_date': args.end_date,
        'social_source': social_source,
        'data_provenance': {
            'prices': get_provenance(prices),
            'factors': get_provenance(factors),
            'social_source': social_source,
            'n_events': len(events_data),
            'n_signals': len(signals_df),
            'n_positions': int(stats['n_positions']),
        },
        'metrics': flat_metrics,
        'factor': factor_record,
        'factor_status': factor_status,
        'portfolio_stats': {k: (float(v) if isinstance(v, (int, float)) else v)
                            for k, v in stats.items()},
        'validation': {'passed': validation_passed, 'issues': validation_issues},
        'paths': {
            'signals_csv': signals_file,
            'portfolio_csv': portfolio_file,
            'equity_csv': equity_file,
            'tearsheet_txt': tearsheet_file,
        },
    }
    runs_dir = Path('results/runs')
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_json_path = runs_dir / f"{run_id}.json"
    with open(run_json_path, 'w') as f:
        json.dump(run_record, f, indent=2, default=str)
    logger.info(f"Saved run record to {run_json_path}")

    # Final summary
    logger.info("\n" + "="*60)
    logger.info(f"PRODUCTION RUN {status}")
    logger.info("="*60)
    logger.info(f"Events detected: {len(events_data)}")
    logger.info(f"Signals generated: {len(signals_df)}")
    logger.info(f"Portfolio positions: {stats['n_positions']}")
    logger.info(f"Final return: {results.get_total_return()*100:.2f}%")
    logger.info(f"Data provenance: prices={get_provenance(prices)}, factors={get_provenance(factors)}")
    logger.info(f"Status: {status}")
    if validation_issues:
        logger.info("Validation issues:")
        for issue in validation_issues:
            logger.info(f"  {issue}")
    logger.info("="*60)
    date_validator.print_summary()

    # Exit code reflects acceptance: 0 = COMPLETE, non-zero = ran but failed a
    # gate (validation/factor analysis), so CI and callers can detect it.
    if status != 'COMPLETE':
        sys.exit(3)


if __name__ == '__main__':
    try:
        main()
    except DataUnavailableError as e:
        # Fail-closed: a real-data run could not obtain real data. Abort with a
        # clear, non-zero exit rather than fabricating or reporting fake results.
        logging.getLogger(__name__).error("ABORTING (data unavailable): %s", e)
        print(f"\nABORTING: {e}\n"
              "A production run will not fabricate data. Fix network/credentials, "
              "or pass --allow-mock for an explicitly-synthetic demo run.", file=sys.stderr)
        sys.exit(2)

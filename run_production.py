"""
Production Runner for ESG Event-Driven Alpha Strategy
Runs on real NASDAQ-100 stocks with real Twitter data
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
from src.data import SECDownloader, PriceFetcher, FamaFrenchFactors, TwitterFetcher
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


def validate_twitter_config(config):
    """Validate Twitter API configuration"""
    twitter_config = config.get('data', {}).get('twitter', {})

    if twitter_config.get('use_mock', True):
        print("\n" + "="*60)
        print("WARNING: Running in MOCK DATA mode")
        print("="*60)
        print("To use real Twitter data:")
        print("1. Set 'use_mock: false' in config/config.yaml")
        print("2. Add your Twitter Bearer Token to config/config.yaml")
        print("3. See TWITTER_SETUP.md for instructions")
        print("="*60 + "\n")
        return False

    bearer_token = twitter_config.get('bearer_token', '')
    if not bearer_token or bearer_token == '':
        print("\n" + "="*60)
        print("ERROR: No Twitter Bearer Token configured")
        print("="*60)
        print("Please add your Twitter API Bearer Token to config/config.yaml")
        print("See TWITTER_SETUP.md for setup instructions")
        print("="*60 + "\n")
        sys.exit(1)

    return True


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
    parser.add_argument('--universe', type=str, default='nasdaq100',
                       choices=['nasdaq100', 'sp500', 'custom'],
                       help='Stock universe to use')
    parser.add_argument('--tickers', type=str, nargs='*',
                       help='Specific tickers (if universe=custom)')
    parser.add_argument('--max-tickers', type=int, default=None,
                       help='Limit number of tickers to process')
    parser.add_argument('--save-data', action='store_true',
                       help='Save intermediate data to disk')
    parser.add_argument('--force-real-twitter', action='store_true',
                       help='Force real Twitter API (override mock mode)')

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

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

    # Validate Twitter configuration
    if args.force_real_twitter:
        config['data']['twitter']['use_mock'] = False

    use_real_twitter = validate_twitter_config(config)

    # Step 1: Get stock universe
    logger.info("\n>>> STEP 1: FETCHING STOCK UNIVERSE")
    universe_fetcher = UniverseFetcher()

    if args.universe == 'nasdaq100':
        tickers = universe_fetcher.get_nasdaq100_tickers()
    elif args.universe == 'sp500':
        tickers = universe_fetcher.get_sp500_tickers()
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

        # Rate limiting
        if i < len(tickers) - 1 and not sec_downloader.use_mock:
            import time
            time.sleep(0.1)  # SEC allows 10 requests/second

    logger.info(f"Downloaded {len(all_filings)} SEC filings")

    if args.save_data:
        filings_file = f"data/filings_{args.start_date}_to_{args.end_date}.pkl"
        pd.to_pickle(all_filings, filings_file)
        logger.info(f"Saved filings to {filings_file}")

    # Step 3: Fetch price data
    logger.info("\n>>> STEP 3: FETCHING PRICE DATA")
    price_fetcher = PriceFetcher()

    # Extend date range for returns calculation
    extended_start = (start_date - timedelta(days=30)).strftime('%Y-%m-%d')
    extended_end = (end_date + timedelta(days=30)).strftime('%Y-%m-%d')

    prices = price_fetcher.fetch_price_data(
        tickers=tickers,
        start_date=extended_start,
        end_date=extended_end
    )

    logger.info(f"Fetched price data: {len(prices)} rows")

    if args.save_data:
        prices_file = f"data/prices_{args.start_date}_to_{args.end_date}.pkl"
        prices.to_pickle(prices_file)
        logger.info(f"Saved prices to {prices_file}")

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
    logger.info("\n>>> STEP 5: EVENT DETECTION & TWITTER SENTIMENT ANALYSIS")

    # Initialize NLP components
    parser = SECFilingParser()
    text_cleaner = TextCleaner()
    event_detector = ESGEventDetector()
    sentiment_analyzer = FinancialSentimentAnalyzer()
    feature_extractor = ReactionFeatureExtractor(sentiment_analyzer)

    # Initialize Twitter fetcher
    twitter_config = config['data']['twitter']
    twitter_fetcher = TwitterFetcher(
        bearer_token=twitter_config.get('bearer_token') if not twitter_config.get('use_mock') else None,
        use_mock=twitter_config.get('use_mock', True)
    )

    if use_real_twitter:
        logger.info("✓ Using REAL Twitter API")
    else:
        logger.info("⚠ Using MOCK Twitter data")

    events_data = []

    for i, filing in enumerate(all_filings):
        logger.info(f"Processing filing {i+1}/{len(all_filings)}: {filing['ticker']}...")

        try:
            # Extract and clean text
            if 'text' in filing:
                text = filing['text']
            else:
                text = parser.extract_text(filing['file_path'])

            text = text_cleaner.clean_for_sentiment_analysis(text)

            # Detect ESG events
            event_result = event_detector.detect_event(text)

            if event_result['has_event']:
                logger.info(f"  ✓ ESG Event detected: {event_result['category']} "
                          f"(confidence: {event_result['confidence']:.2f})")

                # Fetch Twitter data
                event_date = datetime.strptime(filing.get('date', args.start_date), '%Y-%m-%d')
                logger.info(f"  Fetching Twitter data around {event_date.date()}...")

                tweets_df = twitter_fetcher.fetch_tweets_for_event(
                    ticker=filing['ticker'],
                    event_date=event_date,
                    keywords=twitter_config.get('esg_keywords', []),
                    days_before=twitter_config.get('days_before_event', 3),
                    days_after=twitter_config.get('days_after_event', 7),
                    max_results=twitter_config.get('max_tweets_per_ticker', 100)
                )

                if tweets_df.empty:
                    logger.warning(f"  ⚠ No tweets found for {filing['ticker']}")
                    continue

                # Extract reaction features
                reaction_features = feature_extractor.extract_features(tweets_df, event_date)

                logger.info(f"  Tweets: {reaction_features['n_tweets']}, "
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

    logger.info(f"\nDetected {len(events_data)} ESG events with Twitter reactions")

    if args.save_data:
        events_file = f"data/events_{args.start_date}_to_{args.end_date}.pkl"
        pd.to_pickle(events_data, events_file)
        logger.info(f"Saved events to {events_file}")

    if len(events_data) == 0:
        logger.warning("No events detected. Cannot generate signals.")
        logger.info("\nPossible reasons:")
        logger.info("- No 8-K filings in date range")
        logger.info("- Events didn't meet confidence threshold")
        logger.info("- No Twitter activity for detected events")
        return

    # Step 6: Signal Generation
    logger.info("\n>>> STEP 6: SIGNAL GENERATION")

    signal_generator = ESGSignalGenerator()
    signals_list = []

    for event_data in events_data:
        signal = signal_generator.compute_signal(
            ticker=event_data['ticker'],
            date=event_data['date'],
            event_features=event_data['event_features'],
            reaction_features=event_data['reaction_features']
        )
        signals_list.append(signal)

    signals_df = pd.DataFrame(signals_list)
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
        method=config['portfolio']['method']
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

    backtest_engine = BacktestEngine(
        prices=prices,
        initial_capital=config['backtest']['initial_capital'],
        commission_pct=config['backtest']['commission_pct'],
        slippage_bps=config['backtest']['slippage_bps']
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
        factor_results = factor_analyzer.run_regression(
            returns=results.get_daily_returns(),
            factors=factors
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

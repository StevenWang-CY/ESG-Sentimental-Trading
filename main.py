"""
Main Execution Script
Runs the complete ESG Event-Driven Alpha Strategy pipeline
"""

import argparse
import yaml
from datetime import datetime
from pathlib import Path

# Import project modules
from src.utils.logging_config import setup_logging
from src.data import SECDownloader, PriceFetcher, FamaFrenchFactors
from src.preprocessing import SECFilingParser, TextCleaner
from src.nlp import ESGEventDetector, FinancialSentimentAnalyzer, ReactionFeatureExtractor
from src.signals import ESGSignalGenerator, PortfolioConstructor
from src.backtest import BacktestEngine, PerformanceAnalyzer, FactorAnalysis


def load_config(config_path: str = 'config/config.yaml'):
    """Load configuration from YAML file"""
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config


def main():
    """Main execution function"""

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='ESG Event-Driven Alpha Strategy')
    parser.add_argument('--config', type=str, default='config/config.yaml',
                       help='Path to configuration file')
    parser.add_argument('--tickers', type=str, nargs='+',
                       default=['AAPL', 'TSLA', 'XOM', 'JPM', 'MSFT'],
                       help='List of tickers to analyze')
    parser.add_argument('--start-date', type=str, default='2023-01-01',
                       help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, default='2023-12-31',
                       help='End date (YYYY-MM-DD)')
    parser.add_argument('--mode', type=str, default='full',
                       choices=['full', 'data_only', 'backtest_only', 'demo'],
                       help='Execution mode')

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Setup logging
    logger = setup_logging(
        log_level=config['logging']['level'],
        log_file=config['logging'].get('log_file')
    )

    logger.info("="*60)
    logger.info("ESG EVENT-DRIVEN ALPHA STRATEGY")
    logger.info("="*60)
    logger.info(f"Mode: {args.mode}")
    logger.info(f"Tickers: {args.tickers}")
    logger.info(f"Date Range: {args.start_date} to {args.end_date}")
    logger.info("="*60)

    # Run in demo mode with mock data
    if args.mode == 'demo':
        run_demo(args, config, logger)
        return

    # Phase 1: Data Acquisition
    if args.mode in ['full', 'data_only']:
        logger.info("\n>>> PHASE 1: DATA ACQUISITION")

        # Download SEC filings
        logger.info("Downloading SEC filings...")
        sec_downloader = SECDownloader(
            company_name=config['data']['sec']['company_name'],
            email=config['data']['sec']['email']
        )

        filings = sec_downloader.fetch_filings(
            tickers=args.tickers,
            filing_type='8-K',
            start_date=args.start_date,
            end_date=args.end_date
        )
        logger.info(f"Downloaded {len(filings)} SEC filings")

        # Fetch price data
        logger.info("Fetching price data...")
        price_fetcher = PriceFetcher()
        prices = price_fetcher.fetch_price_data(
            tickers=args.tickers,
            start_date=args.start_date,
            end_date=args.end_date
        )
        logger.info(f"Fetched price data: {len(prices)} rows")

        # Load Fama-French factors
        logger.info("Loading Fama-French factors...")
        ff_factors = FamaFrenchFactors()
        factors = ff_factors.load_ff_factors(
            start_date=args.start_date,
            end_date=args.end_date,
            frequency='daily'
        )
        logger.info(f"Loaded {len(factors)} periods of factor data")

    # Phase 2: Event Detection & Sentiment Analysis
    if args.mode in ['full']:
        logger.info("\n>>> PHASE 2: EVENT DETECTION & SENTIMENT ANALYSIS")

        # Initialize NLP components
        parser = SECFilingParser()
        text_cleaner = TextCleaner()
        event_detector = ESGEventDetector()
        sentiment_analyzer = FinancialSentimentAnalyzer()
        feature_extractor = ReactionFeatureExtractor(sentiment_analyzer)

        # Process filings
        events_data = []

        for i, filing in enumerate(filings[:10]):  # Limit for demo
            logger.info(f"Processing filing {i+1}/{min(len(filings), 10)}...")

            # Extract text
            if 'text' in filing:
                text = filing['text']
            else:
                text = parser.extract_text(filing['file_path'])

            # Clean text
            text = text_cleaner.clean_for_sentiment_analysis(text)

            # Detect events
            event_result = event_detector.detect_event(text)

            if event_result['has_event']:
                logger.info(f"  Event detected: {event_result['category']} "
                          f"(confidence: {event_result['confidence']:.2f})")

                # Create mock social media data for testing
                event_date = datetime.strptime(filing.get('date', args.start_date), '%Y-%m-%d')
                mock_tweets = feature_extractor.create_mock_social_data(
                    ticker=filing['ticker'],
                    event_date=event_date,
                    n_tweets=100,
                    sentiment_bias='negative'
                )

                # Extract reaction features
                reaction_features = feature_extractor.extract_features(
                    mock_tweets,
                    event_date
                )

                logger.info(f"  Reaction intensity: {reaction_features['intensity']:.3f}, "
                          f"Volume ratio: {reaction_features['volume_ratio']:.2f}")

                events_data.append({
                    'ticker': filing['ticker'],
                    'date': event_date,
                    'event_features': event_result,
                    'reaction_features': reaction_features
                })

        logger.info(f"Detected {len(events_data)} ESG events with reactions")

    # Phase 3: Signal Generation
    if args.mode in ['full']:
        logger.info("\n>>> PHASE 3: SIGNAL GENERATION")

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

        import pandas as pd
        signals_df = pd.DataFrame(signals_list)
        logger.info(f"Generated {len(signals_df)} trading signals")

        # Construct portfolio
        portfolio_constructor = PortfolioConstructor(
            strategy_type=config['portfolio']['strategy_type']
        )

        portfolio = portfolio_constructor.construct_portfolio(
            signals_df,
            method=config['portfolio']['method']
        )

        stats = portfolio_constructor.get_portfolio_statistics(portfolio)
        logger.info(f"Portfolio: {stats['n_long']} long, {stats['n_short']} short")

    # Phase 4: Backtesting
    if args.mode in ['full', 'backtest_only']:
        logger.info("\n>>> PHASE 4: BACKTESTING")

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

        logger.info(f"Backtest complete. Final value: ${results.get_final_value():,.2f}")
        logger.info(f"Total return: {results.get_total_return()*100:.2f}%")

    # Phase 5: Performance Analysis
    if args.mode in ['full', 'backtest_only']:
        logger.info("\n>>> PHASE 5: PERFORMANCE ANALYSIS")

        # Generate performance metrics
        perf_analyzer = PerformanceAnalyzer(results)
        perf_analyzer.print_tear_sheet()

        # Factor analysis
        if factors is not None and not results.returns.empty:
            logger.info("Running factor analysis...")
            factor_analysis = FactorAnalysis()
            factor_analysis.load_factors(factors)

            regression_results = factor_analysis.run_regression(results.returns_series)

            interpretation = factor_analysis.interpret_results(regression_results)
            logger.info("\n" + interpretation)

    logger.info("\n" + "="*60)
    logger.info("EXECUTION COMPLETE")
    logger.info("="*60)


def run_demo(args, config, logger):
    """Run a quick demo with mock data"""
    logger.info("\n>>> RUNNING DEMO MODE WITH MOCK DATA")

    from datetime import datetime, timedelta
    import pandas as pd
    import numpy as np

    # Create mock data
    logger.info("Creating mock data...")

    # Mock price data
    dates = pd.date_range(start=args.start_date, end=args.end_date, freq='D')
    mock_prices_list = []

    for ticker in args.tickers:
        np.random.seed(hash(ticker) % 2**32)
        base_price = 100
        returns = np.random.normal(0.0005, 0.02, len(dates))
        prices = base_price * np.exp(np.cumsum(returns))

        for date, price in zip(dates, prices):
            mock_prices_list.append({
                'Date': date,
                'ticker': ticker,
                'Close': price,
                'Adj Close': price,
                'Volume': 1000000
            })

    prices = pd.DataFrame(mock_prices_list).set_index(['Date', 'ticker'])

    # Create mock events and signals
    event_detector = ESGEventDetector()
    sentiment_analyzer = FinancialSentimentAnalyzer()
    feature_extractor = ReactionFeatureExtractor(sentiment_analyzer)
    signal_generator = ESGSignalGenerator()

    signals_list = []

    for ticker in args.tickers[:3]:  # Use first 3 tickers
        event_date = datetime.strptime(args.start_date, '%Y-%m-%d') + timedelta(days=30)

        # Mock event
        event_result = {
            'has_event': True,
            'category': 'E',
            'confidence': 0.8,
            'sentiment': 'negative'
        }

        # Mock reaction
        mock_tweets = feature_extractor.create_mock_social_data(
            ticker, event_date, n_tweets=100, sentiment_bias='negative'
        )

        reaction_features = feature_extractor.extract_features(mock_tweets, event_date)

        # Generate signal
        signal = signal_generator.compute_signal(
            ticker=ticker,
            date=event_date,
            event_features=event_result,
            reaction_features=reaction_features
        )

        signals_list.append(signal)

    signals_df = pd.DataFrame(signals_list)
    logger.info(f"Generated {len(signals_df)} mock signals")

    # Construct portfolio
    portfolio_constructor = PortfolioConstructor(strategy_type='long_short')
    portfolio = portfolio_constructor.construct_portfolio(signals_df, method='quintile')

    # Run backtest
    logger.info("Running backtest...")
    backtest_engine = BacktestEngine(prices, initial_capital=1000000)
    results = backtest_engine.run(portfolio, rebalance_freq='W', holding_period=10)

    # Analyze performance
    perf_analyzer = PerformanceAnalyzer(results)
    perf_analyzer.print_tear_sheet()

    logger.info("\n>>> DEMO COMPLETE")
    logger.info("To run with real data, use: python main.py --mode full")


if __name__ == '__main__':
    main()

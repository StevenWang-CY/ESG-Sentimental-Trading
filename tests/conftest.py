"""
Shared test fixtures for pytest

This file contains common fixtures used across multiple test modules.
Fixtures are automatically discovered by pytest.
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def sample_events_df():
    """Sample ESG events DataFrame for testing"""
    return pd.DataFrame({
        'ticker': ['AAPL', 'TSLA', 'MSFT', 'GOOGL', 'AMZN'],
        'date': pd.to_datetime(['2024-01-15', '2024-02-20', '2024-03-10', '2024-04-05', '2024-05-12']),
        'filing_type': ['8-K', '8-K', '8-K', '8-K', '8-K'],
        'category': ['Governance', 'Environmental', 'Social', 'Governance', 'Social'],
        'confidence': [0.35, 0.42, 0.28, 0.31, 0.38],
        'keywords_matched': [
            'board,directors',
            'emissions,carbon',
            'diversity,inclusion',
            'ethics,compliance',
            'labor,workers'
        ]
    })


@pytest.fixture
def sample_prices_df():
    """Sample price data DataFrame for testing"""
    dates = pd.date_range('2024-01-01', '2024-05-31', freq='D')
    tickers = ['AAPL', 'TSLA', 'MSFT', 'GOOGL', 'AMZN']

    data = []
    for ticker in tickers:
        # Generate realistic price data with random walk
        np.random.seed(hash(ticker) % (2**32))
        base_price = {'AAPL': 180, 'TSLA': 200, 'MSFT': 400, 'GOOGL': 140, 'AMZN': 170}[ticker]

        prices = base_price + np.cumsum(np.random.randn(len(dates)) * 2)

        for date, price in zip(dates, prices):
            data.append({
                'date': date,
                'ticker': ticker,
                'close': price,
                'open': price * (1 + np.random.randn() * 0.01),
                'high': price * (1 + abs(np.random.randn()) * 0.015),
                'low': price * (1 - abs(np.random.randn()) * 0.015),
                'volume': int(50000000 + np.random.randn() * 10000000),
                'adj_close': price
            })

    df = pd.DataFrame(data)
    return df.set_index(['date', 'ticker']).sort_index()


@pytest.fixture
def sample_reddit_df():
    """Sample Reddit sentiment data for testing"""
    return pd.DataFrame({
        'timestamp': pd.to_datetime([
            '2024-01-15 10:30:00',
            '2024-01-15 14:20:00',
            '2024-02-20 09:15:00',
            '2024-02-20 16:45:00',
            '2024-03-10 11:00:00'
        ]),
        'ticker': ['AAPL', 'AAPL', 'TSLA', 'TSLA', 'MSFT'],
        'text': [
            "Apple's new board changes look promising for governance.",
            "Not sure about the board shuffle.",
            "Tesla's carbon reduction plan is impressive!",
            "TSLA to the moon with these sustainability moves!",
            "Microsoft diversity programs are exactly what tech needs."
        ],
        'sentiment': [0.65, -0.15, 0.82, 0.70, 0.58],
        'upvotes': [342, 145, 1250, 567, 890],
        'comments': [25, 12, 78, 34, 45]
    })


@pytest.fixture
def sample_signals_df():
    """Sample trading signals DataFrame for testing"""
    return pd.DataFrame({
        'date': pd.to_datetime(['2024-01-15', '2024-01-16', '2024-02-20', '2024-02-21', '2024-03-10']),
        'ticker': ['AAPL', 'AAPL', 'TSLA', 'TSLA', 'MSFT'],
        'raw_score': [0.65, 0.72, 0.85, 0.78, 0.58],
        'z_score': [0.5, 0.7, 1.2, 0.9, 0.3],
        'quintile': [4, 4, 5, 5, 3],
        'signal': [1, 1, 1, 1, 0],
        'event_confidence': [0.35, 0.35, 0.42, 0.42, 0.28],
        'sentiment_intensity': [0.65, 0.70, 0.82, 0.78, 0.58]
    })


@pytest.fixture
def baseline_config():
    """Baseline MEDIUM sensitivity configuration"""
    return {
        'nlp': {
            'event_detector': {
                'confidence_threshold': 0.20
            }
        },
        'portfolio': {
            'rebalance_frequency': 'W',
            'holding_period': 7,
            'max_position': 0.1,
            'strategy_type': 'long_short',
            'method': 'quintile'
        },
        'data': {
            'social_media': {
                'days_before_event': 3,
                'days_after_event': 7
            }
        },
        'signals': {
            'weights': {
                'event_severity': 0.20,  # Event detection confidence
                'intensity': 0.45,       # PRIMARY: Sentiment (research-backed)
                'volume': 0.25,          # Social conviction
                'duration': 0.10,        # Persistence
                'max_sentiment': 0.0,    # Optional: MDPI 2025
                'polarization': 0.0      # Optional: Sentiment std
            }
        },
        'backtest': {
            'initial_capital': 1000000.0,
            'commission_pct': 0.0005,
            'slippage_bps': 3
        }
    }


@pytest.fixture
def failed_high_config():
    """Failed HIGH sensitivity configuration (for comparison tests)"""
    return {
        'nlp': {
            'event_detector': {
                'confidence_threshold': 0.15  # TOO LOW
            }
        },
        'portfolio': {
            'rebalance_frequency': 'D',  # OVERTRADING
            'holding_period': 5,          # TOO SHORT
            'max_position': 0.1,
            'strategy_type': 'long_short',
            'method': 'quintile'
        },
        'data': {
            'social_media': {
                'days_before_event': 7,   # TOO WIDE
                'days_after_event': 14     # TOO WIDE
            }
        },
        'signals': {
            'weights': {
                'event_severity': 0.20,  # Event detection confidence
                'intensity': 0.45,       # PRIMARY: Sentiment (research-backed)
                'volume': 0.25,          # Social conviction
                'duration': 0.10,        # Persistence
                'max_sentiment': 0.0,    # Optional: MDPI 2025
                'polarization': 0.0      # Optional: Sentiment std
            }
        },
        'backtest': {
            'initial_capital': 1000000.0,
            'commission_pct': 0.0005,
            'slippage_bps': 3
        }
    }


@pytest.fixture
def sample_portfolio_weights():
    """Sample portfolio weights for testing"""
    return pd.DataFrame({
        'date': pd.to_datetime(['2024-01-15'] * 5),
        'ticker': ['AAPL', 'TSLA', 'MSFT', 'GOOGL', 'AMZN'],
        'weight': [0.10, 0.10, 0.08, -0.08, -0.10],  # Long + short
        'quintile': [5, 5, 4, 2, 1]
    })


@pytest.fixture
def expected_baseline_metrics():
    """Expected metrics for MEDIUM baseline configuration"""
    return {
        'sharpe_ratio': 0.70,
        'sortino_ratio': 1.29,
        'total_return': 20.38,
        'volatility': 7.08,
        'max_drawdown': -5.29,
        'turnover': 3.19,
        'num_trades': 21,
        'num_events': 58
    }


@pytest.fixture
def expected_high_metrics():
    """Expected metrics for failed HIGH sensitivity configuration"""
    return {
        'sharpe_ratio': 0.04,  # CATASTROPHIC
        'sortino_ratio': 0.06,
        'total_return': 5.91,
        'volatility': 6.33,
        'max_drawdown': -7.88,
        'turnover': 7.44,  # OVERTRADING
        'num_trades': 50,
        'num_events': 99
    }


@pytest.fixture
def fixtures_dir():
    """Path to test fixtures directory"""
    return Path(__file__).parent / 'fixtures'


@pytest.fixture
def temp_results_dir(tmp_path):
    """Temporary directory for test results"""
    results_dir = tmp_path / 'test_results'
    results_dir.mkdir()
    return results_dir

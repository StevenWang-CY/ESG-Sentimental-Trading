# ESG Event-Driven Alpha Strategy

A market-neutral long-short equity strategy that generates alpha by exploiting slow information diffusion around ESG (Environmental, Social, and Governance) events, combining hybrid NLP sentiment analysis with event-driven signals.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Version](https://img.shields.io/badge/Version-4.0.0-blue)
![Status](https://img.shields.io/badge/Status-Production--Ready-green)

---

## Performance Highlights

**Best Backtest** (Jan 2024 -- Oct 2025, 22 months, 45 NASDAQ-100 stocks):

| Metric | Value |
|--------|-------|
| Total Return | 20.38% |
| CAGR | 6.92% |
| Sharpe Ratio | 0.70 |
| Sortino Ratio | 1.29 |
| Max Drawdown | -5.29% |
| Annualized Volatility | 7.08% |
| Sentiment-Quintile Correlation | 0.786 |

---

## Strategy Overview

### Core Thesis

ESG-related information diffuses more slowly than earnings data. While earnings surprises are priced within 1--3 days, ESG events take 10--20 days to be fully reflected in stock prices (Hong & Kacperczyk, 2009). This lag creates a tradable window.

The strategy exploits three specific frictions:

1. **Attention scarcity** -- investors focus on earnings and neglect ESG filings, so events are initially underpriced.
2. **Analyst coverage gap** -- mid-cap stocks have fewer analysts, so information asymmetry persists longer.
3. **Sentiment diffusion lag** -- social media sentiment peaks 5--10 days after an event, producing a predictable price catch-up.

### Pipeline

```
SEC EDGAR 8-K Filings ──► ESG Event Detection (rule-based, 150+ keywords)
                              │
Reddit / Arctic Shift /       │
GDELT / StockTwits    ──► Hybrid Sentiment Analysis (FinBERT 70% + Lexicon 30%)
                              │
                              ▼
                     Feature Extraction
                     (Intensity, Volume Ratio, Duration, Polarization)
                              │
                              ▼
                     Composite Scoring & Z-Score Normalization
                     (rolling 252-day window)
                              │
                              ▼
                     Quintile Ranking → Long Q5 / Short Q1
                              │
                              ▼
                     Market-Neutral Portfolio
                     (equal-weight, 10-day holding, weekly rebalance)
```

### Composite Signal Scoring

Each ESG event receives a shock score:

```
Score = 0.15 × Event_Severity
      + 0.35 × Intensity
      + 0.20 × Volume_Normalized
      + 0.10 × Duration
      + 0.20 × Sentiment_Volume_Momentum
```

Weights can be derived statistically via inverse-variance or correlation methods instead of fixed values (configurable in `config/config.yaml`).

### Sentiment Model

The system uses a **70/30 hybrid** of two complementary approaches:

- **FinBERT** (70%) -- context-aware transformer model for financial text (Araci, 2019).
- **Loughran-McDonald Lexicon** (30%) -- domain-validated financial dictionary, stable and interpretable (Loughran & McDonald, 2011).
- **Negation handling** -- 5-word window polarity reversal (Taboada et al., 2011).

### Portfolio Construction

- **Long**: equal-weight Quintile 5 stocks (strongest positive signals)
- **Short**: equal-weight Quintile 1 stocks (strongest negative signals)
- **Net exposure**: ~0% (market-neutral)
- **Max position**: 8% per stock
- **Holding period**: 10 days (calibrated to ESG diffusion cycle)
- **Rebalance**: weekly (matches ESG event frequency)

---

## Project Structure

```
ESG-Sentimental-Trading/
├── main.py                         # General-purpose runner (demo, full, validate)
├── run_production.py               # Production backtest with caching
├── config/
│   ├── config.yaml                 # All strategy parameters
│   └── esg_keywords.json           # ESG keyword dictionaries
│
├── src/
│   ├── data/                       # Data acquisition
│   │   ├── sec_downloader.py       # SEC EDGAR 8-K filings
│   │   ├── reddit_fetcher.py       # Reddit API sentiment
│   │   ├── arctic_shift_fetcher.py # Archived Reddit (free, no auth)
│   │   ├── gdelt_fetcher.py        # Global news articles (free)
│   │   ├── stocktwits_fetcher.py   # Stock social media (free)
│   │   ├── multi_source_fetcher.py # Combined multi-source coordinator
│   │   ├── fetch_coordinator.py    # Atomic sync, circuit breaker, retry
│   │   ├── price_fetcher.py        # Yahoo Finance prices
│   │   ├── ff_factors.py           # Fama-French factor data
│   │   ├── esg_universe.py         # ESG stock universe definitions
│   │   └── universe_fetcher.py     # Dynamic universe selection
│   │
│   ├── nlp/                        # NLP processing
│   │   ├── event_detector.py       # Rule-based ESG event detection
│   │   ├── advanced_sentiment_analyzer.py  # FinBERT + Lexicon hybrid
│   │   ├── feature_extractor.py    # Reaction feature extraction
│   │   └── esg_sentiment_dictionaries.py   # Domain-specific lexicons
│   │
│   ├── signals/                    # Signal generation
│   │   ├── signal_generator.py     # Composite scoring + quintile ranking
│   │   └── portfolio_constructor.py # Long-short portfolio assembly
│   │
│   ├── backtest/                   # Backtesting engine
│   │   ├── engine.py               # Vectorized simulation
│   │   ├── metrics.py              # Core performance metrics
│   │   ├── enhanced_metrics.py     # 30+ institutional metrics
│   │   └── factor_analysis.py      # Fama-French 5-factor attribution
│   │
│   ├── risk/                       # Risk management
│   │   ├── risk_manager.py         # Position limits, volatility targeting
│   │   ├── drawdown_controller.py  # Adaptive drawdown thresholds
│   │   ├── scandal_detector.py     # Flash crash circuit breaker
│   │   ├── dropout_handler.py      # Sentiment data quality fallback
│   │   └── regime_detector.py      # Regime change detection
│   │
│   ├── validation/                 # Walk-forward validation
│   │   └── walk_forward_validator.py  # OOS validation with embargo periods
│   │
│   ├── ml/                         # Machine learning
│   │   ├── enhanced_pipeline.py    # ML classification pipeline
│   │   └── feature_selector.py     # Feature selection
│   │
│   ├── preprocessing/              # Text preprocessing
│   │   ├── sec_parser.py           # SEC filing parser
│   │   └── text_cleaner.py         # Text normalization
│   │
│   └── utils/                      # Utilities
│       └── cache_manager.py        # 3-tier intelligent caching
│
├── tests/                          # Unit & integration tests
├── results/                        # Backtest outputs & tear sheets
├── scripts/                        # Analysis & validation tools
├── docs/                           # Extended documentation
└── data/                           # Cached data files
```

---

## Quick Start

### Prerequisites

```bash
python --version  # 3.10+
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### Run a Demo

```bash
python main.py --mode demo
```

### Production Backtest

```bash
# With multi-source sentiment (free, no credentials)
python run_production.py \
    --universe NASDAQ_100 \
    --social-source multi_source \
    --start-date 2024-01-01 \
    --end-date 2025-01-01

# With Reddit API (requires credentials)
export REDDIT_CLIENT_ID="your_id"
export REDDIT_CLIENT_SECRET="your_secret"
python run_production.py \
    --universe RUSSELL_MIDCAP \
    --social-source reddit \
    --start-date 2024-01-01 \
    --end-date 2025-01-01 \
    --save-data

# Re-run with cached data
python run_production.py --universe RUSSELL_MIDCAP --use-cache
```

### Walk-Forward Validation

```bash
python main.py --mode=validate --config=config/config.yaml
```

---

## Configuration

Key parameters in `config/config.yaml`:

```yaml
nlp:
  event_detector:
    confidence_threshold: 0.30     # Event quality filter (0.0-1.0)

signals:
  weight_derivation_method: "inverse_variance"  # "fixed", "equal", "inverse_variance", "correlation"
  weights:                         # Used when method = "fixed"
    event_severity: 0.15
    intensity: 0.35
    volume: 0.20
    duration: 0.10
    sentiment_volume_momentum: 0.20

portfolio:
  method: "quintile"
  holding_period: 10               # Days
  rebalance_frequency: "W"         # Weekly
  max_position: 0.08               # 8% max per stock
  balance_long_short: true         # Force balanced L/S

risk_management:
  adaptive_thresholds: true        # Derive drawdown levels from data
  target_volatility: 0.12          # 12% annualized
  circuit_breaker:
    volume_spike_threshold: 5.0    # 5x normal volume triggers alert
    sentiment_crash_threshold: -0.5

validation:
  enabled: true
  min_train_months: 12
  test_months: 3
  embargo_days: 5                  # Gap between train/test sets
  acceptance_criteria:
    min_oos_sharpe: 0.0
    min_overfit_ratio: 0.4
    min_profitable_folds: 0.5
```

---

## Risk Management

| Layer | Control | Threshold |
|-------|---------|-----------|
| Position | Max per stock | 8% |
| Sector | Max per sector | 25% |
| Drawdown | Adaptive reduction | Data-derived (or -10% fixed) |
| Volatility | Annual target | 12% |
| Exposure | Net market exposure | 0% +/- 5% |
| Circuit breaker | Scandal / flash crash | Volume 5x + sentiment < -0.5 |
| Data quality | Sentiment dropout | Halt new positions if coverage < 50% |

---

## Data Sources

| Source | Data | Auth Required |
|--------|------|---------------|
| SEC EDGAR | 8-K filings (material events) | No (rate-limited 10 req/s) |
| Reddit API | Social sentiment | Yes (PRAW credentials) |
| Arctic Shift | Archived Reddit posts | No |
| GDELT | Global news articles | No |
| StockTwits | Stock social media | No |
| Yahoo Finance | Price data | No |
| Fama-French Library | Factor data | No |

---

## Academic References

### Sentiment & NLP

1. Araci, D. (2019). "FinBERT: Financial Sentiment Analysis with Pre-trained Language Models." *arXiv:1908.10063*.
2. Loughran, T., & McDonald, B. (2011). "When is a Liability Not a Liability? Textual Analysis, Dictionaries, and 10-Ks." *The Journal of Finance*, 66(1), 35--65.
3. Taboada, M., Brooke, J., Tofiloski, M., Voll, K., & Stede, M. (2011). "Lexicon-Based Methods for Sentiment Analysis." *Computational Linguistics*, 37(2), 267--307.
4. Polanyi, L., & Zaenen, A. (2006). "Contextual Valence Shifters." In *Computing Attitude and Affect in Text: Theory and Applications*.

### ESG & Market Behavior

5. Hong, H., & Kacperczyk, M. (2009). "The Price of Sin: The Effects of Social Norms on Markets." *Journal of Financial Economics*, 93(1), 15--36.
6. Serafeim, G., & Yoon, A. (2023). "Stock Price Reactions to ESG News." *Review of Financial Studies*, 36(12), 4702--4747.
7. Pastor, L., Stambaugh, R. F., & Taylor, L. A. (2022). "Dissecting Green Returns." *Journal of Financial Economics*, 146(2), 403--424.

### Portfolio Construction & Factor Models

8. Fama, E. F., & French, K. R. (1992). "The Cross-Section of Expected Stock Returns." *The Journal of Finance*, 47(2), 427--465.
9. Jegadeesh, N., & Titman, S. (1993). "Returns to Buying Winners and Selling Losers." *The Journal of Finance*, 48(1), 65--91.
10. Cochrane, J. H. (2005). *Asset Pricing* (Revised Edition). Princeton University Press.

### ESG Sentiment & Trading (2024--2025)

11. "From Tweets to Trades: Investor Sentiment in ESG Stocks." *De Gruyter* (2025).
12. "ESG News Sentiment and Stock Price Reactions via BERT." *Schmalenbach Journal of Business Research* (2024).
13. "Strong vs. Stable: ESG Ratings Momentum and Volatility." *Journal of Asset Management* (2024).
14. "Using Social Media & Sentiment Analysis to Make Investment Decisions." *MDPI* (2024, 2025).
15. "Can Machine Learning Explain Alpha Generated by ESG Factors?" *Computational Economics* (2025).
16. "Data-Driven Sustainable Investment Strategies: Integrating ESG." *MDPI* (2024).
17. "Can ESG Add Alpha? ESG Tilt and Momentum Strategies." *Portfolio Management Research* (2024).

---

## Ethical Declaration

- All social media data is publicly available; no private data accessed.
- Reddit API usage follows rate limits and Terms of Service.
- Only aggregate sentiment metrics used; no individual user tracking.
- API credentials stored in environment variables, never committed to version control.

---

## License

[MIT License](LICENSE)

## Contact

**Author**: Steven Wang
**Email**: StevenWANG0805@outlook.com
**GitHub**: [stevenwang2029/ESG-Sentimental-Trading](https://github.com/stevenwang2029/ESG-Sentimental-Trading)

---

*Last Updated: January 2026 | Version 4.0.0*

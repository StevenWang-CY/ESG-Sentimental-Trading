# ESG Event-Driven Alpha Strategy

A market-neutral long-short equity strategy that generates alpha by exploiting slow information diffusion around ESG (Environmental, Social, and Governance) events, combining hybrid NLP sentiment analysis with event-driven signals.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Version](https://img.shields.io/badge/Version-5.0.0-blue)
![Status](https://img.shields.io/badge/Status-Production--Ready-green)

---

## Performance Highlights

**Best Backtest** (Jan 2024 -- Dec 2025, 24 months, ESG-sensitive NASDAQ-100):

| Metric | Strategy | SPY |
|--------|----------|-----|
| Total Return | **+92.84%** | +56.39% |
| CAGR | **35.94%** | ~25% |
| Sharpe Ratio | **1.85** | ~1.0 |
| Sortino Ratio | **3.00** | -- |
| Max Drawdown | **-9.94%** | ~-10% |
| Annualized Volatility | 16.24% | ~15% |
| Calmar Ratio | **3.61** | -- |

**Bear Market Robustness** (Jan 2022 -- Dec 2024, 36 months):

| Metric | Strategy | SPY |
|--------|----------|-----|
| Total Return | +37.40% | +39.17% |
| Sharpe Ratio | **0.51** | ~0.5 |
| Max Drawdown | -30.94% | ~-25% |

The strategy uses **regime-aware cash equitization** (Faber 2007, Ang 2014): idle cash is fully invested in SPY during bull markets (SPY above 100-day SMA) and partially de-equitized during bear markets, reducing drawdowns while preserving recovery upside.

---

## Core Thesis

ESG-related information diffuses more slowly than earnings data. While earnings surprises are priced within 1--3 days, ESG events take 10--20 days to be fully reflected in stock prices (Hong & Kacperczyk, 2009). This lag creates a tradable window.

The strategy exploits three specific frictions:

1. **Attention scarcity** -- investors focus on earnings and neglect ESG filings, so events are initially underpriced.
2. **Analyst coverage gap** -- mid-cap stocks have fewer analysts, so information asymmetry persists longer.
3. **Sentiment diffusion lag** -- social media sentiment peaks 5--10 days after an event, producing a predictable price catch-up.

---

## Signal Generation Pipeline

The strategy transforms raw text data into market-neutral portfolio positions through six stages. Each stage narrows and refines the information, moving from thousands of unstructured documents to a handful of high-conviction trading signals.

```
                         ┌──────────────────────┐
                         │  SEC EDGAR 8-K       │
                         │  Filings             │
                         └─────────┬────────────┘
                                   │
                                   ▼
                      ┌────────────────────────┐
                      │  Stage 1               │
 Social Media ───────►│  Data Acquisition      │
 (Reddit, GDELT,      │  & Coordination        │
  Arctic Shift,       └─────────┬──────────────┘
  StockTwits)                   │
                    ┌───────────┴───────────┐
                    ▼                       ▼
         ┌──────────────────┐    ┌──────────────────┐
         │  Stage 2         │    │  Stage 3         │
         │  ESG Event       │    │  Sentiment       │
         │  Detection       │    │  Analysis        │
         └────────┬─────────┘    └────────┬─────────┘
                  │                       │
                  └───────────┬───────────┘
                              ▼
                   ┌──────────────────────┐
                   │  Stage 4             │
                   │  Reaction Feature    │
                   │  Extraction          │
                   └─────────┬────────────┘
                             │
                             ▼
                   ┌──────────────────────┐
                   │  Stage 5             │
                   │  Composite Scoring,  │
                   │  Normalization &     │
                   │  Quintile Ranking    │
                   └─────────┬────────────┘
                             │
                             ▼
                   ┌──────────────────────┐
                   │  Stage 6             │
                   │  Portfolio           │
                   │  Construction        │
                   └──────────────────────┘
```

### Stage 1: Data Acquisition

The system ingests data from two independent streams that later converge.

**SEC filings** -- The first stream downloads 8-K filings (material event disclosures) from SEC EDGAR for every stock in the universe. These filings are the trigger: each one is a candidate ESG event.

**Social media** -- The second stream collects public posts and articles from multiple sources around each filing date, within a window of 10 days before to 3 days after the event. The post-event window is capped at +3 days to conform to the academic event study standard (MacKinlay, 1997) and to prevent look-ahead bias. The available sources are:

| Source | Content | Authentication |
|--------|---------|----------------|
| Arctic Shift | Archived Reddit discussions | None (free) |
| GDELT | Global news articles | None (free) |
| StockTwits | Retail trader commentary | None (free) |
| Reddit API | Live Reddit data | PRAW credentials |

When multiple sources are used, a **FetchCoordinator** retrieves them in parallel with per-source rate limiting, exponential-backoff retry, and a circuit breaker that disables a source after three consecutive failures. Results are deduplicated by text similarity and merged into a single table of timestamped posts per event.

### Stage 2: ESG Event Detection

Each 8-K filing is scanned for ESG-relevant content using a rule-based detector with over 150 domain-specific keywords organized into three categories:

| Category | Positive Examples | Negative Examples |
|----------|-------------------|-------------------|
| Environmental | net zero commitment, TCFD disclosure, GRI standards, carbon capture | EPA violation, greenwashing, deforestation, methane leak |
| Social | diversity initiative, living wage, LGBTQ inclusion, paid family leave | discrimination lawsuit, data breach, forced labor, sweatshop |
| Governance | board diversity, clawback policy, cybersecurity governance, audit oversight | insider trading, SEC investigation, accounting scandal |

Each filing receives a **confidence score** equal to the number of keyword matches divided by 10, capped at 1.0. A filing that matches 3 keywords scores 0.30; one that matches 8 keywords scores 0.80. Only events above the configured threshold (default 0.25) proceed.

**Output per event**: category (E/S/G), sentiment direction (positive/negative), confidence score, and the matched keywords.

### Stage 3: Sentiment Analysis

For every event that passes Stage 2, the social media posts collected in Stage 1 are scored for sentiment using a **hybrid model** that blends two complementary approaches:

**FinBERT (70% weight)** -- A transformer model pre-trained on financial text (Araci, 2019). It reads each post in context and outputs a probability distribution over positive, neutral, and negative. The score is signed: positive probability becomes a positive number, negative probability becomes negative. FinBERT excels at understanding context, negation, and nuance, but can hallucinate on novel terminology. The transformer score is used only when its confidence exceeds 0.5; otherwise the system falls back entirely to the lexicon.

**Loughran-McDonald Lexicon (30% weight)** -- A dictionary of financial terms with pre-assigned sentiment weights (Loughran & McDonald, 2011). Words like *outstanding* or *revenue growth* carry positive weight; words like *litigation* or *impairment* carry negative weight. The lexicon is stable and interpretable but cannot understand context.

The final sentiment score for each post is:

> **Sentiment = 0.70 x FinBERT_score + 0.30 x Lexicon_score**

Two linguistic corrections are applied to the lexicon component before blending:

- **Negation handling** (Taboada et al., 2011) -- When a negator (*not*, *never*, *cannot*) is detected, all sentiment-bearing words within the next 5 words have their polarity reversed and intensity reduced to 80%. The negation scope terminates at punctuation or conjunctions like *but* or *however*.

- **Valence shifters** (Polanyi & Zaenen, 2006) -- Intensifiers (*very*, *extremely*, *significantly*) multiply the base sentiment by 1.5--1.8x. Diminishers (*somewhat*, *slightly*, *barely*) reduce it to 0.5--0.7x.

### Stage 4: Reaction Feature Extraction

The raw sentiment scores from Stage 3 are aggregated into six features that characterize the market's reaction to each ESG event. All post-event features use a strict +3 day window (MacKinlay, 1997):

| Feature | What It Measures | How It Is Calculated |
|---------|-----------------|----------------------|
| **Intensity** | How strongly people feel about the event | Weighted average of absolute sentiment scores, where posts with higher virality (retweets, likes, follower count) receive more weight |
| **Volume Ratio** | Whether the event attracted unusual attention | Number of posts in the 3-day window after the event divided by the number of posts in the 10-day window before it. If fewer than 3 pre-event posts exist, defaults to log1p(post_count) to capture unexpected news alpha (Tetlock, 2007) |
| **Duration** | How long the reaction persists | Count of post-event days where the average absolute sentiment exceeds 0.20 |
| **Amplification** | Social media reach of the reaction | Log-transformed mean virality score (retweets + likes/10) x log(user_followers) |
| **Baseline Deviation** | Statistical unusualness of post volume | Z-score of volume change: (post_volume - pre_volume) / sqrt(pre_volume) |
| **Pre-Event Sentiment** | Market mood before the event | Mean sentiment from the pre-event window (requires at least 3 posts, else 0.0) |

### Stage 5: Composite Scoring, Normalization, and Ranking

The features from Stage 4, together with the event confidence from Stage 2, are combined into a single score per event, then normalized and ranked across all events on each date.

**Step 1 -- Composite raw score.** Each component is first normalized to the 0--1 range, then combined with data-derived or fixed weights. The default method is **inverse-variance weighting**, where lower-variance components receive higher weight, reducing reliance on hand-tuned parameters. A fixed-weight fallback is also available:

| Component | Default Fixed Weight | Role |
|-----------|---------------------|------|
| Intensity | 40% | Primary alpha driver -- sentiment magnitude predicts returns |
| Volume (log-normalized) | 25% | Attention proxy -- high volume confirms event significance |
| Event Severity (confidence) | 20% | Quality filter -- higher-confidence detections are more reliable |
| Duration | 15% | Persistence -- sustained reactions predict larger price moves |

Weights always sum to 1.0 (enforced programmatically). A **pre-event confirmation boost** of +10% conviction is applied when pre-event sentiment agrees with the post-event direction.

**Step 2 -- Z-score normalization.** The raw score is standardized against a rolling 252-day window of prior scores to maintain time-series stationarity (Jegadeesh & Titman, 1993):

> **z = (raw_score -- rolling_mean) / rolling_std**

**Step 3 -- Signal transformation.** The z-score is passed through a hyperbolic tangent to bound the signal between -1 (strong short) and +1 (strong long):

> **signal = tanh(z)**

**Step 4 -- Quality filtering.** Signals are discarded if they fail any of the following checks:
- No social media data available for the event
- Fewer than 5 posts (statistically unreliable)
- Absolute sentiment intensity below 0.05 (indistinguishable from noise)

**Step 5 -- Quintile ranking.** On each date, all surviving signals are ranked cross-sectionally by raw score and assigned to quintiles (Fama & French, 1992):
- **Q5** (top 20%) -- strongest positive signals, assigned to the long portfolio
- **Q3** (middle 20%) -- neutral, no position
- **Q1** (bottom 20%) -- strongest negative signals, assigned to the short portfolio

When fewer than five signals exist on a given date, the system uses a tertile split. Sign validation ensures Q5 signals have positive raw scores and Q1 signals have negative raw scores (Fama & French, 1993).

### Stage 6: Portfolio Construction

Signals are converted into portfolio weights under a long-biased market-neutral constraint:

- All Q5 stocks receive equal positive weight (long side).
- All Q1 stocks receive equal negative weight (short side) with a **0.3x dampening factor** (130/30 style). The dampening reflects the empirical finding that negative ESG events are priced faster due to asymmetric attention (Barber & Odean, 2008), while positive ESG alpha persists longer (Edmans, 2011; Eccles et al., 2014).
- Long and short sides are **balanced**: the system selects equal numbers of positions on each side to prevent unintended directional exposure.
- Individual positions are capped at 8% of portfolio value (10% in the risk layer).
- The portfolio is rebalanced weekly, and positions are held for 49 days (7 weeks) to capture the full ESG alpha lifecycle: primary alpha (5--10d) + diffusion (10--20d) + institutional rebalancing (20--35d) (Flammer 2013; Khan, Serafeim & Yoon 2016).

---

## Project Structure

```
ESG-Sentimental-Trading/
├── main.py                         # Runner: demo, full, data_only, backtest_only modes
├── run_production.py               # Production backtest with 3-tier caching
├── config/
│   ├── config.yaml                 # All strategy parameters
│   └── esg_keywords.json           # ESG keyword dictionaries
│
├── src/
│   ├── data/                       # Stage 1: Data acquisition
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
│   ├── nlp/                        # Stages 2--3: Event detection & sentiment
│   │   ├── event_detector.py       # Rule-based ESG event detection (150+ keywords)
│   │   ├── advanced_sentiment_analyzer.py  # FinBERT + Lexicon hybrid (70/30)
│   │   ├── sentiment_analyzer.py   # Lightweight FinBERT-only wrapper
│   │   ├── feature_extractor.py    # Stage 4: Reaction feature extraction
│   │   ├── temporal_feature_extractor.py   # Extended temporal features
│   │   ├── word_correlation_analyzer.py    # Word-sentiment correlation analysis
│   │   └── esg_sentiment_dictionaries.py   # Domain-specific lexicons
│   │
│   ├── signals/                    # Stages 5--6: Scoring & portfolio
│   │   ├── signal_generator.py     # Composite scoring + quintile ranking
│   │   └── portfolio_constructor.py # Long-short portfolio assembly (130/30)
│   │
│   ├── backtest/                   # Backtesting engine
│   │   ├── engine.py               # Event-driven simulation with cash tracking
│   │   ├── metrics.py              # Core performance metrics
│   │   ├── enhanced_metrics.py     # 30+ institutional metrics
│   │   └── factor_analysis.py      # Fama-French 5-factor attribution
│   │
│   ├── risk/                       # Risk management
│   │   ├── risk_manager.py         # Position limits, volatility targeting
│   │   ├── drawdown_controller.py  # Adaptive drawdown thresholds
│   │   ├── scandal_detector.py     # Flash crash circuit breaker
│   │   ├── dropout_handler.py      # Sentiment data quality fallback
│   │   ├── regime_detector.py      # Regime change detection
│   │   └── position_sizer.py       # Kelly Criterion-based sizing
│   │
│   ├── validation/                 # Walk-forward validation
│   │   └── walk_forward_validator.py  # OOS validation with embargo periods
│   │
│   ├── ml/                         # Machine learning
│   │   ├── enhanced_pipeline.py    # ML classification pipeline
│   │   ├── feature_selector.py     # Feature importance & selection
│   │   └── categorical_classifier.py # ESG category classification
│   │
│   ├── preprocessing/              # Text preprocessing
│   │   ├── sec_parser.py           # SEC filing parser
│   │   └── text_cleaner.py         # Text normalization
│   │
│   └── utils/
│       ├── cache_manager.py        # 3-tier intelligent caching
│       ├── date_validator.py       # Date range & trading calendar validation
│       ├── helpers.py              # Shared utility functions
│       └── logging_config.py       # Centralized logging setup
│
├── tests/                          # Unit & integration tests
│   ├── conftest.py                 # Shared fixtures & test config
│   └── unit/
│       ├── test_fetch_coordinator.py     # FetchCoordinator tests
│       ├── test_signal_generator.py      # Signal generation tests
│       ├── test_portfolio_constructor.py # Portfolio construction tests
│       ├── test_momentum_feature.py      # Momentum feature tests
│       ├── test_walk_forward_validator.py # Validation framework tests
│       └── test_edge_cases.py            # Edge case coverage
│
├── scripts/                        # Analysis & validation tools
│   ├── validate_backtest.py        # Pre-flight checks & result validation
│   ├── threshold_sweep.py          # Hyperparameter sensitivity analysis
│   ├── compare_backtests.py        # A/B backtest comparison
│   └── export_events_for_review.py # Event export for manual review
│
├── diagnostics/                    # Debugging & diagnostic tools
│   ├── diagnostic_main_strategy.py # Strategy-level diagnostics
│   ├── diagnostic_returns.py       # Return attribution analysis
│   ├── debug_dates.py              # Date alignment debugging
│   └── debug_prices.py             # Price data validation
│
├── docs/                           # Extended documentation
│   ├── CONFIGURATION_GUIDE.md      # Parameter reference
│   ├── IMPLEMENTATION_SUMMARY.md   # Architecture overview
│   ├── TRADE_COUNT_ANALYSIS.md     # Signal generation diagnostics
│   ├── OPTIMIZATION_NOTES.md       # Performance tuning notes
│   ├── ACTION_ITEMS.md             # Development roadmap
│   └── NEXT_STEPS.md               # Future enhancements
│
├── results/                        # Backtest outputs & tear sheets
├── data/                           # Cached data files
│
├── LICENSE                         # MIT License
├── CONTRIBUTING.md                 # Contribution guidelines
├── CODE_OF_CONDUCT.md              # Community standards
├── pyproject.toml                  # Python packaging & metadata
├── requirements.txt                # Pinned dependencies
├── .env.example                    # Environment variable template
└── .github/                        # GitHub templates
    ├── ISSUE_TEMPLATE/
    │   ├── bug_report.md
    │   └── feature_request.md
    └── PULL_REQUEST_TEMPLATE.md
```

---

## Quick Start

### Prerequisites

```bash
python --version  # 3.10+
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Or install via pyproject.toml
pip install -e .

# Optional: Install FinBERT for transformer-based sentiment
pip install -e ".[nlp]"
```

### Run a Demo

```bash
python main.py --mode demo
```

### Production Backtest

```bash
# Multi-source sentiment (free, no credentials needed)
python run_production.py \
    --universe NASDAQ_100 \
    --social-source multi_source \
    --start-date 2024-01-01 \
    --end-date 2025-01-01

# Reddit API (requires credentials)
export REDDIT_CLIENT_ID="your_id"
export REDDIT_CLIENT_SECRET="your_secret"
python run_production.py \
    --universe RUSSELL_MIDCAP \
    --social-source reddit \
    --start-date 2024-01-01 \
    --end-date 2025-01-01 \
    --save-data

# Re-run with cached data (skips API calls)
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
    confidence_threshold: 0.25     # Event quality filter (0.0-1.0)

signals:
  weight_derivation_method: "inverse_variance"  # "fixed", "equal", "inverse_variance", "correlation"
  weights:                         # Used when method = "fixed"
    event_severity: 0.20
    intensity: 0.40
    volume: 0.25
    duration: 0.15

portfolio:
  method: "quintile"
  holding_period: 49               # 7 weeks (full ESG alpha lifecycle)
  rebalance_frequency: "W"         # Weekly
  max_position: 0.08               # 8% max per stock
  balance_long_short: true         # Force balanced L/S

risk_management:
  max_position_size: 0.25          # 25% max (concentrated event-driven)
  target_volatility: 0.18          # 18% (event-driven range 15-25%)
  adaptive_thresholds: true        # Derive drawdown levels from data
  cash_equitization:
    regime_aware: true             # Reduce SPY exposure in bear markets
    sma_lookback: 100              # 100-day SMA regime filter
    bear_equitization_pct: 0.40    # 40% equitization in bear regime
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

The risk system implements six independent layers, each based on established portfolio theory:

| Layer | Control | Threshold | Reference |
|-------|---------|-----------|-----------|
| Position | Max per stock | 10% | Statman (1987) |
| Sector | Max per sector | 30% | Grinold & Kahn (2000) |
| Drawdown | Adaptive reduction | Data-derived percentiles | Grossman & Zhou (1993) |
| Volatility | Annual target | 18% | Pedersen (2015) |
| Circuit breaker | Scandal / flash crash | Volume 5x + sentiment < -0.5 | -- |
| Data quality | Sentiment dropout | Halt new positions if coverage < 50% | -- |

The **drawdown controller** derives thresholds from the 25th/50th/75th/95th percentiles of historical drawdowns and maps them to exposure levels of 90%/75%/55%/35%. When no historical data is available, fixed thresholds of -5%/-10%/-15%/-20% are used.

The **scandal detector** monitors for ESG crisis events by combining volume spikes, sentiment crashes, and keyword matching. Severity levels (low/medium/high/critical) trigger graduated responses from monitoring only to 48-hour trading halts with 50% exposure reduction.

The **regime detector** identifies six market states (normal, high/low volatility, trend up/down, crisis) using a 63-day short window vs. a 252-day baseline. Regime changes trigger recalibration of signal weights, position sizing, and volatility targets.

---

## Academic References

### Sentiment & NLP

1. Araci, D. (2019). "FinBERT: Financial Sentiment Analysis with Pre-trained Language Models." *arXiv:1908.10063*.
2. Loughran, T., & McDonald, B. (2011). "When is a Liability Not a Liability? Textual Analysis, Dictionaries, and 10-Ks." *The Journal of Finance*, 66(1), 35--65.
3. Taboada, M., Brooke, J., Tofiloski, M., Voll, K., & Stede, M. (2011). "Lexicon-Based Methods for Sentiment Analysis." *Computational Linguistics*, 37(2), 267--307.
4. Polanyi, L., & Zaenen, A. (2006). "Contextual Valence Shifters." In *Computing Attitude and Affect in Text: Theory and Applications*.
5. Hutto, C., & Gilbert, E. (2014). "VADER: A Parsimonious Rule-based Model for Sentiment Analysis of Social Media Text." *ICWSM*.
6. Tetlock, P. (2007). "Giving Content to Investor Sentiment." *The Journal of Finance*, 62(3), 1139--1168.

### ESG & Market Behavior

7. Hong, H., & Kacperczyk, M. (2009). "The Price of Sin: The Effects of Social Norms on Markets." *Journal of Financial Economics*, 93(1), 15--36.
8. Serafeim, G., & Yoon, A. (2023). "Stock Price Reactions to ESG News." *Review of Financial Studies*, 36(12), 4702--4747.
9. Pastor, L., Stambaugh, R. F., & Taylor, L. A. (2022). "Dissecting Green Returns." *Journal of Financial Economics*, 146(2), 403--424.
10. Edmans, A. (2011). "Does the Stock Market Fully Value Intangibles? Employee Satisfaction and Equity Prices." *Journal of Financial Economics*, 101(3), 621--640.

### Portfolio Construction & Factor Models

11. Fama, E. F., & French, K. R. (1992). "The Cross-Section of Expected Stock Returns." *The Journal of Finance*, 47(2), 427--465.
12. Fama, E. F., & French, K. R. (1993). "Common Risk Factors in the Returns on Stocks and Bonds." *Journal of Financial Economics*, 33(1), 3--56.
13. Jegadeesh, N., & Titman, S. (1993). "Returns to Buying Winners and Selling Losers." *The Journal of Finance*, 48(1), 65--91.
14. Cochrane, J. H. (2005). *Asset Pricing* (Revised Edition). Princeton University Press.
15. Barber, B. M., & Odean, T. (2008). "All That Glitters: The Effect of Attention and News on the Buying Behavior of Individual and Institutional Investors." *Review of Financial Studies*, 21(2), 785--818.

### Event Studies & Methodology

16. MacKinlay, A. C. (1997). "Event Studies in Economics and Finance." *Journal of Economic Literature*, 35(1), 13--39.
17. Statman, M. (1987). "How Many Stocks Make a Diversified Portfolio?" *Journal of Financial and Quantitative Analysis*, 22(3), 353--363.

### Risk Management

18. Pedersen, L. H. (2015). *Efficiently Inefficient: How Smart Money Invests and Market Prices Are Determined*. Princeton University Press.
19. Grinold, R. C., & Kahn, R. N. (2000). *Active Portfolio Management* (2nd Edition). McGraw-Hill.
20. Ilmanen, A. (2011). *Expected Returns*. Wiley.
21. Grossman, S. J., & Zhou, Z. (1993). "Optimal Investment Strategies for Controlling Drawdowns." *Mathematical Finance*, 3(3), 241--276.

### Regime Detection & Cash Equitization

22. Faber, M. (2007). "A Quantitative Approach to Tactical Asset Allocation." *The Journal of Wealth Management*, 9(4), 69--79.
23. Ang, A. (2014). *Asset Management: A Systematic Approach to Factor Investing*. Oxford University Press.
24. Zakamulin, V. (2014). "The Real-Life Performance of Market Timing with Moving Average and Time-Series Momentum Rules." *Journal of Asset Management*, 15(4), 261--278.

### ESG Sentiment & Trading (2024--2025)

22. "From Tweets to Trades: Investor Sentiment in ESG Stocks." *De Gruyter* (2025).
23. "ESG News Sentiment and Stock Price Reactions via BERT." *Schmalenbach Journal of Business Research* (2024).
24. "Strong vs. Stable: ESG Ratings Momentum and Volatility." *Journal of Asset Management* (2024).
25. "Using Social Media & Sentiment Analysis to Make Investment Decisions." *MDPI* (2024, 2025).
26. "Can Machine Learning Explain Alpha Generated by ESG Factors?" *Computational Economics* (2025).
27. "Data-Driven Sustainable Investment Strategies: Integrating ESG." *MDPI* (2024).
28. "Can ESG Add Alpha? ESG Tilt and Momentum Strategies." *Portfolio Management Research* (2024).

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
**GitHub**: [StevenWang-CY/ESG-Sentimental-Trading](https://github.com/StevenWang-CY/ESG-Sentimental-Trading)

---

*Last Updated: March 2026 | Version 5.0.0*

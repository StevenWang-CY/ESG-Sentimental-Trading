# ESG Event-Driven Alpha Strategy

A quantitative trading strategy that exploits market inefficiencies around material ESG (Environmental, Social, Governance) events using NLP and **Twitter/X sentiment analysis**.

## Executive Summary

This project implements a **systematic alpha strategy** based on the hypothesis that markets systematically underreact to material ESG events in the medium term (5-30 trading days). The strategy:

- **Detects** ESG events from SEC filings using NLP
- **Analyzes** market reaction via sentiment analysis of **Twitter/X data**
- **Generates** trading signals from composite ESG Event Shock Scores
- **Backtests** performance and proves alpha via Fama-French factor regression

**Data Sources:**
- **SEC EDGAR**: For ESG event detection (8-K, 10-K filings)
- **Twitter/X API v2**: For real-time sentiment analysis and market reaction
- **yfinance**: For price data and returns
- **Fama-French Data Library**: For factor regression analysis

**Target Performance:**
- Sharpe Ratio: 1.2 - 1.8
- Annualized Alpha: 4-8% (t-stat > 2.0)
- Max Drawdown: < 20%

## Project Structure

```
ESG-Sentimental-Trading/
├── config/
│   ├── config.yaml              # Main configuration
│   └── esg_keywords.json        # ESG event keywords
├── data/
│   ├── raw/                     # Raw data (SEC filings, etc.)
│   ├── processed/               # Processed data
│   └── signals/                 # Generated signals
├── src/
│   ├── data/                    # Data acquisition modules
│   │   ├── sec_downloader.py
│   │   ├── price_fetcher.py
│   │   └── ff_factors.py
│   ├── preprocessing/           # Text preprocessing
│   │   ├── sec_parser.py
│   │   └── text_cleaner.py
│   ├── nlp/                     # NLP models
│   │   ├── event_detector.py
│   │   ├── sentiment_analyzer.py
│   │   └── feature_extractor.py
│   ├── signals/                 # Signal generation
│   │   ├── signal_generator.py
│   │   └── portfolio_constructor.py
│   ├── backtest/                # Backtesting engine
│   │   ├── engine.py
│   │   ├── metrics.py
│   │   └── factor_analysis.py
│   └── utils/                   # Utilities
├── notebooks/                   # Jupyter notebooks
├── results/                     # Output results
├── main.py                      # Main execution script
├── requirements.txt             # Python dependencies
└── README.md                    # This file
```

## Installation

### 1. Clone the Repository

```bash
cd /Users/chuyuewang/Desktop/Finance/Personal\ Projects/ESG-Sentimental-Trading
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

#### Basic Installation (Core Features)

```bash
pip install -r requirements.txt
```

#### Full Installation (with ML Models)

For advanced NLP features (FinBERT, ESG-BERT):

```bash
pip install -r requirements.txt
pip install transformers torch
```

For CPU-only (faster installation):

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install transformers
```

#### Development Installation

```bash
pip install -e .
pip install -e ".[dev]"
```

## Quick Start

### Demo Mode (No API Keys Required)

Run a quick demo with mock data:

```bash
python main.py --mode demo
```

This will:
1. Generate mock ESG events
2. Create synthetic Twitter reactions
3. Generate trading signals
4. Run backtest
5. Display performance metrics

### Production Mode (Real Data on NASDAQ-100)

For running on real NASDAQ-100 stocks with real Twitter data:

```bash
# Test with 5 stocks first
python run_production.py \
    --start-date 2024-09-01 \
    --end-date 2024-09-30 \
    --universe custom \
    --tickers AAPL MSFT GOOGL TSLA NVDA \
    --save-data

# Full NASDAQ-100 run
python run_production.py \
    --start-date 2024-09-01 \
    --end-date 2024-09-30 \
    --universe nasdaq100 \
    --save-data
```

**📖 Complete deployment guide**: See [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md)

**✅ Quick checklist**: See [ACTION_CHECKLIST.md](ACTION_CHECKLIST.md)

### Full Pipeline

```bash
python main.py \
    --mode full \
    --tickers AAPL TSLA XOM JPM MSFT \
    --start-date 2023-01-01 \
    --end-date 2023-12-31
```

## Configuration

Edit [config/config.yaml](config/config.yaml) to customize:

### Data Sources

```yaml
data:
  sec:
    email: "your-email@example.com"  # REQUIRED for SEC EDGAR
```

### NLP Models

```yaml
nlp:
  event_detector:
    type: "rule_based"  # or "ml" for transformer models
  sentiment_analyzer:
    model: "ProsusAI/finbert"  # FinBERT model
```

### Strategy Parameters

```yaml
signals:
  weights:
    event_severity: 0.3
    intensity: 0.4
    volume: 0.2
    duration: 0.1

portfolio:
  strategy_type: "long_short"  # long_short, long_only, short_only
  rebalance_frequency: "W"     # D, W, M
```

## Usage Examples

### 1. Data Acquisition Only

```bash
python main.py --mode data_only --tickers AAPL TSLA
```

### 2. Custom Date Range

```bash
python main.py \
    --start-date 2022-01-01 \
    --end-date 2023-12-31 \
    --tickers AAPL MSFT GOOGL
```

### 3. Backtest Only (with existing signals)

```bash
python main.py --mode backtest_only
```

## Twitter/X API Setup (Optional for Real Data)

The strategy uses **Twitter/X exclusively** for sentiment analysis. You have two options:

### Option 1: Mock Data (No API Key Required)

The strategy works out-of-the-box with realistic mock Twitter data for testing:

```bash
python main.py --mode demo  # Uses mock Twitter data automatically
```

### Option 2: Real Twitter Data

For production use with real Twitter data, you need a Twitter API v2 Bearer Token:

1. **Get Twitter API Access**: https://developer.twitter.com/
2. **Configure in** [config/config.yaml](config/config.yaml):

```yaml
data:
  twitter:
    bearer_token: "YOUR_TWITTER_BEARER_TOKEN_HERE"
    use_mock: false  # Set to false for real data
    max_tweets_per_ticker: 100
    days_before_event: 3
    days_after_event: 7
```

3. **Install tweepy**:
```bash
pip install tweepy
```

**📖 Detailed Guide**: See [TWITTER_SETUP.md](TWITTER_SETUP.md) for complete setup instructions, API costs, and troubleshooting.

## Understanding the Strategy

### Signal Generation Pipeline

```
1. SEC Filing → 2. Event Detection → 3. Twitter Data → 4. Sentiment Analysis → 5. Signal Generation
   (8-K, 10-K)     (NLP keywords)       (API v2)          (FinBERT)             (Composite Score)

   SEC EDGAR ────> ESG Event ────> Twitter/X ────> Market Sentiment ────> Trading Signal
                   Detected           Fetch           Analysis               Generation
```

### ESG Event Shock Score Formula

```
Score = w1*EventSeverity + w2*Intensity + w3*Volume + w4*Duration

Where:
- EventSeverity: Confidence from event detection (0-1)
- Intensity: Sentiment score (-1 to +1)
- Volume: Log-normalized social media volume ratio
- Duration: Days sentiment stays elevated
```

### Portfolio Construction

- **Long**: Stocks with high ESG event shock scores (Q5)
- **Short**: Stocks with low scores (Q1)
- **Dollar-neutral**: Equal long/short exposure
- **Rebalancing**: Weekly or monthly

## Performance Metrics

The strategy generates comprehensive performance metrics:

### Return Metrics
- Total Return, CAGR
- Sharpe Ratio, Sortino Ratio
- Calmar Ratio

### Risk Metrics
- Maximum Drawdown
- Value at Risk (VaR)
- Conditional VaR (CVaR)
- Downside Deviation

### Factor Analysis
- Fama-French 5-Factor + Momentum regression
- Alpha (with t-statistic and p-value)
- Factor loadings (Betas)

## Expected Output

```
PERFORMANCE TEAR SHEET
============================================================

RETURN METRICS:
------------------------------------------------------------
total_return                  :     15.23%
cagr                          :     12.45%
sharpe_ratio                  :      1.34
sortino_ratio                 :      1.67

RISK METRICS:
------------------------------------------------------------
max_drawdown                  :    -12.34%
var_95                        :     -2.45%

FACTOR REGRESSION RESULTS
========================

Annualized Alpha: 6.24%
T-Statistic: 2.47
P-Value: 0.0138

✓ SIGNIFICANT (p < 0.05): Evidence of alpha.
```

## Troubleshooting

### Common Issues

#### 1. SEC Download Rate Limit

**Error:** `429 Too Many Requests`

**Solution:** Add delay between requests (already implemented). SEC allows 10 requests/second.

#### 2. Missing Dependencies

**Error:** `ModuleNotFoundError: No module named 'transformers'`

**Solution:**
```bash
pip install transformers torch
```

#### 3. Memory Issues with Transformer Models

**Solution:** Use rule-based detection instead:

```yaml
nlp:
  event_detector:
    type: "rule_based"  # Instead of "ml"
```

#### 4. No Price Data

**Error:** `No data found for ticker`

**Solution:** Check ticker symbols and date ranges. yfinance may have limited historical data.

## Advanced Usage

### Custom ESG Keywords

Add your own keywords to [config/esg_keywords.json](config/esg_keywords.json):

```json
{
  "environmental": {
    "negative": ["your-custom-keyword", "another-keyword"]
  }
}
```

### Custom Signal Weights

Optimize weights in [config/config.yaml](config/config.yaml):

```yaml
signals:
  weights:
    event_severity: 0.4  # Increase weight on event detection
    intensity: 0.3
    volume: 0.2
    duration: 0.1
```

### Walk-Forward Optimization

Implement in your code:

```python
from src.backtest import BacktestEngine

# Split data into train/test periods
# Optimize weights on training period
# Validate on test period
```

## Limitations & Risk Warnings

### Known Limitations

1. **Data Availability**: Free APIs have limited historical data
2. **Event Detection Accuracy**: Rule-based detector ~75% precision
3. **Social Media Bias**: Twitter/Reddit may not represent all investors
4. **Transaction Costs**: Real costs may exceed estimates

### Risk Warnings

⚠️ **This is a research project, not investment advice.**

- **Backtested Performance**: Past performance ≠ future results
- **Model Risk**: NLP models may misclassify events
- **Market Risk**: Strategy may underperform during regime changes
- **Overfitting**: Signals optimized on historical data may not generalize

**Always:**
- Test thoroughly before deploying real capital
- Start with paper trading
- Implement proper risk management
- Monitor live performance vs. backtest

## Contributing

This is a research/portfolio project. If you'd like to extend it:

1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## References

### Academic Literature

1. **Serafeim, G., & Yoon, A. (2022)**. "Stock Price Reactions to ESG News." *Review of Accounting Studies*.
2. **Amel-Zadeh, A., & Serafeim, G. (2018)**. "Why and How Investors Use ESG Information." *Financial Analysts Journal*.
3. **Loughran, T., & McDonald, B. (2011)**. "When is a Liability not a Liability?" *Journal of Finance*.

### Technical Resources

- [SEC EDGAR Documentation](https://www.sec.gov/edgar/searchedgar/accessing-edgar-data.htm)
- [Fama-French Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html)
- [FinBERT Paper](https://arxiv.org/abs/1908.10063)

## License

MIT License - See [LICENSE](LICENSE) file for details.

## Contact

For questions or feedback:
- GitHub Issues: [Create an issue](https://github.com/yourusername/esg-event-alpha/issues)
- Email: research@example.com

---

**Disclaimer:** This project is for educational and research purposes only. It does not constitute investment advice. Trading securities involves risk of loss. Always consult with a qualified financial advisor before making investment decisions.

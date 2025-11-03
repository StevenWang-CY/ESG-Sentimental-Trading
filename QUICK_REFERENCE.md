# Quick Reference Guide

## Installation (2 minutes)

```bash
cd "/Users/chuyuewang/Desktop/Finance/Personal Projects/ESG-Sentimental-Trading"
python3 -m venv venv
source venv/bin/activate
pip install numpy pandas pyyaml
```

## Run Demo (30 seconds)

```bash
python main.py --mode demo
```

## Common Commands

### Run Full Pipeline
```bash
python main.py --mode full --tickers AAPL TSLA XOM
```

### Data Acquisition Only
```bash
python main.py --mode data_only --tickers AAPL MSFT
```

### Custom Date Range
```bash
python main.py \
    --start-date 2022-01-01 \
    --end-date 2023-12-31 \
    --tickers AAPL MSFT GOOGL TSLA XOM
```

## File Structure Quick Reference

```
Key Files:
├── main.py                    # Main execution script
├── config/config.yaml         # Configuration (edit this!)
├── requirements.txt           # Dependencies
├── README.md                  # Full documentation
└── PROJECT_SUMMARY.md         # Project overview

Core Modules:
├── src/data/                  # Data acquisition
│   ├── sec_downloader.py     # SEC filings
│   ├── price_fetcher.py      # Stock prices
│   └── ff_factors.py         # Fama-French factors
├── src/nlp/                   # NLP pipeline
│   ├── event_detector.py     # ESG event detection
│   ├── sentiment_analyzer.py # Sentiment analysis
│   └── feature_extractor.py  # Feature extraction
├── src/signals/               # Signal generation
│   ├── signal_generator.py   # Generate signals
│   └── portfolio_constructor.py # Build portfolio
└── src/backtest/              # Backtesting
    ├── engine.py             # Backtest engine
    ├── metrics.py            # Performance metrics
    └── factor_analysis.py    # Alpha analysis
```

## Configuration Quick Edit

Edit `config/config.yaml`:

```yaml
# Change these for your needs:

data:
  sec:
    email: "your-email@example.com"  # REQUIRED

signals:
  weights:  # Customize signal weights
    event_severity: 0.3
    intensity: 0.4
    volume: 0.2
    duration: 0.1

portfolio:
  strategy_type: "long_short"  # or "long_only", "short_only"
  rebalance_frequency: "W"     # D, W, M

backtest:
  initial_capital: 1000000.0   # Starting capital
```

## Python API Quick Reference

### 1. Data Acquisition

```python
from src.data import PriceFetcher, SECDownloader, FamaFrenchFactors

# Fetch prices
prices = PriceFetcher().fetch_price_data(
    tickers=['AAPL', 'TSLA'],
    start_date='2023-01-01',
    end_date='2023-12-31'
)

# Download SEC filings
filings = SECDownloader().fetch_filings(
    tickers=['AAPL'],
    filing_type='8-K',
    start_date='2023-01-01'
)

# Load Fama-French factors
factors = FamaFrenchFactors().load_ff_factors(
    '2023-01-01', '2023-12-31'
)
```

### 2. Event Detection

```python
from src.nlp import ESGEventDetector

detector = ESGEventDetector()
result = detector.detect_event(
    "Company fined $5M by EPA for pollution"
)

print(result['has_event'])     # True
print(result['category'])      # 'E' (Environmental)
print(result['confidence'])    # 0.8
```

### 3. Sentiment Analysis

```python
from src.nlp import FinancialSentimentAnalyzer

analyzer = FinancialSentimentAnalyzer()
sentiment = analyzer.analyze_single(
    "Company reports strong earnings"
)

print(sentiment['label'])      # 'positive'
print(sentiment['score'])      # 0.95
```

### 4. Signal Generation

```python
from src.signals import ESGSignalGenerator

generator = ESGSignalGenerator()
signal = generator.compute_signal(
    ticker='AAPL',
    date=datetime.now(),
    event_features={'confidence': 0.8},
    reaction_features={'intensity': -0.5, 'volume_ratio': 2.0}
)

print(signal['z_score'])       # Standardized signal
print(signal['quintile'])      # Rank (1-5)
```

### 5. Backtesting

```python
from src.backtest import BacktestEngine, PerformanceAnalyzer

engine = BacktestEngine(prices, initial_capital=1000000)
results = engine.run(signals, rebalance_freq='W')

analyzer = PerformanceAnalyzer(results)
metrics = analyzer.generate_tear_sheet()

print(metrics['returns']['sharpe_ratio'])
print(metrics['risk']['max_drawdown'])
```

## Troubleshooting Quick Fixes

### Problem: Module not found
```bash
pip install <module-name>
```

### Problem: No data found
```bash
# Check tickers are valid
python -c "import yfinance as yf; print(yf.Ticker('AAPL').info['shortName'])"
```

### Problem: SEC download fails
```bash
# Make sure email is set in config/config.yaml
grep "email:" config/config.yaml
```

### Problem: Out of memory
```yaml
# Edit config.yaml - reduce batch size
nlp:
  sentiment_analyzer:
    batch_size: 8  # Reduce from 32
```

## Performance Metrics Reference

### Return Metrics
- **Total Return**: Overall gain/loss
- **CAGR**: Compound annual growth rate
- **Sharpe Ratio**: Risk-adjusted return (>1 is good)
- **Sortino Ratio**: Like Sharpe but only downside risk

### Risk Metrics
- **Max Drawdown**: Largest peak-to-trough decline
- **VaR (95%)**: Value at Risk - expected worst 5% loss
- **CVaR (95%)**: Conditional VaR - average of worst 5%

### Trading Metrics
- **Turnover**: How often positions change
- **Win Rate**: % of profitable trades
- **Num Trades**: Total trades executed

## ESG Categories Reference

### Environmental (E)
- Positive: renewable energy, emissions reduction
- Negative: pollution, EPA violations, oil spills

### Social (S)
- Positive: diversity, employee benefits
- Negative: discrimination, data breaches, recalls

### Governance (G)
- Positive: board diversity, transparency
- Negative: fraud, insider trading, accounting scandals

## Command Line Arguments Reference

```bash
python main.py [OPTIONS]

Options:
  --config PATH          Config file (default: config/config.yaml)
  --tickers TICKER...    List of tickers (default: AAPL TSLA XOM JPM MSFT)
  --start-date DATE      Start date YYYY-MM-DD (default: 2023-01-01)
  --end-date DATE        End date YYYY-MM-DD (default: 2023-12-31)
  --mode MODE            Mode: full, data_only, backtest_only, demo

Examples:
  python main.py --mode demo
  python main.py --mode full --tickers AAPL MSFT
  python main.py --mode data_only --start-date 2022-01-01
```

## Jupyter Notebook Quick Start

```bash
pip install jupyter notebook
jupyter notebook
# Open: notebooks/01_quick_start.ipynb
```

## Output Locations

```
results/
├── figures/              # Generated plots
├── tear_sheets/          # Performance reports
└── factor_analysis/      # Alpha analysis results

logs/
└── esg_strategy.log      # Execution logs
```

## Important Files to Edit

1. **config/config.yaml** - Main configuration
2. **config/esg_keywords.json** - ESG keywords (add custom terms)
3. **main.py** - Main script (customize pipeline)

## Testing Checklist

- [ ] Run demo mode: `python main.py --mode demo`
- [ ] Check imports: `python -c "import src.data, src.nlp, src.signals, src.backtest"`
- [ ] Verify config: `python -c "import yaml; yaml.safe_load(open('config/config.yaml'))"`
- [ ] Test single module: `python -c "from src.nlp import ESGEventDetector; print('OK')"`

## Quick Tips

1. **Always start with demo mode** to verify installation
2. **Edit config.yaml** instead of code for customization
3. **Check logs/** folder for detailed execution logs
4. **Use --tickers with few stocks** initially to test faster
5. **Read PROJECT_SUMMARY.md** for comprehensive overview

## Getting Help

1. Check README.md Troubleshooting section
2. Read INSTALL.md for installation issues
3. Review PROJECT_PLAN.md for methodology
4. Check code comments in src/ modules

## Next Steps After Setup

1. ✅ Run demo mode successfully
2. 📝 Edit config/config.yaml with your email
3. 💾 Run with real data: `python main.py --mode full`
4. 📊 Analyze results in results/ folder
5. 🔧 Customize signal weights for optimization
6. 📈 Backtest on longer time periods
7. 🚀 Paper trade before live deployment

---

**Need More Detail?**
- README.md - Full documentation
- INSTALL.md - Detailed installation
- PROJECT_PLAN.md - Complete methodology
- PROJECT_SUMMARY.md - Project overview

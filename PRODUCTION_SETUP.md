# Production Test Guide: Real-World Backtest

Complete guide to running production backtests with real market data.

---

## Phase 1: Environment Verification

### 1.1 Verify Python Environment

```bash
# Ensure you're in the project directory
cd /Users/chuyuewang/Desktop/Finance/Personal\ Projects/ESG-Sentimental-Trading

# Activate virtual environment
source venv/bin/activate

# Verify Python version (should be 3.9+)
python --version
```

### 1.2 Install Required Dependencies

```bash
# Core dependencies (if not already installed)
pip install -r requirements.txt

# Essential for production (no API keys needed)
pip install yfinance pandas-datareader

# Optional: Transformer models for better sentiment analysis
pip install transformers torch
```

**Verify installations**:
```bash
python -c "import yfinance; import pandas; import numpy; print('✓ Core dependencies OK')"
```

---

## Phase 2: Configuration

### 2.1 Twitter API Setup (Optional but Recommended)

**Option A: Use Mock Data (Easier, No API Keys)**
- Already configured by default
- Good for initial testing
- Limited realism

**Option B: Real Twitter Data (Recommended for Production)**

1. **Get Twitter API Access**:
   - Go to https://developer.twitter.com/
   - Create a developer account (free tier available)
   - Create a new project/app
   - Generate Bearer Token

2. **Configure in `config/config.yaml`**:
   ```bash
   # Open config file
   nano config/config.yaml
   # or
   code config/config.yaml
   ```

3. **Update Twitter settings**:
   ```yaml
   data:
     twitter:
       use_mock: false  # Change from true to false
       bearer_token: "YOUR_ACTUAL_BEARER_TOKEN_HERE"
       esg_keywords:
         - "climate"
         - "sustainability"
         - "diversity"
         - "governance"
         - "ESG"
       days_before_event: 3
       days_after_event: 7
       max_tweets_per_ticker: 100
   ```

4. **Save and verify**:
   ```bash
   python -c "import yaml; print(yaml.safe_load(open('config/config.yaml'))['data']['twitter'])"
   ```

### 2.2 Verify Data Access

```bash
# Test Yahoo Finance access
python -c "import yfinance as yf; print(yf.download('AAPL', start='2024-01-01', end='2024-01-10').head())"

# If you configured Twitter API, test it:
python -c "from src.data import TwitterFetcher; t = TwitterFetcher(bearer_token='YOUR_TOKEN', use_mock=False); print('Twitter API OK')"
```

---

## Phase 3: Run Production Backtest

### 3.1 Basic Production Run (ESG-Sensitive Universe)

**Recommended for first production test**:

```bash
python run_production.py \
    --universe esg_nasdaq100 \
    --esg-sensitivity HIGH \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --save-data
```

**Parameters Explained**:
- `--universe esg_nasdaq100`: Use 47 ESG-sensitive NASDAQ-100 stocks
- `--esg-sensitivity HIGH`: Only stocks with "HIGH" or "VERY HIGH" ESG sensitivity
- `--start-date`: Beginning of backtest period
- `--end-date`: End of backtest period (use yesterday's date for most recent)
- `--save-data`: Save intermediate results to disk for analysis

**Expected Runtime**: 30-60 minutes (depending on date range)

### 3.2 Advanced Options

**Shorter Test Period (Faster)**:
```bash
python run_production.py \
    --universe esg_nasdaq100 \
    --esg-sensitivity HIGH \
    --start-date 2024-09-01 \
    --end-date 2024-12-31 \
    --max-tickers 20 \
    --save-data
```

**Full NASDAQ-100 Universe**:
```bash
python run_production.py \
    --universe nasdaq100 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --save-data
```

**Custom Stock List**:
```bash
python run_production.py \
    --universe custom \
    --tickers TSLA AAPL MSFT AMZN GOOGL META SBUX NKE \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --save-data
```

**Conservative Risk Parameters**:
```bash
python run_production.py \
    --universe esg_nasdaq100 \
    --esg-sensitivity HIGH \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --save-data
```

Then edit `config/config.yaml` before running:
```yaml
backtest:
  enable_risk_management: true
  initial_capital: 1000000
  commission_pct: 0.001  # 10 bps
  slippage_bps: 5
  target_volatility: 0.10  # Conservative 10%
  max_drawdown_threshold: 0.10  # Conservative 10%

portfolio:
  strategy_type: "long_short"
  max_position_size: 0.05  # Conservative 5%
  min_positions: 15
  rebalance_frequency: "W"  # Weekly
  holding_period: 10
```

---

## Phase 4: Understanding Output

### 4.1 Real-Time Progress

You'll see output like:
```
============================================================
ESG EVENT-DRIVEN ALPHA STRATEGY - PRODUCTION RUN
============================================================
Universe: ESG_NASDAQ100
Date Range: 2024-01-01 to 2024-12-31
============================================================

>>> STEP 1: FETCHING STOCK UNIVERSE
Using ESG-SENSITIVE NASDAQ-100 (sensitivity: HIGH)
Universe: 47 tickers
Sample: ['TSLA', 'AMZN', 'SBUX', 'AAPL', 'MSFT', ...]

>>> STEP 2: DOWNLOADING SEC FILINGS
Downloading filings for TSLA (1/47)...
Downloading filings for AMZN (2/47)...
[...]
Downloaded 156 SEC filings

>>> STEP 3: FETCHING PRICE DATA
Fetched price data: 12,874 rows

>>> STEP 4: LOADING FAMA-FRENCH FACTORS
Loaded 252 periods of factor data

>>> STEP 5: EVENT DETECTION & TWITTER SENTIMENT ANALYSIS
Processing filing 1/156: TSLA...
  ✓ ESG Event detected: E (confidence: 0.85)
  Fetching Twitter data around 2024-03-15...
  Tweets: 87, Intensity: 0.623, Volume: 3.2x
[...]
Detected 45 ESG events with Twitter reactions

>>> STEP 6: SIGNAL GENERATION
Generated 45 trading signals
Quintile distribution: {1: 9, 2: 9, 3: 9, 4: 9, 5: 9}

>>> STEP 7: PORTFOLIO CONSTRUCTION
Portfolio: 12 long, 13 short positions
Net exposure: -0.05%, Gross exposure: 195.00%

>>> STEP 8: BACKTESTING
Backtest complete!
Final value: $1,285,432.18
Total return: 28.54%

>>> STEP 9: PERFORMANCE ANALYSIS
[Performance tear sheet displayed]

>>> STEP 10: FACTOR ANALYSIS
Annualized Alpha: 8.23%
T-Statistic: 2.34
P-Value: 0.0196
✓ SIGNIFICANT ALPHA (p < 0.05)
```

### 4.2 Expected Performance Metrics (Production)

**Good Performance**:
```
Total Return:       15-30%
Sharpe Ratio:       1.2-2.5
Sortino Ratio:      1.8-3.5
Max Drawdown:       -10% to -20%
Win Rate:           50-60%
Positions:          15-25
Alpha (Fama-French): 5-10% (p < 0.05)
```

**Acceptable Performance**:
```
Total Return:       10-15%
Sharpe Ratio:       0.8-1.2
Max Drawdown:       -15% to -25%
Win Rate:           45-55%
```

**Concerning Signs**:
```
Total Return:       < 5%
Sharpe Ratio:       < 0.5
Win Rate:           < 40% or > 70%
Max Drawdown:       > -30%
Alpha p-value:      > 0.10 (not significant)
```

### 4.3 Saved Output Files

With `--save-data`, files are saved to:

```
data/
├── universe_esg_nasdaq100_2024-01-01.csv       # Stock universe
├── filings_2024-01-01_to_2024-12-31.pkl        # SEC filings
├── prices_2024-01-01_to_2024-12-31.pkl         # Price data
├── events_2024-01-01_to_2024-12-31.pkl         # Detected ESG events
├── signals_2024-01-01_to_2024-12-31.csv        # Trading signals
└── portfolio_2024-01-01_to_2024-12-31.csv      # Portfolio positions

results/
├── tear_sheets/
│   └── tearsheet_2024-01-01_to_2024-12-31.txt  # Performance report
└── factor_analysis/
    └── factors_2024-01-01_to_2024-12-31.pkl    # Factor attribution
```

---

## Phase 5: Analysis and Validation

### 5.1 Review Performance Tear Sheet

```bash
# View saved tear sheet
cat results/tear_sheets/tearsheet_2024-01-01_to_2024-12-31.txt
```

### 5.2 Analyze Signals

```bash
# Load and analyze signals
python << 'PYTHON_EOF'
import pandas as pd

signals = pd.read_csv('data/signals_2024-01-01_to_2024-12-31.csv')

print("Signal Summary:")
print(f"Total signals: {len(signals)}")
print(f"\nQuintile distribution:")
print(signals['quintile'].value_counts().sort_index())
print(f"\nEvent categories:")
print(signals['event_category'].value_counts())
print(f"\nTop 10 signals:")
print(signals.nlargest(10, 'raw_score')[['ticker', 'date', 'raw_score', 'quintile']])
PYTHON_EOF
```

### 5.3 Validate Results

```bash
# Run diagnostic checks
python diagnostic_main_strategy.py
```

**Check for**:
- ✓ Sharpe ratio in reasonable range (0.8-2.5)
- ✓ Sortino/Sharpe ratio < 3.0
- ✓ Win rate 40-70%
- ✓ Max drawdown < -30%
- ✓ No trades with impossible returns (> 100% in one day)

---

## Phase 6: Troubleshooting

### 6.1 Common Issues

**Issue 1: No ESG events detected**
```
Detected 0 ESG events with Twitter reactions
```

**Solution**:
- Try longer date range (more events)
- Lower event detection threshold in `src/nlp/event_detector.py`
- Use broader universe (full NASDAQ-100)
- Check SEC filing availability for your date range

**Issue 2: Twitter API errors**
```
Twitter API 401 Unauthorized
```

**Solution**:
```bash
# Verify bearer token
python -c "import yaml; config = yaml.safe_load(open('config/config.yaml')); print(config['data']['twitter']['bearer_token'])"

# Switch to mock mode if needed
# Edit config/config.yaml: use_mock: true
```

**Issue 3: Insufficient positions**
```
Only 3 positions - risk management requires 5+
```

**Solution**:
- Use longer date range (more events)
- Lower `min_positions` in config.yaml
- Use broader universe (more stocks)

**Issue 4: High volatility (> 25%)**

**Solution**:
- Increase `min_positions` (more diversification)
- Lower `max_position_size` (smaller positions)
- Enable volatility targeting in config

### 6.2 Logging and Debugging

```bash
# Enable detailed logging
# Edit config/config.yaml:
# logging:
#   level: DEBUG

# Check logs
tail -f logs/strategy.log
```

---

## Phase 7: Next Steps for Live Trading

### 7.1 Paper Trading (Recommended: 1-3 months)

1. **Set up paper trading account** (e.g., Interactive Brokers, TD Ameritrade)
2. **Run strategy weekly**:
   ```bash
   # Every Monday morning
   python run_production.py \
       --universe esg_nasdaq100 \
       --esg-sensitivity HIGH \
       --start-date $(date -v-7d +%Y-%m-%d) \
       --end-date $(date +%Y-%m-%d)
   ```
3. **Manually execute trades** in paper account
4. **Track performance** vs backtest predictions

### 7.2 Go Live Checklist

**Before going live**:
- [ ] Paper trading shows consistent results (>3 months)
- [ ] Sharpe ratio > 1.0 in paper trading
- [ ] Max drawdown stayed within limits
- [ ] You understand why each signal was generated
- [ ] Risk management parameters tested and validated
- [ ] Twitter API stable (if using real data)
- [ ] Comfortable with position sizing

**Start Small**:
- Begin with $10,000-$50,000 (2-5% of intended capital)
- Scale up gradually as confidence builds
- Monitor for 1 month before increasing allocation

### 7.3 Production Monitoring

**Daily**:
```bash
# Check for new signals
python run_production.py \
    --start-date $(date -v-1d +%Y-%m-%d) \
    --end-date $(date +%Y-%m-%d)
```

**Weekly**:
- Review performance metrics
- Check if max drawdown threshold breached
- Verify risk management working correctly

**Monthly**:
- Full backtest to validate strategy
- Retrain ML models if using
- Review vs benchmark (SPY)

---

## Quick Reference: Common Commands

```bash
# Basic production run (2024 full year)
python run_production.py --universe esg_nasdaq100 --esg-sensitivity HIGH --start-date 2024-01-01 --end-date 2024-12-31 --save-data

# Recent 3 months (faster)
python run_production.py --universe esg_nasdaq100 --esg-sensitivity HIGH --start-date 2024-09-01 --end-date 2024-12-31 --save-data

# Custom stocks
python run_production.py --universe custom --tickers TSLA AAPL MSFT --start-date 2024-01-01 --end-date 2024-12-31 --save-data

# View saved results
cat results/tear_sheets/tearsheet_*.txt

# Analyze signals
python -c "import pandas as pd; print(pd.read_csv('data/signals_*.csv').describe())"
```

---

**Last Updated**: November 10, 2025
**Status**: Production-Ready

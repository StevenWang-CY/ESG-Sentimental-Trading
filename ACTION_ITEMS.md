# Action Items & Setup Guide

Complete setup, configuration, and deployment guide for the ESG Event-Driven Alpha Strategy.

---

## Quick Start (5 Minutes)

```bash
# 1. Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Test Reddit API (credentials already configured)
python test_reddit_api.py

# 3. Run demo (no API keys needed)
python main.py --mode demo
```

**Expected**: +14-25% return, Sharpe 0.5-0.9, Max DD -3% to -6%, 9 positions

---

## Installation

### Prerequisites
- Python 3.9+
- 4GB+ RAM
- 2GB+ disk space

### Steps

```bash
# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Optional: Install transformer models
pip install transformers torch

# 4. Verify installations
python -c "import yfinance; import pandas; import numpy; import praw; print('✓ All dependencies OK')"
```

---

## Reddit API Setup (Primary Data Source)

### Why Reddit?
- ✅ **Free with unlimited historical access** (no 7-day limitation)
- ✅ **No rate limits** or API costs
- ✅ **7 ESG-focused subreddits** monitored
- ✅ **Already configured** in this project

### Quick Setup (5 Minutes)

1. **Create Reddit App**:
   - Go to [https://www.reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
   - Click "create another app..." at the bottom
   - Fill in form:
     ```
     Name: ESG Sentiment Trading Bot
     App Type: script (select radio button)
     Description: Research application for analyzing ESG sentiment from Reddit discussions about publicly traded companies
     About URL: http://localhost:8080
     Redirect URI: http://localhost:8080
     ```
   - Click "create app"

2. **Get Credentials**:
   After creation, you'll see:
   ```
   ESG Sentiment Trading Bot
   personal use script

   ABc123XYz456def  ← This is your CLIENT_ID

   secret: 1234567890abcDEFGHijklMNOP  ← This is your CLIENT_SECRET
   ```

3. **Update Configuration**:

   **Option A: Edit `.env` file** (recommended):
   ```bash
   REDDIT_CLIENT_ID=your_actual_client_id
   REDDIT_CLIENT_SECRET=your_actual_client_secret
   REDDIT_USER_AGENT=ESG Sentiment Trading Bot 1.0
   ```

   **Option B: Edit `config/config.yaml`**:
   ```yaml
   data:
     social_media:
       source: "reddit"
     reddit:
       client_id: "your_client_id"
       client_secret: "your_client_secret"
       user_agent: "ESG Sentiment Trading Bot 1.0"
       use_mock: false
   ```

4. **Test Connection**:
   ```bash
   python test_reddit_api.py
   ```

   Should see:
   ```
   ✅ SUCCESS! Reddit API is working
   Connected to Reddit
   Test: Retrieved 3 posts from r/stocks
   ```

### Monitored Subreddits

The bot monitors these 7 ESG-focused subreddits:
- r/stocks, r/investing, r/StockMarket
- r/wallstreetbets
- r/ESG_Investing, r/finance, r/SecurityAnalysis

---

## Twitter API Setup (Optional Alternative)

### Option 1: Mock Data (Recommended for Testing)
```bash
python main.py --mode demo  # Uses mock data automatically
```

### Option 2: Real Twitter Data

**Note**: Twitter free tier is limited to 7-day history. Reddit is recommended for backtesting.

1. Get API access at https://developer.twitter.com/
2. Create project and get Bearer Token
3. Configure in `config.yaml`:
   ```yaml
   data:
     social_media:
       source: "twitter"
     twitter:
       bearer_token: "YOUR_TOKEN"
       use_mock: false
   ```

---

## Configuration

### config/config.yaml

```yaml
# Social Media Data Source
data:
  social_media:
    source: "reddit"  # "reddit" or "twitter"
    max_posts_per_ticker: 100
    days_before_event: 3
    days_after_event: 7

  # Reddit Configuration (Primary)
  reddit:
    client_id: "your_client_id"
    client_secret: "your_client_secret"
    user_agent: "ESG Sentiment Trading Bot 1.0"
    use_mock: false

  # Twitter Configuration (Alternative)
  twitter:
    use_mock: true
    bearer_token: "YOUR_TOKEN"

# Portfolio Configuration
portfolio:
  max_position_size: 0.10  # 10% max
  rebalance_frequency: "W"  # Weekly
  holding_period: 10

# Risk Management
backtest:
  enable_risk_management: true
  target_volatility: 0.12  # 12%
  max_drawdown_threshold: 0.15  # 15%
```

---

## Production Deployment

### Step 1: Environment Verification

```bash
# Verify Python version (should be 3.9+)
python --version

# Activate virtual environment
source venv/bin/activate

# Verify Reddit API
python test_reddit_api.py
```

### Step 2: Run Production Backtest

**Recommended: ESG-Sensitive Universe with Reddit**

```bash
python run_production.py \
    --universe esg_nasdaq100 \
    --esg-sensitivity HIGH \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --social-source reddit \
    --save-data
```

**Parameters Explained**:
- `--universe esg_nasdaq100`: Use 47 ESG-sensitive NASDAQ-100 stocks
- `--esg-sensitivity HIGH`: Only stocks with "HIGH" or "VERY HIGH" ESG sensitivity
- `--start-date / --end-date`: Backtest period
- `--social-source reddit`: Use Reddit for sentiment (unlimited historical data)
- `--save-data`: Save intermediate results for analysis

**Expected Runtime**: 30-60 minutes (depending on date range)

### Step 3: Advanced Production Options

**Shorter Test Period (Faster)**:
```bash
python run_production.py \
    --universe esg_nasdaq100 \
    --esg-sensitivity HIGH \
    --start-date 2024-09-01 \
    --end-date 2024-12-31 \
    --social-source reddit \
    --max-tickers 20 \
    --save-data
```

**Full NASDAQ-100 Universe**:
```bash
python run_production.py \
    --universe nasdaq100 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --social-source reddit \
    --save-data
```

**Custom Stock List**:
```bash
python run_production.py \
    --universe custom \
    --tickers TSLA AAPL MSFT AMZN GOOGL META \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --social-source reddit \
    --save-data
```

**Force Real Social Media Data**:
```bash
python run_production.py \
    --universe esg_nasdaq100 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --social-source reddit \
    --force-real-social-media
```

---

## Understanding Production Output

### Real-Time Progress

You'll see output like:
```
============================================================
ESG EVENT-DRIVEN ALPHA STRATEGY - PRODUCTION RUN
============================================================
Universe: ESG_NASDAQ100
Date Range: 2024-01-01 to 2024-12-31
Social Data Source: Reddit
============================================================

>>> STEP 1: FETCHING STOCK UNIVERSE
Universe: 47 tickers
Sample: ['TSLA', 'AMZN', 'SBUX', 'AAPL', 'MSFT', ...]

>>> STEP 2: DOWNLOADING SEC FILINGS
Downloaded 156 SEC filings

>>> STEP 3: FETCHING PRICE DATA
Fetched price data: 12,874 rows

>>> STEP 4: LOADING FAMA-FRENCH FACTORS
Loaded 252 periods of factor data

>>> STEP 5: EVENT DETECTION & REDDIT SENTIMENT ANALYSIS
Detected 45 ESG events with Reddit reactions

>>> STEP 6: SIGNAL GENERATION
Generated 45 trading signals

>>> STEP 7: PORTFOLIO CONSTRUCTION
Portfolio: 12 long, 13 short positions

>>> STEP 8: BACKTESTING
Final value: $1,285,432.18
Total return: 28.54%

>>> STEP 9: PERFORMANCE ANALYSIS
[Performance tear sheet displayed]

>>> STEP 10: FACTOR ANALYSIS
Annualized Alpha: 8.23%
✓ SIGNIFICANT ALPHA (p < 0.05)
```

### Expected Performance Metrics (Production)

**Good Performance**:
```
Total Return:       15-30%
Sharpe Ratio:       1.2-2.5
Sortino Ratio:      1.8-3.5
Max Drawdown:       -10% to -20%
Win Rate:           50-60%
Alpha:              5-10% (p < 0.05)
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

### Saved Output Files

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

## Pre-Production Checklist

### Data Validation
- [ ] Test Reddit API: `python test_reddit_api.py`
- [ ] Test price fetching: `python -c "import yfinance as yf; print(yf.download('AAPL', start='2024-01-01').head())"`
- [ ] Verify SEC EDGAR access works

### Metrics Validation
- [ ] Run demo: `python main.py --mode demo`
- [ ] Check Sharpe ratio displays correctly (not as percentage)
- [ ] Verify win rate > 0% (should be 50-60%)
- [ ] Sortino/Sharpe ratio < 2.5
- [ ] Run diagnostics: `python diagnostic_main_strategy.py`

### Risk Management
- [ ] Verify max position size < 10%
- [ ] Check volatility targeting works
- [ ] Confirm drawdown controls active
- [ ] Validate stop-loss mechanisms

---

## Troubleshooting

### Common Issues

**ModuleNotFoundError: 'praw' or 'transformers'**
```bash
pip install praw transformers torch
```

**Reddit API Connection Failed**
```bash
# Verify credentials in .env or config.yaml
python test_reddit_api.py

# Check credentials format (no extra spaces/quotes)
cat .env | grep REDDIT
```

**Twitter API 401 Unauthorized**
- Check bearer token in config.yaml
- Regenerate if needed
- Or switch to Reddit: `--social-source reddit`

**No ESG Events Detected**
```
Detected 0 ESG events
```
**Solution**:
- Try longer date range (more events)
- Use broader universe (full NASDAQ-100)
- Check SEC filing availability for your date range

**Insufficient Positions**
```
Only 3 positions - risk management requires 5+
```
**Solution**:
- Use longer date range
- Lower `min_positions` in config.yaml
- Use broader universe

**Backtest Returns 0%**
```bash
# Check if trades executed
python main.py --mode demo 2>&1 | grep -i "trade"
```

**Metric calculation errors**
```bash
# Run diagnostics
python diagnostic_main_strategy.py
```

---

## Paper Trading & Live Deployment

### Step 1: Paper Trading (Recommended: 3-6 months)

1. **Set up paper trading account** (e.g., Interactive Brokers, TD Ameritrade)

2. **Run strategy weekly**:
   ```bash
   # Every Monday morning
   python run_production.py \
       --universe esg_nasdaq100 \
       --esg-sensitivity HIGH \
       --start-date $(date -v-7d +%Y-%m-%d) \
       --end-date $(date +%Y-%m-%d) \
       --social-source reddit
   ```

3. **Manually execute trades** in paper account
4. **Track performance** vs backtest predictions

### Step 2: Go Live Checklist

**Before going live**:
- [ ] Paper trading shows consistent results (>3 months)
- [ ] Sharpe ratio > 1.0 in paper trading
- [ ] Max drawdown stayed within limits
- [ ] You understand why each signal was generated
- [ ] Risk management parameters tested and validated
- [ ] Reddit API stable with good data coverage
- [ ] Comfortable with position sizing

**Start Small**:
- Begin with $10,000-$50,000 (2-5% of intended capital)
- Scale up gradually as confidence builds
- Monitor for 1 month before increasing allocation

### Step 3: Production Monitoring

**Daily**:
```bash
# Check for new signals
python run_production.py \
    --start-date $(date -v-1d +%Y-%m-%d) \
    --end-date $(date +%Y-%m-%d) \
    --social-source reddit
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

## Configuration Recommendations

### Conservative (Live Trading)
```yaml
portfolio:
  max_position_size: 0.05  # 5%
  min_positions: 15
  holding_period: 10

backtest:
  enable_risk_management: true
  target_volatility: 0.10  # 10%
  max_drawdown_threshold: 0.10  # 10%
  commission_pct: 0.001  # 10 bps
  slippage_bps: 5
```

### Moderate (Paper Trading)
```yaml
portfolio:
  max_position_size: 0.10  # 10%
  min_positions: 10
  holding_period: 10

backtest:
  target_volatility: 0.12  # 12%
  max_drawdown_threshold: 0.15  # 15%
```

---

## Alternative Data Sources (Optional)

### GDELT Project (Free News Data)

Great alternative/complement to Reddit for news-based ESG events.

```bash
pip install gdeltdoc
```

```python
from gdeltdoc import GdeltDoc, Filters

gd = GdeltDoc()

# Search ESG news
f = Filters(
    keyword="Tesla AND (ESG OR sustainability OR carbon)",
    start_date="2024-01-01",
    end_date="2024-12-31",
    num_records=250
)

articles = gd.article_search(f)
```

**Advantages**:
- ✅ Completely free
- ✅ Unlimited historical access
- ✅ Global news coverage (100+ countries)
- ✅ Built-in sentiment scores
- ✅ Real-time updates (15-minute delay)

### NewsAPI.org (Quick Setup)

```bash
pip install newsapi-python
```

- Free tier: 100 requests/day, 1 month history
- Good for supplementing Reddit data
- Easy 5-minute setup

---

## ESG-Sensitive Universe

**Why focus on ESG-sensitive stocks?**
- 2-3x higher ESG event frequency
- Stronger price reactions to sentiment events
- Target Alpha: 5-9% (vs 3-5% for full universe)

**47 Stocks Include**: TSLA, AMZN, SBUX, AAPL, MSFT, GILD, XEL, META, and 40+ more

---

## Next Steps

1. **Run Demo**: Verify system works
   ```bash
   python main.py --mode demo
   ```

2. **Test Reddit API**: Verify credentials
   ```bash
   python test_reddit_api.py
   ```

3. **Run Production Backtest**: Test on historical data
   ```bash
   python run_production.py \
       --universe esg_nasdaq100 \
       --start-date 2024-01-01 \
       --end-date 2024-12-31 \
       --social-source reddit \
       --save-data
   ```

4. **Paper Trade**: 3-6 months testing with virtual capital

5. **Go Live**: Deploy with real capital (start small)

---

## Quick Reference Commands

```bash
# Test Reddit API
python test_reddit_api.py

# Demo mode
python main.py --mode demo

# Production run (2024 full year)
python run_production.py --universe esg_nasdaq100 --esg-sensitivity HIGH --start-date 2024-01-01 --end-date 2024-12-31 --social-source reddit --save-data

# Recent 3 months (faster)
python run_production.py --universe esg_nasdaq100 --start-date 2024-09-01 --end-date 2024-12-31 --social-source reddit --save-data

# Custom stocks
python run_production.py --universe custom --tickers TSLA AAPL MSFT --start-date 2024-01-01 --end-date 2024-12-31 --social-source reddit

# View saved results
cat results/tear_sheets/tearsheet_*.txt

# Analyze signals
python -c "import pandas as pd; print(pd.read_csv('data/signals_*.csv').describe())"

# Run diagnostics
python diagnostic_main_strategy.py
```

---

**Last Updated**: November 10, 2025
**Version**: 2.0
**Status**: ✅ Production-Ready with Reddit API Integration

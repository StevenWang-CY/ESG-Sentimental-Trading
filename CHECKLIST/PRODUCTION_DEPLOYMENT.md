# Production Deployment Guide

Complete guide to deploy the ESG Event-Driven Alpha Strategy on real NASDAQ-100 stocks with real Twitter data.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Twitter API Setup](#twitter-api-setup)
3. [Environment Setup](#environment-setup)
4. [Configuration](#configuration)
5. [Running the Strategy](#running-the-strategy)
6. [Data Requirements](#data-requirements)
7. [Cost Estimates](#cost-estimates)
8. [Timeline](#timeline)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Accounts

| Service | Purpose | Cost | Sign-up Time |
|---------|---------|------|--------------|
| **Twitter Developer** | Real-time sentiment data | $0-$100/mo | 1-3 days |
| **SEC EDGAR** | ESG event detection | Free | Instant |
| **GitHub** (optional) | Version control | Free | 5 minutes |

### Technical Requirements

```bash
# System requirements
- Python 3.8+
- 8GB RAM minimum (16GB recommended)
- 10GB disk space
- Internet connection (for API calls)
```

---

## Twitter API Setup

### Step 1: Apply for Twitter Developer Account

**Timeline: 1-3 business days**

1. **Go to**: https://developer.twitter.com/en/portal/dashboard
2. **Click**: "Sign up" or "Apply for a developer account"
3. **Choose**: "Academic" (if eligible) or "Hobbyist" > "Exploring the API"
4. **Fill out application**:
   - **Use case**: "Financial market sentiment analysis for academic research"
   - **Description**: "Analyzing Twitter sentiment around ESG (Environmental, Social, Governance) events disclosed in SEC filings to study market reactions"
   - **Will you make Twitter content available to government?**: No
   - **Will you display Twitter content off Twitter?**: No (analysis only)

5. **Submit** and wait for approval (usually 1-3 days)

### Step 2: Create Project and App

**After approval:**

1. **Create Project**:
   - Name: "ESG Sentiment Analysis"
   - Use case: "Building financial analysis tools"

2. **Create App**:
   - App name: "esg-sentiment-analyzer" (must be unique)
   - Description: "ESG event sentiment tracking"

3. **Get Bearer Token**:
   - Go to "Keys and tokens" tab
   - Click "Generate" under "Bearer Token"
   - **COPY AND SAVE THIS TOKEN IMMEDIATELY** (you can only see it once!)

### Step 3: Test Your Token

```bash
# Test Twitter API access
curl -X GET "https://api.twitter.com/2/tweets/search/recent?query=AAPL&max_results=10" \
-H "Authorization: Bearer YOUR_BEARER_TOKEN_HERE"
```

Expected response: JSON with tweets about Apple

---

## Environment Setup

### 1. Clone/Navigate to Project

```bash
cd "/Users/chuyuewang/Desktop/Finance/Personal Projects/ESG-Sentimental-Trading"
```

### 2. Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # On Mac/Linux
# OR
venv\Scripts\activate  # On Windows
```

### 3. Install Dependencies

```bash
# Install all required packages
pip install -r requirements.txt

# Verify installation
python -c "import tweepy; print('Tweepy installed:', tweepy.__version__)"
python -c "import yfinance; print('yfinance installed')"
```

---

## Configuration

### 1. Configure Twitter API

**Edit `config/config.yaml`:**

```yaml
data:
  # SEC Configuration
  sec:
    company_name: "YourName"  # Change this
    email: "your.email@example.com"  # REQUIRED: Use your real email

  # Twitter Configuration
  twitter:
    bearer_token: "PASTE_YOUR_BEARER_TOKEN_HERE"  # ← Add your token
    use_mock: false  # ← Change to false for real data
    max_tweets_per_ticker: 100
    days_before_event: 3
    days_after_event: 7
    esg_keywords:
      - "ESG"
      - "climate"
      - "sustainability"
      - "carbon emissions"
      - "diversity"
      - "governance"
      - "environmental"
      - "social responsibility"
```

### 2. Configure Strategy Parameters

```yaml
# Signal Generation
signals:
  weights:
    event_severity: 0.3
    intensity: 0.4
    volume: 0.2
    duration: 0.1

# Portfolio Construction
portfolio:
  strategy_type: "long_short"  # long_short, long_only, short_only
  method: "quintile"
  rebalance_frequency: "W"  # Weekly
  holding_period: 10  # Days

# Backtesting
backtest:
  initial_capital: 1000000.0  # $1M
  commission_pct: 0.0005  # 5 bps
  slippage_bps: 3
```

---

## Running the Strategy

### Test Run (Recommended First)

Test on a small sample before running on full NASDAQ-100:

```bash
# Test with 5 tickers for Sept 2024
python run_production.py \
    --start-date 2024-09-01 \
    --end-date 2024-09-30 \
    --universe custom \
    --tickers AAPL MSFT TSLA NVDA GOOGL \
    --save-data

# This will:
# 1. Download SEC filings for 5 stocks
# 2. Fetch real Twitter data
# 3. Generate signals
# 4. Run backtest
# 5. Output performance metrics
```

### Full NASDAQ-100 Run

```bash
# Run on full NASDAQ-100 for September 2024
python run_production.py \
    --start-date 2024-09-01 \
    --end-date 2024-09-30 \
    --universe nasdaq100 \
    --save-data

# Options:
# --max-tickers 50      # Limit to first 50 tickers
# --force-real-twitter  # Override mock mode
```

### Custom Date Ranges

```bash
# Q3 2024 (Jul-Sep)
python run_production.py \
    --start-date 2024-07-01 \
    --end-date 2024-09-30 \
    --universe nasdaq100

# Full year 2024
python run_production.py \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --universe nasdaq100
```

---

## Data Requirements

### SEC Filings

**Source**: SEC EDGAR (Free)
**Required**: Your email address (for API identification)

```yaml
# In config/config.yaml
sec:
  email: "your.email@example.com"  # REQUIRED by SEC
```

**Rate Limits**: 10 requests/second (automatically handled)

### Twitter Data

**Timeline**:
- **Free tier**: Last 7 days only
- **Basic tier** ($100/mo): Full archive access

**For September 2024 backtest**:
- If running in October 2024 → Need Basic tier (beyond 7 days)
- If running in real-time → Free tier works

### Price Data

**Source**: Yahoo Finance via `yfinance` (Free)
**Coverage**: Full historical data for most stocks
**Rate Limits**: ~2000 requests/hour (automatically handled)

---

## Cost Estimates

### Minimal Setup (Testing)

| Item | Cost | Notes |
|------|------|-------|
| Twitter Free Tier | $0 | Last 7 days only |
| SEC EDGAR | $0 | Free public data |
| Yahoo Finance | $0 | Free historical data |
| **Total** | **$0/month** | Testing only |

### Production Setup (Historical Backtesting)

| Item | Cost | Notes |
|------|------|-------|
| Twitter Basic | $100/mo | Full archive access |
| SEC EDGAR | $0 | Free |
| Yahoo Finance | $0 | Free |
| **Total** | **$100/month** | For historical data |

### API Call Estimates

For NASDAQ-100 (100 stocks) over 1 month:

```
SEC Filings: ~500 filings
├── 8-K filings: ~200
├── 10-K/Q filings: ~300
└── Cost: $0

Twitter API:
├── Events detected: ~50 (10% event rate)
├── Tweets per event: 100
├── Total tweets: ~5,000
└── Cost: Included in $100 Basic tier

Price Data:
├── 100 stocks × 30 days
├── Requests: ~150
└── Cost: $0
```

---

## Timeline

### Initial Setup (First Time Only)

| Task | Time | When |
|------|------|------|
| Twitter developer approval | 1-3 days | Before you can start |
| Environment setup | 30 min | One-time |
| Configuration | 15 min | One-time |
| Test run (5 stocks) | 10 min | Validate setup |

### Production Runs

| Scope | Tickers | Time Estimate |
|-------|---------|---------------|
| Test (5 stocks) | 5 | ~10 minutes |
| Small (20 stocks) | 20 | ~30 minutes |
| Medium (50 stocks) | 50 | ~1 hour |
| Full NASDAQ-100 | 100 | ~2-3 hours |

**Bottleneck**: SEC filing download and Twitter API calls

---

## Expected Output

### Console Output

```
============================================================
ESG EVENT-DRIVEN ALPHA STRATEGY - PRODUCTION RUN
============================================================
Universe: NASDAQ100
Date Range: 2024-09-01 to 2024-09-30
============================================================

>>> STEP 1: FETCHING STOCK UNIVERSE
Fetched 100 NASDAQ-100 tickers from Wikipedia

>>> STEP 2: DOWNLOADING SEC FILINGS
Downloading filings for AAPL (1/100)...
Downloaded 247 SEC filings

>>> STEP 3: FETCHING PRICE DATA
Fetched price data: 2,234 rows

>>> STEP 4: LOADING FAMA-FRENCH FACTORS
Loaded 21 periods of factor data

>>> STEP 5: EVENT DETECTION & TWITTER SENTIMENT ANALYSIS
✓ Using REAL Twitter API
Processing filing 1/247: AAPL...
  ✓ ESG Event detected: E (confidence: 0.87)
  Fetching Twitter data around 2024-09-15...
  Tweets: 87, Intensity: -0.456, Volume: 3.24x

Detected 23 ESG events with Twitter reactions

>>> STEP 6: SIGNAL GENERATION
Generated 23 trading signals
Quintile distribution: {1: 4, 2: 5, 3: 5, 4: 5, 5: 4}

>>> STEP 7: PORTFOLIO CONSTRUCTION
Portfolio: 4 long, 4 short positions
Net exposure: 0.12%
Gross exposure: 198.45%

>>> STEP 8: BACKTESTING
Backtest complete!
Final value: $1,045,234.56
Total return: 4.52%

>>> STEP 9: PERFORMANCE ANALYSIS

============================================================
PERFORMANCE TEAR SHEET
============================================================

RETURN METRICS:
------------------------------------------------------------
total_return                  :      4.52%
cagr                          :      3.12%
sharpe_ratio                  :      1.45
sortino_ratio                 :      2.01

RISK METRICS:
------------------------------------------------------------
max_drawdown                  :     -8.34%
var_95                        :     -1.23%

>>> STEP 10: FACTOR ANALYSIS

============================================================
FAMA-FRENCH FACTOR REGRESSION
============================================================
Annualized Alpha: 5.67%
T-Statistic: 2.34
P-Value: 0.0198

✓ SIGNIFICANT ALPHA (p < 0.05)

============================================================
PRODUCTION RUN COMPLETE
============================================================
```

### Saved Data Files

```
data/
├── universe_nasdaq100_2024-09-01.csv
├── filings_2024-09-01_to_2024-09-30.pkl
├── prices_2024-09-01_to_2024-09-30.pkl
├── events_2024-09-01_to_2024-09-30.pkl
└── signals_2024-09-01_to_2024-09-30.csv

results/
├── tear_sheets/
│   └── tearsheet_2024-09-01_to_2024-09-30.txt
└── factor_analysis/
    └── factors_2024-09-01_to_2024-09-30.pkl
```

---

## Troubleshooting

### Issue: "Twitter authentication failed"

**Error**: `401 Unauthorized`

**Solutions**:
1. Verify Bearer Token is correct (copy-paste carefully, no extra spaces)
2. Check token hasn't been revoked in developer portal
3. Ensure app has "Read" permissions
4. Test token with curl command above

### Issue: "No tweets found for ticker"

**Possible reasons**:
1. **Small-cap stock** → Few people tweet about it
2. **Beyond 7 days** (Free tier) → Upgrade to Basic ($100/mo)
3. **ESG keywords too restrictive** → Remove some keywords

**Solutions**:
```yaml
# Broaden search
twitter:
  esg_keywords:
    - "ESG"  # Keep only general term
```

### Issue: "Rate limit exceeded"

**Error**: `429 Too Many Requests`

**Solutions**:
- Twitter: Script automatically waits (built-in rate limiting)
- SEC: Script has 0.1s delays (10 req/sec limit)
- If persists: Add longer delays or run in batches

### Issue: "No events detected"

**Possible reasons**:
1. **Date range has few 8-K filings** → Expand date range
2. **Confidence threshold too high** → Lower it

**Solutions**:
```yaml
# In config/config.yaml
nlp:
  event_detector:
    confidence_threshold: 0.2  # Lower from 0.3
```

### Issue: "Memory error"

**Error**: `MemoryError` or `Killed`

**Solutions**:
```bash
# Process in batches
python run_production.py \
    --start-date 2024-09-01 \
    --end-date 2024-09-30 \
    --max-tickers 20  # Process 20 at a time
```

---

## Next Steps After Deployment

### 1. Analyze Results

```bash
# Review saved data
cd data/
head signals_2024-09-01_to_2024-09-30.csv

# Check tear sheet
cat results/tear_sheets/tearsheet_2024-09-01_to_2024-09-30.txt
```

### 2. Iterate on Strategy

- **Adjust signal weights** in `config/config.yaml`
- **Try different holding periods** (5, 10, 20 days)
- **Test different universes** (S&P 500, specific sectors)
- **Optimize ESG keywords** for better event detection

### 3. Walk-Forward Testing

```bash
# Train on Q1, test on Q2
python run_production.py --start-date 2024-01-01 --end-date 2024-03-31
python run_production.py --start-date 2024-04-01 --end-date 2024-06-30

# Compare performance
```

### 4. Live Trading Preparation

- **Paper trading**: Test with live data but no real money
- **Risk management**: Implement position sizing limits
- **Monitoring**: Set up alerts for large drawdowns
- **Rebalancing**: Automate weekly/monthly rebalancing

---

## Security Best Practices

### 1. Protect API Keys

```bash
# NEVER commit config.yaml with real tokens
echo "config/config.yaml" >> .gitignore

# Use environment variables instead
export TWITTER_BEARER_TOKEN="your_token_here"
```

### 2. Monitor Usage

- Check Twitter API usage: https://developer.twitter.com/en/portal/dashboard
- Review SEC download logs for rate limit compliance

### 3. Backup Data

```bash
# Regular backups
cp -r data/ backups/data_$(date +%Y%m%d)/
cp -r results/ backups/results_$(date +%Y%m%d)/
```

---

## Support

For issues:
1. Check [TWITTER_SETUP.md](TWITTER_SETUP.md) for Twitter-specific help
2. Review [QUICK_REFERENCE.md](QUICK_REFERENCE.md) for common commands
3. Check logs in `logs/esg_strategy.log`
4. Open GitHub issue with error logs

---

## Checklist

Before running production:

- [ ] Twitter Developer account approved
- [ ] Bearer Token obtained and tested
- [ ] `config/config.yaml` updated with real token
- [ ] `use_mock: false` in config
- [ ] SEC email address configured
- [ ] Virtual environment activated
- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] Test run completed successfully (5 stocks)
- [ ] Disk space available (10GB+)
- [ ] Expected runtime acceptable (2-3 hours for 100 stocks)

**Ready to run?**

```bash
python run_production.py \
    --start-date 2024-09-01 \
    --end-date 2024-09-30 \
    --universe nasdaq100 \
    --save-data
```

Good luck! 🚀

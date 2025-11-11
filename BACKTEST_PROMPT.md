# AI Coding Assistant Prompt: ESG Strategy Backtest (Q3 2025)

## Objective
Run a complete production backtest of the ESG Event-Driven Alpha Strategy for the period **July 1, 2025 to October 1, 2025** (Q3 2025) and generate comprehensive performance analytics.

---

## Context

You are working with a production-ready quantitative trading strategy that:
- Detects ESG events from SEC 8-K filings
- Analyzes social media sentiment (Reddit) around those events
- Generates trading signals based on sentiment reactions
- Constructs long-short market-neutral portfolios
- Manages risk with institutional-grade controls

**Project Structure:**
- Main runner: `run_production.py`
- Configuration: `config/config.yaml`
- Reddit API: Already configured and tested
- Data sources: SEC EDGAR (filings), Reddit (sentiment), Yahoo Finance (prices)

---

## Task Breakdown

### Step 1: Environment Verification (2 minutes)

First, verify the environment is ready:

```bash
# Navigate to project directory
cd "/Users/chuyuewang/Desktop/Finance/Personal Projects/ESG-Sentimental-Trading"

# Activate virtual environment
source venv/bin/activate

# Verify key dependencies
python -c "import pandas; import numpy; import yfinance; import praw; print('✓ All dependencies available')"

# Test Reddit API connection
python test_reddit_api.py
```

**Expected output:**
```
✅ SUCCESS! Reddit API is working
Connected to Reddit
Test: Retrieved 3 posts from r/stocks
```

**If Reddit API fails:**
- The system will automatically fall back to mock mode
- Backtest will still run but with simulated social media data
- This is acceptable for demonstration purposes

---

### Step 2: Run Production Backtest (30-45 minutes)

Execute the backtest with these exact parameters:

```bash
python run_production.py \
    --universe esg_nasdaq100 \
    --esg-sensitivity HIGH \
    --start-date 2025-07-01 \
    --end-date 2025-10-01 \
    --social-source reddit \
    --save-data
```

**Parameter Explanation:**
- `--universe esg_nasdaq100`: Use 47 ESG-sensitive NASDAQ-100 stocks (highest event frequency)
- `--esg-sensitivity HIGH`: Only stocks with "HIGH" or "VERY HIGH" ESG sensitivity
- `--start-date 2025-07-01`: Q3 2025 start (July 1, 2025)
- `--end-date 2025-10-01`: Q3 2025 end (October 1, 2025)
- `--social-source reddit`: Use Reddit for sentiment (unlimited historical access)
- `--save-data`: Save all intermediate results for analysis

**Expected Runtime:** 30-45 minutes depending on:
- Number of ESG events detected
- Reddit API response time
- Number of signals generated

---

### Step 3: Monitor Progress

You'll see real-time output like:

```
============================================================
ESG EVENT-DRIVEN ALPHA STRATEGY - PRODUCTION RUN
============================================================
Universe: ESG_NASDAQ100
Date Range: 2025-07-01 to 2025-10-01
Social Data Source: Reddit
============================================================

>>> STEP 1: FETCHING STOCK UNIVERSE
Using ESG-SENSITIVE NASDAQ-100 (sensitivity: HIGH)
Universe: 47 tickers
Sample: ['TSLA', 'AMZN', 'SBUX', 'AAPL', 'MSFT', ...]

>>> STEP 2: DOWNLOADING SEC FILINGS
Downloading filings for TSLA (1/47)...
[Progress bar]
Downloaded X SEC filings

>>> STEP 3: FETCHING PRICE DATA
Fetched price data: X rows

>>> STEP 4: LOADING FAMA-FRENCH FACTORS
Loaded X periods of factor data

>>> STEP 5: EVENT DETECTION & REDDIT SENTIMENT ANALYSIS
Processing filing 1/X: TSLA...
  ✓ ESG Event detected: E (confidence: 0.85)
  Fetching Reddit data around 2025-07-15...
  Posts: X, Intensity: X, Volume: X
[Progress continues]
Detected X ESG events with Reddit reactions

>>> STEP 6: SIGNAL GENERATION
Generated X trading signals
Quintile distribution: {1: X, 2: X, 3: X, 4: X, 5: X}

>>> STEP 7: PORTFOLIO CONSTRUCTION
Portfolio: X long, X short positions
Net exposure: ~0%, Gross exposure: ~200%

>>> STEP 8: BACKTESTING
[Backtest running with risk management]
Final value: $X,XXX,XXX.XX
Total return: X.XX%

>>> STEP 9: PERFORMANCE ANALYSIS
[Performance tear sheet displayed]

>>> STEP 10: FACTOR ANALYSIS
Annualized Alpha: X.XX%
T-Statistic: X.XX
P-Value: X.XXXX
```

---

### Step 4: Validate Results

After completion, run validation checks:

```bash
# Check for saved output files
ls -lh data/*2025-07-01*

# Expected files:
# - universe_esg_nasdaq100_2025-07-01.csv
# - filings_2025-07-01_to_2025-10-01.pkl
# - prices_2025-07-01_to_2025-10-01.pkl
# - events_2025-07-01_to_2025-10-01.pkl
# - signals_2025-07-01_to_2025-10-01.csv
# - portfolio_2025-07-01_to_2025-10-01.csv

# View performance tear sheet
cat results/tear_sheets/tearsheet_2025-07-01_to_2025-10-01.txt

# Run diagnostic validation
python diagnostic_main_strategy.py
```

---

### Step 5: Analyze Results

After the backtest completes, analyze the signals:

```bash
python << 'PYTHON_EOF'
import pandas as pd
import numpy as np

# Load results
signals = pd.read_csv('data/signals_2025-07-01_to_2025-10-01.csv')
portfolio = pd.read_csv('data/portfolio_2025-07-01_to_2025-10-01.csv')

print("=" * 60)
print("BACKTEST ANALYSIS - Q3 2025")
print("=" * 60)

print(f"\n1. SIGNAL SUMMARY:")
print(f"   Total signals generated: {len(signals)}")
print(f"\n   Quintile distribution:")
print(signals['quintile'].value_counts().sort_index())

print(f"\n   Event categories:")
print(signals['event_category'].value_counts())

print(f"\n2. TOP 10 SIGNALS (Strongest):")
print(signals.nlargest(10, 'raw_score')[['ticker', 'date', 'event_category', 'raw_score', 'quintile']])

print(f"\n3. BOTTOM 10 SIGNALS (Weakest):")
print(signals.nsmallest(10, 'raw_score')[['ticker', 'date', 'event_category', 'raw_score', 'quintile']])

print(f"\n4. PORTFOLIO POSITIONS:")
print(f"   Total positions: {len(portfolio)}")
if len(portfolio) > 0:
    print(f"   Long positions: {len(portfolio[portfolio['shares'] > 0])}")
    print(f"   Short positions: {len(portfolio[portfolio['shares'] < 0])}")
    print(f"\n   Sample positions:")
    print(portfolio.head(10)[['ticker', 'date', 'shares', 'price', 'value']])

print("\n" + "=" * 60)
PYTHON_EOF
```

---

## Expected Results

### Good Performance (Realistic for 3-month period):
```
RETURN METRICS:
total_return                  :     4-10%
cagr                          :     16-40% (annualized)
sharpe_ratio                  :     0.8-1.8
sortino_ratio                 :     1.2-2.5
calmar_ratio                  :     2-8

RISK METRICS:
max_drawdown                  :     -5% to -15%
annualized_volatility         :     15-25%
downside_deviation            :     8-18%

TRADING METRICS:
num_trades                    :     10-30 positions
win_rate                      :     45-65%
profit_factor                 :     1.3-2.5
avg_trade_return              :     2-8%
```

### Warning Signs (Investigate if you see):
```
❌ Total return < 0% (losing money)
❌ Sharpe ratio < 0.3 (poor risk-adjusted returns)
❌ Win rate < 30% or > 80% (suspicious)
❌ Max drawdown > -25% (excessive risk)
❌ num_trades < 3 (insufficient signals)
```

---

## Troubleshooting

### Issue 1: No ESG Events Detected
```
Detected 0 ESG events with Reddit reactions
```

**Solution:**
```bash
# Check if SEC filings were downloaded
ls -lh data/filings_2025-07-01*.pkl

# If no filings, SEC might be unavailable for future dates
# Fallback: Use a known period with data
python run_production.py \
    --universe esg_nasdaq100 \
    --start-date 2024-07-01 \
    --end-date 2024-10-01 \
    --social-source reddit \
    --save-data
```

### Issue 2: Reddit API Fails
```
Warning: Failed to initialize Reddit client
Falling back to mock data mode
```

**This is OK:** The system will use mock data. Backtest will still complete.

### Issue 3: Insufficient Positions
```
Only X positions - risk management requires 5+
```

**Solution:**
```bash
# Lower the ESG sensitivity to include more stocks
python run_production.py \
    --universe esg_nasdaq100 \
    --start-date 2025-07-01 \
    --end-date 2025-10-01 \
    --social-source reddit \
    --save-data
# (removes --esg-sensitivity HIGH)
```

### Issue 4: Date in Future / No Price Data
```
Error: No price data available for future dates
```

**Solution:**
```bash
# Use a known historical period
python run_production.py \
    --universe esg_nasdaq100 \
    --esg-sensitivity HIGH \
    --start-date 2024-07-01 \
    --end-date 2024-10-01 \
    --social-source reddit \
    --save-data
```

---

## Success Criteria

The backtest is successful if:

✅ **Execution completes without fatal errors**
✅ **At least 5 ESG events detected**
✅ **At least 5 trading signals generated**
✅ **At least 3 portfolio positions created**
✅ **Performance metrics calculated (Sharpe, Sortino, etc.)**
✅ **Output files saved to data/ and results/ directories**
✅ **Validation checks pass (no red flags)**

---

## Final Deliverables

After successful completion, you should have:

1. **Performance Tear Sheet** (text file)
   - Location: `results/tear_sheets/tearsheet_2025-07-01_to_2025-10-01.txt`
   - Contains: All metrics, risk analysis, factor attribution

2. **Trading Signals** (CSV file)
   - Location: `data/signals_2025-07-01_to_2025-10-01.csv`
   - Contains: All generated signals with scores and quintiles

3. **Portfolio Positions** (CSV file)
   - Location: `data/portfolio_2025-07-01_to_2025-10-01.csv`
   - Contains: All positions with entry/exit dates and P&L

4. **Intermediate Data Files**
   - SEC filings: `data/filings_2025-07-01_to_2025-10-01.pkl`
   - Price data: `data/prices_2025-07-01_to_2025-10-01.pkl`
   - ESG events: `data/events_2025-07-01_to_2025-10-01.pkl`

---

## Important Notes

1. **Date Consideration:**
   - The specified dates (July-October 2025) are in the future as of November 2025
   - If Yahoo Finance doesn't have future price data, the backtest will fail
   - **Fallback:** Use July-October 2024 instead (same Q3 period, one year back)

2. **Reddit API:**
   - Already configured with working credentials
   - Will search 7 ESG-focused subreddits
   - Falls back to mock mode if API fails (this is fine)

3. **Runtime:**
   - Expect 30-45 minutes for complete execution
   - SEC filing downloads take longest (10-15 min)
   - Reddit sentiment analysis takes 10-15 min
   - Backtesting and metrics calculation takes 5-10 min

4. **Data Storage:**
   - All results saved with `--save-data` flag
   - Files can be large (10-100 MB total)
   - Review with analysis script provided in Step 5

---

## Quick Copy-Paste Commands

```bash
# Activate environment
cd "/Users/chuyuewang/Desktop/Finance/Personal Projects/ESG-Sentimental-Trading"
source venv/bin/activate

# Test setup
python test_reddit_api.py

# Run backtest (try future dates first)
python run_production.py --universe esg_nasdaq100 --esg-sensitivity HIGH --start-date 2025-07-01 --end-date 2025-10-01 --social-source reddit --save-data

# If future dates fail, use 2024 Q3
python run_production.py --universe esg_nasdaq100 --esg-sensitivity HIGH --start-date 2024-07-01 --end-date 2024-10-01 --social-source reddit --save-data

# View results
cat results/tear_sheets/tearsheet_*.txt
python -c "import pandas as pd; df=pd.read_csv('data/signals_2024-07-01_to_2024-10-01.csv'); print(f'Signals: {len(df)}'); print(df.groupby('quintile').size())"

# Run validation
python diagnostic_main_strategy.py
```

---

## Summary

This prompt provides:
- ✅ Clear objective and context
- ✅ Step-by-step execution instructions
- ✅ Expected outputs and success criteria
- ✅ Troubleshooting for common issues
- ✅ Validation procedures
- ✅ Fallback options if issues arise
- ✅ Copy-paste commands for quick execution

Execute the commands in order, monitor progress, and analyze the results. The system is production-ready and should complete successfully with comprehensive performance analytics.

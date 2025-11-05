# Action Items & Deployment Checklist

Quick reference for key actions and production deployment steps.

---

## Quick Actions

### Test Immediately (No Setup)
```bash
source venv/bin/activate
python examples/enhanced_pipeline_example.py
```

### Get Twitter API Token
1. Visit https://developer.twitter.com/en/portal/dashboard
2. Create account and app (free)
3. Generate Bearer Token
4. Add to `.env`: `TWITTER_BEARER_TOKEN=AAAA...`

### Collect Real Data
```bash
python scripts/collect_data.py --start-date 2023-01-01 --end-date 2024-01-01
```

### Train Pipeline
```bash
python scripts/train_pipeline.py --data-dir data/processed --model-dir models/production
```

### Run Backtest
```bash
python scripts/backtest.py --model-dir models/production --test-start 2024-01-01
```

---

## Pre-Production Checklist

Before deploying to live trading:

### Data & Testing
- [ ] Collected 2-3 years of historical data
- [ ] Trained pipeline on historical data
- [ ] Backtest shows Sharpe ratio > 1.0
- [ ] Tested on out-of-sample period (2024 data)
- [ ] Win rate > 55%
- [ ] Max drawdown < 20%

### API & Configuration
- [ ] Twitter API Bearer Token working
- [ ] Tested API connection successfully
- [ ] `.env` file configured properly
- [ ] `config.yaml` settings reviewed
- [ ] Universe selection confirmed (esg_nasdaq100)

### Risk Management
- [ ] Max position size set (default: 10%)
- [ ] Max number of positions defined (default: 10)
- [ ] Stop-loss strategy defined
- [ ] Portfolio rebalancing frequency set
- [ ] Capital allocation decided

### Model Validation
- [ ] Feature importance reviewed
- [ ] Top features make sense (no data leakage)
- [ ] Word correlations trained on sufficient data
- [ ] Model performance stable across time periods
- [ ] No overfitting detected (train vs validation gap < 5%)

### Infrastructure
- [ ] Logging configured (`logs/` directory)
- [ ] Monitoring dashboard set up (optional)
- [ ] Alert system configured (optional)
- [ ] Backup strategy for models and data
- [ ] Retraining schedule planned (monthly recommended)

### Paper Trading
- [ ] Ran paper trading for 1 month minimum
- [ ] Signals match backtest expectations
- [ ] No execution issues
- [ ] Performance metrics tracked
- [ ] Comfortable with signal frequency

### Legal & Compliance
- [ ] Broker account set up (if auto-trading)
- [ ] Broker API configured and tested
- [ ] Understand trading costs and slippage
- [ ] Tax implications reviewed
- [ ] Compliance with regulations confirmed

---

## Production Deployment Steps

### Step 1: Final Configuration

```bash
# Edit .env
vim .env
```

Set:
```bash
PRODUCTION_MODE=true
DRY_RUN=false  # Remove for live trading
```

### Step 2: Deploy

```bash
python main.py \
  --mode production \
  --model models/production \
  --universe esg_nasdaq100 \
  --max-positions 10 \
  --max-position-size 0.05
```

### Step 3: Monitor

```bash
# View live logs
tail -f logs/esg_trading.log

# Check performance
python scripts/monitor_performance.py --live
```

### Step 4: Retraining Schedule

Set up monthly retraining:

```bash
# Add to crontab
crontab -e

# Add line:
0 0 1 * * cd /path/to/ESG-Sentimental-Trading && ./scripts/retrain_monthly.sh
```

---

## ESG-Sensitive Universe

### Current Universe (esg_nasdaq100)

**50-60 ESG-sensitive NASDAQ-100 stocks** most impacted by ESG events:

**Energy & Utilities** (Very High Sensitivity):
- XEL, CEG, EXC, AEP

**Consumer** (High Sensitivity):
- TSLA, AMZN, SBUX, NKE, LULU, ROST, ABNB, BKNG, COST, MAR, WBD

**Industrials** (High Sensitivity):
- HON, ADP, PCAR, ODFL, CTAS

**Technology** (Medium-High Sensitivity):
- AAPL, MSFT, GOOGL, META, TSLA, INTC, AMD, NVDA, QCOM

**Healthcare** (Medium-High Sensitivity):
- GILD, AMGN, VRTX, REGN, BIIB, MRNA, ILMN

**Financials** (Medium Sensitivity):
- PYPL, COIN

### Why These Stocks?

- **Higher event frequency**: 2-3x more ESG events than general stocks
- **Material impact**: ESG events significantly affect stock prices
- **Predictable reactions**: Market responses to ESG news are systematic
- **Large caps**: Sufficient liquidity for trading
- **Media coverage**: High Twitter/news coverage for sentiment analysis

---

## Monitoring & Maintenance

### Daily Checks
- Review generated signals
- Check Twitter API usage (stay under 500k/month)
- Monitor position sizes and portfolio exposure
- Check for errors in logs

### Weekly Reviews
- Performance metrics (return, Sharpe, drawdown)
- Signal quality (win rate, avg return per signal)
- Feature importance changes
- Market regime changes

### Monthly Actions
- Retrain pipeline with latest data
- Review model performance
- Update word correlations
- Analyze profitable vs. unprofitable trades
- Adjust parameters if needed

### Quarterly Reviews
- Comprehensive performance analysis
- Compare vs. benchmark (S&P 500, NASDAQ-100)
- Review ESG universe (add/remove stocks)
- Update ESG dictionaries if needed
- Consider strategy adjustments

---

## Performance Targets

### Minimum Viable Performance (Go/No-Go)

**Required before deploying**:
- Backtest Sharpe ratio > 1.0
- Win rate > 52%
- Max drawdown < 25%
- Positive return in out-of-sample test

### Target Performance (ESG Strategy)

Based on thesis + ESG characteristics:
- **Sharpe Ratio**: 1.2 - 1.8
- **Annual Return**: 10-18%
- **Annualized Alpha**: 5-9% (vs. benchmark)
- **Win Rate**: 55-62%
- **Max Drawdown**: < 20%
- **Monthly signals**: 10-20 per month

---

## Troubleshooting Production Issues

### Low Signal Frequency
- Lower event confidence threshold
- Expand universe to more stocks
- Adjust ESG keyword sensitivity

### Poor Signal Quality
- Retrain with more recent data
- Check Twitter API is returning data
- Verify word correlations are current
- Review feature importance

### High Drawdown
- Reduce position sizes
- Increase holding period
- Add market regime filter
- Tighten BUY/SELL thresholds

### API Rate Limits
- Reduce tweets per ticker
- Increase time between requests
- Cache more aggressively
- Consider upgrading Twitter API tier

---

## Emergency Procedures

### Halt Trading

```bash
# Stop production script
pkill -f "python main.py"

# Set dry run mode
vim .env  # PRODUCTION_MODE=false
```

### Model Issues Detected

1. Stop live trading immediately
2. Revert to previous model version
3. Investigate issue (data, features, bugs)
4. Retrain on extended data
5. Re-backtest before redeploying

### Data Issues

1. Check Twitter API connection
2. Verify SEC data downloads
3. Check price data freshness
4. Fall back to cached data if needed

---

## Key Contacts & Resources

### APIs
- **Twitter Developer Portal**: https://developer.twitter.com/en/portal/dashboard
- **SEC EDGAR**: https://www.sec.gov/edgar/searchedgar/companysearch.html

### Documentation
- **Technical Details**: THESIS_IMPROVEMENTS.md
- **Getting Started**: GETTING_STARTED.md
- **Project Overview**: README.md

### Models & Data
- **Trained Models**: `models/production/`
- **Historical Data**: `data/processed/`
- **Backtest Results**: `results/backtest/`

---

**Ready for deployment!** Follow the checklist above before going live. 🚀

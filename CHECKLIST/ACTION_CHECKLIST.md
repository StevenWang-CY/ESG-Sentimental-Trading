# Action Checklist - ESG Strategy Deployment

Quick checklist for deploying the strategy on real ESG-sensitive stocks.

## 🎯 Goal
Run the ESG Event-Driven Alpha Strategy on **ESG-sensitive NASDAQ-100 stocks** for **September 2024** using **real Twitter data**.

**Key Change**: Now focuses on ~50-60 ESG-sensitive companies (not all 100) for better performance.

**Why ESG-Sensitive Universe?**
- ✅ Higher event concentration (2-3x more ESG events)
- ✅ Stronger Twitter reactions (better sentiment signals)
- ✅ Companies where ESG actually matters (energy, consumer brands, pharma)
- ✅ Better alpha (5-9% vs 2-5% for full NASDAQ-100)

📖 **See [ESG_UNIVERSE_GUIDE.md](ESG_UNIVERSE_GUIDE.md) for detailed explanation**

---

## ✅ Phase 1: Pre-Deployment (Estimate: 1-3 days)

### Twitter API Setup (Cannot code this - requires manual action)

- [ ] **Day 1**: Apply for Twitter Developer Account
  - Go to: https://developer.twitter.com/
  - Click "Apply for developer account"
  - Choose use case: "Academic" or "Exploring the API"
  - Fill out application (15 minutes)
  - **Wait for approval** (1-3 business days typically)

- [ ] **After Approval**: Create App & Get Bearer Token
  - Create new project: "ESG Sentiment Analysis"
  - Create app: "esg-sentiment-analyzer"
  - Navigate to "Keys and tokens"
  - Click "Generate" under "Bearer Token"
  - **SAVE THE TOKEN IMMEDIATELY** (shown only once!)

- [ ] **Test Token**:
  ```bash
  curl -X GET "https://api.twitter.com/2/tweets/search/recent?query=AAPL&max_results=10" \
  -H "Authorization: Bearer YOUR_BEARER_TOKEN_HERE"
  ```
  - Should return JSON with tweets

---

## ✅ Phase 2: Environment Setup (Estimate: 30 minutes)

### Local Setup

- [ ] **Navigate to project**:
  ```bash
  cd "/Users/chuyuewang/Desktop/Finance/Personal Projects/ESG-Sentimental-Trading"
  ```

- [ ] **Activate virtual environment**:
  ```bash
  source venv/bin/activate
  ```

- [ ] **Install dependencies**:
  ```bash
  pip install -r requirements.txt
  ```

- [ ] **Verify tweepy installed**:
  ```bash
  python -c "import tweepy; print('✓ Tweepy installed')"
  ```

---

## ✅ Phase 3: Configuration (Estimate: 10 minutes)

### Update config/config.yaml

- [ ] **Open** `config/config.yaml` in editor

- [ ] **Update SEC email** (line 8):
  ```yaml
  sec:
    email: "your.actual.email@example.com"  # ← Put your real email
  ```

- [ ] **Add Twitter Bearer Token** (line 19):
  ```yaml
  twitter:
    bearer_token: "PASTE_YOUR_BEARER_TOKEN_HERE"  # ← Paste token from Twitter
  ```

- [ ] **Disable mock mode** (line 20):
  ```yaml
    use_mock: false  # ← Change from true to false
  ```

- [ ] **Save file**

---

## ✅ Phase 4: Test Run (Estimate: 10 minutes)

### Small Test Before Full Run

- [ ] **Test with 5 stocks**:
  ```bash
  python run_production.py \
      --start-date 2024-09-01 \
      --end-date 2024-09-30 \
      --universe custom \
      --tickers AAPL MSFT GOOGL TSLA NVDA \
      --save-data
  ```

- [ ] **Verify output**:
  - [ ] See "✓ Using REAL Twitter API" message
  - [ ] No authentication errors
  - [ ] Events detected (should be > 0)
  - [ ] Signals generated
  - [ ] Backtest completes
  - [ ] Results printed

- [ ] **Check saved data**:
  ```bash
  ls -lh data/
  # Should see: universe, filings, prices, events, signals files
  ```

---

## ✅ Phase 5: Production Run (Estimate: 1-2 hours)

### ESG-Sensitive Universe (RECOMMENDED)

- [ ] **Run with ESG-sensitive stocks (HIGH sensitivity)**:
  ```bash
  python run_production.py \
      --start-date 2024-09-01 \
      --end-date 2024-09-30 \
      --universe esg_nasdaq100 \
      --esg-sensitivity HIGH \
      --save-data
  ```

  **This is now the DEFAULT and RECOMMENDED approach!**
  - ~50-60 ESG-sensitive stocks
  - Better signal quality
  - Higher expected alpha

### Alternative: Full NASDAQ-100 (Not Recommended)

- [ ] **Optional: Run with all 100 stocks** (for comparison):
  ```bash
  python run_production.py \
      --start-date 2024-09-01 \
      --end-date 2024-09-30 \
      --universe nasdaq100 \
      --save-data
  ```

  **Note**: Full NASDAQ-100 expected to have lower performance due to including many non-ESG-sensitive stocks

- [ ] **Monitor progress** (in another terminal):
  ```bash
  tail -f logs/esg_strategy.log
  ```

- [ ] **Wait for completion** (2-3 hours)

---

## ✅ Phase 6: Review Results (Estimate: 30 minutes)

### Analyze Performance

- [ ] **Check tear sheet**:
  ```bash
  cat results/tear_sheets/tearsheet_2024-09-01_to_2024-09-30.txt
  ```

- [ ] **Review signals**:
  ```bash
  head -20 data/signals_2024-09-01_to_2024-09-30.csv
  ```

- [ ] **Key metrics to review**:
  - [ ] Total return
  - [ ] Sharpe ratio
  - [ ] Maximum drawdown
  - [ ] Alpha (from factor analysis)
  - [ ] Alpha p-value (< 0.05 = significant)

- [ ] **Number of events**:
  - Expected: 20-50 events for 100 stocks in 1 month
  - If too few (< 10): Lower confidence threshold in config
  - If too many (> 100): Raise confidence threshold

---

## 🚨 Common Issues & Solutions

### Issue: "Twitter authentication failed"
**Solution**:
1. Check Bearer Token is correct (no extra spaces)
2. Verify token in developer portal: https://developer.twitter.com/en/portal/dashboard
3. Regenerate token if necessary

### Issue: "No tweets found"
**Solution**:
1. **If date > 7 days ago**: Need Twitter Basic tier ($100/mo) for historical data
2. **If running real-time**: Should work with free tier
3. **Small cap stocks**: May have few tweets - this is normal

### Issue: "No events detected"
**Solution**:
1. Lower confidence threshold in `config/config.yaml`:
   ```yaml
   nlp:
     event_detector:
       confidence_threshold: 0.2  # Lower from 0.3
   ```
2. Expand date range

### Issue: "Rate limit exceeded"
**Solution**:
- Script has automatic rate limiting
- If persists: Run with `--max-tickers 50` to process fewer stocks

---

## 📊 What You Need to Provide (Beyond Code)

### 1. Twitter API Access (Manual - Cannot be automated)
- **Task**: Apply for developer account
- **Time**: 1-3 business days for approval
- **Cost**: Free tier OK for testing; Basic ($100/mo) for historical data
- **Action**: https://developer.twitter.com/

### 2. Date Range Decision
- **For September 2024**:
  - If running in October 2024+: Need Basic tier (beyond 7 days)
  - If running real-time: Free tier works

- **Alternative**: Use recent month within 7 days (Free tier)
  ```bash
  # Example: If today is Oct 10, 2024, use:
  --start-date 2024-10-03 --end-date 2024-10-10
  ```

### 3. Strategy Parameters (Optional - Can tune later)
- Signal weights (intensity, volume, duration)
- Holding period (currently 10 days)
- Rebalancing frequency (currently weekly)
- Confidence threshold for event detection

### 4. Universe Selection (UPDATED - ESG Focus)
- **ESG-Sensitive NASDAQ-100** (RECOMMENDED): ~50-60 stocks where ESG events matter
  - **HIGH sensitivity** (default): Energy, consumer brands, pharma (best performance)
  - **VERY HIGH**: Only most sensitive (~20-30 stocks)
  - **MEDIUM**: Broader coverage (~80 stocks)
- **Full NASDAQ-100**: All 100 stocks (lower performance, not recommended)
- **Custom list**: Specific ESG-sensitive tickers

**Why ESG-Sensitive?** See [ESG_UNIVERSE_GUIDE.md](ESG_UNIVERSE_GUIDE.md)

---

## 📅 Timeline Summary

| Phase | Time | Blockers |
|-------|------|----------|
| **Twitter API approval** | 1-3 days | Manual approval process |
| **Environment setup** | 30 min | None |
| **Configuration** | 10 min | Need Twitter token |
| **Test run (5 stocks)** | 10 min | None |
| **Full run (100 stocks)** | 2-3 hours | CPU/API limits |
| **Analysis** | 30 min | None |
| **Total** | **2-4 days** | Twitter approval |

---

## 🎯 Success Criteria

After completing all phases, you should have:

- [ ] ✅ Twitter API working (real tweets fetched)
- [ ] ✅ 20-50 ESG events detected
- [ ] ✅ Trading signals generated for detected events
- [ ] ✅ Portfolio constructed (long + short positions)
- [ ] ✅ Backtest completed successfully
- [ ] ✅ Performance metrics calculated
- [ ] ✅ Factor analysis showing alpha (ideally significant)
- [ ] ✅ All data saved to disk

**Expected outcome**:
- Sharpe ratio: 0.8 - 1.8
- Alpha: 3-8% annualized
- Some events will be profitable, some not (that's normal!)

---

## 📝 Next Steps After First Run

### Iteration & Optimization

1. **Analyze which events worked**:
   - Check `data/signals_*.csv` for signal scores
   - Compare with actual returns

2. **Tune parameters**:
   - Adjust signal weights if one feature dominates
   - Try different holding periods (5, 15, 20 days)
   - Experiment with rebalancing frequency

3. **Expand testing**:
   - Run on multiple months
   - Try different universes (S&P 500, sectors)
   - Walk-forward testing (train on Q1, test on Q2)

4. **Production considerations**:
   - Set up automated runs (cron job)
   - Implement real-time alerting
   - Add risk management (stop losses, position limits)

---

## 🆘 Need Help?

1. **Check logs**: `tail -f logs/esg_strategy.log`
2. **Review**: [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md) for detailed guide
3. **Twitter issues**: [TWITTER_SETUP.md](TWITTER_SETUP.md)
4. **GitHub issues**: Create issue with error logs

---

## ✨ Quick Commands Reference

```bash
# Test run (5 ESG-sensitive stocks)
python run_production.py --start-date 2024-09-01 --end-date 2024-09-30 --universe custom --tickers TSLA SBUX GILD AMZN AAPL --save-data

# RECOMMENDED: ESG-Sensitive NASDAQ-100 (HIGH sensitivity)
python run_production.py --start-date 2024-09-01 --end-date 2024-09-30 --universe esg_nasdaq100 --esg-sensitivity HIGH --save-data

# Conservative: Very high ESG sensitivity only
python run_production.py --start-date 2024-09-01 --end-date 2024-09-30 --universe esg_nasdaq100 --esg-sensitivity "VERY HIGH" --save-data

# Comprehensive: Medium ESG sensitivity
python run_production.py --start-date 2024-09-01 --end-date 2024-09-30 --universe esg_nasdaq100 --esg-sensitivity MEDIUM --save-data

# For comparison: Full NASDAQ-100 (not recommended)
python run_production.py --start-date 2024-09-01 --end-date 2024-09-30 --universe nasdaq100 --save-data

# Check results
cat results/tear_sheets/tearsheet_2024-09-01_to_2024-09-30.txt
```

---

**Ready to start?** Begin with Phase 1: Twitter API Setup! 🚀

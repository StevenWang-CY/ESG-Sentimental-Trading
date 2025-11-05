# Documentation Index

Quick navigation to all project documentation.

---

## 📚 Core Documentation (Read in Order)

### 1. [README.md](README.md) - **START HERE**
- Project overview
- What this strategy does
- Expected performance (+30-70% improvement)
- Recent thesis-based improvements

### 2. [GETTING_STARTED.md](GETTING_STARTED.md) - **HOW TO USE**
- Complete setup guide
- Installation instructions
- Configuration steps
- Running with synthetic data
- Using real data
- Training and backtesting
- Production deployment

### 3. [ACTION_ITEMS.md](ACTION_ITEMS.md) - **CHECKLIST**
- Quick actions reference
- Pre-production checklist
- Deployment steps
- Monitoring procedures
- ESG universe details

### 4. [THESIS_IMPROVEMENTS.md](THESIS_IMPROVEMENTS.md) - **TECHNICAL DETAILS**
- Research-backed enhancements
- Implementation details
- Module documentation
- Performance expectations
- Integration guide

---

## 🚀 Quick Links by Use Case

### "I want to test this immediately"
→ [GETTING_STARTED.md - Quick Start](GETTING_STARTED.md#quick-start)

### "I want to understand what this does"
→ [README.md](README.md)

### "I want to use real data"
→ [GETTING_STARTED.md - Using Real Data](GETTING_STARTED.md#using-real-data)

### "I want to deploy to production"
→ [ACTION_ITEMS.md - Production Checklist](ACTION_ITEMS.md#pre-production-checklist)

### "I want technical details"
→ [THESIS_IMPROVEMENTS.md](THESIS_IMPROVEMENTS.md)

### "I need Twitter API setup"
→ [GETTING_STARTED.md - Twitter API Setup](GETTING_STARTED.md#twitter-api-setup)

---

## 📁 File Structure

```
ESG-Sentimental-Trading/
├── README.md                    ← GitHub main page, project overview
├── GETTING_STARTED.md          ← Complete how-to guide (most important!)
├── ACTION_ITEMS.md             ← Checklists and deployment
├── THESIS_IMPROVEMENTS.md      ← Technical documentation
├── DOCUMENTATION.md            ← This file (navigation)
│
├── examples/
│   └── enhanced_pipeline_example.py  ← Test with synthetic data
│
├── src/
│   ├── ml/                     ← New thesis-based ML modules
│   │   ├── enhanced_pipeline.py
│   │   ├── categorical_classifier.py
│   │   ├── feature_selector.py
│   │   └── __init__.py
│   ├── nlp/                    ← NLP & sentiment analysis
│   │   ├── word_correlation_analyzer.py
│   │   ├── temporal_feature_extractor.py
│   │   ├── esg_sentiment_dictionaries.py
│   │   └── ...
│   └── ...
│
├── config/
│   ├── config.yaml             ← Main configuration
│   └── esg_keywords.json       ← ESG keyword dictionaries
│
├── setup.sh                    ← Automated setup script
├── .env.example                ← Environment variable template
└── requirements.txt            ← Python dependencies
```

---

## 💡 Common Questions

### Q: Where do I start?
**A**: Run the Quick Start in [GETTING_STARTED.md](GETTING_STARTED.md#quick-start) (takes 5 minutes)

### Q: Do I need API keys to test?
**A**: No! Use synthetic data with `python examples/enhanced_pipeline_example.py`

### Q: How do I get real data?
**A**: Follow [Twitter API Setup](GETTING_STARTED.md#twitter-api-setup) then collect data with the scripts

### Q: What are the thesis improvements?
**A**: 6 research-backed enhancements:
1. Word-level correlation analysis
2. Temporal features (7-day window)
3. ESG-specific dictionaries (285 terms)
4. Categorical classification (BUY/SELL/HOLD)
5. Random Forest + ensemble
6. Smart feature selection

Details: [THESIS_IMPROVEMENTS.md](THESIS_IMPROVEMENTS.md)

### Q: What performance should I expect?
**A**: Based on research: +30-70% profit improvement, 60-70% accuracy, Sharpe ratio 1.2-1.8

### Q: Is this production-ready?
**A**: Yes! Follow the [Pre-Production Checklist](ACTION_ITEMS.md#pre-production-checklist)

---

## 🎯 Recommended Reading Path

### For Beginners
1. [README.md](README.md) - Understand what this is
2. [GETTING_STARTED.md - Quick Start](GETTING_STARTED.md#quick-start) - Run example
3. [GETTING_STARTED.md - Installation](GETTING_STARTED.md#installation) - Set up properly
4. [GETTING_STARTED.md - Using Real Data](GETTING_STARTED.md#using-real-data) - Collect data

### For Advanced Users
1. [THESIS_IMPROVEMENTS.md](THESIS_IMPROVEMENTS.md) - Technical details
2. [ACTION_ITEMS.md](ACTION_ITEMS.md) - Production deployment
3. Module docstrings - API documentation

### For Production Deployment
1. [GETTING_STARTED.md - Training](GETTING_STARTED.md#training-the-pipeline)
2. [GETTING_STARTED.md - Backtesting](GETTING_STARTED.md#backtesting)
3. [ACTION_ITEMS.md - Pre-Production Checklist](ACTION_ITEMS.md#pre-production-checklist)
4. [GETTING_STARTED.md - Production Deployment](GETTING_STARTED.md#production-deployment)

---

## 📊 Key Metrics & Targets

### Expected Performance (from thesis research)
| Metric | Target |
|--------|--------|
| Sharpe Ratio | 1.2 - 1.8 |
| Annual Return | 10-18% |
| Win Rate | 55-62% |
| Max Drawdown | < 20% |
| Improvement | +30-70% vs baseline |

### Universe
- **50-60 ESG-sensitive NASDAQ-100 stocks**
- High event frequency (2-3x vs general stocks)
- Material ESG impact on prices

---

## 🔧 Quick Commands Reference

```bash
# Setup
./setup.sh

# Activate
source venv/bin/activate

# Test
python examples/enhanced_pipeline_example.py

# Collect data
python scripts/collect_data.py --start-date 2023-01-01 --end-date 2024-01-01

# Train
python scripts/train_pipeline.py --data-dir data/processed

# Backtest
python scripts/backtest.py --model-dir models/production

# Deploy
python main.py --mode production --model models/production
```

---

**Need help?** Start with [GETTING_STARTED.md](GETTING_STARTED.md) 📖

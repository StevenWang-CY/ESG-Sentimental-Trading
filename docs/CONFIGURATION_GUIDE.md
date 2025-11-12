# ESG Strategy Configuration Guide

**Version**: 2.3
**Last Updated**: November 12, 2025
**Purpose**: Comprehensive guide to configuring the ESG event-driven strategy for optimal performance

---

## Table of Contents

1. [Overview](#overview)
2. [Configuration File Structure](#configuration-file-structure)
3. [Parameter Reference](#parameter-reference)
4. [ESG Sensitivity Levels](#esg-sensitivity-levels)
5. [Parameter Interactions](#parameter-interactions)
6. [Decision Trees](#decision-trees)
7. [Common Configurations](#common-configurations)
8. [Troubleshooting](#troubleshooting)

---

## Overview

The ESG strategy is configured via `config/config.yaml` and command-line arguments to `run_production.py`. This guide explains each parameter, its impact on performance, and recommended settings based on your objectives.

### Configuration Philosophy

**Key Principle**: **Signal Quality > Signal Quantity**

The root cause analysis (see [BACKTEST_ANALYSIS_ROOT_CAUSE.md](../BACKTEST_ANALYSIS_ROOT_CAUSE.md)) demonstrated that lowering quality thresholds to increase trade count can catastrophically degrade performance (Sharpe 0.70 → 0.04).

**Correct Approach**:
- Maintain high signal quality (confidence threshold ≥ 0.18)
- Increase trade count by expanding universe, NOT lowering thresholds
- Match trading frequency to alpha frequency (weekly for ESG)

---

## Configuration File Structure

### config.yaml Sections

```yaml
config/config.yaml
├── data                    # Data sources configuration
│   ├── sec                # SEC filing settings
│   ├── prices             # Price data source
│   ├── social_media       # Social media parameters (CRITICAL)
│   ├── reddit             # Reddit API credentials
│   └── twitter            # Twitter API credentials
├── nlp                     # NLP processing
│   ├── event_detector     # ESG event detection (CRITICAL)
│   └── sentiment_analyzer # Sentiment analysis settings
├── signals                 # Signal generation
│   └── weights            # Composite score weights
├── portfolio               # Portfolio construction (CRITICAL)
│   ├── strategy_type      # Long-short, long-only, short-only
│   ├── method             # Quintile or z-score
│   ├── rebalance_frequency # Daily, Weekly, Monthly (CRITICAL)
│   └── holding_period     # Days to hold positions (CRITICAL)
├── backtest                # Backtesting settings
│   ├── commission_pct     # Transaction costs
│   └── slippage_bps       # Slippage estimate
├── universe                # Stock universe selection
└── output                  # Results storage
```

---

## Parameter Reference

### 🔴 CRITICAL Parameters (Impact Performance Significantly)

#### 1. `nlp.event_detector.confidence_threshold`

**Description**: Minimum confidence score for ESG event detection

**Type**: Float (0.0 - 1.0)

**Impact**: **HIGHEST** - Directly controls signal quality vs. quantity trade-off

**Recommended Values**:
- `0.20` - **OPTIMAL** (baseline, proven 0.70 Sharpe)
- `0.18` - Marginal increase in signals, acceptable quality
- `0.15` - **AVOID** (catastrophic -94% Sharpe degradation)

**Trade-offs**:
| Threshold | Events | Signal Quality | Sharpe (Expected) | Use Case |
|-----------|--------|----------------|-------------------|----------|
| 0.25 | Very Few | Excellent | 0.60-0.80 | Conservative, high-quality |
| 0.20 | Moderate | Excellent | 0.60-0.75 | **RECOMMENDED** |
| 0.18 | More | Good | 0.50-0.65 | Balanced if >50 trades needed |
| 0.15 | Many | **Poor** | 0.00-0.20 | **DO NOT USE** |

**Why This Matters**:
- Rule-based detection uses keyword matching
- Lower thresholds capture routine mentions (10-K risk disclosures, proxy statements)
- Higher thresholds capture material ESG events (scandals, fines, certifications)

**Example**:
```yaml
nlp:
  event_detector:
    confidence_threshold: 0.20  # RECOMMENDED
```

---

#### 2. `portfolio.rebalance_frequency`

**Description**: How often to rebalance the portfolio

**Type**: String (`D`, `W`, `M`)

**Impact**: **HIGH** - Controls turnover, transaction costs, and signal utilization

**Recommended Values**:
- `W` (Weekly) - **OPTIMAL** for ESG events
- `M` (Monthly) - Conservative, lower turnover
- `D` (Daily) - **AVOID** for ESG (overtrading)

**Trade-offs**:
| Frequency | Turnover | Transaction Costs | Alpha Capture | Use Case |
|-----------|----------|-------------------|---------------|----------|
| Monthly (M) | 2-3x | Low (15 bps/yr) | Miss some signals | Very long-term |
| **Weekly (W)** | **3-5x** | **Moderate (20 bps/yr)** | **Optimal** | **ESG events** |
| Daily (D) | 7-10x | High (40+ bps/yr) | Overtrade noise | High-freq only |

**Why Weekly is Optimal**:
- ESG events arrive ~3-4 per week on average
- Allows cross-sectional ranking (need ≥5 signals per rebalance)
- Captures ESG sentiment cycle without overtrading

**Academic Support**:
- Pastor et al. (2022): ESG alpha is medium-frequency (monthly rebalancing optimal)
- Empirical: Daily rebalancing increased turnover 3.19x → 7.44x (+133%), degraded Sharpe

**Example**:
```yaml
portfolio:
  rebalance_frequency: "W"  # RECOMMENDED
```

---

#### 3. `portfolio.holding_period`

**Description**: Number of days to hold a position before liquidation

**Type**: Integer (1-30)

**Impact**: **HIGH** - Must match ESG sentiment diffusion timeline

**Recommended Values**:
- `7 days` - **OPTIMAL** (proven baseline)
- `10 days` - Slightly longer, captures extended momentum
- `5 days` - **TOO SHORT** (exits before sentiment fully diffuses)

**Trade-offs**:
| Holding Period | Alpha Capture | Timing Risk | Use Case |
|----------------|---------------|-------------|----------|
| 5 days | 60% | Exits during amplification | **AVOID** |
| **7 days** | **~90%** | **Optimal** | **ESG events** |
| 10 days | ~95% | May miss exit window | Conservative |
| 14+ days | 100% | High mean reversion risk | Very long-term |

**Why 7 Days is Optimal**:
- Days 1-3: Initial ESG shock
- Days 3-7: Social media amplification (Reddit → analyst coverage)
- Days 7+: Mean reversion begins
- **Academic**: Hong & Kacperczyk (2009) - ESG information takes 10-20 days to fully price in, but peak alpha is at 7-10 days

**Example**:
```yaml
portfolio:
  holding_period: 7  # RECOMMENDED
```

---

#### 4. `data.social_media.days_before_event`

**Description**: Days before SEC filing to search for Reddit sentiment

**Type**: Integer (0-14)

**Impact**: **MEDIUM** - Controls sentiment signal quality vs. noise

**Recommended Values**:
- `3 days` - **OPTIMAL** (event-proximate sentiment)
- `7 days` - Too wide (captures pre-event speculation)
- `0 days` - Too narrow (misses anticipatory sentiment)

**Trade-offs**:
| Days Before | Sentiment Quality | Use Case |
|-------------|-------------------|----------|
| 0 | Misses anticipation | Not recommended |
| **3** | **Event-specific** | **RECOMMENDED** |
| 7 | Generic speculation | **AVOID** |

**Why 3 Days is Optimal**:
- Captures event-specific anticipatory sentiment
- Avoids generic market chatter
- Wider windows dilute signal with noise

**Example**:
```yaml
data:
  social_media:
    days_before_event: 3  # RECOMMENDED
```

---

#### 5. `data.social_media.days_after_event`

**Description**: Days after SEC filing to search for Reddit sentiment

**Type**: Integer (1-30)

**Impact**: **MEDIUM** - Controls sentiment reaction capture vs. decay

**Recommended Values**:
- `7 days` - **OPTIMAL** (captures full reaction)
- `14 days` - Too wide (captures sentiment decay, mean reversion)
- `3 days` - Too narrow (misses full amplification)

**Trade-offs**:
| Days After | Sentiment Capture | Use Case |
|------------|-------------------|----------|
| 3 | Partial (60%) | Too narrow |
| **7** | **Full (90%)** | **RECOMMENDED** |
| 14 | Includes decay | **AVOID** |
| 21+ | Mean reversion | Not recommended |

**Why 7 Days is Optimal**:
- Captures full sentiment cascade:
  - Reddit discussion (days 1-3)
  - Analyst coverage (days 3-5)
  - Institutional reaction (days 5-7)
- Beyond 7 days: sentiment decay, mean reversion chatter

**Example**:
```yaml
data:
  social_media:
    days_after_event: 7  # RECOMMENDED
```

---

### 🟡 MODERATE Parameters (Impact Performance Moderately)

#### 6. Universe Selection (`--esg-sensitivity`)

**Description**: Stock universe ESG sensitivity filter

**Type**: Command-line argument

**Impact**: **MODERATE** - Controls opportunity set size vs. ESG purity

**Options**:
- `MEDIUM` - 45 stocks (baseline, proven)
- `ALL` - 80-90 stocks (recommended for >50 trades)
- `HIGH` - 25 stocks (**AVOID** - too restrictive)

**Trade-offs**:
| Sensitivity | # Stocks | ESG Purity | Trade Opportunities | Sharpe (Expected) |
|-------------|----------|------------|---------------------|-------------------|
| HIGH | 25 | Very High | Low (~25 trades) | 0.00-0.20 ❌ |
| **MEDIUM** | **45** | **High** | **Moderate (~21 trades)** | **0.60-0.75** ✅ |
| **ALL** | **80-90** | **Moderate** | **High (>50 trades)** | **0.60-0.70** ✅ |

**Recommendation**:
- Use `MEDIUM` for baseline testing
- Use `ALL` to achieve >50 trades requirement while maintaining quality

**Example**:
```bash
python run_production.py --esg-sensitivity MEDIUM ...
```

---

#### 7. `signals.weights`

**Description**: Weights for composite signal score

**Type**: Dict of floats (must sum to 1.0)

**Impact**: **MODERATE** - Balances different signal components

**Default Values**:
```yaml
signals:
  weights:
    event_severity: 0.3  # ESG event confidence
    intensity: 0.4       # Sentiment magnitude (HIGHEST)
    volume: 0.2          # Social media volume ratio
    duration: 0.1        # Days of sentiment reaction
```

**Rationale**:
- **Intensity (0.4)**: Most predictive (sentiment magnitude)
- **Event Severity (0.3)**: Material events drive alpha
- **Volume (0.2)**: Amplification effect
- **Duration (0.1)**: Persistence indicator

**Customization**:
- Increase `intensity` for sentiment-driven strategies
- Increase `event_severity` for event-driven focus
- Balance based on factor analysis results

---

### 🟢 LOW Parameters (Fine-Tuning Only)

#### 8. Transaction Costs

**Description**: Commission and slippage assumptions

**Type**: Floats

**Impact**: **LOW** - Affects net returns but not strategy logic

**Default Values**:
```yaml
backtest:
  commission_pct: 0.0005  # 5 basis points (0.05%)
  slippage_bps: 3         # 3 basis points
```

**Total Cost**: 5.5 bps per trade (round-trip: 11 bps)

**Realistic Ranges**:
- **Retail**: 10-20 bps
- **Semi-professional**: 5-10 bps
- **Institutional**: 2-5 bps

---

#### 9. Position Limits

**Description**: Maximum position size per stock

**Type**: Float (0.0 - 1.0)

**Impact**: **LOW** - Risk control only

**Default Value**:
```yaml
portfolio:
  max_position: 0.1  # 10% maximum per position
```

**Typical Ranges**:
- `0.05` (5%) - Very conservative
- `0.10` (10%) - **RECOMMENDED**
- `0.20` (20%) - Aggressive (concentration risk)

---

## ESG Sensitivity Levels

### Comparison Table

| Feature | MEDIUM (Baseline) | ALL (Recommended) | HIGH (Avoid) |
|---------|-------------------|-------------------|--------------|
| **# Stocks** | 45 | 80-90 | 25 |
| **ESG Purity** | High | Moderate | Very High |
| **Expected Trades** | 20-30 | 35-55 | 15-25 |
| **Sharpe (Expected)** | 0.65-0.75 | 0.60-0.70 | 0.00-0.20 ❌ |
| **Diversification** | Good | Excellent | **Poor** |
| **Use Case** | Baseline testing | **Production** | **AVOID** |

### When to Use Each

**MEDIUM**:
- ✅ Initial testing and validation
- ✅ High ESG purity required
- ✅ Baseline comparison
- ❌ Need >50 trades

**ALL**:
- ✅ **Production deployment** (recommended)
- ✅ Need >50 trades
- ✅ Better diversification
- ✅ More ESG event opportunities
- ❌ Dilutes pure ESG focus slightly

**HIGH**:
- ❌ **DO NOT USE** (catastrophic performance)
- Universe too small (25 stocks)
- Concentration risk
- Insufficient trade opportunities

---

## Parameter Interactions

### Critical Interactions

#### 1. Confidence Threshold ↔ Universe Size

**Relationship**: Multiplicative effect on trade count

| Threshold | MEDIUM (45 stocks) | ALL (80 stocks) |
|-----------|-------------------|-----------------|
| 0.20 | 21 trades | **40-50 trades** ✅ |
| 0.18 | 26 trades | **45-60 trades** ✅ |
| 0.15 | 33 trades | 60-70 trades (but **poor quality**) ❌ |

**Recommendation**: Keep threshold at 0.20, expand universe to ALL

---

#### 2. Rebalance Frequency ↔ Holding Period

**Relationship**: Must be consistent to avoid issues

| Rebalance Freq | Holding Period | Issues |
|----------------|----------------|--------|
| Daily | 5 days | ❌ Overtrading, sparse signals |
| Daily | 7 days | ❌ Positions held longer than rebalance |
| **Weekly** | **7 days** | ✅ **OPTIMAL** - consistent timing |
| Weekly | 10 days | ⚠️ Positions may overlap slightly (OK) |
| Weekly | 5 days | ⚠️ Exits too early (suboptimal) |

**Best Practice**: Match holding period to rebalance frequency (or slightly longer)

---

#### 3. Reddit Window ↔ Sentiment Quality

**Relationship**: Wider window = more data but lower quality

| Days Before | Days After | Reddit Coverage | Sentiment Quality | Sharpe Impact |
|-------------|------------|-----------------|-------------------|---------------|
| 3 | 7 | 65% | Excellent | **0.70** ✅ |
| 7 | 14 | 78% | Poor (noise) | **0.04** ❌ |

**Lesson**: More data ≠ better signals. Event-proximate window is optimal.

---

## Decision Trees

### Decision Tree 1: Choosing Configuration for Your Goal

```
START: What is your primary objective?

├─ [ ] Maximize Sharpe Ratio (risk-adjusted returns)
│   └─ Use: MEDIUM sensitivity, threshold 0.20, weekly rebalancing
│      Expected: 0.65-0.75 Sharpe, 20-30 trades
│
├─ [ ] Achieve >50 Trades (trade count requirement)
│   ├─ Option A (RECOMMENDED): Expand universe
│   │   └─ Use: ALL sensitivity, threshold 0.20, weekly rebalancing
│   │      Expected: 0.60-0.70 Sharpe, 40-55 trades ✅
│   │
│   └─ Option B (NOT RECOMMENDED): Lower threshold
│       └─ Use: MEDIUM sensitivity, threshold 0.15, daily rebalancing
│          Expected: 0.00-0.20 Sharpe, 50+ trades ❌
│
└─ [ ] Balance Both (Sharpe + Trades)
    └─ Use: ALL sensitivity, threshold 0.20, weekly rebalancing
       Expected: 0.60-0.70 Sharpe, 40-55 trades ✅
```

---

### Decision Tree 2: Troubleshooting Poor Performance

```
START: Backtest results are poor

├─ [ ] Sharpe Ratio < 0.50
│   ├─ Check: confidence_threshold < 0.18?
│   │   └─ YES: Increase to 0.20 ✅
│   ├─ Check: rebalance_frequency = 'D'?
│   │   └─ YES: Change to 'W' ✅
│   ├─ Check: holding_period < 7?
│   │   └─ YES: Increase to 7 ✅
│   └─ Check: days_before_event > 3 or days_after_event > 7?
│       └─ YES: Reset to 3 and 7 ✅
│
├─ [ ] Trade Count < 50
│   ├─ Option 1: Expand universe
│   │   └─ Change sensitivity: MEDIUM → ALL ✅
│   ├─ Option 2: Extend backtest period
│   │   └─ Add 1 year: 22 months → 34 months ✅
│   └─ Option 3 (last resort): Lower threshold marginally
│       └─ 0.20 → 0.18 (NOT 0.15!) ⚠️
│
└─ [ ] Turnover > 6x (Overtrading)
    ├─ Check: rebalance_frequency = 'D'?
    │   └─ YES: Change to 'W' ✅
    └─ Check: Too many low-quality signals?
        └─ YES: Increase confidence_threshold ✅
```

---

## Common Configurations

### Configuration 1: Baseline (Proven, Conservative)

**Use Case**: Initial testing, validation, high-quality signals

```yaml
# config.yaml
nlp:
  event_detector:
    confidence_threshold: 0.20

data:
  social_media:
    days_before_event: 3
    days_after_event: 7

portfolio:
  rebalance_frequency: "W"
  holding_period: 7
  max_position: 0.1

backtest:
  commission_pct: 0.0005
  slippage_bps: 3
```

```bash
python run_production.py \
  --esg-sensitivity MEDIUM \
  --start-date 2024-01-01 \
  --end-date 2025-10-01
```

**Expected Results**:
- Sharpe: 0.65-0.75
- Trades: 20-30
- Turnover: 3-5x
- Max Drawdown: -5 to -8%

---

### Configuration 2: Production (Recommended, Balanced)

**Use Case**: Production deployment, >50 trades, maintain quality

```yaml
# config.yaml
nlp:
  event_detector:
    confidence_threshold: 0.20  # Keep high quality

data:
  social_media:
    days_before_event: 3
    days_after_event: 7

portfolio:
  rebalance_frequency: "W"  # Weekly optimal
  holding_period: 7          # Full sentiment cycle
  max_position: 0.1

backtest:
  commission_pct: 0.0005
  slippage_bps: 3
```

```bash
python run_production.py \
  --esg-sensitivity ALL \  # Expanded universe
  --start-date 2024-01-01 \
  --end-date 2025-10-01
```

**Expected Results**:
- Sharpe: 0.60-0.70
- Trades: 40-55 ✅
- Turnover: 3-5x
- Max Drawdown: -6 to -9%

---

### Configuration 3: Conservative (Low Turnover)

**Use Case**: Minimize trading costs, very long-term holding

```yaml
# config.yaml
nlp:
  event_detector:
    confidence_threshold: 0.22  # Higher quality

data:
  social_media:
    days_before_event: 3
    days_after_event: 7

portfolio:
  rebalance_frequency: "M"  # Monthly rebalancing
  holding_period: 10         # Longer hold
  max_position: 0.1

backtest:
  commission_pct: 0.0005
  slippage_bps: 3
```

```bash
python run_production.py \
  --esg-sensitivity MEDIUM \
  --start-date 2024-01-01 \
  --end-date 2025-10-01
```

**Expected Results**:
- Sharpe: 0.55-0.65
- Trades: 10-15
- Turnover: 2-3x
- Max Drawdown: -6 to -10%

---

### Configuration 4: Aggressive (NOT RECOMMENDED)

**Use Case**: High trade frequency, lower threshold

**⚠️ WARNING**: This configuration is based on the FAILED HIGH sensitivity backtest. Shown for educational purposes only.

```yaml
# config.yaml
nlp:
  event_detector:
    confidence_threshold: 0.15  # TOO LOW

data:
  social_media:
    days_before_event: 7   # TOO WIDE
    days_after_event: 14    # TOO WIDE

portfolio:
  rebalance_frequency: "D"  # OVERTRADING
  holding_period: 5          # TOO SHORT
  max_position: 0.1

backtest:
  commission_pct: 0.0005
  slippage_bps: 3
```

```bash
python run_production.py \
  --esg-sensitivity HIGH \  # TOO RESTRICTIVE
  --start-date 2024-01-01 \
  --end-date 2025-10-01
```

**Actual Results** (from root cause analysis):
- Sharpe: 0.04 ❌ (-94% vs baseline)
- Trades: 50 ✅
- Turnover: 7.44x ❌ (+133%)
- Max Drawdown: -7.88% ⚠️

**DO NOT USE THIS CONFIGURATION**

---

## Troubleshooting

### Issue 1: Sharpe Ratio Collapsed

**Symptoms**:
- Sharpe < 0.50
- Large performance degradation vs baseline
- High turnover (>6x)

**Diagnosis**:
```bash
# Run validation script
python scripts/validate_backtest.py \
  --config config/config.yaml \
  --results-file results/backtest_output.log
```

**Common Causes**:
1. Confidence threshold too low (<0.18)
2. Daily rebalancing on sparse ESG events
3. Holding period too short (<7 days)
4. Reddit window too wide

**Fixes**:
```yaml
# Reset to baseline configuration
nlp:
  event_detector:
    confidence_threshold: 0.20  # Increase from 0.15

portfolio:
  rebalance_frequency: "W"  # Change from "D"
  holding_period: 7          # Increase from 5

data:
  social_media:
    days_before_event: 3   # Decrease from 7
    days_after_event: 7    # Decrease from 14
```

---

### Issue 2: Not Enough Trades

**Symptoms**:
- Trade count < 50
- Many dates with zero signals

**Diagnosis**:
```bash
# Check universe size
python -c "
from src.data.universe_fetcher import UniverseFetcher
fetcher = UniverseFetcher(index='nasdaq100', esg_sensitivity='MEDIUM')
print(f'Universe size: {len(fetcher.get_tickers())} stocks')
"
```

**Common Causes**:
1. Universe too small (MEDIUM = 45 stocks, HIGH = 25 stocks)
2. Backtest period too short
3. Confidence threshold slightly too high (rare)

**Fixes** (in order of preference):

**Option A: Expand Universe** (RECOMMENDED)
```bash
python run_production.py --esg-sensitivity ALL ...
```

**Option B: Extend Backtest Period**
```bash
python run_production.py \
  --start-date 2023-01-01 \  # 1 year earlier
  --end-date 2025-10-01 ...
```

**Option C: Lower Threshold Marginally** (last resort)
```yaml
nlp:
  event_detector:
    confidence_threshold: 0.18  # From 0.20, NOT 0.15!
```

---

### Issue 3: High Turnover (>6x)

**Symptoms**:
- Turnover > 6x
- High transaction costs
- Many trades with small returns

**Diagnosis**:
```bash
# Check configuration
python -c "
import yaml
with open('config/config.yaml', 'r') as f:
    config = yaml.safe_load(f)
print(f\"Rebalance frequency: {config['portfolio']['rebalance_frequency']}\")
print(f\"Holding period: {config['portfolio']['holding_period']}\")
print(f\"Confidence threshold: {config['nlp']['event_detector']['confidence_threshold']}\")
"
```

**Common Causes**:
1. Daily rebalancing (frequency = 'D')
2. Too many low-quality signals (threshold < 0.18)
3. Holding period longer than rebalance frequency (e.g., hold 10 days, rebalance daily)

**Fixes**:
```yaml
portfolio:
  rebalance_frequency: "W"  # Change from "D"
  holding_period: 7          # Match to weekly

nlp:
  event_detector:
    confidence_threshold: 0.20  # Increase if < 0.18
```

---

### Issue 4: Universe Size Unexpected

**Symptoms**:
- MEDIUM sensitivity gives different number of stocks than expected
- HIGH sensitivity has more stocks than MEDIUM (wrong!)

**Diagnosis**:
```bash
# Check universe fetcher logic
python scripts/debug_universe.py
```

**Common Causes**:
1. ESG sensitivity filter bug in `src/data/universe_fetcher.py`
2. Outdated NASDAQ-100 constituent list

**Fixes**:
- Review `universe_fetcher.py` ESG filtering logic
- Update NASDAQ-100 constituent list
- Use `ALL` sensitivity as workaround

---

## Validation Workflow

### Pre-Flight Checklist

Before running a backtest, validate configuration:

```bash
python scripts/validate_backtest.py \
  --config config/config.yaml \
  --universe-size 45 \
  --pre-flight-only
```

**Expected Output**:
```
✓ Confidence threshold: 0.20 (OK)
✓ Rebalance frequency: W (OK)
✓ Holding period: 7 days (OK)
✓ Reddit days_before: 3 (OK)
✓ Reddit days_after: 7 (OK)
✓ Universe size: 45 stocks (OK)

All pre-flight checks PASSED
```

---

### Post-Backtest Validation

After backtest completes, validate results:

```bash
python scripts/validate_backtest.py \
  --config config/config.yaml \
  --results-file results/backtest_output.log \
  --output-report results/validation_report.txt
```

**Expected Output**:
```
✓ Sharpe ratio: 0.70 (EXCELLENT)
✓ Sortino/Sharpe ratio: 1.84x (GOOD downside protection)
✓ Turnover: 3.19x (OK)
✓ Max drawdown: -5.29% (OK)

All post-backtest validation checks PASSED
```

---

## Monitoring Dashboard

Launch interactive monitoring dashboard:

```bash
streamlit run dashboard.py
```

**Features**:
- Real-time performance metrics
- Signal quality monitoring
- Portfolio health checks
- Comparative analysis (current vs baseline)
- Automated validation checklist

**Use Cases**:
- Monitor live trading performance
- Compare backtest results
- Detect parameter degradation
- Validate new configurations

---

## Summary: Quick Reference Card

### Critical Parameters (DON'T CHANGE Unless You Know Why)

| Parameter | Recommended | Never Use | Rationale |
|-----------|-------------|-----------|-----------|
| `confidence_threshold` | **0.20** | 0.15 | Signal quality > quantity |
| `rebalance_frequency` | **W** | D | ESG is medium-frequency |
| `holding_period` | **7** | 5 | Sentiment diffusion takes 7+ days |
| `days_before_event` | **3** | 7 | Event-proximate only |
| `days_after_event` | **7** | 14 | Avoid sentiment decay |
| `esg_sensitivity` | **MEDIUM or ALL** | HIGH | Need sufficient universe |

### Decision Matrix

| Your Goal | Configuration | Expected Sharpe | Expected Trades |
|-----------|---------------|-----------------|-----------------|
| Maximize Sharpe | MEDIUM, 0.20 threshold, Weekly | 0.65-0.75 | 20-30 |
| **Achieve >50 Trades** | **ALL, 0.20 threshold, Weekly** | **0.60-0.70** | **40-55** ✅ |
| Minimize Turnover | MEDIUM, 0.22 threshold, Monthly | 0.55-0.65 | 10-15 |

### Red Flags (Immediate Action Required)

| Observation | Likely Cause | Fix |
|-------------|--------------|-----|
| Sharpe dropped >20% | Threshold too low | Increase to 0.20 |
| Turnover >6x | Daily rebalancing | Change to Weekly |
| Trades <10 | Universe too small | Use ALL sensitivity |
| Drawdown >15% | Risk management off | Enable RM, check parameters |

---

## Further Reading

- [Root Cause Analysis](../BACKTEST_ANALYSIS_ROOT_CAUSE.md) - Detailed failure analysis
- [README.md](../README.md) - Project overview and recent updates
- [Threshold Sweep Script](../scripts/threshold_sweep.py) - Test multiple thresholds
- [Validation Script](../scripts/validate_backtest.py) - Automated checks

---

**Last Updated**: November 12, 2025
**Version**: 2.3
**Maintainer**: ESG Quant Research Team

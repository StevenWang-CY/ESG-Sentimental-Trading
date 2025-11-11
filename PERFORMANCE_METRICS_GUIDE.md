# Performance Metrics Guide

## Overview
This document explains the performance metrics used in the ESG Event-Driven Alpha Strategy, including fixes applied to address unrealistic values and how to interpret validation warnings.

---

## Recent Fixes Applied

### Fix #1: Realistic Market Noise in Mock Data
**Problem**: Mock data had perfectly correlated returns with signals, creating unrealistically smooth equity curves.

**Solution** ([main.py:325-350](main.py#L325-L350)):
```python
# Added market shocks (8% chance per day)
if np.random.random() < 0.08:
    shock = np.random.normal(0, 0.035)
    base_return += shock

# Signal effectiveness now varies: -50% to +200%
# (Signals can predict wrong direction!)
signal_noise = np.random.uniform(-0.5, 2.0)

# Reduced signal strength by 80% (0.002 → 0.0004)
signal_effect = (signal_score - 0.5) * 0.0004 * decay * signal_noise
```

**Impact**: Increases drawdowns, adds realistic noise, but demo still shows optimistic results due to structural limitations.

---

### Fix #2: Consistent Annualized Return Calculation
**Problem**: Two different methods produced different results:
- CAGR: 70.26% (geometric, correct)
- Annualized Return: 58.00% (arithmetic mean × 252, incorrect)

**Solution** ([metrics.py:52-55](src/backtest/metrics.py#L52-L55)):
```python
# OLD: annualized_return = self.returns.mean() * 252
# NEW: annualized_return = cagr  (use geometric compounding)
```

**Impact**: Both metrics now show the same value (correct geometric method).

---

### Fix #3: Metric Validation Warnings
**Solution** ([metrics.py:282-342](src/backtest/metrics.py#L282-L342)):

Added automatic validation that flags unrealistic metrics:

| Metric | Warning Threshold | Real-World Expectation |
|--------|------------------|------------------------|
| **Sortino Ratio** | > 5.0 | 1.5 - 3.0 (excellent) |
| **Calmar Ratio** | > 10.0 | 2 - 5 (excellent) |
| **Max Drawdown** | < 5% | 10% - 30% (typical) |
| **Downside Dev / Vol** | < 30% | 50% - 100% (normal) |
| **CAGR** | > 50% | 10% - 30% (hedge funds) |

---

## Understanding Demo Mode Results

### Why Demo Metrics Are Unrealistic

**Fundamental Issue**: Demo mode creates prices that are **correlated with signals** by design. This guarantees the strategy "works" but is unrealistic.

```python
# Demo creates this relationship:
Long stocks (Q5) → prices move UP
Short stocks (Q1) → prices move DOWN
```

In reality:
- Signals are noisy and often wrong
- Markets have regime changes
- Many events don't move prices
- Transaction costs erode returns

### Demo vs Real-World Comparison

| Metric | Demo Mode | Real Backtest | Real Live Trading |
|--------|-----------|---------------|-------------------|
| **CAGR** | 40-70% | 15-35% | 10-25% |
| **Sharpe** | 1.4-1.7 | 1.0-1.5 | 0.8-1.3 |
| **Sortino** | 10-25 | 1.5-3.0 | 1.2-2.5 |
| **Calmar** | 20-45 | 2-5 | 1.5-4 |
| **Max DD** | 1-3% | 10-25% | 15-35% |

---

## Realistic Performance Expectations

### Excellent ESG Event Strategy (Real Backtest)
```
CAGR:                20-30%
Sharpe Ratio:        1.2-1.8
Sortino Ratio:       1.8-2.5
Calmar Ratio:        3-5
Max Drawdown:        -12% to -20%
Annualized Vol:      18-25%
```

### Top Hedge Fund Benchmarks
- Renaissance Medallion: 39% CAGR (1988-2018), Sharpe ~1.5
- Citadel: 19% CAGR (1990-2020), Sharpe ~1.0
- Two Sigma: 23% CAGR (2001-2020), Sharpe ~1.2

### Why Lower Returns Are Expected

1. **Transaction Costs**: 5-10 bps per trade × 50-100 trades/year = 0.5-1% annual drag
2. **Slippage**: Market impact on entries/exits
3. **Signal Decay**: Edge disappears as others discover it
4. **Regime Changes**: Strategies that worked in backtests fail in different market conditions
5. **Overfitting**: Historical optimization doesn't predict future

---

## How to Use the Strategy

### Step 1: Run Demo Mode (Educational Only)
```bash
python main.py --mode demo --start-date 2024-01-01 --end-date 2024-12-31
```
- **Purpose**: Verify code works, understand workflow
- **Warning**: Metrics will be unrealistic (expect validation warnings)

### Step 2: Run Real Backtest (Historical Data)
```bash
python run_production.py \
    --universe esg_nasdaq100 \
    --esg-sensitivity HIGH \
    --start-date 2020-01-01 \
    --end-date 2023-12-31 \
    --max-tickers 50
```
- **Purpose**: Test strategy on real market data
- **Expected**: Sharpe 1.0-1.5, Max DD 10-25%
- **Reality Check**: If Sortino > 5 or Calmar > 10, suspect data issues

### Step 3: Paper Trading (Forward Test)
```bash
# Run on recent data NOT used in backtesting
python run_production.py --start-date 2024-01-01 --end-date 2024-12-31
```
- **Purpose**: Validate out-of-sample performance
- **Expected**: Returns 30-50% lower than backtest
- **Reality**: This is normal (regression to mean)

### Step 4: Live Trading (Small Capital First)
- Start with 1-5% of intended capital
- Monitor for 3-6 months
- Expect 40-60% degradation from backtest

---

## Interpreting Validation Warnings

### ⚠ Sortino Ratio > 5.0

**What it means**: Strategy has very few large down days relative to up days.

**Possible causes**:
1. **Mock data** (demo mode) → Expected, ignore
2. **Short backtest period** (< 1 year) → Run longer period
3. **Look-ahead bias** → Check you're not using future data
4. **Overfitting** → Test out-of-sample

**Action**: If using real data and Sortino > 5, be skeptical. Real strategies rarely exceed 3.0.

---

### ⚠ Calmar Ratio > 10.0

**What it means**: CAGR is very high relative to max drawdown.

**Example**: 50% CAGR with only 3% max drawdown = Calmar of 16.7

**Reality check**:
- With 25% volatility, expect 15-30% drawdown
- Your 3% drawdown suggests:
  - Very short test period (lucky run)
  - Overfitting (curve-fitted to avoid past drawdowns)
  - Mock data (prices follow signals)

**Action**: If real backtest shows Calmar > 10, extend test period to 5+ years.

---

### ⚠ Max Drawdown < 5%

**What it means**: Equity curve is unrealistically smooth.

**Why it's suspicious**:
```
Typical relationship: Max DD ≈ 50-100% of annualized volatility
Your data: 23% volatility → expect 12-23% drawdown
Actual: 2% drawdown → 10x too small!
```

**Possible causes**:
1. Short backtest (haven't seen market crash yet)
2. Perfect signals (demo mode artifact)
3. Look-ahead bias (using future information)

**Action**: Run backtest through at least one major market correction (2020 COVID, 2022 bear market, etc.)

---

### ⚠ Downside Dev / Volatility < 30%

**What it means**: Strategy has asymmetric returns (few large losses).

**Normal distribution**: Downside dev ≈ 70% of total volatility
**Your strategy**: Downside dev = 12% of volatility

**Interpretation**: Returns are skewed positive (sounds great, but suspicious!)

**Reality**: Even the best strategies have ~50% downside/total volatility ratio.

---

## Checklist: Is My Backtest Realistic?

✅ **Good backtest**:
- [ ] Sharpe ratio: 1.0-1.8
- [ ] Sortino ratio: 1.5-3.0
- [ ] Calmar ratio: 2-5
- [ ] Max drawdown: 10-25%
- [ ] Downside dev: 50-80% of volatility
- [ ] Test period: 3-5+ years
- [ ] Includes at least one market crash
- [ ] Win rate: 45-60% (not 80%+)

❌ **Suspicious backtest** (check for bugs):
- [ ] Sharpe > 2.5
- [ ] Sortino > 5.0
- [ ] Calmar > 10
- [ ] Max drawdown < 5%
- [ ] Win rate > 70%
- [ ] Zero losing months

---

## Summary

### What We Fixed
1. ✅ Mock data now includes market shocks and signal imperfection
2. ✅ Annualized return = CAGR (consistent calculation)
3. ✅ Automatic validation warnings for unrealistic metrics

### What Demo Mode Shows
- Educational workflow demonstration
- Code verification
- Optimistic performance (expected)

### Real-World Performance
- Use production backtests on historical data
- Expect Sharpe 1.0-1.5, Max DD 10-25%
- Forward test before risking capital
- Live performance degrades 40-60% from backtest

---

**Remember**: If metrics seem too good to be true in a real backtest, they probably are. Always validate with out-of-sample testing and paper trading before live deployment.


# Strategy Optimization Recommendations

## Current Performance (13 Days Backtest)

- **Total Trades**: 28 (2.15 trades/day)
- **Win Rate**: 42.86% (12 wins, 16 losses)
- **Total P&L**: ₹189.89 (0.19% return)
- **Annualized Return**: ~5.3% (very low)

### Detailed Breakdown

- **Winning Trades**: 12
  - Total Profit: ₹573.15
  - Average Win: ₹47.76
  
- **Losing Trades**: 16
  - Total Loss: ₹-383.26
  - Average Loss: ₹-23.95

- **Exit Reasons**:
  - TARGET: 5 trades, ₹317.01 profit ✅
  - STOPLOSS: 16 trades, ₹-367.19 loss ❌
  - TIME: 7 trades, ₹240.07 profit ✅

## Issues Identified

1. **Too Many STOPLOSS Hits**: 57% of trades hit stoploss
2. **Low Win Rate**: 42.86% (should be >50% for good profitability)
3. **Low Return**: 0.19% in 13 days = ~5.3% annual (target: 15-25%)
4. **False Breakouts**: Strategy entering on weak signals

## Recommendations

### ⚠️ DO NOT GO LIVE YET

The strategy is working correctly but needs optimization before live trading.

### Option 1: Tighten Entry Filters (Recommended)

**Goal**: Reduce false breakouts, improve win rate

**Changes**:
```python
# In backtest_momentum_strategy.py and run_momentum_strategy.py

# Current:
RSI_BUY_MIN = 55
RSI_SELL_MAX = 45

# Recommended:
RSI_BUY_MIN = 60  # Stricter for BUY
RSI_SELL_MAX = 40  # Stricter for SELL

# Also require stronger EMA crossover:
# BUY: EMA5 > EMA20 * 1.001 (1% gap)
# SELL: EMA5 < EMA20 * 0.999 (1% gap)
```

**Expected Result**: Fewer trades (15-20 in 13 days), higher win rate (50-60%)

### Option 2: Adjust Risk Parameters

**Goal**: Give trades more room, reduce stoploss hits

**Changes**:
```python
# Current:
TARGET_PCT = 1.5%  # +1.5%
STOPLOSS_PCT = 0.7%  # -0.7%

# Recommended:
TARGET_PCT = 1.5%  # Keep same
STOPLOSS_PCT = 1.0%  # Widen to -1.0%
```

**Expected Result**: Fewer stoploss hits, more TIME exits (some profitable)

### Option 3: Reduce Trade Frequency

**Goal**: Only take strongest signals

**Changes**:
- Add minimum range size requirement (e.g., range must be >50 points)
- Require volume spike (current volume > 2x average)
- Skip trades if multiple signals in same direction within 30 minutes

### Option 4: Combine Approaches (Best)

1. Tighten RSI filters (60/40 instead of 55/45)
2. Widen stoploss slightly (-0.7% → -0.9%)
3. Add minimum range size filter
4. Require stronger EMA gap

## Testing Plan

1. **Week 1**: Test Option 1 (tighter filters)
2. **Week 2**: Test Option 2 (wider stoploss)
3. **Week 3**: Test Option 4 (combined)
4. **Week 4**: Compare results, choose best parameters

## Success Criteria for Going Live

- ✅ Win rate > 50%
- ✅ Annualized return > 15%
- ✅ Profit factor > 1.5
- ✅ Max drawdown < 5% of capital
- ✅ At least 20-30 trades in backtest period

## Current Status: ❌ NOT READY FOR LIVE

**Action Required**: Optimize parameters and retest before live trading.


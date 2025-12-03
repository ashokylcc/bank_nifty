# Stop-Loss Implementation Report
**Date:** 2025-12-01  
**Strategy:** Heikin Ashi Strategy  
**File:** `trading/management/commands/run_heikinashi_strategy.py`

---

## Executive Summary

### ✅ **Daily Stop-Loss: IMPLEMENTED & ACTIVE**
- **Status:** Working correctly
- **Value:** 50% of daily profit target
- **Example:** For ₹1000 daily target → ₹500 stop-loss
- **Monitoring:** Continuous (every loop iteration)
- **Action:** Exits position + Halts trading for the day

### ❌ **Per-Trade Stop-Loss: NOT IMPLEMENTED**
- **Status:** DISABLED
- **Constants Defined:** Yes (but not used)
  - `STOPLOSS_OPTION_PCT = -30%` (option premium loss)
  - `STOPLOSS_FUTURES_POINTS = 30` (futures adverse movement)
- **Monitoring:** None
- **Risk:** Individual trades can lose unlimited amounts

---

## Detailed Analysis

### 1. Daily Stop-Loss Implementation

#### Configuration (Lines 33, 93)
```python
DAILY_STOP_LOSS_FACTOR = Decimal('0.5')  # 50% of daily profit target
self.daily_stop_loss = self.daily_profit_target * DAILY_STOP_LOSS_FACTOR
```

#### Calculation Example:
- **Quantity:** 35 lots
- **Daily Target:** ₹1000
- **Daily Stop-Loss:** ₹1000 × 0.5 = **₹500**

#### Monitoring (Lines 617-646)
- **Method:** `monitor_daily_limits()`
- **Frequency:** Called continuously in main loop (line 1434)
- **Check:** `if self.daily_pnl <= -self.daily_stop_loss:`
- **Action:** 
  1. Sets `trading_halted_for_day = True`
  2. Exits any open position
  3. Logs: "🛑 Daily stop-loss hit. Trading halted."

#### Status Display (Line 1632)
- Shows: `Stop: -₹{daily_stop_loss:.2f}` in terminal

#### ✅ **Verification: WORKING**
- Daily stop-loss is properly calculated
- Monitored continuously
- Correctly halts trading when hit
- Exits open positions

---

### 2. Per-Trade Stop-Loss Implementation

#### Constants Defined (Lines 38-39)
```python
STOPLOSS_OPTION_PCT = Decimal('0.30')  # -30% option premium
STOPLOSS_FUTURES_POINTS = 30  # 30 points adverse movement
```

#### Status: ❌ **DISABLED**

**Evidence (Lines 861-870):**
```python
# EXIT CONDITIONS DISABLED: Only exit on next candle trend reversal (handled elsewhere)
# The following exit logics are intentionally disabled but kept for reference:
# - Futures profit target
# - Absolute profit target (old ₹1300)
# - Option percentage target
# - Completed-candle HA reversal
# - Option/Futures stop-loss  ← DISABLED
```

#### Current Exit Conditions (Active):
1. ✅ **Per-trade profit target:** ₹500 (line 855)
2. ✅ **Next candle trend reversal** (line 1450)
3. ✅ **Time exit:** 3:20 PM (line 858)
4. ✅ **Daily stop-loss:** ₹500 (line 639)

#### Missing Exit Conditions:
- ❌ **Per-trade option stop-loss:** -30% premium loss
- ❌ **Per-trade futures stop-loss:** -30 points adverse movement

---

## Risk Analysis

### Current Risk Profile

#### ✅ Protected:
- **Daily Loss Limit:** ₹500 (50% of ₹1000 target)
- **Time-based Exit:** 3:20 PM square-off

#### ❌ Unprotected:
- **Individual Trade Losses:** No limit per trade
- **Large Adverse Moves:** No futures-based stop-loss
- **Option Premium Erosion:** No -30% stop-loss per trade

### Example Scenario:

**Trade 1:**
- Entry: ₹823.70
- If price drops to ₹576.59 (-30% = ₹247.11 loss)
- **Current behavior:** Trade continues until:
  - Next candle reversal, OR
  - Daily stop-loss hit (₹500 total), OR
  - Time exit (3:20 PM)

**Risk:** A single bad trade could lose ₹500+ before daily stop-loss triggers.

---

## Recommendations

### Option 1: Enable Per-Trade Stop-Loss (Recommended)

**Add to `check_exit_conditions()` method (after line 859):**

```python
# 2. PER-TRADE STOP-LOSS: Exit when trade loses -30% or -30 points
# Option stop-loss: -30% premium loss
option_loss_pct = ((entry_premium - current_option_ltp) / entry_premium) if entry_premium > 0 else Decimal('0')
if option_loss_pct >= STOPLOSS_OPTION_PCT:
    logger.info(
        f"🛑 Per-trade option stop-loss: Loss {option_loss_pct*100:.2f}% >= {STOPLOSS_OPTION_PCT*100:.0f}%"
    )
    return 'STOPLOSS'

# Futures stop-loss: -30 points adverse movement
if 'CE' in side:  # CALL
    futures_loss = entry_future_price - current_futures_ltp
    if futures_loss >= STOPLOSS_FUTURES_POINTS:
        logger.info(
            f"🛑 Per-trade futures stop-loss: Loss {futures_loss:.2f} points >= {STOPLOSS_FUTURES_POINTS} points"
        )
        return 'STOPLOSS'
else:  # PUT
    futures_loss = current_futures_ltp - entry_future_price
    if futures_loss >= STOPLOSS_FUTURES_POINTS:
        logger.info(
            f"🛑 Per-trade futures stop-loss: Loss {futures_loss:.2f} points >= {STOPLOSS_FUTURES_POINTS} points"
        )
        return 'STOPLOSS'
```

### Option 2: Keep Current Setup (Accept Risk)

**Rationale:**
- Daily stop-loss provides overall protection
- Per-trade ₹500 profit target limits exposure
- Next candle reversal provides trend-based exit
- Simpler logic, fewer false exits

**Trade-off:** Accepts risk of larger individual trade losses.

---

## Testing Recommendations

### Test Case 1: Daily Stop-Loss
- **Setup:** Start with ₹0 daily P&L
- **Action:** Execute trades that lose money
- **Expected:** Trading halts when daily P&L <= -₹500
- **Verify:** Status shows "HALTED", no new entries

### Test Case 2: Per-Trade Stop-Loss (if enabled)
- **Setup:** Enter a trade
- **Action:** Option price drops -30% or futures moves -30 points
- **Expected:** Trade exits immediately with 'STOPLOSS' reason
- **Verify:** Daily P&L updated, position cleared

---

## Summary Table

| Stop-Loss Type | Status | Value | Monitoring | Action |
|---------------|--------|-------|------------|--------|
| **Daily Stop-Loss** | ✅ Active | ₹500 (50% of ₹1000) | Continuous | Exit + Halt |
| **Per-Trade Option** | ❌ Disabled | -30% premium | None | N/A |
| **Per-Trade Futures** | ❌ Disabled | -30 points | None | N/A |

---

## Conclusion

**Current State:**
- ✅ Daily stop-loss is properly implemented and working
- ❌ Per-trade stop-loss is disabled (constants exist but not used)
- ⚠️ Individual trades have no loss limit (only daily aggregate limit)

**Recommendation:**
Enable per-trade stop-loss to protect against large individual trade losses while maintaining the daily stop-loss as a safety net.

---

**Report Generated:** 2025-12-01  
**Code Version:** Latest  
**Status:** Ready for Review


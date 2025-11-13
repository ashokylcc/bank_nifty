# Validation Guide - How to Interpret Results

This guide explains how to validate simulation results and interpret the validation output.

## Running Validation

After running a simulation, validate the results:

```bash
python manage.py validate_simulation
```

Or for a specific strategy:

```bash
python manage.py validate_simulation --strategy-id 1
```

## Validation Checks

### 1. Range Detection ✅

**What it checks:**
- `first_high` and `first_low` are captured from first candle (9:15-9:30)
- Range calculation: `range = first_high - first_low`
- High > Low (logical validation)

**Expected output:**
```
📊 1. Range Detection Validation
   Signal 1:
     First High: ₹58500
     First Low: ₹58300
     Range: ₹200
     ✅ Range calculation correct
     ✅ Range values valid (High > Low)
```

**If it fails:**
- Check CSV first candle data
- Verify `range_detector.py` is capturing correctly
- Check time window (9:15-9:30)

---

### 2. Momentum Score ✅

**What it checks:**
- Executed signals must have `momentum_score == 4`
- All 4 conditions must be met before execution:
  1. Volume breakout (1.5x avg)
  2. EMA alignment
  3. RSI in range
  4. Price momentum

**Expected output:**
```
🎯 2. Momentum Score Validation
   Signal 1 (BUY):
     Momentum Score: 4/4
     Executed: True
     ✅ Momentum score = 4 (all conditions met)
```

**If it fails:**
- Signal executed with score < 4 → **BUG** in `strategy_engine.py`
- Signal has score = 4 but not executed → Check `execution_reason` field
- Fix in `momentum.py` or `strategy_engine.py`

---

### 3. Strike Selection ✅

**What it checks:**
- Option symbol format: `BANKNIFTY{DD}{MMM}{YY}{C|P}{STRIKE}`
- Example: `BANKNIFTY27NOV25C58400`
- Strike matches signal's `selected_strike`
- Option type (C/P) matches signal type (BUY=Call, SELL=Put)
- Symbol can be rebuilt using `build_option_symbol()`

**Expected output:**
```
🎲 3. Strike Selection Validation
   Signal 1:
     Symbol: BANKNIFTY27NOV25C58400
     Strike: 58400
     Expiry: 2025-11-27
     ✅ Strike matches: 58400
     ✅ Option type correct: C
     ✅ Symbol format matches README example
```

**If it fails:**
- Invalid symbol format → Fix `strike_selector.py`
- Strike mismatch → Check strike calculation
- Option type mismatch → Fix option type selection logic

---

### 4. Risk Manager ✅

**What it checks:**
- Quantity calculation formula:
  ```
  qty = floor((capital * risk_per_trade_pct) / (stoploss_points * tick_value))
  ```
- Minimum qty = 1 lot

**Expected output:**
```
💰 4. Risk Manager Validation
   Signal 1:
     Capital: ₹100000
     Risk %: 1.00%
     Stoploss Points: 60
     Tick Value: 1.00
     Calculated Qty: 16
     ✅ Qty calculation correct: 16
```

**If it fails:**
- Qty mismatch → Fix `risk_manager.py` calculation
- Division by zero → Check stoploss_points and tick_value
- Formula shown in error message for debugging

---

### 5. Execution Adapter ✅

**What it checks:**
- Orders have `dry_run=True` in simulation
- Status transitions: PENDING → FILLED
- Filled orders have `filled_price` populated
- Order details are correct

**Expected output:**
```
📦 5. Execution Adapter Validation
   Order MOCK_000001:
     Symbol: BANKNIFTY27NOV25C58400
     Side: BUY
     Qty: 16
     Status: FILLED
     Dry Run: True
     Filled Price: ₹100.00
     ✅ Order filled at ₹100.00
```

**If it fails:**
- Missing filled_price → Fix `execution_adapter.py`
- Status not FILLED → Check order placement logic
- Not in dry_run → Check simulation mode

---

### 6. TradeLog Fields ✅

**What it checks:**
- Entry fields: `entry_time`, `entry_price`, `entry_symbol`, `entry_side`, `entry_quantity`
- Exit fields (if closed): `exit_time`, `exit_price`, `exit_reason`
- P&L fields: `pnl_points`, `pnl_value`

**Expected output:**
```
📝 6. TradeLog Fields Validation
   Trade 1:
     ✅ Entry fields populated
        Entry: BUY 16 BANKNIFTY27NOV25C58400 @ ₹100.00 at 2025-11-25 09:45:00
     ✅ Exit fields populated
        Exit: ₹120.00 at 2025-11-25 10:30:00 (TARGET)
     ✅ P&L fields populated
        PnL: 20.0 points = ₹11200.00
```

**If it fails:**
- Missing entry fields → Fix `strategy_engine.py` trade creation
- Missing exit fields → Fix `strategy_engine.py` exit logic
- Missing P&L → Fix P&L calculation

---

### 7. DailyStats ✅

**What it checks:**
- Win rate calculation: `(winning_trades / total_trades) * 100`
- Trade counts: `winning_trades + losing_trades <= total_trades`
- Total PnL is reasonable
- Max drawdown is non-negative

**Expected output:**
```
📊 7. DailyStats Validation
   Date: 2025-11-25
     Total Trades: 2
     Winning: 1, Losing: 1
     Win Rate: 50.00%
     Total PnL: ₹500.00
     Max Drawdown: ₹200.00
     ✅ Win rate calculation correct
     ✅ Trade counts consistent
     ✅ Total PnL seems reasonable
     ✅ Max drawdown is non-negative
```

**If it fails:**
- Win rate mismatch → Fix `strategy_engine.py` `update_daily_stats()`
- Trade count mismatch → Check trade counting logic
- Unreasonable PnL → Review trade data
- Negative drawdown → Fix drawdown calculation

---

## Interpreting Results

### All Passed ✅
```
✅ ALL VALIDATIONS PASSED
```
**Meaning:** All components working correctly. System is ready for use.

### Some Failed ❌
```
❌ SOME VALIDATIONS FAILED - Check details above
```
**Action:** Review failed validations and fix the corresponding modules:
- Range detection → `range_detector.py`
- Momentum → `momentum.py`
- Strike selection → `strike_selector.py`
- Risk manager → `risk_manager.py`
- Execution adapter → `execution_adapter.py`
- TradeLog → `strategy_engine.py`
- DailyStats → `strategy_engine.py` (update_daily_stats method)

---

## Common Issues and Fixes

### Issue: Range not captured
**Fix:** Check CSV first candle timestamp is 9:15-9:30, or use `force=True` in simulation

### Issue: Momentum score < 4 but executed
**Fix:** Add check in `strategy_engine.py` `execute_trade()` to verify score == 4

### Issue: Invalid option symbol format
**Fix:** Check `build_option_symbol()` in `expiry_functions.py`, verify date format

### Issue: Qty calculation wrong
**Fix:** Review formula in `risk_manager.py` `calculate_position_size()`

### Issue: Order not filled
**Fix:** Check `execution_adapter.py` mock adapter returns FILLED status

### Issue: Missing TradeLog fields
**Fix:** Ensure all fields set in `strategy_engine.py` `execute_trade()` and `exit_trade()`

### Issue: DailyStats incorrect
**Fix:** Review `update_daily_stats()` method in `strategy_engine.py`

---

**Last Updated:** 2025-11-13


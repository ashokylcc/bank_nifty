# 📊 HOW TO UPDATE YESTERDAY_CLOSING - Step by Step Guide

## 🎯 What is YESTERDAY_CLOSING?

**YESTERDAY_CLOSING** = The closing price of Bank Nifty from the previous trading day.

**Current Value:** `58375` (Line 68 in `slippage_compensated_strategy.py`)

---

## 📍 Where to Find This Value?

### Option 1: NSE Website (Recommended)
1. Go to: https://www.nseindia.com/
2. Search for "BANKNIFTY" or "NIFTY BANK"
3. Check "Previous Close" or "Last Traded Price" from yesterday
4. Use that value

### Option 2: Trading Platform (Alice Blue)
1. Open Alice Blue app/website
2. Search for "BANKNIFTY" or "BANKNIFTY FUT"
3. Check yesterday's closing price
4. Use that value

### Option 3: Google Finance
1. Search: "Bank Nifty NSE"
2. Check "Previous Close" value
3. Use that value

---

## ✏️ How to Update YESTERDAY_CLOSING

### Step 1: Open the File
```bash
# File location:
/var/www/html/bank_nifty/strategy/management/commands/slippage_compensated_strategy.py
```

### Step 2: Find Line 68
Look for this line:
```python
YESTERDAY_CLOSING = 58375
```

### Step 3: Update the Value
Change `58375` to the new value:
```python
YESTERDAY_CLOSING = 58500  # Example: if yesterday's close was 58500
```

### Step 4: Save the File
Save the file after updating.

---

## 📝 Example Update

### Before:
```python
YESTERDAY_CLOSING = 58375
```

### After (if yesterday's close was 58500):
```python
YESTERDAY_CLOSING = 58500
```

---

## 🔍 How the Strategy Uses This Value

### 1. Calculate Movement:
```python
movement = current_price - YESTERDAY_CLOSING
# Example: If current = 58500, YESTERDAY_CLOSING = 58375
# Movement = 58500 - 58375 = 125 points
```

### 2. Calculate Percentage:
```python
price_change_percent = (movement / YESTERDAY_CLOSING) * 100
# Example: (125 / 58375) * 100 = 0.21%
```

### 3. Select Strike Price:
```python
atm_strike = round(YESTERDAY_CLOSING / 100) * 100
# Example: round(58375 / 100) * 100 = 58400
```

---

## ⏰ When to Update?

### Daily Update Required:
- ✅ **Every morning before 9:15 AM** (before market opens)
- ✅ Update with **previous day's closing price**
- ✅ Must be accurate for strategy to work correctly

### Example Timeline:
- **Today:** Market closes at 3:30 PM → Closing price = 58375
- **Tomorrow Morning:** Update `YESTERDAY_CLOSING = 58375` before 9:15 AM
- **Strategy runs:** Uses 58375 as reference for today's trading

---

## ✅ Verification Steps

### After Updating:

1. **Check the Value:**
   ```bash
   grep "YESTERDAY_CLOSING" /var/www/html/bank_nifty/strategy/management/commands/slippage_compensated_strategy.py
   ```
   Should show: `YESTERDAY_CLOSING = 58375` (or your new value)

2. **Test in Simulation:**
   ```bash
   python3 manage.py slippage_compensated_strategy --simulate
   ```
   Check the output - it should show:
   ```
   📊 Yesterday's Closing: ₹58375
   ```

3. **Verify Strike Selection:**
   - Strategy will select strike based on this value
   - If YESTERDAY_CLOSING = 58375, ATM strike = 58400

---

## 🎯 Current Status

**Current Value:** `58375` ✅

**File Location:** Line 68 in `slippage_compensated_strategy.py`

**Status:** Already set correctly!

---

## 📋 Quick Reference

### Daily Checklist:
- [ ] Check yesterday's Bank Nifty closing price
- [ ] Open `slippage_compensated_strategy.py`
- [ ] Update Line 68: `YESTERDAY_CLOSING = [NEW_VALUE]`
- [ ] Save file
- [ ] Verify with simulation test (optional)

### Example Values:
- If yesterday closed at **58200** → `YESTERDAY_CLOSING = 58200`
- If yesterday closed at **58500** → `YESTERDAY_CLOSING = 58500`
- If yesterday closed at **58375** → `YESTERDAY_CLOSING = 58375` ✅ (current)

---

## ⚠️ Important Notes

1. **Must be Previous Day's Close:**
   - Not today's opening price
   - Not current price
   - **Only** previous day's closing price

2. **Update Before Market Opens:**
   - Best time: 9:00 AM - 9:15 AM
   - Must be done before running strategy

3. **Accuracy Matters:**
   - Wrong value = Wrong movement calculation
   - Wrong value = Wrong strike selection
   - Always verify from reliable source

4. **No Decimal Values:**
   - Use whole numbers only
   - Example: `58375` ✅ (correct)
   - Example: `58375.50` ❌ (wrong - no decimals)

---

## 🚀 Ready to Trade!

Once you've updated `YESTERDAY_CLOSING`:
1. ✅ Value is set correctly
2. ✅ Strategy will use it for calculations
3. ✅ Ready to run live trading

**Command to run:**
```bash
python3 manage.py slippage_compensated_strategy
```

---

**Last Updated:** Guide for YESTERDAY_CLOSING updates  
**Current Value:** 58375 ✅


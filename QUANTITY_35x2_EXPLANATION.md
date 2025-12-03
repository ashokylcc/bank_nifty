# Quantity Calculation: lot_size=35 × num_lots=2

## Scenario: Setting lot_size=35 and num_lots=2 in DB

### What Will Happen:

#### 1. **Quantity Calculation**
```
Quantity = lot_size × num_lots
Quantity = 35 × 2 = 70 units
```

#### 2. **Daily Profit Target Calculation**
```
Base daily target per lot = ₹1000 (from DB or constant)
Quantity factor = 70 / 35 = 2.0
Daily profit target = 2.0 × ₹1000 = ₹2000
```

#### 3. **Daily Stop-Loss Calculation**
```
Daily stop-loss factor = 0.5 (50% of daily target)
Daily stop-loss = ₹2000 × 0.5 = ₹1000
```

#### 4. **Per-Trade Profit Target**
```
Per-trade profit target = ₹500 (unchanged, per trade)
```

---

## Complete Calculation Summary

| Parameter | Value | Calculation |
|-----------|-------|-------------|
| **lot_size** | 35 | From DB |
| **num_lots** | 2 | From DB |
| **Quantity** | **70** | 35 × 2 |
| **Base daily target** | ₹1000 | From DB or constant |
| **Daily profit target** | **₹2000** | (70/35) × ₹1000 = 2.0 × ₹1000 |
| **Daily stop-loss** | **₹1000** | ₹2000 × 0.5 |
| **Per-trade target** | ₹500 | Per trade (unchanged) |

---

## Daily P&L Behavior

### Daily Profit Target: ₹2000
- Trading **halts** when daily P&L reaches **₹2000**
- No new trades allowed after ₹2000 profit

### Daily Stop-Loss: -₹1000
- Trading **halts** when daily P&L reaches **-₹1000**
- No new trades allowed after -₹1000 loss

### Per-Trade Target: ₹500
- Each individual trade exits at **₹500 profit**
- This is **per trade**, not per lot

---

## Example Trading Day

### Scenario 1: Profitable Day
1. **Trade 1:** Enter 70 units → Exit at ₹500 → Daily P&L = **₹500**
2. **Trade 2:** Enter 70 units → Exit at ₹500 → Daily P&L = **₹1000**
3. **Trade 3:** Enter 70 units → Exit at ₹500 → Daily P&L = **₹1500**
4. **Trade 4:** Enter 70 units → Exit at ₹500 → Daily P&L = **₹2000** → **HALTED** ✅

**Result:** 4 trades, ₹2000 profit, trading stopped

### Scenario 2: Losing Day
1. **Trade 1:** Enter 70 units → Exit at -₹300 → Daily P&L = **-₹300**
2. **Trade 2:** Enter 70 units → Exit at -₹400 → Daily P&L = **-₹700**
3. **Trade 3:** Enter 70 units → Exit at -₹300 → Daily P&L = **-₹1000** → **HALTED** ✅

**Result:** 3 trades, -₹1000 loss, trading stopped

### Scenario 3: Mixed Day
1. **Trade 1:** Enter 70 units → Exit at ₹500 → Daily P&L = **₹500**
2. **Trade 2:** Enter 70 units → Exit at -₹200 → Daily P&L = **₹300**
3. **Trade 3:** Enter 70 units → Exit at ₹500 → Daily P&L = **₹800**
4. **Trade 4:** Enter 70 units → Exit at ₹500 → Daily P&L = **₹1300**
5. **Trade 5:** Enter 70 units → Exit at ₹500 → Daily P&L = **₹1800**
6. **Trade 6:** Enter 70 units → Exit at ₹500 → Daily P&L = **₹2300** → **HALTED** ✅

**Result:** 6 trades, ₹2300 profit (exceeded ₹2000 target), trading stopped

---

## Comparison: Different Configurations

| Configuration | Quantity | Daily Target | Daily Stop-Loss |
|--------------|----------|--------------|-----------------|
| **35 × 1** | 35 | ₹1000 | -₹500 |
| **35 × 2** | **70** | **₹2000** | **-₹1000** |
| **70 × 2** | 140 | ₹4000 | -₹2000 |

---

## Key Points

### ✅ **What Happens:**
- **Quantity:** 70 units per trade (35 × 2)
- **Daily target:** ₹2000 (2× base ₹1000)
- **Daily stop-loss:** -₹1000 (50% of ₹2000)
- **Per-trade target:** ₹500 (unchanged)

### 📊 **Daily P&L Limits:**
- **Maximum profit:** ₹2000 (then halts)
- **Maximum loss:** -₹1000 (then halts)
- **Per-trade profit:** ₹500 (each trade exits at this)

### 💡 **Important:**
- With 70 units, you need **₹500 total profit** to exit a trade (not ₹500 × 2)
- Daily target is **₹2000** (double the base ₹1000)
- You can make **4 profitable trades** of ₹500 each to reach ₹2000

---

## Terminal Output

When strategy starts, you'll see:
```
📊 Quantity from DB: lot_size=35 × num_lots=2 = 70
📊 Parameters loaded from DB: Per-trade target ₹500.00, Daily target ₹2000.00, Stop-loss -₹1000.00
🧮 Quantity: 70 | Daily target ₹2000.00 | Stop-loss -₹1000.00
```

During trading:
```
[10:15:30] Daily P&L: ₹500.00 / ₹2000.00 | Stop: -₹1000.00
[10:30:45] Daily P&L: ₹1000.00 / ₹2000.00 | Stop: -₹1000.00
[10:45:20] Daily P&L: ₹1500.00 / ₹2000.00 | Stop: -₹1000.00
[11:00:15] Daily P&L: ₹2000.00 / ₹2000.00 | Stop: -₹1000.00 | Status: HALTED
```

---

## Summary

**If you set:**
- `lot_size = 35`
- `num_lots = 2`

**Then:**
- ✅ Quantity = **70 units**
- ✅ Daily profit target = **₹2000**
- ✅ Daily stop-loss = **-₹1000**
- ✅ Per-trade target = **₹500** (unchanged)
- ✅ Trading continues until ₹2000 profit or -₹1000 loss

**The strategy will:**
1. Trade with 70 units per position
2. Exit each trade at ₹500 profit
3. Halt when daily P&L reaches ₹2000 or -₹1000
4. Show daily P&L progress in terminal


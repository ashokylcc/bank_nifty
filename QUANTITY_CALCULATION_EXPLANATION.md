# Quantity Calculation: lot_size × num_lots

## Scenario: Setting lot_size=70 and num_lots=2 in DB

### What Will Happen:

#### 1. **Quantity Calculation**
```
Quantity = lot_size × num_lots
Quantity = 70 × 2 = 140
```

#### 2. **Daily Profit Target Calculation**
```
Base daily target per lot = ₹1000 (from DB or constant)
Quantity factor = 140 / 35 = 4.0
Daily profit target = 4.0 × ₹1000 = ₹4000
```

#### 3. **Daily Stop-Loss Calculation**
```
Daily stop-loss factor = 0.5 (50% of daily target)
Daily stop-loss = ₹4000 × 0.5 = ₹2000
```

#### 4. **Per-Trade Profit Target**
```
Per-trade profit target = ₹500 (unchanged, per trade)
```

---

## Complete Calculation Summary

| Parameter | Value | Calculation |
|-----------|-------|-------------|
| **lot_size** | 70 | From DB |
| **num_lots** | 2 | From DB |
| **Quantity** | **140** | 70 × 2 |
| **Base daily target** | ₹1000 | From DB or constant |
| **Daily profit target** | **₹4000** | (140/35) × ₹1000 |
| **Daily stop-loss** | **₹2000** | ₹4000 × 0.5 |
| **Per-trade target** | ₹500 | Per trade (unchanged) |

---

## Trading Behavior

### Entry:
- **Order size:** 140 units (70 × 2)
- **Each trade:** Still exits at ₹500 profit

### Daily Limits:
- **Profit target:** ₹4000 (4× the base ₹1000)
- **Stop-loss:** ₹2000 (50% of ₹4000)
- **Trading halts:** When daily P&L reaches ₹4000 or -₹2000

### Example Trading Day:
1. **Trade 1:** Enter 140 units → Exit at ₹500 → Daily P&L = ₹500
2. **Trade 2:** Enter 140 units → Exit at ₹500 → Daily P&L = ₹1000
3. **Trade 3:** Enter 140 units → Exit at ₹500 → Daily P&L = ₹1500
4. **Trade 4:** Enter 140 units → Exit at ₹500 → Daily P&L = ₹2000
5. **Trade 5:** Enter 140 units → Exit at ₹500 → Daily P&L = ₹2500
6. **Trade 6:** Enter 140 units → Exit at ₹500 → Daily P&L = ₹3000
7. **Trade 7:** Enter 140 units → Exit at ₹500 → Daily P&L = ₹3500
8. **Trade 8:** Enter 140 units → Exit at ₹500 → Daily P&L = ₹4000 → **HALTED** ✅

---

## Priority Order

### Quantity Source Priority:
1. **Command-line `--quantity`** (if provided) → HIGHEST
2. **DB: lot_size × num_lots** (if not provided via CLI) → SECOND
3. **Constant: LOT_SIZE (35)** → FALLBACK

### Example:
```bash
# Scenario 1: No --quantity flag
python manage.py run_heikinashi_strategy
# Uses: DB (70 × 2 = 140)

# Scenario 2: With --quantity flag
python manage.py run_heikinashi_strategy --quantity 105
# Uses: Command-line (105) - DB values ignored
```

---

## What Gets Logged

When strategy starts, you'll see:
```
📊 Quantity from DB: lot_size=70 × num_lots=2 = 140
📊 Parameters loaded from DB: Per-trade target ₹500.00, Daily target ₹4000.00, Stop-loss -₹2000.00
🧮 Quantity: 140 | Daily target ₹4000.00 | Stop-loss -₹2000.00
```

---

## Important Notes

### ✅ **What Changes:**
- Order size: 35 → 140 units
- Daily profit target: ₹1000 → ₹4000
- Daily stop-loss: ₹500 → ₹2000
- P&L per trade: Still ₹500 (unchanged)

### ⚠️ **What Stays Same:**
- Per-trade profit target: ₹500 (per trade, not per lot)
- Exit logic: Same (₹500 per trade, next candle reversal, time exit)
- Entry logic: Same (LTP breakout above/below previous high/low)

### 💡 **Key Point:**
- **Per-trade target (₹500)** is **per trade**, not per lot
- With 140 units, you need ₹500 total profit to exit (not ₹500 × 4)
- Daily target scales with quantity (₹4000 for 140 units)

---

## Risk Considerations

### Increased Exposure:
- **Order size:** 4× larger (140 vs 35)
- **Daily target:** 4× larger (₹4000 vs ₹1000)
- **Daily stop-loss:** 4× larger (₹2000 vs ₹500)

### Risk Management:
- Each trade still exits at ₹500 profit (same risk per trade)
- Daily stop-loss protects against large losses (₹2000 limit)
- Position size is larger, so price movements have 4× impact

---

## Summary

**If you set:**
- `lot_size = 70`
- `num_lots = 2`

**Then:**
- ✅ Quantity = **140 units**
- ✅ Daily target = **₹4000**
- ✅ Daily stop-loss = **₹2000**
- ✅ Per-trade target = **₹500** (unchanged)
- ✅ Trading continues until ₹4000 profit or -₹2000 loss

**The strategy will automatically:**
1. Read `lot_size` and `num_lots` from DB
2. Calculate `quantity = 70 × 2 = 140`
3. Calculate daily targets based on quantity
4. Use these values for all trades


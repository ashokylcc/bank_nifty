# Default Parameters Summary

## ✅ Recommended Default Values (Starting Point)

All parameters have been set to recommended defaults. Tune based on paper trading results.

### Risk Parameters

| Parameter | Value | Calculation |
|-----------|-------|-------------|
| **capital** | ₹30,000 | Starting capital |
| **risk_per_trade_pct** | 1.00% | Risk per trade |
| **max_daily_loss** | ₹600 | 2% of ₹30,000 |
| **max_concurrent_trades** | 1 | Single position |

**Risk Calculations:**
- Risk per trade: ₹30,000 × 1% = ₹300
- Max daily loss: ₹30,000 × 2% = ₹600

---

### Trading Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| **breakout_buffer** | 10 pts | Points above/below range for breakout |
| **min_stoploss_points** | 40 pts | Minimum stoploss points |
| **stoploss_range_multiplier** | 0.6 | Stoploss as % of range |
| **target_multiplier** | 1.5 | Target as multiple of stoploss |
| **lot_size** | 35 | BankNifty lot size |
| **tick_value** | 1.00 | Point value per lot |

**Example Calculation:**
- Range: ₹200
- Stoploss: max(floor(200 × 0.6), 40) = 120 pts
- Target: 120 × 1.5 = 180 pts

---

### Momentum Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| **volume_multiplier** | 1.5x | Volume breakout threshold |
| **ema_fast** | 20 | Fast EMA period |
| **ema_slow** | 50 | Slow EMA period |
| **rsi_period** | 14 | RSI period |
| **rsi_buy_min** | 55 | RSI minimum for BUY |
| **rsi_buy_max** | 70 | RSI maximum for BUY |
| **rsi_sell_min** | 30 | RSI minimum for SELL |
| **rsi_sell_max** | 45 | RSI maximum for SELL |

**Momentum Conditions (All Required - Score = 4):**
1. ✅ Volume ≥ 1.5× average (last 5 candles)
2. ✅ EMA20 > EMA50 (BUY) or EMA20 < EMA50 (SELL)
3. ✅ RSI 55-70 (BUY) or RSI 30-45 (SELL)
4. ✅ Price momentum: Close > Open (BUY) or Close < Open (SELL)

---

### Time Windows

| Parameter | Value | Description |
|-----------|-------|-------------|
| **range_start_time** | 09:15:00 | Range detection start |
| **range_end_time** | 09:30:00 | Range detection end |
| **trade_start_time** | 09:30:00 | Trading window start |
| **trade_end_time** | 10:30:00 | Trading window end |
| **square_off_time** | 14:45:00 | Square-off time |

**Timeline:**
- **9:15-9:30 AM:** Capture first 15-min range
- **9:30-10:30 AM:** Trading window (breakout detection)
- **2:45 PM:** Square-off all positions

---

### Strike Selection

| Parameter | Value | Description |
|-----------|-------|-------------|
| **strike_step** | 100 | Strike rounding (nearest 100) |

**Example:**
- Spot: ₹58,423
- ATM Strike: Round to nearest 100 = ₹58,400
- Strong momentum: ATM ± 100

---

## Creating Strategy with Defaults

### Method 1: Management Command (Recommended)

```bash
# Create with all defaults
python manage.py create_default_strategy

# Custom name
python manage.py create_default_strategy --name "My Strategy"

# Create and enable
python manage.py create_default_strategy --enabled
```

### Method 2: Django Admin

1. Go to `/admin/trading/strategy/`
2. Click "Add Strategy"
3. Enter name
4. All fields pre-filled with defaults
5. Click "Save"

### Method 3: Python Code

```python
from trading.models import Strategy
from decimal import Decimal

strategy = Strategy.objects.create(
    name="BankNifty Momentum Breakout",
    # All defaults applied automatically
)
```

---

## Quick Reference

```python
# Risk
capital = 30000
risk_per_trade_pct = 1.00  # 1%
max_daily_loss = 600  # 2% of capital

# Trading
breakout_buffer = 10  # pts
min_stoploss_points = 40  # pts
stoploss_range_multiplier = 0.6
target_multiplier = 1.5

# Momentum
volume_multiplier = 1.5  # x avg
rsi_buy = (55, 70)
rsi_sell = (30, 45)

# Time
trade_window = (09:30, 10:30)
square_off = 14:45
```

---

## Tuning Guide

**After paper trading, adjust based on results:**

### If Win Rate < 50%
- Increase RSI thresholds (55→60, 70→75)
- Increase volume multiplier (1.5→2.0)
- Increase breakout buffer (10→15)

### If Trades Too Frequent
- Increase breakout buffer (10→15)
- Increase volume multiplier (1.5→2.0)
- Tighten RSI ranges

### If Trades Too Infrequent
- Decrease breakout buffer (10→8)
- Decrease volume multiplier (1.5→1.3)
- Widen RSI ranges

### If Drawdown Too High
- Decrease risk per trade (1%→0.5%)
- Increase min stoploss (40→50)
- Increase stoploss multiplier (0.6→0.7)

### If Profits Too Low
- Increase target multiplier (1.5→2.0)
- Decrease stoploss multiplier (0.6→0.5)
- Trade stronger trends only

---

**Last Updated:** 2025-11-13  
**Status:** ✅ Defaults set - Ready for paper trading


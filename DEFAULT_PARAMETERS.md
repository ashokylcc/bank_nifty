# Recommended Default Parameters

## Overview

These are the recommended starting point parameters for the BankNifty Momentum Breakout Strategy. Tune these based on paper trading results.

## Risk Parameters

| Parameter | Default Value | Description |
|-----------|---------------|-------------|
| **capital** | ₹30,000 | Available trading capital |
| **risk_per_trade_pct** | 1.00% | Risk per trade as % of capital |
| **max_daily_loss** | ₹600 | Maximum daily loss (2% of ₹30,000) |
| **max_concurrent_trades** | 1 | Maximum open positions |

**Calculation:**
- Risk per trade: ₹30,000 × 1% = ₹300
- Max daily loss: ₹30,000 × 2% = ₹600

---

## Trading Parameters

| Parameter | Default Value | Description |
|-----------|---------------|-------------|
| **lot_size** | 35 | BankNifty lot size |
| **tick_value** | 1.00 | Point value per lot |
| **breakout_buffer** | 10 pts | Points above/below range for breakout |
| **min_stoploss_points** | 40 pts | Minimum stoploss points |
| **stoploss_range_multiplier** | 0.6 | Stoploss as % of range |
| **target_multiplier** | 1.5 | Target as multiple of stoploss |

**Example:**
- Range: ₹200
- Stoploss: max(floor(200 × 0.6), 40) = 120 pts
- Target: 120 × 1.5 = 180 pts

---

## Momentum Parameters

| Parameter | Default Value | Description |
|-----------|---------------|-------------|
| **volume_multiplier** | 1.5x | Volume breakout threshold (1.5× avg) |
| **ema_fast** | 20 | Fast EMA period |
| **ema_slow** | 50 | Slow EMA period |
| **rsi_period** | 14 | RSI period |
| **rsi_buy_min** | 55 | RSI minimum for BUY |
| **rsi_buy_max** | 70 | RSI maximum for BUY |
| **rsi_sell_min** | 30 | RSI minimum for SELL |
| **rsi_sell_max** | 45 | RSI maximum for SELL |

**Momentum Conditions (All Required):**
1. Volume ≥ 1.5× average (last 5 candles)
2. EMA20 > EMA50 (BUY) or EMA20 < EMA50 (SELL)
3. RSI 55-70 (BUY) or RSI 30-45 (SELL)
4. Price momentum: Close > Open (BUY) or Close < Open (SELL)

---

## Time Windows

| Parameter | Default Value | Description |
|-----------|---------------|-------------|
| **range_start_time** | 09:15:00 | Range detection start |
| **range_end_time** | 09:30:00 | Range detection end |
| **trade_start_time** | 09:30:00 | Trading window start |
| **trade_end_time** | 10:30:00 | Trading window end |
| **square_off_time** | 14:45:00 | Square-off time |

**Timeline:**
- 9:15-9:30 AM: Capture first 15-min range
- 9:30-10:30 AM: Trading window (breakout detection)
- 2:45 PM: Square-off all positions

---

## Strike Selection

| Parameter | Default Value | Description |
|-----------|---------------|-------------|
| **strike_step** | 100 | Strike rounding step (nearest 100) |

**Example:**
- Spot: ₹58,423
- ATM Strike: Round to nearest 100 = ₹58,400
- Strong momentum: ATM ± 100 (₹58,500 for BUY, ₹58,300 for SELL)

---

## Creating Strategy with Defaults

### Method 1: Django Admin

1. Go to `/admin/trading/strategy/`
2. Click "Add Strategy"
3. Fill in name
4. All other fields will use recommended defaults
5. Click "Save"

### Method 2: Management Command

```bash
# Create with defaults
python manage.py create_default_strategy

# Create with custom name
python manage.py create_default_strategy --name "My Strategy"

# Create and enable immediately
python manage.py create_default_strategy --enabled
```

### Method 3: Python Code

```python
from trading.models import Strategy
from decimal import Decimal

strategy = Strategy.objects.create(
    name="BankNifty Momentum Breakout",
    capital=Decimal('30000'),
    risk_per_trade_pct=Decimal('1.00'),
    max_daily_loss=Decimal('600'),
    # ... other defaults
)
```

---

## Tuning Parameters

### Based on Paper Trading Results

**If win rate < 50%:**
- Increase `rsi_buy_min` (e.g., 55 → 60)
- Increase `rsi_sell_max` (e.g., 45 → 40)
- Increase `volume_multiplier` (e.g., 1.5 → 2.0)
- Increase `breakout_buffer` (e.g., 10 → 15)

**If trades too frequent:**
- Increase `breakout_buffer` (e.g., 10 → 15)
- Increase `volume_multiplier` (e.g., 1.5 → 2.0)
- Tighten RSI ranges

**If trades too infrequent:**
- Decrease `breakout_buffer` (e.g., 10 → 8)
- Decrease `volume_multiplier` (e.g., 1.5 → 1.3)
- Widen RSI ranges

**If drawdown too high:**
- Decrease `risk_per_trade_pct` (e.g., 1% → 0.5%)
- Increase `min_stoploss_points` (e.g., 40 → 50)
- Increase `stoploss_range_multiplier` (e.g., 0.6 → 0.7)

**If profits too low:**
- Increase `target_multiplier` (e.g., 1.5 → 2.0)
- Decrease `stoploss_range_multiplier` (e.g., 0.6 → 0.5)
- Trade stronger trends only (increase RSI thresholds)

---

## Parameter Ranges

### Safe Ranges

| Parameter | Min | Max | Recommended |
|-----------|-----|-----|--------------|
| risk_per_trade_pct | 0.5% | 2% | 1% |
| breakout_buffer | 5 | 20 | 10 |
| min_stoploss_points | 30 | 60 | 40 |
| volume_multiplier | 1.2 | 2.0 | 1.5 |
| rsi_buy_min | 50 | 60 | 55 |
| rsi_buy_max | 65 | 75 | 70 |
| rsi_sell_min | 25 | 35 | 30 |
| rsi_sell_max | 40 | 50 | 45 |

---

## Quick Reference

```python
# Recommended defaults
capital = 30000
risk_per_trade_pct = 1.00  # 1%
max_daily_loss = 600  # 2% of capital
breakout_buffer = 10  # pts
min_stoploss_points = 40  # pts
volume_multiplier = 1.5  # x avg
rsi_buy = (55, 70)
rsi_sell = (30, 45)
trade_window = (09:30, 10:30)
square_off = 14:45
```

---

**Last Updated:** 2025-11-13  
**Status:** Recommended starting point - Tune based on paper trading results


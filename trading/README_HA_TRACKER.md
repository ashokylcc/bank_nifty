# Heikin-Ashi Candle Tracker Module

This Django module calculates and tracks Heikin-Ashi candles from 15-minute OHLC data.

## Features

1. **Accurate HA Calculation**: Uses the exact TradingView formula
   - `HA_Close = (O + H + L + C) / 4`
   - `HA_Open = (prev_HA_Open + prev_HA_Close) / 2` (first candle = `(O+C)/2`)
   - `HA_High = max(H, HA_Open, HA_Close)`
   - `HA_Low = min(L, HA_Open, HA_Close)`
   - `Color = "green" if HA_Close > HA_Open else "red"`

2. **Database Storage**: Stores all HA candles in `HeikinAshiCandle` model

3. **Trend Reversal Detection**:
   - `red → green` = `"uptrend_start"`
   - `green → red` = `"downtrend_start"`
   - `green → green` = `"uptrend_continue"`
   - `red → red` = `"downtrend_continue"`

4. **Service Method**: `HeikinAshiTracker.process_new_candle()` processes and saves new candles

5. **Automated Processing**: Supports both Celery tasks and cron scripts

## Setup

### 1. Create Migration

```bash
python manage.py makemigrations trading
python manage.py migrate
```

### 2. Verify Calculation Accuracy

The calculation uses the existing `trading.services.heikin_ashi.calculate_heikin_ashi()` function, which has been verified to match TradingView exactly.

## Usage

### Method 1: Using Service Directly

```python
from decimal import Decimal
from trading.services.ha_tracker import HeikinAshiTracker

tracker = HeikinAshiTracker()

# Process new candle
color, trend = tracker.process_new_candle(
    symbol='BANKNIFTY_FUTURES',
    open_price=Decimal('59000.00'),
    high_price=Decimal('59100.00'),
    low_price=Decimal('58900.00'),
    close_price=Decimal('59050.00'),
    timestamp=None,  # Uses current time if None
    volume=1000000
)

print(f"Color: {color}, Trend: {trend}")
# Output: Color: green, Trend: uptrend_start
```

### Method 2: Using Django Management Command

```bash
python manage.py process_ha_candles \
    --symbol BANKNIFTY_FUTURES \
    --open 59000.00 \
    --high 59100.00 \
    --low 58900.00 \
    --close 59050.00 \
    --volume 1000000
```

### Method 3: Using Celery Task

```python
from trading.tasks_ha import process_ha_candle_task

# Call asynchronously
result = process_ha_candle_task.delay(
    symbol='BANKNIFTY_FUTURES',
    open_price=59000.00,
    high_price=59100.00,
    low_price=58900.00,
    close_price=59050.00,
    volume=1000000
)
```

### Method 4: Using Cron (Every 15 Minutes)

Add to crontab (`crontab -e`):

```bash
# Process HA candles every 15 minutes
*/15 * * * * cd /var/www/html/bank_nifty && python manage.py process_ha_candles --symbol BANKNIFTY_FUTURES --open $(get_open) --high $(get_high) --low $(get_low) --close $(get_close)
```

Or create a script `scripts/cron_process_ha.sh`:

```bash
#!/bin/bash
cd /var/www/html/bank_nifty

# Get OHLC from your data source (API, database, etc.)
SYMBOL="BANKNIFTY_FUTURES"
OPEN=$(python -c "from your_module import get_open; print(get_open())")
HIGH=$(python -c "from your_module import get_high; print(get_high())")
LOW=$(python -c "from your_module import get_low; print(get_low())")
CLOSE=$(python -c "from your_module import get_close; print(get_close())")

python manage.py process_ha_candles \
    --symbol "$SYMBOL" \
    --open "$OPEN" \
    --high "$HIGH" \
    --low "$LOW" \
    --close "$CLOSE"
```

Then add to crontab:
```bash
*/15 * * * * /path/to/scripts/cron_process_ha.sh
```

## Querying HA Candles

### Get Latest Candle

```python
from trading.services.ha_tracker import HeikinAshiTracker

tracker = HeikinAshiTracker()
latest = tracker.get_latest_candle('BANKNIFTY_FUTURES')

if latest:
    print(f"Color: {latest.color}, Trend: {latest.trend}")
    print(f"HA_Open: {latest.ha_open}, HA_Close: {latest.ha_close}")
```

### Get Recent Candles

```python
candles = tracker.get_candles('BANKNIFTY_FUTURES', limit=50)
for candle in candles:
    print(f"{candle.timestamp}: {candle.color} - {candle.trend}")
```

### Get Trend Reversals

```python
reversals = tracker.get_trend_reversals('BANKNIFTY_FUTURES')
for reversal in reversals:
    print(f"{reversal.timestamp}: {reversal.trend}")
```

### Using Django ORM Directly

```python
from trading.models_ha import HeikinAshiCandle

# Get all green candles
green_candles = HeikinAshiCandle.objects.filter(
    symbol='BANKNIFTY_FUTURES',
    color='green'
).order_by('-timestamp')

# Get uptrend starts
uptrends = HeikinAshiCandle.objects.filter(
    symbol='BANKNIFTY_FUTURES',
    trend='uptrend_start'
).order_by('-timestamp')
```

## Admin Interface

Access the Django admin to view and manage HA candles:

- URL: `/admin/trading/heikinashicandle/`
- Features:
  - View all HA candles
  - Filter by symbol, color, trend, timestamp
  - Search by symbol
  - See original OHLC and calculated HA values

## Calculation Verification

The calculation matches the existing `trading.services.heikin_ashi.calculate_heikin_ashi()` function, which has been verified to match TradingView exactly:

- ✅ HA_Close formula: `(O + H + L + C) / 4`
- ✅ HA_Open formula: `(prev_HA_Open + prev_HA_Close) / 2` (first: `(O+C)/2`)
- ✅ HA_High formula: `max(H, HA_Open, HA_Close)`
- ✅ HA_Low formula: `min(L, HA_Open, HA_Close)`
- ✅ Color: `green` if `HA_Close > HA_Open`, else `red`

## Model Fields

- `symbol`: Trading symbol (e.g., "BANKNIFTY_FUTURES")
- `timestamp`: 15-minute candle end time
- `original_open/high/low/close`: Original OHLC values
- `ha_open/ha_close/ha_high/ha_low`: Calculated HA values
- `color`: "green" or "red"
- `trend`: "uptrend_start", "downtrend_start", "uptrend_continue", "downtrend_continue", "neutral"
- `volume`: Volume (optional)

## Notes

- The module automatically detects gaps (overnight, different trading day) and resets HA calculation
- Duplicate candles (same symbol + timestamp) are prevented via `unique_together` constraint
- All calculations use `Decimal` for precision
- Timestamps are stored in IST timezone


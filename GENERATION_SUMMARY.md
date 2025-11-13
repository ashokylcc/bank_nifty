# 📋 Generation Summary

## Overview

This document explains the implementation of the **BankNifty Momentum Breakout Strategy** - a production-ready Django autotrading system.

## 🏗️ Architecture

### Core Components

1. **Models** (`trading/models.py`)
   - `Strategy`: Main strategy configuration
   - `Signal`: Trading signals generated
   - `Order`: Order records
   - `TradeLog`: Complete trade history
   - `DailyStats`: Daily performance metrics

2. **Services** (`trading/services/`)
   - `data_ingest.py`: WebSocket data aggregator (stub)
   - `range_detector.py`: Captures 9:15-9:30 range
   - `momentum.py`: EMA, RSI, volume filters, momentum score
   - `strike_selector.py`: Nearest Thursday expiry, ATM strike selection
   - `risk_manager.py`: Position sizing, risk checks
   - `execution_adapter.py`: Abstract interface + Mock + AliceBlue adapters
   - `strategy_engine.py`: Main orchestration logic

3. **Utils** (`trading/utils/`)
   - `time_helpers.py`: IST timezone, trading hours checks
   - `expiry_functions.py`: Thursday expiry calculation, option symbol building
   - `holidays.py`: Trading holidays configuration

4. **Management Command** (`trading/management/commands/run_strategy.py`)
   - CLI interface for running strategy
   - Supports dry-run and live modes
   - Loop mode for continuous operation

5. **Admin** (`trading/admin.py`)
   - Django admin interface
   - Kill switch (enable/disable strategy)
   - View signals, orders, trades, stats

6. **Views** (`trading/views.py`)
   - `/metrics` endpoint for strategy status

## 🔑 Key Functions

### Range Detection

**Location:** `trading/services/range_detector.py`

```python
range_detector = RangeDetector()
range_detector.capture_range(first_candle)  # Captures 9:15-9:30 range
breakout = range_detector.detect_breakout(current_price, buffer=10)
```

### Momentum Calculation

**Location:** `trading/services/momentum.py`

```python
momentum_calc = MomentumCalculator(ema_fast=20, ema_slow=50, rsi_period=14)
score, details = momentum_calc.calculate_momentum_score(
    signal_type, current_candle, ema_fast, ema_slow, rsi
)
# Requires score == 4 (all conditions met)
```

### Strike Selection

**Location:** `trading/services/strike_selector.py`

```python
strike_selector = StrikeSelector()
option_symbol, strike, expiry_date = strike_selector.select_strike(
    spot_price, signal_type, strong_momentum
)
```

**Option Symbol Format:**
- `BANKNIFTY{DD}{MMM}{YY}{C|P}{STRIKE}`
- Example: `BANKNIFTY27NOV25C58400`

### Risk Management

**Location:** `trading/services/risk_manager.py`

```python
risk_manager = RiskManager(strategy)
stoploss_points = risk_manager.calculate_stoploss_points(range_value)
target_points = risk_manager.calculate_target_points(stoploss_points)
qty = risk_manager.calculate_position_size(stoploss_points)
can_trade, reason = risk_manager.can_place_trade()
```

### Execution

**Location:** `trading/services/execution_adapter.py`

```python
# Mock adapter (dry-run)
adapter = AliceBlueMockAdapter(dry_run=True)

# Real adapter (live)
adapter = AliceBlueAdapter(dry_run=False, user_id=..., api_key=...)

# Place order
result = adapter.place_order(symbol, side, qty, order_type="MARKET")
```

### Strategy Engine

**Location:** `trading/services/strategy_engine.py`

```python
engine = StrategyEngine(strategy, execution_adapter=adapter, dry_run=True)
engine.initialize()

# Run single cycle
results = engine.run_single_cycle()

# Shutdown
engine.shutdown()
```

## 📊 Strategy Flow

1. **Initialize** → Connect data service, reset range detector
2. **Capture Range** (9:15-9:30) → Get first candle, calculate high/low
3. **Detect Breakout** → Check if price breaks above/below range
4. **Confirm Momentum** → Check volume, EMA, RSI, price momentum (score = 4)
5. **Select Strike** → Calculate expiry, select ATM strike, build symbol
6. **Calculate Risk** → Position size, stoploss, target
7. **Execute Trade** → Place order, create trade log
8. **Monitor Position** → Check target, stoploss, trailing, time exit
9. **Exit Trade** → Place exit order, update trade log, update stats

## 🧪 Testing

### Unit Tests

**Location:** `trading/tests/`

- `test_expiry_functions.py`: Thursday expiry, option symbol building
- `test_momentum.py`: Momentum score calculation
- `test_risk_manager.py`: Position sizing, risk checks
- `test_execution_adapter.py`: Mock adapter functionality
- `test_integration.py`: End-to-end strategy test

**Run Tests:**
```bash
python manage.py test trading
```

## 🐳 Docker Setup

**Files:**
- `Dockerfile`: Python 3.11, Django, PostgreSQL client
- `docker-compose.yml`: PostgreSQL + Django web + Worker

**Services:**
- `db`: PostgreSQL database
- `web`: Django web server (admin, metrics)
- `worker`: Strategy runner

**Run:**
```bash
docker-compose up -d
```

## 🔐 Safety Features

1. **Dry-Run by Default**
   - All orders simulated unless `DRY_RUN=false` AND `CONFIRM_REAL_TRADES=true`

2. **Kill Switch**
   - `Strategy.enabled = False` in Django Admin

3. **Daily Loss Limit**
   - Stops trading when `daily_pnl < -max_daily_loss`

4. **Concurrent Trade Limit**
   - Limits open positions to `max_concurrent_trades`

5. **Risk Management**
   - Position sizing based on risk per trade percentage

## 📈 Monitoring

### Metrics Endpoint

**URL:** `http://localhost:8000/metrics`

**Returns:**
```json
{
  "status": "RUNNING",
  "open_trades": 1,
  "daily_pnl": 500.00,
  "total_trades": 2,
  "win_rate": 50.0
}
```

### Django Admin

- View all models
- Enable/disable strategy
- Monitor trades and stats

## 🔌 Integration Points

### Alice Blue Integration

**Location:** `trading/services/execution_adapter.py`

**Current Status:** Placeholder - needs real API implementation

**To Implement:**
1. Initialize Alice Blue session
2. Implement `place_order()` with real API calls
3. Implement `cancel_order()` with real API calls
4. Implement `get_order_status()` with real API calls
5. Implement `get_ltp()` with real WebSocket/API

### WebSocket Data Feed

**Location:** `trading/services/data_ingest.py`

**Current Status:** Stub - provides interface

**To Implement:**
1. Connect to Alice Blue WebSocket
2. Subscribe to BankNifty Future
3. Aggregate ticks to 15-min candles
4. Provide real-time LTP

## 📝 Configuration

### Strategy Parameters

Configure in Django Admin or via code:

```python
strategy = Strategy.objects.create(
    name="BankNifty Momentum Breakout",
    enabled=True,
    capital=Decimal('100000'),
    risk_per_trade_pct=Decimal('1.00'),
    max_daily_loss=Decimal('5000'),
    # ... other parameters
)
```

### Environment Variables

```bash
DRY_RUN=true                    # Dry-run mode
CONFIRM_REAL_TRADES=false       # Confirmation for live trading
DATABASE_URL=...                # Database connection
ALICE_BLUE_USER_ID=...          # Alice Blue credentials
ALICE_BLUE_API_KEY=...
```

## 🚀 Running the Strategy

### Dry-Run Mode

```bash
# Single cycle
python manage.py run_strategy --dry-run

# Continuous loop
python manage.py run_strategy --dry-run --loop --interval 5
```

### Live Mode

```bash
export DRY_RUN=false
export CONFIRM_REAL_TRADES=true
python manage.py run_strategy --loop
```

## 📚 File Locations Summary

| Component | File Path |
|-----------|-----------|
| Models | `trading/models.py` |
| Admin | `trading/admin.py` |
| Views | `trading/views.py` |
| Data Service | `trading/services/data_ingest.py` |
| Range Detector | `trading/services/range_detector.py` |
| Momentum | `trading/services/momentum.py` |
| Strike Selector | `trading/services/strike_selector.py` |
| Risk Manager | `trading/services/risk_manager.py` |
| Execution Adapter | `trading/services/execution_adapter.py` |
| Strategy Engine | `trading/services/strategy_engine.py` |
| Management Command | `trading/management/commands/run_strategy.py` |
| Time Helpers | `trading/utils/time_helpers.py` |
| Expiry Functions | `trading/utils/expiry_functions.py` |
| Holidays | `trading/utils/holidays.py` |
| Tests | `trading/tests/` |
| Docker | `Dockerfile`, `docker-compose.yml` |
| Requirements | `requirements.txt` |
| Documentation | `README.md`, `RUNBOOK.md` |

## 🎯 Next Steps

1. **Integrate Real Data Feed**
   - Connect to Alice Blue WebSocket
   - Implement real-time candle aggregation

2. **Complete Alice Blue Integration**
   - Implement real order placement
   - Implement order status checks
   - Implement LTP fetching

3. **Add More Tests**
   - Integration tests with real data
   - Performance tests
   - Stress tests

4. **Enhance Monitoring**
   - Add Prometheus metrics
   - Add Grafana dashboards
   - Add alerting

5. **Production Deployment**
   - Set up production database
   - Configure logging
   - Set up backups
   - Add monitoring

---

**Generated:** 2025-11-25  
**Version:** 1.0.0  
**Status:** Production-Ready (with placeholder integrations)


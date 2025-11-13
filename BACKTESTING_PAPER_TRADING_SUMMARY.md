# Backtesting & Paper Trading - Implementation Summary

## ✅ Complete Implementation

### 1. Backtesting Command

**Location:** `trading/management/commands/backtest.py`

**Features:**
- Processes historical CSV files (3-12 months)
- Calculates comprehensive metrics
- Supports custom date ranges
- Exports results to CSV

**Metrics Calculated:**
1. **CAGR** - Compound Annual Growth Rate
2. **Win Rate** - Percentage of winning trades
3. **Profit Factor** - Gross Profit / Gross Loss
4. **Sharpe-like** - Mean Daily PnL / Std Dev
5. **Max Drawdown** - Maximum peak-to-trough decline
6. **Average Win/Loss** - Average win / Average loss
7. **Trade Frequency** - Trades per trading day
8. **Daily PnL Distribution** - Min, Max, Median

**Usage:**
```bash
# Basic backtest (3 months default)
python manage.py backtest --csv-dir historical_data/

# Custom date range
python manage.py backtest --csv-dir historical_data/ \
    --start-date 2024-01-01 --end-date 2024-12-31

# Save results
python manage.py backtest --csv-dir historical_data/ \
    --output backtest_results.csv
```

---

### 2. Slippage Simulation

**Location:** `trading/services/execution_adapter.py`

**Features:**
- Configurable slippage: 0.1-0.4%
- Random variation: 0.5x to 1.5x
- Realistic order fills:
  - Buy orders: Fill at higher price
  - Sell orders: Fill at lower price

**Configuration:**
```python
adapter = AliceBlueMockAdapter(
    dry_run=True,
    slippage_pct=0.2,  # 0.2% slippage
    commission_per_lot=20.0  # ₹20 per lot
)
```

**Slippage Levels:**
- **Conservative:** 0.1% (tight markets)
- **Standard:** 0.2% (normal conditions) - Default
- **Aggressive:** 0.3-0.4% (volatile markets)

---

### 3. Commission Simulation

**Features:**
- Per-lot commission
- Applied to both entry and exit
- Automatically deducted from PnL

**Calculation:**
```
Total Commission = 2 × qty × commission_per_lot
```

**Example:**
- Qty: 16 lots
- Commission: ₹20/lot
- Total: 2 × 16 × 20 = ₹640

---

### 4. Paper Trading Setup

**Live Data Integration:**
- `data_ingest_live.py` - WebSocket integration stub
- Ready for Alice Blue WebSocket
- Real-time tick aggregation

**Paper Trading Mode:**
```bash
# Real WebSocket data + Mock execution
DRY_RUN=true python manage.py run_momentum_strategy --loop
```

**Requirements:**
- Minimum 10 trading days
- Minimum 100 trades
- Compare vs. backtest results

---

### 5. Pre-Live Checklist

**File:** `PRE_LIVE_CHECKLIST.md`

**5 Phases:**
1. **Backtesting** - Historical data validation
2. **Paper Trading** - Live data, mock execution
3. **Risk Management** - Position sizing, stoploss, limits
4. **System Readiness** - Infrastructure, monitoring
5. **Final Checks** - Configuration, documentation

**Go-Live Requirements:**
- ✅ All phases completed
- ✅ `DRY_RUN=false`
- ✅ `CONFIRM_REAL_TRADES=true`
- ✅ At least 2 approvals
- ✅ Start with minimum capital

---

## 📊 Recommended Workflow

### Step 1: Backtest (3-12 months)

```bash
# Collect historical data
# Format: CSV files in historical_data/ directory

# Run backtest
python manage.py backtest --csv-dir historical_data/ \
    --start-date 2024-01-01 --end-date 2024-12-31

# Review metrics
# - CAGR ≥ 15-20%
# - Win Rate ≥ 50%
# - Profit Factor ≥ 1.5
# - Max Drawdown < 20%
```

### Step 2: Paper Trading (10+ days, 100+ trades)

```bash
# Integrate real WebSocket (update data_ingest_live.py)
# Run paper trading
DRY_RUN=true python manage.py run_momentum_strategy --loop

# Monitor for 10+ trading days
# Compare results vs. backtest
```

### Step 3: Validate Results

```bash
# Run validation
python manage.py validate_simulation

# Check all metrics
# - Win rate matches backtest (±5%)
# - Average PnL matches backtest (±10%)
# - Slippage impact understood
```

### Step 4: Go Live (After Checklist)

```bash
# Complete PRE_LIVE_CHECKLIST.md
# Get approvals
# Set environment:
export DRY_RUN=false
export CONFIRM_REAL_TRADES=true

# Start trading
python manage.py run_momentum_strategy --loop
```

---

## 📈 Metrics Targets

| Metric | Target | Description |
|--------|--------|-------------|
| CAGR | ≥ 15-20% | Compound Annual Growth Rate |
| Win Rate | ≥ 50% | Percentage of winning trades |
| Profit Factor | ≥ 1.5 | Gross Profit / Gross Loss |
| Sharpe-like | ≥ 1.0 | Mean / Std Dev of daily PnL |
| Max Drawdown | < 20% | Maximum decline from peak |
| Avg Win/Loss | ≥ 1.5 | Average win / Average loss |
| Trade Frequency | 1-3/day | Trades per trading day |

---

## 🔧 Configuration Examples

### Backtest with Slippage

```python
# In backtest.py, adapter is created with default slippage
adapter = AliceBlueMockAdapter(
    dry_run=True,
    slippage_pct=0.2,  # 0.2% slippage
    commission_per_lot=20.0  # ₹20 per lot
)
```

### Paper Trading with Custom Slippage

```python
# Update strategy_engine.py or create custom adapter
adapter = AliceBlueMockAdapter(
    dry_run=True,
    slippage_pct=0.3,  # Higher slippage for volatile markets
    commission_per_lot=25.0  # Higher commission
)
```

---

## 📚 Documentation

- `BACKTESTING_GUIDE.md` - Detailed backtesting instructions
- `PRE_LIVE_CHECKLIST.md` - Pre-live checklist
- `VALIDATION_GUIDE.md` - Validation interpretation
- `INTEGRATION_SUMMARY.md` - Integration overview

---

## ✅ Status

**Backtesting:** ✅ Ready  
**Paper Trading:** ✅ Ready (WebSocket integration needed)  
**Slippage Simulation:** ✅ Working  
**Commission Simulation:** ✅ Working  
**Pre-Live Checklist:** ✅ Complete  

---

**Last Updated:** 2025-11-13


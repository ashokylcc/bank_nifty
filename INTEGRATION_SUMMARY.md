# Integration Summary - Backtesting & Paper Trading

## ✅ Implementation Complete

### 1. Backtesting System

**Command:** `python manage.py backtest`

**Features:**
- Processes historical CSV files (3-12 months)
- Calculates comprehensive metrics:
  - CAGR (Compound Annual Growth Rate)
  - Win Rate
  - Profit Factor
  - Sharpe-like Metric (Mean/SD)
  - Max Drawdown
  - Average Win/Loss Ratio
  - Trade Frequency
  - Daily PnL Distribution

**Usage:**
```bash
# Basic backtest
python manage.py backtest --csv-dir historical_data/

# Custom date range
python manage.py backtest --csv-dir historical_data/ \
    --start-date 2024-01-01 --end-date 2024-12-31

# Save results
python manage.py backtest --csv-dir historical_data/ \
    --output backtest_results.csv
```

---

### 2. Slippage & Commission Simulation

**Mock Adapter Enhanced:**
- Slippage simulation: 0.1-0.4% (configurable)
- Commission simulation: Per lot basis
- Realistic order fills with random variation

**Configuration:**
```python
adapter = AliceBlueMockAdapter(
    dry_run=True,
    slippage_pct=0.2,  # 0.2% slippage
    commission_per_lot=20.0  # ₹20 per lot
)
```

**Slippage Behavior:**
- Buy orders: Fill at higher price (slippage against you)
- Sell orders: Fill at lower price (slippage against you)
- Random variation: 0.5x to 1.5x of base slippage

---

### 3. Paper Trading Setup

**Live Data Integration:**
- `data_ingest_live.py` - WebSocket integration stub
- Ready for Alice Blue WebSocket connection
- Real-time tick aggregation to 15-min candles

**Paper Trading Mode:**
```bash
# Real data, mock execution
DRY_RUN=true python manage.py run_momentum_strategy --loop
```

**Requirements:**
- Minimum 10 trading days
- Minimum 100 trades
- Compare results vs. backtest

---

### 4. Pre-Live Checklist

**File:** `PRE_LIVE_CHECKLIST.md`

**Phases:**
1. ✅ Backtesting (3-12 months historical data)
2. ✅ Paper Trading (10+ days, 100+ trades)
3. ✅ Risk Management (position sizing, stoploss, limits)
4. ✅ System Readiness (infrastructure, monitoring)
5. ✅ Final Checks (configuration, documentation, team)

**Go-Live Requirements:**
- `DRY_RUN=false`
- `CONFIRM_REAL_TRADES=true`
- All checklist items completed
- At least 2 approvals

---

## 📊 Metrics Tracking

### Backtest Metrics

| Metric | Target | Description |
|--------|--------|-------------|
| CAGR | ≥ 15-20% | Compound Annual Growth Rate |
| Win Rate | ≥ 50% | Percentage of winning trades |
| Profit Factor | ≥ 1.5 | Gross Profit / Gross Loss |
| Sharpe-like | ≥ 1.0 | Mean Daily PnL / Std Dev |
| Max Drawdown | < 20% | Maximum peak-to-trough decline |
| Avg Win/Loss | ≥ 1.5 | Average win / Average loss |
| Trade Frequency | 1-3/day | Trades per trading day |

### Paper Trading Validation

**Compare Paper vs. Backtest:**
- Win rate: ±5% tolerance
- Average PnL: ±10% tolerance
- Account for slippage impact
- Verify system stability

---

## 🔧 Configuration

### Slippage Settings

**Conservative (Tight Markets):**
```python
slippage_pct=0.1  # 0.1%
```

**Standard (Normal Conditions):**
```python
slippage_pct=0.2  # 0.2% (default)
```

**Aggressive (Volatile Markets):**
```python
slippage_pct=0.3  # 0.3-0.4%
```

### Commission Settings

**Alice Blue (Example):**
```python
commission_per_lot=20.0  # ₹20 per lot
```

**Total Commission per Trade:**
- Entry: `qty * commission_per_lot`
- Exit: `qty * commission_per_lot`
- Total: `2 * qty * commission_per_lot`

---

## 📝 Next Steps

### 1. Collect Historical Data

**Format:** CSV with columns: `timestamp,open,high,low,close,volume`

**Directory Structure:**
```
historical_data/
├── 2024-01-01.csv
├── 2024-01-02.csv
└── ...
```

### 2. Run Backtest

```bash
python manage.py backtest --csv-dir historical_data/ --output results.csv
```

### 3. Analyze Results

- Review all metrics
- Validate against targets
- Identify areas for improvement

### 4. Paper Trading

- Integrate real WebSocket feed
- Run for 10+ trading days
- Compare vs. backtest
- Adjust parameters if needed

### 5. Go Live

- Complete `PRE_LIVE_CHECKLIST.md`
- Get approvals
- Start with minimum capital
- Monitor closely

---

## 📚 Documentation

- `BACKTESTING_GUIDE.md` - Detailed backtesting instructions
- `PRE_LIVE_CHECKLIST.md` - Pre-live checklist
- `VALIDATION_GUIDE.md` - Validation interpretation
- `README.md` - Main documentation

---

**Status:** ✅ Ready for backtesting and paper trading  
**Last Updated:** 2025-11-13


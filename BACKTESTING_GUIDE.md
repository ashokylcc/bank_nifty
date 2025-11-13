# Backtesting & Paper Trading Guide

## Overview

This guide covers the recommended order for backtesting and paper trading before going live.

## Phase 1: Backtesting on Historical Data

### Step 1: Prepare Historical Data

**Data Requirements:**
- 15-minute OHLCV candles
- Format: CSV with columns: `timestamp,open,high,low,close,volume`
- Filename format: `YYYY-MM-DD.csv` or `YYYYMMDD.csv`
- Minimum: 3 months, Recommended: 6-12 months

**Example CSV:**
```csv
timestamp,open,high,low,close,volume
2025-01-01T09:15:00,58400,58500,58300,58450,10000
2025-01-01T09:30:00,58450,58550,58400,58500,12000
...
```

**Directory Structure:**
```
historical_data/
├── 2025-01-01.csv
├── 2025-01-02.csv
├── 2025-01-03.csv
└── ...
```

### Step 2: Run Backtest

```bash
# Basic backtest (3 months default)
python manage.py backtest --csv-dir historical_data/

# Custom date range
python manage.py backtest --csv-dir historical_data/ \
    --start-date 2024-01-01 \
    --end-date 2024-12-31

# Save results to file
python manage.py backtest --csv-dir historical_data/ \
    --output backtest_results.csv
```

### Step 3: Analyze Results

**Key Metrics to Track:**

1. **CAGR (Compound Annual Growth Rate)**
   - Target: ≥ 15-20%
   - Formula: `((Final Capital / Initial Capital) ^ (1 / Years) - 1) * 100`

2. **Win Rate**
   - Target: ≥ 50%
   - Formula: `(Winning Trades / Total Trades) * 100`

3. **Profit Factor**
   - Target: ≥ 1.5
   - Formula: `Gross Profit / Gross Loss`

4. **Sharpe-like Metric**
   - Target: ≥ 1.0
   - Formula: `Mean Daily PnL / Std Dev Daily PnL`

5. **Max Drawdown**
   - Target: < 20% of capital
   - Maximum peak-to-trough decline

6. **Average Win/Loss Ratio**
   - Target: ≥ 1.5
   - Formula: `Average Win / Average Loss`

7. **Trade Frequency**
   - Target: 1-3 trades per day
   - Formula: `Total Trades / Trading Days`

**Example Output:**
```
📊 BACKTEST RESULTS
======================================================================

📈 Trade Statistics:
   Total Trades: 150
   Winning: 85 (56.67%)
   Losing: 65
   Trade Frequency: 1.25 trades/day
   Trading Days: 120

💰 P&L Metrics:
   Total PnL: ₹45,000.00
   Gross Profit: ₹75,000.00
   Gross Loss: ₹30,000.00
   Average Win: ₹882.35
   Average Loss: ₹461.54
   Profit Factor: 2.50

⚠️  Risk Metrics:
   Max Drawdown: ₹8,500.00
   Sharpe-like (Mean/SD): 1.85

🚀 Performance Metrics:
   CAGR: 18.50%
   Mean Daily PnL: ₹375.00
   Std Daily PnL: ₹202.50
```

### Step 4: Validate Results

```bash
# Run validation after backtest
python manage.py validate_simulation
```

**Acceptance Criteria:**
- ✅ All validations pass
- ✅ Metrics meet targets
- ✅ No unexpected behavior
- ✅ Results consistent across different periods

---

## Phase 2: Paper Trading (Live Data, Mock Execution)

### Step 1: Integrate Real WebSocket Feed

**Update `data_ingest_live.py`:**

```python
from strategy.broker.websocket_ltp import WebSocketLTP

class LiveDataIngestService(DataIngestService):
    def connect(self):
        self.ws_client = WebSocketLTP()
        self.ws_client.connect()
        self.ws_client.set_callback(self.on_tick_received)
        self._connected = True
    
    def subscribe(self, symbol):
        self.ws_client.subscribe(symbol)
```

### Step 2: Configure Mock Adapter with Slippage

**In `run_momentum_strategy.py` or strategy engine:**

```python
# Create adapter with slippage simulation
adapter = AliceBlueMockAdapter(
    dry_run=True,
    slippage_pct=0.2,  # 0.2% slippage
    commission_per_lot=20.0  # ₹20 per lot commission
)
```

**Slippage Configuration:**
- **Conservative:** 0.1% (tight markets, high liquidity)
- **Standard:** 0.2% (normal conditions)
- **Aggressive:** 0.3-0.4% (volatile markets, low liquidity)

### Step 3: Run Paper Trading

```bash
# Paper trading mode (real data, mock execution)
DRY_RUN=true python manage.py run_momentum_strategy --loop

# Or with custom adapter settings
DRY_RUN=true python manage.py run_momentum_strategy --loop \
    --slippage 0.2 \
    --commission 20
```

### Step 4: Monitor Paper Trading

**Daily Checks:**
- [ ] All trades execute correctly
- [ ] Slippage impact within expected range
- [ ] PnL matches backtest expectations (±10%)
- [ ] No system errors or disconnects
- [ ] WebSocket connection stable

**Metrics to Track:**
- Win rate vs. backtest
- Average PnL vs. backtest
- Slippage impact on profits
- System uptime
- Order fill rates

**Minimum Duration:**
- **Minimum:** 10 trading days
- **Recommended:** 20-30 trading days
- **Minimum Trades:** 100 trades

### Step 5: Validate Paper Trading Results

**Compare Paper vs. Backtest:**
- Win rate should match (±5%)
- Average PnL should match (±10%)
- Account for slippage impact
- Verify system stability

**If Results Don't Match:**
1. Check slippage assumptions
2. Review commission impact
3. Verify data quality
4. Check for execution delays
5. Review market conditions

---

## Phase 3: Pre-Live Checklist

**Before going live, complete `PRE_LIVE_CHECKLIST.md`:**

1. ✅ All backtesting complete
2. ✅ Paper trading results acceptable
3. ✅ Risk management verified
4. ✅ System infrastructure ready
5. ✅ Team trained and ready

**Go-Live Requirements:**
- `DRY_RUN=false`
- `CONFIRM_REAL_TRADES=true`
- At least 2 approvals
- Start with minimum capital

---

## Slippage & Commission Configuration

### Slippage Simulation

The mock adapter simulates slippage based on:
- **Order Type:** Market orders have higher slippage
- **Side:** Buy orders fill higher, Sell orders fill lower
- **Random Variation:** 0.5x to 1.5x of base slippage percentage

**Example:**
```python
# Base price: ₹100
# Slippage: 0.2%
# Buy order: Fills at ₹100.20 (worse)
# Sell order: Fills at ₹99.80 (worse)
```

### Commission Simulation

Configure commission per lot:
```python
adapter = AliceBlueMockAdapter(
    commission_per_lot=20.0  # ₹20 per lot
)
```

**Commission Calculation:**
- Entry: `qty * commission_per_lot`
- Exit: `qty * commission_per_lot`
- Total: `2 * qty * commission_per_lot`

---

## Troubleshooting

### Issue: Backtest shows profits but paper trading shows losses

**Possible Causes:**
1. Slippage not accounted for in backtest
2. Commission not included in backtest
3. Real market conditions differ from historical
4. Execution delays in live trading

**Fix:**
- Increase slippage simulation in backtest
- Add commission to backtest
- Review market conditions
- Check execution timing

### Issue: WebSocket disconnects frequently

**Fix:**
- Implement reconnection logic
- Add exponential backoff
- Monitor connection health
- Use heartbeat/ping mechanism

### Issue: Orders not filling in paper trading

**Fix:**
- Check mock adapter configuration
- Verify LTP is being updated
- Check order placement logic
- Review execution adapter code

---

## Next Steps

After successful paper trading:

1. **Review Results:** Compare paper vs. backtest
2. **Adjust Parameters:** Fine-tune if needed
3. **Complete Checklist:** Finish `PRE_LIVE_CHECKLIST.md`
4. **Get Approvals:** Team review and approval
5. **Start Small:** Begin with minimum capital
6. **Monitor Closely:** First week critical

---

**Last Updated:** 2025-11-13


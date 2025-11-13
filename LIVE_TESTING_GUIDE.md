# Live Testing Guide - Real Data, Mock Execution

## Overview

This guide explains how to run the strategy with **real market data** (Alice Blue WebSocket) but **mock order execution** (no real trades). This gives the most realistic paper trading experience.

---

## 1. Configuration Setup

### Step 1: Update `.env` File

Make sure your `.env` file has these settings:

```bash
# Trading Mode
DRY_RUN=true
CONFIRM_REAL_TRADES=false
LOG_LEVEL=INFO

# Alice Blue Credentials (for WebSocket data only)
ALICE_BLUE_USER_ID=your_user_id_here
ALICE_BLUE_API_KEY=your_api_key_here
```

**Important:**
- ✅ `DRY_RUN=true` - No real orders will be placed
- ✅ `CONFIRM_REAL_TRADES=false` - Additional safety check
- ✅ `LOG_LEVEL=INFO` - See detailed logs

---

## 2. Verify Configuration

### Check Environment Variables

```bash
# Check if .env is loaded
python manage.py shell -c "import os; print('DRY_RUN:', os.getenv('DRY_RUN')); print('CONFIRM_REAL_TRADES:', os.getenv('CONFIRM_REAL_TRADES'))"
```

**Expected Output:**
```
DRY_RUN: true
CONFIRM_REAL_TRADES: false
```

---

## 3. Run Live Test with Mock Execution

### Option A: At Market Open (Recommended)

**Best Time:** 9:15 AM IST (when range detection starts)

```bash
# Run with live WebSocket data, mock execution
python manage.py run_momentum_strategy --loop --live-data --dry-run
```

**What This Does:**
- ✅ Connects to Alice Blue WebSocket for real market prices
- ✅ Uses mock execution adapter (no real orders)
- ✅ Runs continuously in loop mode
- ✅ Shows all strategy logic, entries/exits, PnL

**Output Example:**
```
✅ DRY-RUN MODE - No real orders
📡 Connecting to live WebSocket feed...
✅ Connected to live data feed
🔔 Subscribed to: BANKNIFTY
🔄 Starting continuous loop (interval: 5s)
✅ Range captured
🎯 Breakout detected
📝 Signal created
✅ Trade executed
```

---

### Option B: Single Cycle Test

```bash
# Run single cycle with live data
python manage.py run_momentum_strategy --live-data --dry-run
```

---

## 4. What You'll See

### Strategy Logic
- ✅ Range detection (9:15-9:30 AM)
- ✅ Breakout detection
- ✅ Momentum confirmation
- ✅ Strike selection
- ✅ Risk management checks

### Trade Execution (Simulated)
- ✅ Entry orders (mock)
- ✅ Exit orders (mock)
- ✅ PnL calculations
- ✅ Commission & slippage simulation

### Logs
- ✅ Strategy decisions
- ✅ Trade entries/exits
- ✅ PnL per trade
- ✅ Daily statistics

---

## 5. Monitoring

### Check Strategy Status

```bash
# View metrics
curl http://localhost:8000/metrics
```

**Response:**
```json
{
  "status": "running",
  "strategy": "BankNifty Momentum Breakout",
  "dry_run": true,
  "open_trades": 0,
  "daily_pnl": 0.00,
  "range_captured": true
}
```

### View Trade Logs

```bash
# Django Admin
# Go to: http://localhost:8000/admin/trading/tradelog/
```

---

## 6. Safety Checks

### Before Running

1. ✅ Verify `DRY_RUN=true` in `.env`
2. ✅ Verify `CONFIRM_REAL_TRADES=false`
3. ✅ Check strategy is enabled in Django Admin
4. ✅ Verify Alice Blue credentials (for WebSocket only)

### During Execution

- ✅ All orders show `dry_run=True` in logs
- ✅ No real money is at risk
- ✅ Strategy logic runs normally
- ✅ PnL is calculated but not real

---

## 7. Troubleshooting

### Issue: WebSocket Not Connecting

**Symptoms:**
```
❌ Failed to connect to live data feed
```

**Fix:**
1. Check Alice Blue credentials in `.env`
2. Verify network connection
3. Check if market is open (9:15 AM - 3:30 PM IST)
4. Review WebSocket logs

### Issue: No Ticks Received

**Symptoms:**
```
⏳ Waiting for LTP...
```

**Fix:**
1. Verify subscription to BANKNIFTY
2. Check WebSocket connection status
3. Ensure market is open
4. Review `data_ingest_live.py` logs

### Issue: Strategy Not Running

**Symptoms:**
```
❌ No active strategy found
```

**Fix:**
1. Create strategy: `python manage.py create_default_strategy`
2. Enable strategy in Django Admin
3. Check strategy ID: `python manage.py run_momentum_strategy --strategy-id 1`

---

## 8. Comparison: Live Test vs. Simulation

| Feature | Live Test (`--live-data`) | Simulation (`--simulate`) |
|---------|---------------------------|--------------------------|
| **Data Source** | Real WebSocket | CSV file |
| **Market Prices** | Real-time | Historical |
| **Order Execution** | Mock | Mock |
| **Timing** | Real market hours | Any time |
| **Realism** | Highest | Medium |
| **Use Case** | Paper trading | Backtesting |

---

## 9. Recommended Workflow

### Phase 1: Simulation (Historical Data)
```bash
# Test with historical CSV
python manage.py run_momentum_strategy --simulate --csv historical_data/2024-11-25.csv --once
```

### Phase 2: Live Test (Real Data, Mock Orders)
```bash
# Paper trade with real market data
python manage.py run_momentum_strategy --loop --live-data --dry-run
```

### Phase 3: Go Live (After Validation)
```bash
# Only after thorough testing
# Set DRY_RUN=false and CONFIRM_REAL_TRADES=true
python manage.py run_momentum_strategy --loop
```

---

## 10. Best Practices

### Before Market Open
1. ✅ Start strategy at 9:10 AM (5 minutes before range detection)
2. ✅ Verify WebSocket connection
3. ✅ Check strategy is enabled
4. ✅ Review previous day's results

### During Trading
1. ✅ Monitor logs for errors
2. ✅ Check metrics endpoint periodically
3. ✅ Watch for unexpected behavior
4. ✅ Keep kill switch accessible (Django Admin)

### After Market Close
1. ✅ Review all trades
2. ✅ Check daily statistics
3. ✅ Analyze PnL
4. ✅ Adjust parameters if needed

---

## 11. Command Reference

### Basic Commands

```bash
# Live data, mock execution, loop mode
python manage.py run_momentum_strategy --loop --live-data --dry-run

# Live data, single cycle
python manage.py run_momentum_strategy --live-data --dry-run

# Specific strategy ID
python manage.py run_momentum_strategy --strategy-id 1 --loop --live-data --dry-run

# Custom interval
python manage.py run_momentum_strategy --loop --live-data --dry-run --interval 10
```

### Environment Variables

```bash
# Override .env settings
DRY_RUN=true CONFIRM_REAL_TRADES=false python manage.py run_momentum_strategy --loop --live-data
```

---

## 12. Expected Behavior

### At 9:15 AM
- ✅ Strategy starts
- ✅ WebSocket connects
- ✅ Range detection begins

### At 9:30 AM
- ✅ Range captured
- ✅ Trading window opens
- ✅ Breakout detection active

### During Trading Hours (9:30 AM - 10:30 AM)
- ✅ Breakout signals generated
- ✅ Momentum confirmed
- ✅ Trades executed (mock)
- ✅ Positions monitored

### At 2:45 PM
- ✅ Square-off all positions
- ✅ Daily statistics updated

---

## Summary

**Live Testing with Mock Execution:**
- ✅ Real market data (WebSocket)
- ✅ Mock order execution (no real trades)
- ✅ Full strategy logic
- ✅ Realistic PnL simulation
- ✅ Safe for testing

**Command:**
```bash
python manage.py run_momentum_strategy --loop --live-data --dry-run
```

**Safety:**
- ✅ `DRY_RUN=true` - No real orders
- ✅ `CONFIRM_REAL_TRADES=false` - Additional check
- ✅ All orders marked `dry_run=True`

---

**Last Updated:** 2025-11-13  
**Status:** ✅ Ready for live testing


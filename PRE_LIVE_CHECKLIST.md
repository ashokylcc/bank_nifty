# Pre-Live Trading Checklist

**⚠️ CRITICAL: Only proceed to live trading after ALL items are checked ✅**

## Phase 1: Backtesting ✅

- [ ] **Historical Data Collected**
  - [ ] 3-12 months of 15-min BankNifty data in CSV format
  - [ ] Data covers various market conditions (trending, ranging, volatile)
  - [ ] Data quality verified (no gaps, correct timestamps)

- [ ] **Backtest Completed**
  - [ ] Run: `python manage.py backtest --csv-dir historical_data/`
  - [ ] Minimum 3 months of data processed
  - [ ] All backtest metrics calculated

- [ ] **Backtest Results Acceptable**
  - [ ] Win rate ≥ 50%
  - [ ] Profit factor ≥ 1.5
  - [ ] CAGR ≥ 15% (or your target)
  - [ ] Max drawdown < 20% of capital
  - [ ] Sharpe-like metric > 1.0
  - [ ] Average win > 1.5 × average loss

---

## Phase 2: Paper Trading ✅

- [ ] **Paper Trading Setup**
  - [ ] Real WebSocket feed integrated (`data_ingest_live.py`)
  - [ ] Execution adapter = Mock (dry_run=True)
  - [ ] Slippage simulation enabled (0.1-0.4%)
  - [ ] Commission simulation enabled

- [ ] **Paper Trading Duration**
  - [ ] Minimum 10 trading days
  - [ ] Minimum 100 trades executed
  - [ ] Covers different market conditions

- [ ] **Paper Trading Results**
  - [ ] Win rate matches backtest (±5%)
  - [ ] Average PnL matches backtest (±10%)
  - [ ] Slippage impact understood
  - [ ] No unexpected behavior observed
  - [ ] System stability confirmed (no crashes, disconnects)

---

## Phase 3: Risk Management ✅

- [ ] **Position Sizing Verified**
  - [ ] Qty calculation formula correct
  - [ ] Risk per trade ≤ 1% of capital
  - [ ] Maximum position size tested

- [ ] **Stoploss Verified**
  - [ ] Stoploss triggers correctly
  - [ ] Stoploss accounts for slippage
  - [ ] Trailing stoploss works

- [ ] **Daily Limits Set**
  - [ ] Max daily loss limit configured
  - [ ] Max concurrent trades set
  - [ ] Daily profit target realistic

- [ ] **Kill Switch Tested**
  - [ ] Django Admin kill switch works
  - [ ] Strategy stops immediately when disabled
  - [ ] Emergency stop procedure documented

---

## Phase 4: System Readiness ✅

- [ ] **Infrastructure**
  - [ ] Server stable (uptime > 99%)
  - [ ] Database backups configured
  - [ ] Logging and monitoring set up
  - [ ] Error alerts configured

- [ ] **Data Feed**
  - [ ] WebSocket connection stable
  - [ ] Reconnection logic tested
  - [ ] Data quality verified
  - [ ] Latency acceptable (< 100ms)

- [ ] **Execution**
  - [ ] Order placement tested (paper)
  - [ ] Order cancellation works
  - [ ] Order status tracking works
  - [ ] Fill confirmation reliable

---

## Phase 5: Final Checks ✅

- [ ] **Configuration**
  - [ ] `DRY_RUN=false` set correctly
  - [ ] `CONFIRM_REAL_TRADES=true` set
  - [ ] Strategy parameters finalized
  - [ ] Capital allocation confirmed

- [ ] **Documentation**
  - [ ] Runbook reviewed
  - [ ] Emergency procedures understood
  - [ ] Support contacts available
  - [ ] Backup plan documented

- [ ] **Team Readiness**
  - [ ] All team members trained
  - [ ] Monitoring schedule set
  - [ ] Review meetings scheduled
  - [ ] Escalation path clear

---

## Go-Live Decision

**Only proceed if:**
- ✅ All Phase 1 items checked
- ✅ All Phase 2 items checked
- ✅ All Phase 3 items checked
- ✅ All Phase 4 items checked
- ✅ All Phase 5 items checked
- ✅ At least 2 team members approve
- ✅ Start with minimum capital (test allocation)

**Recommended:**
- Start with 25% of planned capital
- Monitor closely for first week
- Scale up gradually if results match expectations

---

## Post-Go-Live Monitoring

**First Week:**
- [ ] Monitor every trade manually
- [ ] Verify all orders execute correctly
- [ ] Check PnL matches expectations
- [ ] Review logs daily
- [ ] Adjust parameters if needed

**First Month:**
- [ ] Weekly performance review
- [ ] Compare live vs. backtest results
- [ ] Identify and fix any issues
- [ ] Document learnings

---

**Last Updated:** 2025-11-13  
**Status:** Template - Complete before going live

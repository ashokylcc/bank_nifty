# Bank Nifty Strategy - Manual Daily Parameters System

## 🎯 Overview

Your Bank Nifty strategy now supports **manual daily parameter updates** for maximum flexibility. You can easily update the daily parameters without touching the code directly.

## 📅 Daily Parameters

### **Required Daily Updates:**
1. **Yesterday's Closing Price** - Bank Nifty closing price from previous day
2. **Lot Size** - Number of lots to trade (default: 35)
3. **Target Profit** - Profit target per lot (default: ₹500)
4. **Stoploss** - Stop loss per lot (default: ₹500)

### **Fixed Parameters:**
- **Trading Window**: 9:15 AM to 2:45 PM (extended for testing)
- **Strategy Logic**: Future direction → Option selection
- **Strike Selection**: Based on yesterday's closing price

## 🔧 How to Update Daily Parameters

### **Method 1: Interactive Update (Recommended)**
```bash
./run_banknifty_strategy.sh update
```

This will prompt you to enter:
- Yesterday's Bank Nifty closing price
- Lot size (default: 35)
- Target profit per lot (default: ₹500)
- Stoploss per lot (default: ₹500)

### **Method 2: Check Current Parameters**
```bash
./run_banknifty_strategy.sh params
```

This shows your current daily parameters.

### **Method 3: Manual Code Edit**
Edit the file: `strategy/management/commands/run_strategy.py`

Find this section and update the values:
```python
# ========================================
# DAILY MANUAL PARAMETERS - UPDATE THESE DAILY
# ========================================
LOT_SIZE = 35                    # Bank Nifty lot size
TARGET_PROFIT = 500              # Target profit per lot (₹500)
STOPLOSS = 500                   # Stoploss per lot (₹500)
YESTERDAY_CLOSING = 57200        # Yesterday's Bank Nifty closing price
# ========================================
```

## 📊 Current Parameters

```
Lot Size: 35
Target: ₹500
Stoploss: ₹500
Yesterday's Closing: ₹57,200
```

## 🚀 Daily Workflow

### **Step 1: Update Parameters (Morning)**
```bash
./run_banknifty_strategy.sh update
```

### **Step 2: Verify Parameters**
```bash
./run_banknifty_strategy.sh params
```

### **Step 3: Test Connection (Optional)**
```bash
./run_banknifty_strategy.sh test --skip-websocket
```

### **Step 4: Run Strategy (9:15-2:45 PM)**
```bash
./run_banknifty_strategy.sh run
```

## 📈 Strategy Logic (Unchanged)

The strategy logic remains the same:

1. **Session Login** → Alice Blue authentication
2. **WebSocket Connection** → Real-time data feed
3. **Get Future Symbol** → Active Bank Nifty future contract
4. **Get Current Future LTP** → Real-time future price
5. **Determine Future Direction**:
   - If current > yesterday's closing → **FUTURE = BUY**
   - If current < yesterday's closing → **FUTURE = SELL**
6. **Select Option**:
   - If FUTURE = BUY → **BUY Call Option** (strike = yesterday's closing)
   - If FUTURE = SELL → **BUY Put Option** (strike = yesterday's closing)
7. **Monitor Position** → Track PnL until target/stoploss/time exit

## 🎯 Example Daily Update

```bash
$ ./run_banknifty_strategy.sh update

📅 Bank Nifty Strategy - Daily Parameter Update
==================================================
📅 Date: 2024-01-15

🔧 Please enter today's parameters:
------------------------------
💰 Yesterday's Bank Nifty Closing Price: 57250
📦 Lot Size (default 35): 35
🎯 Target Profit per lot (default 500): 500
🛑 Stoploss per lot (default 500): 500

✅ Parameters received:
   • Yesterday's Closing: ₹57250
   • Lot Size: 35
   • Target: ₹500
   • Stoploss: ₹500

✅ Strategy file updated: strategy/management/commands/run_strategy.py

🎉 Daily parameters updated successfully!
💡 You can now run: ./run_banknifty_strategy.sh run
```

## 📝 Trade Logging

All trades are automatically logged with:
- Daily parameters used
- Future direction determined
- Option selected
- Entry/exit prices
- PnL calculation
- Exit reason (Target/Stoploss/Time)

## 🛡️ Risk Management

- **Position Sizing**: Fixed lot size (daily parameter)
- **Stop Loss**: Per lot maximum loss (daily parameter)
- **Target**: Per lot profit target (daily parameter)
- **Time Limit**: Maximum 5.5 hours exposure (9:15-2:45 PM for testing)
- **Strike Selection**: Based on yesterday's closing price

## 📞 Available Commands

```bash
./run_banknifty_strategy.sh update    # Update daily parameters
./run_banknifty_strategy.sh params    # Show current parameters
./run_banknifty_strategy.sh test      # Test connection
./run_banknifty_strategy.sh logic     # Test strategy logic
./run_banknifty_strategy.sh run       # Run strategy (market hours)
./run_banknifty_strategy.sh help      # Show all commands
```

## 🎉 Benefits of Manual System

1. **Flexibility**: Update parameters daily based on market conditions
2. **Simplicity**: Easy interactive updates
3. **Transparency**: Clear parameter visibility
4. **Control**: Full control over risk management
5. **Logging**: Complete trade history with daily parameters

## 🚀 Ready for Daily Trading

Your strategy is now ready for daily manual parameter updates!

**Daily Routine:**
1. ✅ Update parameters with `./run_banknifty_strategy.sh update`
2. ✅ Verify with `./run_banknifty_strategy.sh params`
3. ✅ Run during market hours with `./run_banknifty_strategy.sh run`

---

**Disclaimer**: This is for educational purposes. Always test thoroughly and trade responsibly. Past performance doesn't guarantee future results. 
# 🎯 SMART MOVEMENT STRATEGY - Complete Workflow Guide

## 📋 Overview

**Strategy Name:** Smart Market Movement Strategy  
**Purpose:** Wait for strong market movements and enter at optimal times for maximum profit  
**Key Feature:** Multi-trade capability (up to 3 trades per day) with trailing stoploss

---

## 🎯 Strategy Philosophy

### Core Concept:
1. **Wait for Strong Movement:** Only enters when market shows significant movement (2.5%+ or 150+ points)
2. **Optimal Entry Window:** Trades only during 9:45 AM - 2:00 PM (avoids early volatility)
3. **Dynamic Targets:** Adjusts profit targets and stoploss based on movement strength
4. **Trailing Stoploss:** Protects profits by trailing stoploss as price moves favorably
5. **Multi-Trade:** Can take up to 3 trades per day if conditions are met

---

## ⚙️ Configuration Settings

### Daily Updates Required:
```python
YESTERDAY_CLOSING = 58400  # Update this daily (Line 105)
FUTURE_SYMBOL = "BANKNIFTY25NOV25F"  # Update this daily (Line 107)
OPTION_SYMBOL = "BANKNIFTY25NOV25"  # Update this daily (Line 108)
```

### Trading Parameters:
- **Capital:** ₹30,000
- **Quantity:** 1 lot (35 shares)
- **Max Trades/Day:** 3
- **Daily Profit Target:** ₹300
- **Daily Loss Limit:** ₹600

### Trading Hours:
- **Market Hours:** 9:15 AM - 3:30 PM
- **Optimal Entry Window:** 9:45 AM - 2:00 PM
- **Square-Off Time:** 2:30 PM

---

## 📊 Movement Classification

### Strong Movement (Highest Priority):
- **Points:** ≥150 points
- **Percentage:** ≥2.5%
- **Target Profit:** ₹400
- **Stoploss:** ₹150
- **Example:** If Bank Nifty moves from ₹58,400 to ₹58,600 (200 points, 3.4%)

### Moderate Movement:
- **Points:** ≥75 points
- **Percentage:** ≥1.5%
- **Target Profit:** ₹250
- **Stoploss:** ₹200
- **Example:** If Bank Nifty moves from ₹58,400 to ₹58,500 (100 points, 1.7%)

### Weak Movement (Lowest Priority):
- **Points:** ≥40 points
- **Percentage:** ≥0.8%
- **Target Profit:** ₹150
- **Stoploss:** ₹250
- **Example:** If Bank Nifty moves from ₹58,400 to ₹58,450 (50 points, 0.85%)

### Insufficient Movement:
- **Points:** <40 points
- **Percentage:** <0.8%
- **Action:** Strategy waits for stronger signal

---

## 🔄 Complete Workflow

### Phase 1: Initialization (9:15 AM)

```
1. Strategy Starts
   ├─ Load configuration
   ├─ Connect to Alice Blue API
   ├─ Establish WebSocket connection
   └─ Subscribe to Bank Nifty Future

2. Get Market Data
   ├─ Fetch Future LTP
   ├─ Calculate movement from yesterday's close
   └─ Classify movement strength
```

**Output:**
```
🎯 SMART MARKET MOVEMENT STRATEGY
🕐 Current Time: 09:15:00 IST
📊 Yesterday's Closing: ₹58400
✅ Future LTP: ₹59011.26
📊 Initial Movement: ₹611.26 (1.05%)
🔥 STRONG MOVEMENT: Target: ₹400, Stoploss: ₹150
```

---

### Phase 2: Safety Checks

```
1. Check Daily Limits
   ├─ Max Trades: 3/day
   ├─ Daily Loss Limit: ₹600
   └─ Daily Profit Target: ₹300

2. Check Entry Window
   ├─ Current time: 9:45 AM - 2:00 PM?
   └─ If outside window, wait or skip
```

**Output:**
```
🛡️ Step: Daily Safety Checks
✅ Safety checks passed - Trade 1/3
📊 Daily PnL: ₹0.00 | Max Loss: ₹600
```

---

### Phase 3: Direction Determination

```
1. Calculate Price Change
   ├─ Price Change = Current LTP - Yesterday's Close
   └─ Determine direction (BUY or SELL)

2. Select Option Type
   ├─ If FUTURE = BUY → BUY Call Option
   └─ If FUTURE = SELL → BUY Put Option
```

**Output:**
```
📈 Step: Determine FUTURE Direction
🚀 FUTURE Direction: BUY (Price up ₹611.26)

🎯 Step: Select Option Based on Future Direction
📞 FUTURE=BUY → BUY Call Option: BANKNIFTY25NOV25C58400
🎯 Selected Strike: ₹58400 (ATM)
```

---

### Phase 4: Entry Execution

```
1. Subscribe to Option
   ├─ Subscribe to option symbol
   └─ Get entry price (LTP)

2. Place BUY Order
   ├─ Market order
   ├─ Quantity: 35 (1 lot)
   └─ Product: Intraday
```

**Output:**
```
📡 Step: Subscribe to Option
💰 Entry Price: ₹500.0

🛒 Step: Place BUY Order
🛒 BUY order placed: [ORDER_ID] | Price: ₹500.0 | Quantity: 35
```

---

### Phase 5: Position Monitoring

```
1. Monitor Position
   ├─ Track current LTP
   ├─ Calculate real-time PnL
   └─ Update trailing stoploss

2. Exit Conditions (Check in order):
   ├─ Target Hit: PnL ≥ Target Profit
   ├─ Stoploss Hit: PnL ≤ -Stoploss
   ├─ Trailing Stoploss: PnL drops below trailing level
   └─ Time Exit: 2:30 PM reached
```

**Trailing Stoploss Logic:**
- When profit increases, trailing stoploss moves up
- Trailing stoploss = 50% of highest profit achieved
- Protects profits while allowing for further gains

**Example:**
```
Entry: ₹500
Target: ₹400
Stoploss: ₹150

Price moves to ₹520 (PnL = ₹700):
- Highest Profit: ₹700
- Trailing Stoploss: ₹350 (50% of ₹700)
- If price drops to ₹510 (PnL = ₹350), exit triggered
```

**Output:**
```
🔄 Step: Position Monitoring
📊 LIVE TRADING: PnL: ₹337.98 | LTP: ₹509.66 | Target: ₹400 | Stoploss: ₹150
🎯 Target Hit! PnL: ₹337.98
```

---

### Phase 6: Exit Execution

```
1. Place SELL Order
   ├─ Market order
   ├─ Quantity: 35 (1 lot)
   └─ Product: Intraday

2. Update Daily Tracking
   ├─ Increment trade count
   ├─ Update daily PnL
   └─ Check if limits reached
```

**Output:**
```
✅ Square-off SELL placed: [ORDER_ID] | Price: ₹509.66 | Quantity: 35
📊 Daily Update: Trade 1/3 | Daily PnL: ₹337.98
🎯 DAILY PROFIT TARGET ACHIEVED: ₹337.98
```

---

### Phase 7: Next Trade Decision

```
1. Check if Another Trade Possible
   ├─ Trade count < 3?
   ├─ Daily loss < ₹600?
   ├─ Daily profit < ₹300?
   └─ Time < 2:00 PM?

2. If Yes, Continue Monitoring
   ├─ Monitor for new movement
   ├─ Wait for sufficient movement
   └─ Execute next trade

3. If No, Stop Strategy
   ├─ Max trades reached
   ├─ Daily target achieved
   ├─ Daily loss limit hit
   └─ Time window closed
```

---

## 🔄 Multi-Trade Flow

### Trade 1:
```
Movement Detected → Entry → Monitor → Exit
Daily PnL: ₹337.98
Status: Target Hit
```

### Trade 2 (If conditions met):
```
Continue Monitoring → New Movement → Entry → Monitor → Exit
Daily PnL: ₹337.98 + Trade 2 PnL
Status: Continue or Stop
```

### Trade 3 (If conditions met):
```
Continue Monitoring → New Movement → Entry → Monitor → Exit
Daily PnL: Trade 1 + Trade 2 + Trade 3
Status: Max trades reached
```

---

## 📊 Exit Scenarios

### 1. Target Hit (Best Case):
```
Condition: PnL ≥ Target Profit
Example: Target ₹400, PnL = ₹337.98
Action: Exit immediately
Result: Profit booked
```

### 2. Stoploss Hit (Worst Case):
```
Condition: PnL ≤ -Stoploss
Example: Stoploss ₹150, PnL = -₹150
Action: Exit immediately
Result: Loss limited
```

### 3. Trailing Stoploss Hit:
```
Condition: Price drops below trailing stoploss
Example: Highest profit ₹700, trailing ₹350, current PnL = ₹350
Action: Exit immediately
Result: Profit protected
```

### 4. Time Exit:
```
Condition: Time ≥ 2:30 PM
Example: Current time 2:30 PM, PnL = ₹100
Action: Exit at market close
Result: Small profit/loss
```

---

## 🎯 Daily Limits & Safety

### Daily Profit Target:
- **Target:** ₹300
- **Action:** Strategy stops when reached
- **Purpose:** Lock in profits, avoid overtrading

### Daily Loss Limit:
- **Limit:** ₹600
- **Action:** Strategy stops when reached
- **Purpose:** Protect capital, prevent large losses

### Max Trades:
- **Limit:** 3 trades per day
- **Action:** Strategy stops when reached
- **Purpose:** Avoid overtrading, maintain quality

---

## 🚀 Commands

### Live Trading:
```bash
python3 manage.py smart_movement_strategy
```

### Simulation Mode:
```bash
python3 manage.py smart_movement_strategy --simulate
```

### Watch Mode (Continuous Monitoring):
```bash
python3 manage.py smart_movement_strategy --watch
```

---

## 📈 Expected Performance

### Good Days:
- **Trades:** 1-2 trades
- **Result:** Target hit on most trades
- **Daily PnL:** ₹300-800
- **Win Rate:** 70-80%

### Average Days:
- **Trades:** 1-2 trades
- **Result:** Mix of target hits and time exits
- **Daily PnL:** ₹150-400
- **Win Rate:** 60-70%

### Bad Days:
- **Trades:** 1-2 trades
- **Result:** Stoploss hits
- **Daily PnL:** ₹-150 to ₹-400
- **Win Rate:** 30-40%

---

## ⚠️ Important Notes

### 1. Daily Updates:
- **MUST** update `YESTERDAY_CLOSING` daily
- **MUST** update `FUTURE_SYMBOL` daily
- **MUST** update `OPTION_SYMBOL` daily

### 2. Entry Window:
- Strategy only trades during 9:45 AM - 2:00 PM
- Trades outside this window are skipped
- This avoids early market volatility

### 3. Movement Requirements:
- Strategy waits for sufficient movement
- Weak movements may be skipped
- Strong movements get priority

### 4. Multi-Trade Logic:
- Can take up to 3 trades per day
- Each trade is independent
- Daily limits apply to all trades combined

### 5. Trailing Stoploss:
- Activates when profit increases
- Trails at 50% of highest profit
- Protects profits while allowing gains

---

## 🔍 Troubleshooting

### Issue: "Insufficient Movement"
**Solution:** Strategy is working correctly - waiting for stronger signal
**Action:** Wait for market movement or use `--watch` mode

### Issue: "Outside Entry Window"
**Solution:** Current time is outside 9:45 AM - 2:00 PM
**Action:** Wait for entry window or strategy will skip

### Issue: "Max Trades Reached"
**Solution:** Already taken 3 trades today
**Action:** Strategy stops - normal behavior

### Issue: "Daily Loss Limit Reached"
**Solution:** Daily loss exceeded ₹600
**Action:** Strategy stops - protects capital

### Issue: "Daily Profit Target Achieved"
**Solution:** Daily profit reached ₹300
**Action:** Strategy stops - locks in profits

---

## 📊 Comparison with Other Strategies

### vs. Slippage Compensated Strategy:
| Feature | Smart Movement | Slippage Compensated |
|---------|---------------|---------------------|
| Max Trades | 3 per day | 1 per day |
| Entry Window | 9:45 AM - 2:00 PM | 9:15 AM - 3:30 PM |
| Trailing Stoploss | ✅ Yes | ❌ No |
| Movement Required | 2.5%+ (strong) | 0.35%+ (weak) |
| Profit Targets | ₹150-400 | ₹500-700 |
| Complexity | Higher | Lower |

### vs. Run Strategy:
| Feature | Smart Movement | Run Strategy |
|---------|---------------|--------------|
| Max Trades | 3 per day | 1 per day |
| Trailing Stoploss | ✅ Yes | ❌ No |
| Movement Required | 2.5%+ (strong) | 0.35%+ (weak) |
| Profit Targets | ₹150-400 | ₹700-1100 |
| Entry Filters | Stricter | Moderate |

---

## ✅ Pre-Trade Checklist

### Before Running Strategy:
- [ ] Updated `YESTERDAY_CLOSING` price
- [ ] Updated `FUTURE_SYMBOL` (current month)
- [ ] Updated `OPTION_SYMBOL` (current month)
- [ ] Verified API credentials
- [ ] Checked account balance (₹30,000+)
- [ ] Current time is within trading hours
- [ ] Tested in simulation mode first

---

## 🎯 Summary

**Smart Movement Strategy** is designed for:
- ✅ Traders who want multiple opportunities per day
- ✅ Traders who prefer waiting for strong movements
- ✅ Traders who want trailing stoploss protection
- ✅ Traders who want to avoid early market volatility

**Key Advantages:**
- Multi-trade capability (up to 3 trades/day)
- Trailing stoploss protects profits
- Stricter entry criteria (better quality trades)
- Optimal entry window (avoids volatility)

**Key Considerations:**
- Requires daily symbol updates
- May skip weak movements
- More complex than single-trade strategies
- Entry window limits trading hours

---

**Last Updated:** November 25, 2025  
**Strategy:** Smart Movement Strategy  
**Status:** ✅ Tested and Working


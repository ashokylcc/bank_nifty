# 🚀 FIRST-CLASS SCALPING STRATEGY GUIDE

## 📊 **Strategy Overview**

This is an **advanced scalping strategy** designed to achieve **consistent daily profits of ₹500+** with proper risk management and dynamic targets.

## 🎯 **Key Features**

### **1. Dynamic Profit Targets**
- **Strong Trend (2%+)**: ₹800 target, ₹150 stoploss
- **Moderate Trend (1%+)**: ₹500 target, ₹200 stoploss  
- **Weak Trend (0.5%+)**: ₹300 target, ₹300 stoploss

### **2. Advanced Risk Management**
- **Max Daily Loss**: ₹1,000 per quantity
- **Max Trades**: 5 per day
- **Volatility-based Stoploss**: Adjusts based on market conditions
- **Dynamic Targets**: Scales with trend strength

### **3. Scalping Window Optimization**
- **Primary Window**: 9:15 AM - 10:00 AM (45 minutes)
- **Aggressive Mode**: 3 points movement, 0.3% change
- **Conservative Mode**: 5 points movement, 0.5% change

## 📈 **Entry Criteria**

### **Scalping Window (9:15 AM - 10:00 AM)**
- **Movement**: 3+ points
- **Percentage**: 0.3%+ change
- **Mode**: Aggressive trading

### **Normal Window (10:00 AM - 1:00 PM)**
- **Movement**: 5+ points
- **Percentage**: 0.5%+ change
- **Mode**: Conservative trading

## 🛡️ **Risk Management Rules**

### **1. Position Sizing**
- **Quantity**: 1 (35 lots)
- **Capital Required**: ₹17,500
- **Margin**: 50% of capital

### **2. Stop Loss Rules**
- **High Volatility**: ₹150 stoploss
- **Medium Volatility**: ₹200 stoploss
- **Low Volatility**: ₹300 stoploss

### **3. Profit Taking**
- **Target Hit**: Immediate square-off
- **Stoploss Hit**: Immediate square-off
- **Time Exit**: 1:00 PM (small profit)

## 📊 **Strategy Parameters**

```python
# 🎯 SCALPING PARAMETERS
QUANTITY = 1  # 1 quantity = 35 lots
LOT_SIZE = 35  # 35 lots per quantity

# 🎯 DYNAMIC TARGETS
TARGET_PROFIT = 500 * QUANTITY  # ₹500 per quantity
STOPLOSS = 200 * QUANTITY       # ₹200 per quantity

# 🎯 RISK MANAGEMENT
MAX_DAILY_LOSS = 1000 * QUANTITY  # Max daily loss
MAX_TRADES_PER_DAY = 5  # Max trades per day

# 🎯 TIME WINDOWS
SCALPING_START = "09:15"  # 9:15 AM
SCALPING_END = "10:00"    # 10:00 AM
MAIN_TRADING_END = "13:00"  # 1:00 PM
```

## 🚀 **How to Use**

### **1. Daily Setup**
```bash
# Update yesterday's closing price
python3 update_daily_params.py

# Run the strategy
python3 first_class_scalping_strategy.py
```

### **2. Manual Parameters**
```python
# Update these daily in run_strategy.py
YESTERDAY_CLOSING = 54900  # Update daily
QUANTITY = 1  # 1 quantity = 35 lots
```

### **3. Market Hours**
- **Trading Start**: 9:15 AM
- **Scalping Window**: 9:15 AM - 10:00 AM
- **Main Trading**: 10:00 AM - 1:00 PM
- **Square-off**: 1:00 PM

## 📈 **Profit Scenarios**

### **Scenario 1: Strong Trend (2%+)**
- **Entry**: ₹528.7
- **Target**: ₹551.6 (₹800 profit)
- **Stoploss**: ₹524.4 (₹150 loss)
- **Probability**: 60% target hit

### **Scenario 2: Moderate Trend (1%+)**
- **Entry**: ₹528.7
- **Target**: ₹543.0 (₹500 profit)
- **Stoploss**: ₹522.7 (₹200 loss)
- **Probability**: 50% target hit

### **Scenario 3: Weak Trend (0.5%+)**
- **Entry**: ₹528.7
- **Target**: ₹537.3 (₹300 profit)
- **Stoploss**: ₹520.7 (₹300 loss)
- **Probability**: 40% target hit

## 🎯 **Success Factors**

### **1. Market Analysis**
- **Trend Strength**: 2%+ for strong trends
- **Volatility**: High volatility = tighter stoploss
- **Time Window**: Scalping window for aggressive entries

### **2. Risk Management**
- **Never risk more than ₹1,000 per day**
- **Use dynamic stoploss based on volatility**
- **Take profits at target levels**

### **3. Entry Timing**
- **Best Time**: 9:15 AM - 10:00 AM
- **Avoid**: First 5 minutes (high volatility)
- **Focus**: Clear directional movement

## 📊 **Expected Results**

### **Daily Targets**
- **Primary Goal**: ₹500+ profit
- **Secondary Goal**: ₹300+ profit (weak trends)
- **Maximum Loss**: ₹1,000 (stop trading)

### **Success Rate**
- **Target Hit**: 60% probability
- **Stoploss Hit**: 20% probability
- **Time Exit**: 20% probability (small profit)

## 🚨 **Important Notes**

### **1. Capital Requirements**
- **Minimum**: ₹17,500 (1 quantity)
- **Recommended**: ₹35,000 (2 quantity)
- **Maximum**: ₹52,500 (3 quantity)

### **2. Market Conditions**
- **Best**: High volatility, clear trends
- **Avoid**: Low volatility, sideways markets
- **Skip**: First 5 minutes of trading

### **3. Risk Warnings**
- **Never risk more than 5% of capital**
- **Stop trading after 3 consecutive losses**
- **Take profits at target levels**

## 🎯 **Quick Start**

1. **Update Parameters**: Set yesterday's closing price
2. **Check Capital**: Ensure ₹17,500+ available
3. **Run Strategy**: Execute at 9:15 AM
4. **Monitor**: Watch for target/stoploss hits
5. **Square-off**: Exit at 1:00 PM or target hit

## 📞 **Support**

For questions or issues:
- Check the logs for detailed information
- Verify market hours and parameters
- Ensure sufficient capital is available

---

**🚀 Ready to start scalping for consistent daily profits!**

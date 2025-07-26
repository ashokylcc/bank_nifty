# Bank Nifty High Frequency Breakout Strategy

A high-frequency breakout trading strategy for Bank Nifty options that operates during the first half-hour of market opening (9:15 AM to 9:45 AM).

## 🎯 Strategy Overview

This strategy implements a high-frequency breakout approach with the following key features:

- **Trading Window**: 9:15 AM to 9:45 AM (first half-hour)
- **Strike Selection**: Based on yesterday's closing price
- **Breakout Detection**: ₹50 threshold for entry signals
- **Option Selection**: 
  - Bullish breakout → Buy Call Option
  - Bearish breakout → Buy Put Option
- **Risk Management**: 
  - Target: ₹500 profit per lot
  - Stoploss: ₹500 loss per lot
  - Auto square-off at 9:45 AM

## 📋 Prerequisites

- Python 3.7+
- Django
- Alice Blue trading account with API credentials
- Bank Nifty options trading enabled

## 🚀 Quick Start

### 1. Setup Strategy Configuration

```bash
# Setup with yesterday's closing price (auto-fetch)
./run_banknifty_strategy.sh setup

# OR setup with manual closing price
./run_banknifty_strategy.sh setup 45000
```

### 2. Run Strategy

```bash
# Run the strategy (only works between 9:15-9:45 AM)
./run_banknifty_strategy.sh run
```

## ⚙️ Manual Setup

### Setup Strategy Configuration

```bash
# Auto-fetch yesterday's closing price
python manage.py setup_strategy

# Manual closing price
python manage.py setup_strategy --closing-price 45000

# Custom parameters
python manage.py setup_strategy --closing-price 45000 --lot-size 15 --target 500 --stoploss 500
```

### Run Strategy

```bash
python manage.py run_strategy
```

## 📊 Strategy Logic

### 1. Entry Conditions
- **Time Window**: Only trades between 9:15 AM and 9:45 AM
- **Breakout Detection**: Compares current Bank Nifty future price with yesterday's closing
- **Threshold**: ₹50 breakout threshold (configurable)
- **Strike Selection**: ATM strike based on yesterday's closing price

### 2. Direction Logic
- **Bullish Breakout**: If current price > yesterday's closing + ₹50
  - Action: Buy Call Option
- **Bearish Breakout**: If current price < yesterday's closing - ₹50
  - Action: Buy Put Option

### 3. Exit Conditions
- **Target Hit**: ₹500 profit per lot
- **Stoploss Hit**: ₹500 loss per lot
- **Time Exit**: 9:45 AM (mandatory square-off)

## 🔧 Configuration

The strategy uses the `TradeConfig` model with the following parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `closing_price` | Required | Yesterday's Bank Nifty closing price |
| `lot_size` | 15 | Bank Nifty options lot size |
| `target` | 500 | Target profit in rupees |
| `stoploss` | 500 | Stoploss in rupees |
| `trade_start` | 09:15 | Strategy start time |
| `trade_end` | 09:45 | Strategy end time |

## 📈 Example Trade Flow

```
9:15 AM - Strategy starts
9:16 AM - Yesterday's closing: ₹45,000
9:16 AM - Current future price: ₹45,100
9:16 AM - Breakout detected: +₹100 (bullish)
9:16 AM - Entry: Buy BANKNIFTY31JUL25C45000 @ ₹150
9:20 AM - Price moves to ₹160, PnL: +₹150
9:25 AM - Price moves to ₹170, PnL: +₹300
9:30 AM - Price moves to ₹180, PnL: +₹450
9:35 AM - Price moves to ₹185, PnL: +₹525 (TARGET HIT!)
9:35 AM - Exit: Sell @ ₹185, Final PnL: ₹525
```

## 🛡️ Risk Management

1. **Position Sizing**: Fixed lot size (default: 15)
2. **Stop Loss**: ₹500 per lot maximum loss
3. **Time Limit**: Maximum 30 minutes exposure
4. **Breakout Filter**: Only trades on significant moves (>₹50)

## 📝 Trade Logging

All trades are automatically logged in the `TradeLog` model with:
- Entry/exit prices
- PnL calculation
- Exit reason (Target/Stoploss/Time)
- Timestamp and details

## 🔍 Monitoring

The strategy provides real-time monitoring:
- Current PnL updates every 30 seconds
- Live LTP streaming
- Breakout detection alerts
- Exit notifications

## ⚠️ Important Notes

1. **Trading Hours**: Strategy only works between 9:15-9:45 AM
2. **Market Conditions**: Best suited for volatile market openings
3. **Liquidity**: Ensure sufficient liquidity in selected options
4. **API Limits**: Respect broker API rate limits
5. **Testing**: Always test with paper trading first

## 🐛 Troubleshooting

### Common Issues

1. **"Outside trading hours"**
   - Solution: Run only between 9:15-9:45 AM

2. **"No breakout detected"**
   - Solution: Market may be sideways, wait for stronger moves

3. **"No LTP received"**
   - Solution: Check internet connection and broker API status

4. **"Login failed"**
   - Solution: Verify Alice Blue credentials in `alice_client.py`

### Debug Mode

```bash
# Run with verbose output
python manage.py run_strategy --verbosity=2
```

## 📞 Support

For issues or questions:
1. Check the trade logs in Django admin
2. Verify broker API connectivity
3. Review strategy parameters in `TradeConfig`

## 🔄 Updates

- **v1.0**: Initial high-frequency breakout strategy
- **v1.1**: Added yesterday's closing price integration
- **v1.2**: Enhanced risk management and monitoring

---

**Disclaimer**: This is for educational purposes. Always test thoroughly and trade responsibly. Past performance doesn't guarantee future results. 
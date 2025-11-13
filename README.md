# BankNifty Momentum Breakout Strategy

A production-ready Django-based autotrading system implementing the BankNifty Momentum Breakout Strategy for weekly options trading.

## 📋 Overview

This strategy:
- Captures the first 15-minute range (9:15-9:30 AM)
- Detects breakouts above/below the range
- Confirms momentum using EMA, RSI, and volume filters
- Selects ATM options (nearest Thursday expiry)
- Manages risk with position sizing and stoploss
- Executes trades via execution adapter (dry-run or live)

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL (or SQLite for development)
- Django 5.2+

### Installation

1. **Clone and setup:**
```bash
cd /var/www/html/bank_nifty
pip install -r requirements.txt
```

2. **Configure environment:**
```bash
# Copy sample env file
cp config.sample.env .env

# Edit .env to set DRY_RUN=true and DB credentials, etc.
# For Docker, the .env file will be used automatically
```

3. **Option A: Docker (Recommended)**
```bash
# Start PostgreSQL + Django + Worker
docker-compose up -d

# View logs
docker-compose logs -f worker

# Stop
docker-compose down
```

4. **Option B: Local Development**
```bash
# Configure database
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run Django server
python manage.py runserver
```

5. **Create strategy with recommended defaults:**
```bash
# Create default strategy
python manage.py create_default_strategy

# Or create in Django Admin
# Go to http://localhost:8000/admin/trading/strategy/
# Click "Add Strategy" - defaults are pre-filled
```

**Recommended Defaults:**
- Capital: ₹30,000
- Risk per trade: 1%
- Max daily loss: ₹600 (2% of capital)
- Breakout buffer: 10 pts
- Min stoploss: 40 pts
- RSI BUY: 55-70, RSI SELL: 30-45
- Trading window: 9:30 AM - 10:30 AM
- Square-off: 2:45 PM

See `DEFAULT_PARAMETERS.md` for full list and tuning guide.

6. **Run in dry-run mode:**

**Option A: Live Test (Real WebSocket Data, Mock Execution)**
```bash
# Run with live market data but mock orders (recommended for paper trading)
python manage.py run_momentum_strategy --loop --live-data --dry-run
```

**Option B: Simulation (CSV Data)**
```bash
# If using Docker, worker runs automatically
# For local development:
python manage.py run_strategy --dry-run --loop
```

## 🔧 Configuration

### Environment Variables

Create a `.env` file or set environment variables:

```bash
# Trading mode
DRY_RUN=true                    # Set to false for live trading
CONFIRM_REAL_TRADES=false       # Must be true for live trading

# Database (if using PostgreSQL)
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname

# Alice Blue credentials (for live trading)
ALICE_BLUE_USER_ID=your_user_id
ALICE_BLUE_API_KEY=your_api_key
```

### Strategy Parameters

Configure in Django Admin (`/admin/trading/strategy/`):

- **Risk Parameters:**
  - Capital: Available trading capital
  - Risk per trade: % of capital to risk per trade (default: 1%)
  - Max daily loss: Maximum loss per day (default: ₹5000)
  - Max concurrent trades: Maximum open positions (default: 1)

- **Trading Parameters:**
  - Lot size: BankNifty lot size (default: 35)
  - Breakout buffer: Points above/below range for breakout (default: 10)
  - Min stoploss points: Minimum stoploss (default: 40)
  - Stoploss range multiplier: Stoploss as % of range (default: 0.6)
  - Target multiplier: Target as multiple of stoploss (default: 1.5)

- **Momentum Parameters:**
  - Volume multiplier: Volume breakout threshold (default: 1.5x)
  - EMA fast/slow: EMA periods (default: 20/50)
  - RSI period: RSI period (default: 14)
  - RSI buy/sell ranges: RSI ranges for entry

- **Time Windows:**
  - Range detection: 9:15 AM - 9:30 AM
  - Trading window: 9:30 AM - 10:30 AM
  - Square-off: 2:45 PM

## 📖 Usage

### Dry-Run Mode (Paper Trading)

```bash
# Single cycle
python manage.py run_strategy --dry-run

# Continuous loop (5 second interval)
python manage.py run_strategy --dry-run --loop

# Custom interval
python manage.py run_strategy --dry-run --loop --interval 10
```

### Live Trading Mode

⚠️ **WARNING: Real money will be used!**

```bash
# Set environment variables
export DRY_RUN=false
export CONFIRM_REAL_TRADES=true

# Run strategy
python manage.py run_strategy --loop
```

### Docker

```bash
# 1. Setup environment file
cp config.sample.env .env
# Edit .env to set DRY_RUN=true and DB credentials

# 2. Build and run
docker-compose up -d

# 3. View logs
docker-compose logs -f worker

# 4. Stop
docker-compose down
```

**Docker Services:**
- `db`: PostgreSQL database
- `web`: Django web server (admin, metrics)
- `worker`: Strategy runner (runs continuously)

## 📊 Strategy Logic

### Step A: Range Detection (9:15-9:30)
- Captures first 15-minute candle
- Calculates `first_high` and `first_low`
- Range = `first_high - first_low`

### Step B: Breakout Detection
- BUY signal: Spot LTP > `first_high + 10`
- SELL signal: Spot LTP < `first_low - 10`

### Step C: Momentum Confirmation
Requires **ALL** conditions (score = 4):
1. Volume breakout: Current volume ≥ 1.5 × avg(last 5 candles)
2. EMA alignment: EMA20 > EMA50 (BUY) or EMA20 < EMA50 (SELL)
3. RSI in range: 55-70 (BUY) or 30-45 (SELL)
4. Price momentum: Close > Open (BUY) or Close < Open (SELL)

### Step D: Strike Selection
- Nearest Thursday expiry (if Thursday is holiday, use previous business day)
- ATM strike: Round spot to nearest 100
- Strong momentum: ATM ± 100 (OTM)
- Build symbol: `BANKNIFTY{DD}{MMM}{YY}{C|P}{STRIKE}`

**Example:**
- Expiry: 2025-11-27 (Thursday)
- Strike: 58400
- Type: Call
- Symbol: `BANKNIFTY27NOV25C58400`

### Step E: Position Sizing
- Risk per trade = Capital × risk_per_trade_pct
- Stoploss points = max(floor(range × 0.6), 40)
- Quantity = floor(risk_amount / (stoploss_points × tick_value))

### Step F: Execution & Management
- Place market order
- Set stoploss and target
- Trailing stoploss: Move to breakeven after +1 × initial risk
- Exit on: Target, Stoploss, or Time (2:45 PM)

## 🛡️ Safety Features

1. **Dry-Run by Default:** All orders are simulated unless explicitly enabled
2. **Kill Switch:** Disable strategy in Django Admin (`strategy.enabled = False`)
3. **Daily Loss Limit:** Stops trading when daily loss limit breached
4. **Concurrent Trade Limit:** Limits maximum open positions
5. **Risk Management:** Position sizing based on risk per trade

## 📈 Monitoring

### Metrics Endpoint

```bash
curl http://localhost:8000/metrics
```

Returns:
```json
{
  "status": "RUNNING",
  "strategy_enabled": true,
  "open_trades": 1,
  "daily_pnl": 500.00,
  "total_trades": 2,
  "win_rate": 50.0,
  "daily_stats": {...}
}
```

### Django Admin

- View all signals, orders, and trades
- Monitor daily statistics
- Enable/disable strategy (kill switch)
- View trade logs with P&L

## 🧪 Testing

```bash
# Run all tests
python manage.py test trading

# Run specific test
python manage.py test trading.tests.test_expiry_functions
python manage.py test trading.tests.test_momentum
python manage.py test trading.tests.test_risk_manager
python manage.py test trading.tests.test_execution_adapter
python manage.py test trading.tests.test_integration
```

## ✅ Validation

After running a simulation, validate the results:

```bash
# Validate all components
python manage.py validate_simulation

# Validate specific strategy
python manage.py validate_simulation --strategy-id 1
```

The validation checks:
1. **Range Detection**: First high/low from CSV
2. **Momentum Score**: Score == 4 before execution
3. **Strike Selection**: Option symbol format matches README
4. **Risk Manager**: Qty calculation formula
5. **Execution Adapter**: Order flow (PENDING → FILLED)
6. **TradeLog Fields**: All fields populated
7. **DailyStats**: Winrate, total_pnl, max_drawdown

See `VALIDATION_GUIDE.md` for detailed interpretation.

## 📈 Backtesting

Backtest strategy on historical data:

```bash
# Backtest on historical CSV files
python manage.py backtest --csv-dir historical_data/

# Custom date range
python manage.py backtest --csv-dir historical_data/ \
    --start-date 2024-01-01 \
    --end-date 2024-12-31

# Save results
python manage.py backtest --csv-dir historical_data/ \
    --output backtest_results.csv
```

**Metrics Calculated:**
- CAGR (Compound Annual Growth Rate)
- Win Rate
- Profit Factor
- Sharpe-like Metric (Mean/SD)
- Max Drawdown
- Average Win/Loss
- Trade Frequency
- Daily PnL Distribution

See `BACKTESTING_GUIDE.md` for detailed instructions.

## 📁 Project Structure

```
bank_nifty/
├── trading/                    # Main Django app
│   ├── models.py              # Strategy, Signal, Order, TradeLog, DailyStats
│   ├── admin.py               # Django admin interface
│   ├── views.py               # Metrics endpoint
│   ├── services/              # Core services
│   │   ├── data_ingest.py     # WebSocket data aggregator
│   │   ├── range_detector.py  # Range detection (9:15-9:30)
│   │   ├── momentum.py        # EMA, RSI, momentum calculation
│   │   ├── strike_selector.py # Strike and expiry selection
│   │   ├── risk_manager.py    # Position sizing, risk checks
│   │   ├── execution_adapter.py  # Order execution interface
│   │   └── strategy_engine.py    # Main orchestration
│   ├── management/commands/
│   │   └── run_strategy.py    # CLI command
│   ├── tests/                 # Unit and integration tests
│   └── utils/                 # Helper functions
│       ├── time_helpers.py    # Time utilities
│       ├── expiry_functions.py # Expiry calculation
│       └── holidays.py        # Trading holidays
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md
├── RUNBOOK.md
└── GENERATION_SUMMARY.md
```

## 🔌 Integration with Alice Blue

The execution adapter supports Alice Blue integration:

1. **Set credentials:**
```bash
export ALICE_BLUE_USER_ID=your_user_id
export ALICE_BLUE_API_KEY=your_api_key
```

2. **Use AliceBlue adapter:**
```python
from trading.services.execution_adapter import get_execution_adapter

adapter = get_execution_adapter(
    dry_run=False,
    adapter_type="aliceblue",
    user_id=os.getenv("ALICE_BLUE_USER_ID"),
    api_key=os.getenv("ALICE_BLUE_API_KEY")
)
```

**Note:** Real Alice Blue integration requires implementing the API calls in `AliceBlueAdapter`. Currently, it's a placeholder.

## 📝 Logging

Logs are written to console with structured format:
- ✅ Success operations
- ⚠️ Warnings
- ❌ Errors
- 📊 Status updates
- 🎯 Breakout detection
- 📝 Signal creation
- ✅ Trade execution
- 🔚 Trade exit

## 🚨 Emergency Procedures

See `RUNBOOK.md` for:
- Emergency kill switch
- How to disable trading
- How to simulate data
- Troubleshooting

## 📚 Additional Documentation

- `RUNBOOK.md` - Operational procedures
- `GENERATION_SUMMARY.md` - Implementation details

## ⚠️ Disclaimer

This software is for educational purposes only. Trading involves risk of loss. Past performance does not guarantee future results. Always:
- Test thoroughly in dry-run mode
- Start with small capital
- Use proper risk management
- Monitor trades closely
- Consult financial advisors if needed

## 📄 License

[Your License Here]

## 🤝 Contributing

[Your Contributing Guidelines Here]

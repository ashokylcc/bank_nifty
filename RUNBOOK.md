# 🚨 Runbook - Operational Procedures

## Emergency Kill Switch

### Method 1: Django Admin (Recommended)

1. **Access Django Admin:**
   ```
   http://localhost:8000/admin
   ```

2. **Navigate to Trading > Strategies**

3. **Select your strategy**

4. **Uncheck "Enabled" checkbox**

5. **Click "Save"**

The strategy will stop placing new orders immediately. Existing open positions will be monitored and exited normally.

### Method 2: Database (Direct)

```bash
# Connect to database
python manage.py shell

# Disable strategy
from trading.models import Strategy
strategy = Strategy.objects.get(id=1)
strategy.enabled = False
strategy.save()
```

### Method 3: Environment Variable

```bash
# Stop the worker process
docker-compose stop worker

# Or if running manually
# Press Ctrl+C to stop the process
```

## Disable Trading for the Day

### Option 1: Disable Strategy

Follow "Emergency Kill Switch" procedure above.

### Option 2: Set Daily Loss Limit to 0

```python
from trading.models import Strategy
strategy = Strategy.objects.get(id=1)
strategy.max_daily_loss = 0
strategy.save()
```

This will prevent new trades once any loss is detected.

### Option 3: Stop Worker Process

```bash
# Docker
docker-compose stop worker

# Manual
# Find process: ps aux | grep run_strategy
# Kill process: kill <PID>
```

## Simulate Data for Testing

### Method 1: CSV File

1. **Create CSV file** (`sample_data.csv`):
```csv
timestamp,open,high,low,close,volume
2025-11-25T09:15:00,58400,58500,58300,58450,10000
2025-11-25T09:30:00,58450,58550,58400,58500,12000
2025-11-25T09:45:00,58500,58600,58450,58550,20000
```

2. **Load in code:**
```python
from trading.services.data_ingest import DataIngestService

data_service = DataIngestService()
data_service.load_from_csv('sample_data.csv')
```

### Method 2: Mock Execution Adapter

```python
from trading.services.execution_adapter import AliceBlueMockAdapter

adapter = AliceBlueMockAdapter(dry_run=True)
adapter.set_mock_ltp("BANKNIFTY", Decimal('58500'))
adapter.set_mock_ltp("BANKNIFTY27NOV25C58400", Decimal('100.00'))
```

### Method 3: Python Script

Create `simulate_data.py`:
```python
from trading.services.data_ingest import DataIngestService, CandleData
from datetime import datetime
from decimal import Decimal

data_service = DataIngestService()
data_service.connect()

# Add sample candles
candle = CandleData(
    timestamp=datetime.now(),
    open=Decimal('58400'),
    high=Decimal('58500'),
    low=Decimal('58300'),
    close=Decimal('58450'),
    volume=10000
)
data_service.candles.append(candle)
```

## Troubleshooting

### Issue: Strategy Not Running

**Check:**
1. Is strategy enabled? (`strategy.enabled = True`)
2. Is it within trading hours?
3. Are there any errors in logs?
4. Is database connection working?

**Solution:**
```bash
# Check logs
docker-compose logs worker

# Check strategy status
python manage.py shell
>>> from trading.models import Strategy
>>> Strategy.objects.filter(enabled=True).count()
```

### Issue: No Trades Executed

**Possible Reasons:**
1. Range not captured (not 9:15-9:30)
2. No breakout detected
3. Momentum not confirmed (score < 4)
4. Daily loss limit breached
5. Max concurrent trades reached

**Check:**
```python
# Check signals
from trading.models import Signal
Signal.objects.filter(executed=False).count()

# Check why signals not executed
Signal.objects.filter(executed=False).values('execution_reason')
```

### Issue: Orders Not Filling

**Check:**
1. Is execution adapter connected?
2. Is dry-run mode enabled?
3. Are symbols correct?
4. Is market open?

**Solution:**
```python
# Test adapter
from trading.services.execution_adapter import AliceBlueMockAdapter
adapter = AliceBlueMockAdapter()
result = adapter.place_order("BANKNIFTY27NOV25C58400", "BUY", 1)
print(result)
```

### Issue: Database Connection Error

**Check:**
1. Is PostgreSQL running?
2. Are credentials correct?
3. Is database created?

**Solution:**
```bash
# Test connection
python manage.py dbshell

# Create database
createdb banknifty_trading

# Run migrations
python manage.py migrate
```

### Issue: WebSocket Disconnection

**Symptoms:**
- No data updates
- LTP not updating
- Strategy stuck

**Solution:**
1. Check WebSocket connection status
2. Implement reconnection logic (exponential backoff)
3. Restart data service

```python
# In data_ingest.py, add reconnection logic
import time

def connect_with_retry(self, max_retries=5):
    for i in range(max_retries):
        try:
            self.connect()
            return True
        except Exception as e:
            wait_time = 2 ** i  # Exponential backoff
            time.sleep(wait_time)
    return False
```

## Monitoring Checklist

### Daily Checks

- [ ] Strategy enabled in Admin
- [ ] Daily loss limit not breached
- [ ] Open trades count within limit
- [ ] Database connection healthy
- [ ] WebSocket feed connected
- [ ] Execution adapter working

### Weekly Checks

- [ ] Review daily statistics
- [ ] Check win rate
- [ ] Analyze drawdowns
- [ ] Update holiday calendar
- [ ] Review and adjust parameters

## Backup and Recovery

### Backup Database

```bash
# PostgreSQL
pg_dump banknifty_trading > backup.sql

# SQLite
cp db.sqlite3 backup_$(date +%Y%m%d).sqlite3
```

### Restore Database

```bash
# PostgreSQL
psql banknifty_trading < backup.sql

# SQLite
cp backup_20251125.sqlite3 db.sqlite3
```

## Performance Optimization

### Database Indexing

```python
# Add indexes in models.py
class TradeLog(models.Model):
    class Meta:
        indexes = [
            models.Index(fields=['strategy', 'is_open']),
            models.Index(fields=['entry_time']),
        ]
```

### Query Optimization

```python
# Use select_related for foreign keys
trades = TradeLog.objects.select_related('strategy', 'signal').filter(is_open=True)

# Use prefetch_related for many-to-many
signals = Signal.objects.prefetch_related('orders').all()
```

## Logging Configuration

### Enable File Logging

```python
# settings.py
LOGGING = {
    'version': 1,
    'handlers': {
        'file': {
            'class': 'logging.FileHandler',
            'filename': 'trading.log',
        },
    },
    'loggers': {
        'trading': {
            'handlers': ['file'],
            'level': 'INFO',
        },
    },
}
```

## Health Checks

### Create Health Check Endpoint

```python
# views.py
def health(request):
    from trading.models import Strategy
    strategy = Strategy.objects.filter(enabled=True).first()
    return JsonResponse({
        'status': 'healthy' if strategy else 'no_strategy',
        'database': 'connected',
        'timestamp': datetime.now().isoformat()
    })
```

## Contact and Support

- **Documentation:** See README.md
- **Issues:** [Your Issue Tracker]
- **Email:** [Your Support Email]

---

**Last Updated:** 2025-11-25


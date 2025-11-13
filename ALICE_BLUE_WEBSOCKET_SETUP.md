# Alice Blue WebSocket Integration Guide

## Overview

This guide explains how to connect to the real Alice Blue WebSocket to get live market data for the BankNifty Momentum Breakout Strategy.

---

## 1. Prerequisites

### Required Credentials

You need one of the following:

**Option A: User ID + API Key**
```bash
ALICE_BLUE_USER_ID=your_user_id
ALICE_BLUE_API_KEY=your_api_key
```

**Option B: Access Token (Alternative)**
```bash
ALICE_BLUE_USER_ID=your_user_id
ALICE_BLUE_ACCESS_TOKEN=your_access_token
```

### Get Your Credentials

1. **User ID**: Your Alice Blue user ID (e.g., `1293756`)
2. **API Key**: Get from Alice Blue developer portal
3. **Access Token**: Alternative authentication method

---

## 2. Configuration

### Update `.env` File

```bash
# Copy sample config
cp config.sample.env .env

# Edit .env and add your credentials
ALICE_BLUE_USER_ID=your_user_id_here
ALICE_BLUE_API_KEY=your_api_key_here
# OR
ALICE_BLUE_ACCESS_TOKEN=your_access_token_here
```

---

## 3. How It Works

### Integration Flow

1. **Session Creation**: Uses `alice_client.py` to create session
2. **WebSocket Connection**: Connects to Alice Blue WebSocket
3. **Subscription**: Subscribes to BANKNIFTY for tick data
4. **Tick Processing**: Receives real-time ticks and updates LTP cache
5. **Strategy Use**: Strategy engine uses live LTP for decisions

### Code Location

- **WebSocket Integration**: `trading/services/data_ingest_live.py`
- **Session Management**: `strategy/broker/alice_client.py`
- **Alice Blue Library**: Uses `alice-blue` Python package

---

## 4. Running with Real WebSocket

### Command

```bash
# Run with live WebSocket data
python manage.py run_momentum_strategy --loop --live-data --dry-run
```

### What Happens

1. **Connection**: Connects to Alice Blue WebSocket
2. **Subscription**: Subscribes to BANKNIFTY
3. **Live Ticks**: Receives real-time market data
4. **LTP Display**: Shows LIVE LTP in status updates
5. **Strategy**: Uses real prices for breakout detection

### Expected Output

```
✅ DRY-RUN MODE - No real orders
📊 Running Strategy: Test Strategy
📡 Connecting to live WebSocket feed...
✅ Alice Blue session created
✅ Alice Blue WebSocket started
✅ WebSocket connected to Alice Blue
✅ Subscribed to BANKNIFTY (real WebSocket)
🔄 Starting continuous loop (interval: 5s)

[13:32:51] Cycle #12
  Status: Range ⏳ | Open trades: 0 | LIVE LTP: ₹58,423.50
```

---

## 5. Troubleshooting

### Issue: "ALICE_BLUE_USER_ID not set"

**Solution:**
```bash
# Add to .env
ALICE_BLUE_USER_ID=your_user_id
ALICE_BLUE_API_KEY=your_api_key
```

### Issue: "Failed to create session"

**Possible Causes:**
- Invalid credentials
- Network issue
- Alice Blue API down

**Solution:**
- Verify credentials in `.env`
- Check network connection
- Try using `ALICE_BLUE_ACCESS_TOKEN` instead

### Issue: "Instrument not found"

**Solution:**
- Check symbol name (should be exact match)
- Verify exchange (NFO for BankNifty)
- Try searching for instrument first

### Issue: "WebSocket not receiving ticks"

**Check:**
1. Market is open (9:15 AM - 3:30 PM IST)
2. WebSocket is connected (check logs)
3. Subscription successful (check logs)
4. Symbol is correct

---

## 6. Testing

### Test WebSocket Connection

```bash
# Test connection only
python manage.py shell
```

```python
from trading.services.data_ingest_live import LiveDataIngestService
from decimal import Decimal

service = LiveDataIngestService()
if service.connect():
    print("✅ Connected")
    service.subscribe("BANKNIFTY")
    # Wait a few seconds
    import time
    time.sleep(5)
    ltp = service.get_latest_ltp("BANKNIFTY")
    print(f"LTP: {ltp}")
```

### Verify Credentials

```bash
# Test session creation
python -c "from strategy.broker.alice_client import get_encryption_key, get_session_id, USER_ID, API_KEY; enc_key = get_encryption_key(USER_ID); session_id = get_session_id(USER_ID, API_KEY, enc_key); print(f'Session: {session_id[:20]}...')"
```

---

## 7. Fallback Behavior

### Stub Mode

If credentials are not set or connection fails:
- Falls back to stub mode automatically
- Shows warning messages
- Uses test LTP (₹58,423.50) for demonstration
- Strategy still runs but with mock data

### When Stub Mode Activates

- No `ALICE_BLUE_USER_ID` in environment
- Session creation fails
- WebSocket connection fails
- Subscription fails

---

## 8. Real vs. Stub Mode

| Feature | Real WebSocket | Stub Mode |
|---------|---------------|-----------|
| **Data Source** | Alice Blue live feed | Test/mock data |
| **LTP Updates** | Real-time ticks | Static test value |
| **Market Hours** | Only during market hours | Works anytime |
| **Credentials** | Required | Not required |
| **Use Case** | Production/Paper trading | Development/Testing |

---

## 9. Monitoring

### Check Connection Status

```bash
# View logs
tail -f logs/trading.log

# Or check in Django shell
python manage.py shell
```

```python
from trading.services.data_ingest_live import LiveDataIngestService
service = LiveDataIngestService()
print(f"Connected: {service._connected}")
print(f"Subscribed: {service.subscribed_symbols}")
print(f"LTP Cache: {service.ltp_cache}")
```

### View Live Ticks

Ticks are logged every 50th tick to avoid spam:
```
📩 Live tick: BANKNIFTY = ₹58,423.50
```

---

## 10. Best Practices

### Security

- ✅ Never commit `.env` file to git
- ✅ Use environment variables for credentials
- ✅ Rotate API keys regularly
- ✅ Use access tokens when possible

### Performance

- ✅ WebSocket runs in background thread
- ✅ Ticks are processed asynchronously
- ✅ LTP cache updated in real-time
- ✅ Minimal logging to avoid spam

### Reliability

- ✅ Automatic reconnection with exponential backoff
- ✅ Fallback to stub mode on failure
- ✅ Error handling for all operations
- ✅ Connection health monitoring

---

## 11. Next Steps

1. **Set Credentials**: Add to `.env` file
2. **Test Connection**: Run with `--live-data` flag
3. **Verify Ticks**: Check logs for tick reception
4. **Monitor LTP**: Watch status updates for LIVE LTP
5. **Run Strategy**: Strategy will use real prices

---

## Summary

**To get real LIVE LTP:**

1. Set credentials in `.env`:
   ```bash
   ALICE_BLUE_USER_ID=your_user_id
   ALICE_BLUE_API_KEY=your_api_key
   ```

2. Run command:
   ```bash
   python manage.py run_momentum_strategy --loop --live-data --dry-run
   ```

3. You'll see:
   ```
   ✅ Alice Blue WebSocket started
   ✅ Subscribed to BANKNIFTY (real WebSocket)
   LIVE LTP: ₹58,423.50  (updates in real-time)
   ```

---

**Last Updated:** 2025-11-13  
**Status:** ✅ Real WebSocket integration ready


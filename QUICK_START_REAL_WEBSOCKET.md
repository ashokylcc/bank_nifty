# Quick Start - Real Alice Blue WebSocket

## 🚀 Get Real Live Data in 3 Steps

### Step 1: Add Credentials to `.env`

```bash
# Edit .env file
ALICE_BLUE_USER_ID=1293756
ALICE_BLUE_API_KEY=your_api_key_here
```

**Where to get credentials:**
- **User ID**: Your Alice Blue user ID (e.g., `1293756`)
- **API Key**: Get from Alice Blue developer portal or your account

### Step 2: Run Command

```bash
python manage.py run_momentum_strategy --loop --live-data --dry-run
```

### Step 3: Watch Real Data Flow

**You'll see:**
```
✅ DRY-RUN MODE - No real orders
📊 Running Strategy: Test Strategy
📡 Connecting to live WebSocket feed...
✅ Alice Blue session created
✅ Alice Blue WebSocket started
✅ WebSocket connected to Alice Blue
✅ Subscribed to BANKNIFTY (real WebSocket)
⏳ Waiting for WebSocket to be ready...
✅ Real WebSocket connected - receiving live ticks
🔄 Starting continuous loop (interval: 5s)

[13:32:51] Cycle #12
  Status: Range ⏳ | Open trades: 0 | LIVE LTP: ₹58,423.50

[13:33:01] Cycle #14
  Status: Range ⏳ | Open trades: 0 | LIVE LTP: ₹58,425.75
```

**The LTP updates in real-time as market moves!**

---

## ✅ What's Working

1. **Real WebSocket Connection** - Connects to Alice Blue
2. **Live Tick Reception** - Receives real-time market data
3. **LTP Updates** - Updates every tick (shown every ~1 minute in status)
4. **Strategy Uses Real Prices** - Breakout detection uses live LTP
5. **Automatic Reconnection** - Reconnects if connection drops

---

## 🔍 Verify It's Working

### Check 1: Session Created
```
✅ Alice Blue session created
```

### Check 2: WebSocket Started
```
✅ Alice Blue WebSocket started
✅ WebSocket connected to Alice Blue
```

### Check 3: Subscription Successful
```
✅ Subscribed to BANKNIFTY (real WebSocket)
```

### Check 4: Live LTP Updates
```
LIVE LTP: ₹58,423.50  (should change as market moves)
```

---

## ⚠️ Troubleshooting

### Issue: "ALICE_BLUE_USER_ID not set"

**Fix:**
```bash
# Add to .env
ALICE_BLUE_USER_ID=your_user_id
ALICE_BLUE_API_KEY=your_api_key
```

### Issue: "Failed to create session"

**Possible causes:**
- Invalid credentials
- Network issue
- API key expired

**Fix:**
- Verify credentials in `.env`
- Check network connection
- Regenerate API key if needed

### Issue: "Instrument not found"

**Fix:**
- The system will try to find BankNifty future automatically
- If still fails, check market is open (9:15 AM - 3:30 PM IST)

### Issue: "LTP not updating"

**Check:**
1. WebSocket is connected (see logs)
2. Subscription successful (see logs)
3. Market is open
4. Check logs for tick reception

---

## 📊 Expected Behavior

### During Market Hours (9:15 AM - 3:30 PM IST)

- ✅ WebSocket connects
- ✅ Ticks received continuously
- ✅ LTP updates every tick
- ✅ Status shows LIVE LTP every ~1 minute
- ✅ Strategy uses real prices

### Outside Market Hours

- ⚠️ WebSocket may connect but no ticks
- ⚠️ LTP will show last value or "Waiting for data..."
- ✅ Strategy still runs (but won't trade)

---

## 🎯 Next Steps

1. **Test with Real Data**: Run during market hours
2. **Monitor LTP Updates**: Watch status updates
3. **Check Strategy Logic**: Verify breakout detection works
4. **Review Logs**: Check for any errors
5. **Paper Trade**: Run for 10+ days to validate

---

## 📝 Notes

- **Dry-Run Mode**: Orders are still simulated (safe)
- **Real Data**: Prices are real from Alice Blue
- **Automatic**: Everything happens automatically
- **Fallback**: Falls back to stub mode if connection fails

---

**Ready to test!** Add your credentials and run the command.


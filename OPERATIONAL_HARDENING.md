# Operational Hardening Guide

## Overview

This guide covers operational best practices and hardening features for production deployment.

## 1. Network Latency Optimization

### Recommendations

**Host Location:**
- Host trading system near broker endpoints (Mumbai for NSE)
- Use low-latency network connection
- Consider dedicated line or premium internet

**Connection Stability:**
- Use wired connection (avoid WiFi)
- Monitor connection quality
- Set up connection health checks

**Implementation:**
```python
# In data_ingest_live.py
# Use WebSocket with low-latency settings
# Monitor ping/pong for connection health
```

---

## 2. Webhook Reliability & Deduplication

### Order Deduplication

**Location:** `trading/services/order_deduplication.py`

**Features:**
- Prevents duplicate order processing
- Uses broker order IDs for deduplication
- Idempotent order creation

**Usage:**
```python
from trading.services.order_deduplication import OrderDeduplicator

# Check if order exists
if OrderDeduplicator.is_duplicate_order(order_id):
    # Handle duplicate
    pass

# Get or create (idempotent)
order, created = OrderDeduplicator.get_or_create_order(
    order_id=order_id,
    symbol=symbol,
    side=side,
    qty=qty
)
```

**How It Works:**
1. Incoming webhook/order has unique broker order ID
2. Check if order ID already exists in database
3. If exists, return existing order (no duplicate)
4. If not, create new order record

---

## 3. Idempotent Order Placement

### Implementation

**Location:** `trading/services/idempotent_executor.py`

**Features:**
- Checks for existing orders before placing
- Prevents duplicate orders on re-sends
- Handles order status updates idempotently

**Usage:**
```python
from trading.services.idempotent_executor import IdempotentExecutor

executor = IdempotentExecutor(execution_adapter)

# Place order (idempotent)
result = executor.place_order_idempotent(
    symbol="BANKNIFTY27NOV25C58400",
    side="BUY",
    qty=1
)

# Check if order was existing
if result.get('is_existing'):
    logger.info("Order already exists, using existing")
```

**How It Works:**
1. Before placing order, check for similar recent orders (last 5 seconds)
2. If similar order found, return existing (no duplicate)
3. Place order via adapter
4. Create order record (with deduplication check)
5. Return order details

**Benefits:**
- Safe to retry on network errors
- Prevents duplicate orders
- Handles webhook re-delivery

---

## 4. Exponential Backoff & Reconnection

### WebSocket Manager

**Location:** `trading/services/websocket_manager.py`

**Features:**
- Exponential backoff for reconnection
- Configurable retry limits
- Last tick persistence (resume after disconnect)

**Configuration:**
```python
from trading.services.websocket_manager import WebSocketManager

manager = WebSocketManager(
    max_retries=10,        # Maximum reconnection attempts
    initial_backoff=1.0,   # Start with 1 second
    max_backoff=60.0       # Max 60 seconds
)

# Connect with backoff
manager.connect_with_backoff(connect_function)

# Reconnect
manager.reconnect(connect_function)
```

**Backoff Sequence:**
- Attempt 1: Wait 1 second
- Attempt 2: Wait 2 seconds
- Attempt 3: Wait 4 seconds
- Attempt 4: Wait 8 seconds
- ...
- Attempt N: Wait min(2^N, 60) seconds

**Resume After Disconnect:**
```python
# Check if should resume from last tick
if manager.should_resume_from_last_tick():
    last_tick = manager.get_last_tick_time()
    # Resume from last tick (skip already processed)
```

---

## 5. Last Tick Persistence

### Resume Without Reprocessing

**Implementation:**
- Last tick stored per symbol
- Timestamp tracked for resume point
- Deduplication using tick IDs

**Usage:**
```python
# In data_ingest_live.py
# Last tick automatically persisted
# On reconnect, resume from last tick
last_tick = data_service.get_last_tick_for_symbol("BANKNIFTY")
if last_tick:
    # Resume from this point
    pass
```

**Benefits:**
- No duplicate processing after reconnect
- Faster recovery
- Data consistency

---

## 6. Concurrency Control

### Single Authoritative Process

**Location:** `trading/services/concurrency_guard.py`

**Features:**
- File-based locking
- Prevents multiple strategy runners
- Process ID tracking

**Usage:**
```python
from trading.services.concurrency_guard import ConcurrencyGuard

# Check if another instance running
guard = ConcurrencyGuard()
if guard.is_another_instance_running():
    print("Another instance is running!")
    exit(1)

# Acquire lock (context manager)
with guard:
    # Run strategy
    pass
# Lock automatically released
```

**Implementation:**
- Uses file locking (`/tmp/banknifty_strategy.lock`)
- Non-blocking lock acquisition
- Process ID stored in lock file
- Automatic cleanup on exit

**Best Practices:**
- **Production:** Single authoritative process
- **Workers:** Use for non-critical jobs (alerts, reports)
- **Avoid:** Multiple strategy runners (race conditions)

---

## 7. Testing Harness

### CSV-Driven Simulation

**Location:** `trading/services/tick_replay.py`

**Features:**
- Deterministic tick replay
- CSV-driven testing
- Replay until specific time

**Usage:**
```python
from trading.services.tick_replay import TickReplay

replay = TickReplay(data_service)

# Load ticks from CSV
replay.load_ticks_from_csv('test_ticks.csv')

# Replay all ticks
replay.replay_all()

# Or replay until specific time
target_time = datetime(2025, 11, 25, 10, 0, 0)
replay.replay_until_time(target_time)
```

**CSV Format:**
```csv
timestamp,ltp,volume,order_id,symbol
2025-11-25T09:15:00,58400,1000,ORDER_001,BANKNIFTY
2025-11-25T09:15:01,58401,1200,ORDER_002,BANKNIFTY
...
```

**Benefits:**
- Deterministic testing
- Reproducible results
- Easy to create test scenarios

---

## Production Deployment Checklist

### Network & Infrastructure

- [ ] Host near broker endpoints (Mumbai)
- [ ] Use stable, low-latency connection
- [ ] Monitor connection health
- [ ] Set up connection alerts

### Reliability

- [ ] Order deduplication enabled
- [ ] Idempotent order placement
- [ ] WebSocket reconnection with backoff
- [ ] Last tick persistence configured

### Concurrency

- [ ] Single authoritative strategy runner
- [ ] Concurrency guard enabled
- [ ] Workers for non-critical jobs only
- [ ] No multiple strategy instances

### Testing

- [ ] CSV-driven simulation working
- [ ] Tick replay functional
- [ ] Deterministic test results
- [ ] Test scenarios documented

---

## Monitoring & Alerts

### Key Metrics to Monitor

1. **Connection Health**
   - WebSocket connection status
   - Reconnection frequency
   - Last tick timestamp

2. **Order Processing**
   - Duplicate order detection
   - Order fill rates
   - Execution latency

3. **System Health**
   - Lock file status
   - Process uptime
   - Memory usage

### Alert Conditions

- WebSocket disconnected > 5 minutes
- Reconnection attempts > 5
- Duplicate orders detected
- Lock file stale (process died)
- High latency (> 100ms)

---

## Troubleshooting

### Issue: Duplicate Orders

**Symptoms:** Same order placed multiple times

**Fix:**
1. Check order deduplication is enabled
2. Verify broker order IDs are unique
3. Check idempotent executor is used

### Issue: WebSocket Disconnects Frequently

**Symptoms:** Frequent reconnections

**Fix:**
1. Check network stability
2. Increase backoff max time
3. Review connection health
4. Check broker endpoint status

### Issue: Multiple Strategy Runners

**Symptoms:** Race conditions, duplicate trades

**Fix:**
1. Check concurrency guard is enabled
2. Verify only one process running
3. Check for stale lock files
4. Kill duplicate processes

### Issue: Lost Ticks After Reconnect

**Symptoms:** Missing data after disconnect

**Fix:**
1. Enable last tick persistence
2. Resume from last tick
3. Check tick deduplication
4. Verify tick storage

---

## Code Examples

### Using Concurrency Guard

```python
from trading.services.concurrency_guard import ConcurrencyGuard

guard = ConcurrencyGuard()

try:
    with guard:
        # Only one process can execute this
        run_strategy()
except RuntimeError:
    print("Another instance is running")
```

### Using Idempotent Executor

```python
from trading.services.idempotent_executor import IdempotentExecutor

executor = IdempotentExecutor(adapter)

# Safe to retry
result = executor.place_order_idempotent(
    symbol="BANKNIFTY27NOV25C58400",
    side="BUY",
    qty=1
)
```

### Using WebSocket Manager

```python
from trading.services.websocket_manager import WebSocketManager

manager = WebSocketManager()

# Connect with backoff
manager.connect_with_backoff(connect_function)

# Reconnect on disconnect
if not manager.is_connected:
    manager.reconnect(connect_function)
```

---

**Last Updated:** 2025-11-13  
**Status:** ✅ All hardening features implemented


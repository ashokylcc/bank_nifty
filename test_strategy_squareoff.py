#!/usr/bin/env python3
"""
Test strategy square-off functionality
"""

import time
from datetime import datetime, time as dt_time
import pytz

def test_squareoff():
    # Set timezone to IST
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    current_time = now.time()
    
    print("🕐 Strategy Square-off Test")
    print("=" * 40)
    print(f"Current Time (IST): {current_time.strftime('%H:%M:%S')}")
    
    # Strategy parameters
    SQUARE_OFF_TIME = dt_time(13, 0)  # Changed to 1:00 PM
    TARGET_PROFIT = 500
    STOPLOSS = 500
    LOT_SIZE = 35
    
    print(f"Square-off Time: {SQUARE_OFF_TIME.strftime('%H:%M:%S')} (1:00 PM)")
    print(f"Target: ₹{TARGET_PROFIT} | Stoploss: ₹{STOPLOSS}")
    
    # Simulate entry
    entry_price = 150.0
    print(f"Entry Price: ₹{entry_price}")
    
    # Simulate monitoring
    print("\n🔄 Simulating position monitoring...")
    status = "HOLD"
    exit_price = entry_price
    pnl = 0
    
    for i in range(60):  # Simulate 1 minute
        current_time = datetime.now(ist).time()
        
        # Check square-off time
        if current_time >= SQUARE_OFF_TIME:
            status = "TIME EXIT"
            exit_price = entry_price + 5.0  # Small profit
            pnl = (exit_price - entry_price) * LOT_SIZE
            print(f"\n⏰ TIME EXIT: Square-off time reached!")
            print(f"🕐 Current Time: {current_time.strftime('%H:%M:%S')} IST")
            print(f"Exit Price: ₹{exit_price:.2f}")
            print(f"PnL: ₹{pnl:.2f}")
            break
        
        # Simulate price movement
        import random
        price_change = random.uniform(-10, 10)
        current_ltp = entry_price + price_change
        pnl = (current_ltp - entry_price) * LOT_SIZE
        
        # Check target and stoploss
        if pnl >= TARGET_PROFIT:
            status = "TARGET HIT"
            exit_price = current_ltp
            print(f"\n🎯 TARGET HIT! PnL: ₹{pnl:.2f}")
            break
        elif pnl <= -STOPLOSS:
            status = "STOPLOSS HIT"
            exit_price = current_ltp
            print(f"\n🛑 STOPLOSS HIT! PnL: ₹{pnl:.2f}")
            break
        
        # Log every 10 seconds
        if i % 10 == 0:
            print(f"📊 Current PnL: ₹{pnl:.2f} | LTP: ₹{current_ltp:.2f} | Time: {current_time.strftime('%H:%M:%S')} IST")
        
        time.sleep(0.1)  # Fast simulation
    
    print(f"\n📋 Final Status: {status}")
    print(f"Entry: ₹{entry_price:.2f} | Exit: ₹{exit_price:.2f} | PnL: ₹{pnl:.2f}")

if __name__ == "__main__":
    test_squareoff() 
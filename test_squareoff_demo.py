#!/usr/bin/env python3
"""
Demo: Square-off at 1:15 PM
"""

import time
from datetime import datetime, time as dt_time
import pytz

def demo_squareoff():
    # Set timezone to IST
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    current_time = now.time()
    
    print("🕐 Square-off Demo (1:15 PM)")
    print("=" * 40)
    print(f"Current Time: {current_time.strftime('%H:%M:%S')} IST")
    
    # Strategy parameters
    SQUARE_OFF_TIME = dt_time(13, 15)  # 1:15 PM
    TARGET_PROFIT = 500
    STOPLOSS = 500
    LOT_SIZE = 35
    
    print(f"Square-off Time: {SQUARE_OFF_TIME.strftime('%H:%M:%S')} (1:15 PM)")
    print(f"Trading Window: 09:15-13:15 (9:15 AM to 1:15 PM)")
    
    # Check if within trading hours
    if current_time < dt_time(9, 15) or current_time > dt_time(13, 15):
        print(f"❌ Outside trading hours: {current_time.strftime('%H:%M:%S')} IST")
        print(f"✅ Trading window: 09:15-13:15")
        return
    
    print(f"✅ Within trading hours: {current_time.strftime('%H:%M:%S')} IST")
    
    # Simulate trade
    entry_price = 150.0
    print(f"\n💰 Entry Price: ₹{entry_price}")
    print(f"🎯 Target: ₹{TARGET_PROFIT} | Stoploss: ₹{STOPLOSS}")
    
    # Simulate monitoring
    print(f"\n🔄 Monitoring until 1:15 PM...")
    status = "HOLD"
    exit_price = entry_price
    pnl = 0
    
    for i in range(30):  # Simulate 30 seconds
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
        
        # Log every 5 seconds
        if i % 5 == 0:
            print(f"📊 PnL: ₹{pnl:.2f} | LTP: ₹{current_ltp:.2f} | Time: {current_time.strftime('%H:%M:%S')} IST")
        
        time.sleep(0.1)  # Fast simulation
    
    print(f"\n📋 Final Status: {status}")
    print(f"Entry: ₹{entry_price:.2f} | Exit: ₹{exit_price:.2f} | PnL: ₹{pnl:.2f}")
    
    # Summary
    print(f"\n📈 Strategy Summary:")
    print(f"✅ Trading Window: 09:15-13:15")
    print(f"✅ Square-off Time: 13:15 (1:15 PM)")
    print(f"✅ Target: ₹{TARGET_PROFIT} | Stoploss: ₹{STOPLOSS}")
    print(f"✅ Automatic exit at 1:15 PM if no target/stoploss hit")

if __name__ == "__main__":
    demo_squareoff() 
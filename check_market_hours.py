#!/usr/bin/env python3
"""
Check if market is currently open
"""

import pytz
from datetime import datetime, time as dt_time

def check_market_hours():
    # Set timezone to IST
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    current_time = now.time()
    
    print("🕐 Market Hours Check")
    print("=" * 30)
    print(f"Current Time: {current_time.strftime('%H:%M:%S')} IST")
    print(f"Current Date: {now.strftime('%Y-%m-%d')}")
    
    # Market hours (IST)
    market_start = dt_time(9, 0)   # 9:00 AM
    market_end = dt_time(15, 30)   # 3:30 PM
    
    print(f"Market Hours: {market_start.strftime('%H:%M')} - {market_end.strftime('%H:%M')} IST")
    
    # Check if market is open
    if market_start <= current_time <= market_end:
        print("✅ Market is OPEN")
        print("✅ You can run the strategy for live trading")
    else:
        print("❌ Market is CLOSED")
        print("💡 Use --simulate flag for testing")
        
        # Calculate time until market opens
        if current_time < market_start:
            # Market opens later today
            hours_until_open = (market_start.hour - current_time.hour) * 60 + (market_start.minute - current_time.minute)
            print(f"⏰ Market opens in {hours_until_open} minutes")
        else:
            # Market closed for today
            print("🌙 Market closed for today")
    
    # Trading strategy hours
    strategy_start = dt_time(9, 15)   # 9:15 AM
    strategy_end = dt_time(13, 15)    # 1:15 PM
    
    print(f"\n📊 Strategy Trading Window: {strategy_start.strftime('%H:%M')} - {strategy_end.strftime('%H:%M')} IST")
    
    if strategy_start <= current_time <= strategy_end:
        print("✅ Within strategy trading hours")
    else:
        print("❌ Outside strategy trading hours")
        if current_time < strategy_start:
            print(f"⏰ Strategy starts at {strategy_start.strftime('%H:%M')} IST")
        else:
            print(f"⏰ Strategy ended at {strategy_end.strftime('%H:%M')} IST")

if __name__ == "__main__":
    check_market_hours() 
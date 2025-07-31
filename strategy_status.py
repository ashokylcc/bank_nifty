#!/usr/bin/env python3
"""
Bank Nifty Strategy Status
"""

import pytz
from datetime import datetime, time as dt_time

def show_strategy_status():
    print("🏦 Bank Nifty Strategy Status")
    print("=" * 40)
    
    # Set timezone to IST
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    current_time = now.time()
    
    print(f"🕐 Current Time: {current_time.strftime('%H:%M:%S')} IST")
    print(f"📅 Date: {now.strftime('%Y-%m-%d')}")
    
    # Market hours
    market_start = dt_time(9, 0)
    market_end = dt_time(15, 30)
    strategy_start = dt_time(9, 15)
    strategy_end = dt_time(13, 15)
    
    # Check market status
    if market_start <= current_time <= market_end:
        print("✅ Market: OPEN")
    else:
        print("❌ Market: CLOSED")
    
    # Check strategy window
    if strategy_start <= current_time <= strategy_end:
        print("✅ Strategy Window: ACTIVE")
        print("🚀 Ready to run: python3 manage.py run_strategy")
    else:
        print("⏸️ Strategy Window: INACTIVE")
        if current_time < strategy_start:
            print(f"⏰ Strategy starts at {strategy_start.strftime('%H:%M')} IST")
        else:
            print(f"⏰ Strategy ended at {strategy_end.strftime('%H:%M')} IST")
    
    print(f"\n📊 Trading Hours:")
    print(f"   Market: {market_start.strftime('%H:%M')} - {market_end.strftime('%H:%M')} IST")
    print(f"   Strategy: {strategy_start.strftime('%H:%M')} - {strategy_end.strftime('%H:%M')} IST")
    
    print(f"\n🎯 Strategy Parameters:")
    print(f"   Yesterday's Closing: ₹56200")
    print(f"   Target Profit: ₹500")
    print(f"   Stoploss: ₹500")
    print(f"   Lot Size: 35 contracts")
    print(f"   Square-off Time: 13:15 IST")
    
    print(f"\n💡 Commands:")
    print(f"   Live Trading: python3 manage.py run_strategy")
    print(f"   Simulation: python3 manage.py run_strategy --simulate")
    print(f"   Market Check: python3 check_market_hours.py")

if __name__ == "__main__":
    show_strategy_status() 
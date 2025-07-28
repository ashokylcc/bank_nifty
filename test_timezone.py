#!/usr/bin/env python3
"""
Test timezone fix
"""

import pytz
from datetime import datetime, time as dt_time

def test_timezone():
    # Set timezone to IST
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    current_time = now.time()
    
    print("🕐 Timezone Test")
    print("=" * 30)
    print(f"Current Time (IST): {current_time.strftime('%H:%M:%S')}")
    print(f"Current DateTime (IST): {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    # Test square-off time
    SQUARE_OFF_TIME = dt_time(9, 45)
    print(f"Square-off Time: {SQUARE_OFF_TIME.strftime('%H:%M:%S')}")
    
    # Test comparison
    if current_time >= SQUARE_OFF_TIME:
        print("✅ Time comparison works: Current time >= Square-off time")
    else:
        print("✅ Time comparison works: Current time < Square-off time")
    
    print(f"Time difference: {current_time} vs {SQUARE_OFF_TIME}")

if __name__ == "__main__":
    test_timezone() 
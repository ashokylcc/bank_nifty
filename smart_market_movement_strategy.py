#!/usr/bin/env python3
"""
🎯 SMART MARKET MOVEMENT STRATEGY
=================================

This strategy waits for strong market movements and enters at the right time
for maximum profit potential.

Key Features:
- Waits for strong market movement (2%+ or 100+ points)
- Enters only when momentum is confirmed
- Uses trailing stoploss for maximum profit
- Exits at optimal profit levels
- Avoids false breakouts and sideways markets

Usage:
    python3 smart_market_movement_strategy.py
"""

import os
import sys
import django
from datetime import datetime, time as dt_time
import pytz

# Add the project directory to Python path
sys.path.append('/var/www/html/bank_nifty')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'banknifty_trader.settings')
django.setup()

from strategy.management.commands.run_strategy import Command

def main():
    """
    🎯 SMART MARKET MOVEMENT STRATEGY
    =================================
    
    This strategy waits for strong market movements and enters at the right time
    for maximum profit potential.
    """
    
    print("🎯 SMART MARKET MOVEMENT STRATEGY")
    print("=" * 50)
    print("📊 Strategy Overview:")
    print("   • Wait for strong market movement (2%+ or 100+ points)")
    print("   • Enter only when momentum is confirmed")
    print("   • Use trailing stoploss for maximum profit")
    print("   • Exit at optimal profit levels")
    print("   • Avoid false breakouts and sideways markets")
    print("=" * 50)
    
    # Get current time
    ist = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(ist)
    
    print(f"🕐 Current Time: {current_time.strftime('%H:%M:%S')} IST")
    
    # Check if we're in trading hours
    trading_start = dt_time(9, 15)
    trading_end = dt_time(15, 30)
    current_time_only = current_time.time()
    
    if trading_start <= current_time_only <= trading_end:
        print("✅ Market is OPEN - Ready to trade!")
    else:
        print("❌ Market is CLOSED - Strategy will not execute")
        return
    
    print("\n🎯 Strategy Parameters:")
    print("   • Quantity: 1 (35 lots)")
    print("   • Capital Required: ₹17,500")
    print("   • Target Profit: ₹800-1200 (based on movement)")
    print("   • Stoploss: ₹200-400 (trailing)")
    print("   • Square-off Time: 1:00 PM")
    
    print("\n🛡️ Risk Management:")
    print("   • Max Daily Loss: ₹1,000")
    print("   • Max Trades per Day: 3")
    print("   • Trailing Stoploss: Lock in profits")
    print("   • Dynamic Targets: Based on movement strength")
    
    print("\n📈 Entry Criteria:")
    print("   • Strong Movement: 2%+ or 100+ points")
    print("   • Momentum Confirmation: 3 consecutive higher highs")
    print("   • Volume Confirmation: Above average volume")
    print("   • Time Window: 9:30 AM - 12:00 PM")
    
    print("\n🎯 Profit Targets by Movement:")
    print("   • Strong Movement (2%+): ₹1,200 target, ₹200 stoploss")
    print("   • Moderate Movement (1%+): ₹800 target, ₹300 stoploss")
    print("   • Weak Movement (0.5%+): ₹500 target, ₹400 stoploss")
    
    print("\n" + "=" * 50)
    print("🚀 Starting Smart Market Movement Strategy...")
    print("=" * 50)
    
    # Run the strategy
    try:
        command = Command()
        command.handle()
    except Exception as e:
        print(f"❌ Error running strategy: {e}")
        return
    
    print("\n" + "=" * 50)
    print("✅ Smart Market Movement Strategy completed!")
    print("=" * 50)

if __name__ == "__main__":
    main()

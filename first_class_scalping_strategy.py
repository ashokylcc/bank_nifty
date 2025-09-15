#!/usr/bin/env python3
"""
🚀 FIRST-CLASS SCALPING STRATEGY FOR BANK NIFTY OPTIONS
=======================================================

This is an advanced scalping strategy designed to achieve consistent daily profits
of ₹500+ with proper risk management and dynamic targets.

Key Features:
- Dynamic profit targets based on trend strength
- Advanced risk management with volatility-based stoploss
- Scalping window optimization (9:15 AM - 10:00 AM)
- Multiple entry criteria for different market conditions
- Daily loss limits and trade limits
- Real-time market analysis

Usage:
    python3 first_class_scalping_strategy.py
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
    🚀 FIRST-CLASS SCALPING STRATEGY
    ================================
    
    This strategy is designed to achieve consistent daily profits of ₹500+
    with advanced risk management and dynamic targets.
    """
    
    print("🚀 FIRST-CLASS SCALPING STRATEGY")
    print("=" * 50)
    print("📊 Strategy Overview:")
    print("   • Daily Target: ₹500+ per quantity")
    print("   • Scalping Window: 9:15 AM - 10:00 AM")
    print("   • Dynamic Targets: Based on trend strength")
    print("   • Risk Management: Volatility-based stoploss")
    print("   • Max Daily Loss: ₹1,000 per quantity")
    print("   • Max Trades: 5 per day")
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
    
    # Check if we're in scalping window
    scalping_start = dt_time(9, 15)
    scalping_end = dt_time(10, 0)
    
    if scalping_start <= current_time_only <= scalping_end:
        print("🔥 SCALPING WINDOW ACTIVE - Aggressive trading mode!")
    else:
        print("⏰ Outside scalping window - Conservative trading mode")
    
    print("\n🎯 Strategy Parameters:")
    print("   • Quantity: 1 (35 lots)")
    print("   • Capital Required: ₹17,500")
    print("   • Target Profit: ₹500")
    print("   • Stoploss: ₹200 (tighter for scalping)")
    print("   • Square-off Time: 1:00 PM")
    
    print("\n🛡️ Risk Management:")
    print("   • Max Daily Loss: ₹1,000")
    print("   • Max Trades per Day: 5")
    print("   • Dynamic Stoploss: Based on volatility")
    print("   • Dynamic Targets: Based on trend strength")
    
    print("\n📈 Entry Criteria:")
    print("   • Scalping Window: 3 points movement, 0.3% change")
    print("   • Normal Window: 5 points movement, 0.5% change")
    print("   • Strong Trend: 2%+ movement")
    print("   • Moderate Trend: 1%+ movement")
    print("   • Weak Trend: 0.5%+ movement")
    
    print("\n🎯 Profit Targets by Trend:")
    print("   • Strong Trend: ₹800 target, ₹150 stoploss")
    print("   • Moderate Trend: ₹500 target, ₹200 stoploss")
    print("   • Weak Trend: ₹300 target, ₹300 stoploss")
    
    print("\n" + "=" * 50)
    print("🚀 Starting First-Class Scalping Strategy...")
    print("=" * 50)
    
    # Run the strategy
    try:
        command = Command()
        command.handle()
    except Exception as e:
        print(f"❌ Error running strategy: {e}")
        return
    
    print("\n" + "=" * 50)
    print("✅ First-Class Scalping Strategy completed!")
    print("=" * 50)

if __name__ == "__main__":
    main()

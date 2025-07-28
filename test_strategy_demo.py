#!/usr/bin/env python3
"""
Bank Nifty Strategy Demo
This demonstrates the Future-based option selection and automatic square-off logic.
"""

import time
from datetime import datetime, time as dt_time
import pytz

def demo_strategy():
    """Demo the strategy logic"""
    
    # Set timezone to IST
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    current_time = now.time()
    
    print("🚀 Bank Nifty Future-Based Option Strategy Demo")
    print("=" * 60)
    print(f"🕐 Current Time: {current_time.strftime('%H:%M:%S')} IST")
    
    # Strategy Parameters
    YESTERDAY_CLOSING = 56600
    LOT_SIZE = 35
    TARGET_PROFIT = 500
    STOPLOSS = 500
    SQUARE_OFF_TIME = dt_time(9, 45)
    
    print(f"📊 Yesterday's Closing: ₹{YESTERDAY_CLOSING}")
    print(f"🎯 Target: ₹{TARGET_PROFIT} | Stoploss: ₹{STOPLOSS}")
    print(f"⏰ Square-off Time: {SQUARE_OFF_TIME.strftime('%H:%M:%S')}")
    
    # Simulate Future LTP
    import random
    future_ltp = YESTERDAY_CLOSING + random.uniform(-200, 200)
    print(f"\n💰 Simulated Future LTP: ₹{future_ltp:.2f}")
    
    # Determine Future Direction
    price_change = future_ltp - YESTERDAY_CLOSING
    if price_change > 0:
        future_direction = "BUY"
        print(f"🚀 FUTURE SIGNAL: BUY (Price up ₹{price_change:.2f})")
    else:
        future_direction = "SELL"
        print(f"📉 FUTURE SIGNAL: SELL (Price down ₹{abs(price_change):.2f})")
    
    # Select Option
    base_strike = int(round(YESTERDAY_CLOSING / 100.0) * 100)
    expiry = "31JUL25"
    
    if future_direction == "BUY":
        strike_price = base_strike + 100  # OTM Call
        option_symbol = f"BANKNIFTY{expiry}C{strike_price}"
        option_direction = "BUY"
        print(f"📞 FUTURE=BUY → BUY Call Option: {option_symbol}")
    else:
        strike_price = base_strike - 100  # OTM Put
        option_symbol = f"BANKNIFTY{expiry}P{strike_price}"
        option_direction = "BUY"
        print(f"📞 FUTURE=SELL → BUY Put Option: {option_symbol}")
    
    print(f"🎯 Strike Price: ₹{strike_price} (OTM)")
    
    # Simulate Entry Price
    entry_price = random.uniform(50, 200)
    print(f"💰 Entry Price: ₹{entry_price:.2f}")
    print(f"🎯 TRADE EXECUTED: {option_direction} {option_symbol} at ₹{entry_price:.2f}")
    
    # Monitor Position
    print(f"\n🔄 Starting position monitoring...")
    print(f"📊 Target: ₹{TARGET_PROFIT} | Stoploss: ₹{STOPLOSS} | Exit Time: {SQUARE_OFF_TIME.strftime('%H:%M:%S')}")
    
    status = "HOLD"
    exit_price = entry_price
    pnl = 0
    entry_time = datetime.now(ist)
    
    # Simulate monitoring for 2 minutes
    for i in range(120):  # 2 minutes simulation
        current_time = datetime.now(ist).time()
        
        # Check square-off time
        if current_time >= SQUARE_OFF_TIME:
            status = "TIME EXIT"
            exit_price = entry_price + random.uniform(-10, 20)
            pnl = (exit_price - entry_price) * LOT_SIZE
            print(f"\n⏰ TIME EXIT: Square-off time reached!")
            print(f"🕐 Current Time: {current_time.strftime('%H:%M:%S')} IST")
            break
        
        # Simulate price movement
        price_change = random.uniform(-15, 15)
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
        
        # Log every 30 seconds
        if i % 30 == 0:
            print(f"📊 Current PnL: ₹{pnl:.2f} | LTP: ₹{current_ltp:.2f} | Time: {current_time.strftime('%H:%M:%S')} IST")
        
        time.sleep(0.1)  # Fast simulation
    
    # Final Summary
    print(f"\n" + "=" * 50)
    print(f"📋 TRADE SUMMARY")
    print(f"=" * 50)
    print(f"Future LTP: ₹{future_ltp:.2f}")
    print(f"Future Direction: {future_direction}")
    print(f"Yesterday's Closing: ₹{YESTERDAY_CLOSING}")
    print(f"Option Symbol: {option_symbol}")
    print(f"Option Direction: {option_direction}")
    print(f"Strike Price: ₹{strike_price}")
    print(f"Entry Price: ₹{entry_price:.2f}")
    print(f"Exit Price: ₹{exit_price:.2f}")
    print(f"Status: {status}")
    print(f"PnL: ₹{pnl:.2f}")
    print(f"Lot Size: {LOT_SIZE}")
    print(f"=" * 50)
    
    # Strategy Logic Summary
    print(f"\n📈 Strategy Logic:")
    print(f"✅ Future Direction Detection: {future_direction}")
    print(f"✅ Option Selection: {option_symbol}")
    print(f"✅ Automatic Square-off: {SQUARE_OFF_TIME.strftime('%H:%M:%S')}")
    print(f"✅ Risk Management: Target ₹{TARGET_PROFIT}, Stoploss ₹{STOPLOSS}")
    print(f"✅ Trade Logging: Complete")

if __name__ == "__main__":
    demo_strategy() 
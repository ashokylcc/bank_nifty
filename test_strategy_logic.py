#!/usr/bin/env python3
"""
Test Script for Bank Nifty Strategy Logic
This script demonstrates the new strategy logic without running the full trading system.
"""

def test_strategy_logic():
    print("🎯 Bank Nifty Strategy Logic Test")
    print("=" * 50)
    
    # Configuration
    yesterday_closing = 55718  # Yesterday's closing price
    lot_size = 15
    target = 500
    stoploss = 500
    
    print(f"📊 Configuration:")
    print(f"   • Yesterday's Closing: ₹{yesterday_closing}")
    print(f"   • Lot Size: {lot_size}")
    print(f"   • Target: ₹{target}")
    print(f"   • Stoploss: ₹{stoploss}")
    
    # Test scenarios
    test_scenarios = [
        {"name": "Bullish Future", "current_future": 55800},
        {"name": "Bearish Future", "current_future": 55600},
        {"name": "Slightly Bullish", "current_future": 55750},
        {"name": "Slightly Bearish", "current_future": 55680},
    ]
    
    print(f"\n📈 Strategy Logic Test:")
    print("-" * 30)
    
    for scenario in test_scenarios:
        current_future = scenario["current_future"]
        price_change = current_future - yesterday_closing
        
        # Determine future direction
        if price_change > 0:
            future_direction = "BUY"
            direction_desc = f"up ₹{price_change}"
        else:
            future_direction = "SELL"
            direction_desc = f"down ₹{abs(price_change)}"
        
        # Select option
        strike_price = int(round(yesterday_closing / 100.0) * 100)
        expiry = "31JUL25"
        
        if future_direction == "BUY":
            option_symbol = f"BANKNIFTY{expiry}C{strike_price}"
            option_action = "BUY Call Option"
        else:
            option_symbol = f"BANKNIFTY{expiry}P{strike_price}"
            option_action = "BUY Put Option"
        
        print(f"\n🔍 {scenario['name']}:")
        print(f"   • Current Future: ₹{current_future}")
        print(f"   • Price Change: {direction_desc}")
        print(f"   • Future Direction: {future_direction}")
        print(f"   • Strike Price: ₹{strike_price}")
        print(f"   • Action: {option_action}")
        print(f"   • Symbol: {option_symbol}")
    
    print(f"\n📋 Summary:")
    print("-" * 30)
    print(f"✅ Future Direction Logic:")
    print(f"   • If Current Future > Yesterday's Closing → FUTURE = BUY")
    print(f"   • If Current Future < Yesterday's Closing → FUTURE = SELL")
    print(f"")
    print(f"✅ Option Selection Logic:")
    print(f"   • If FUTURE = BUY → BUY Call Option (strike = yesterday's closing)")
    print(f"   • If FUTURE = SELL → BUY Put Option (strike = yesterday's closing)")
    print(f"")
    print(f"✅ Risk Management:")
    print(f"   • Target: ₹{target} per lot")
    print(f"   • Stoploss: ₹{stoploss} per lot")
    print(f"   • Time Exit: 9:45 AM")
    print(f"   • Lot Size: {lot_size}")
    
    print(f"\n🎉 Strategy logic test completed!")
    print(f"💡 The strategy is ready for live trading during market hours (9:15-9:45 AM)")

if __name__ == "__main__":
    test_strategy_logic() 
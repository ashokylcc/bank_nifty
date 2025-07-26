#!/usr/bin/env python3
"""
Daily Parameter Update Script
This script helps you easily update the daily parameters for the Bank Nifty strategy.
"""

import re
from datetime import datetime

def update_daily_parameters():
    print("📅 Bank Nifty Strategy - Daily Parameter Update")
    print("=" * 50)
    
    # Get today's date
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"📅 Date: {today}")
    
    # Get user input for daily parameters
    print("\n🔧 Please enter today's parameters:")
    print("-" * 30)
    
    try:
        yesterday_closing = float(input("💰 Yesterday's Bank Nifty Closing Price: "))
        lot_size = int(input("📦 Lot Size (default 35): ") or "35")
        target_profit = float(input("🎯 Target Profit per lot (default 500): ") or "500")
        stoploss = float(input("🛑 Stoploss per lot (default 500): ") or "500")
        
        print(f"\n✅ Parameters received:")
        print(f"   • Yesterday's Closing: ₹{yesterday_closing}")
        print(f"   • Lot Size: {lot_size}")
        print(f"   • Target: ₹{target_profit}")
        print(f"   • Stoploss: ₹{stoploss}")
        
        # Update the strategy file
        update_strategy_file(yesterday_closing, lot_size, target_profit, stoploss)
        
        print(f"\n🎉 Daily parameters updated successfully!")
        print(f"💡 You can now run: ./run_banknifty_strategy.sh run")
        
    except ValueError as e:
        print(f"❌ Error: Please enter valid numbers. {e}")
    except KeyboardInterrupt:
        print(f"\n❌ Update cancelled by user.")

def update_strategy_file(yesterday_closing, lot_size, target_profit, stoploss):
    """Update the strategy file with new parameters"""
    
    strategy_file = "strategy/management/commands/run_strategy.py"
    
    try:
        # Read the current file
        with open(strategy_file, 'r') as f:
            content = f.read()
        
        # Update the parameters section
        new_params = f"""        # ========================================
        # DAILY MANUAL PARAMETERS - UPDATE THESE DAILY
        # ========================================
        LOT_SIZE = {lot_size}                    # Bank Nifty lot size
        TARGET_PROFIT = {target_profit}              # Target profit per lot (₹{target_profit})
        STOPLOSS = {stoploss}                   # Stoploss per lot (₹{stoploss})
        YESTERDAY_CLOSING = {yesterday_closing}        # Yesterday's Bank Nifty closing price
        # ========================================"""
        
        # Replace the parameters section
        pattern = r'# ========================================\s*# DAILY MANUAL PARAMETERS - UPDATE THESE DAILY\s*# ========================================.*?# ========================================'
        updated_content = re.sub(pattern, new_params, content, flags=re.DOTALL)
        
        # Write the updated content back
        with open(strategy_file, 'w') as f:
            f.write(updated_content)
            
        print(f"✅ Strategy file updated: {strategy_file}")
        
    except Exception as e:
        print(f"❌ Error updating file: {e}")

def show_current_parameters():
    """Show current parameters in the strategy file"""
    
    strategy_file = "strategy/management/commands/run_strategy.py"
    
    try:
        with open(strategy_file, 'r') as f:
            content = f.read()
        
        # Extract current parameters
        lot_size_match = re.search(r'LOT_SIZE = (\d+)', content)
        target_match = re.search(r'TARGET_PROFIT = (\d+)', content)
        stoploss_match = re.search(r'STOPLOSS = (\d+)', content)
        closing_match = re.search(r'YESTERDAY_CLOSING = (\d+)', content)
        
        print("📊 Current Parameters:")
        print("-" * 30)
        if lot_size_match:
            print(f"   • Lot Size: {lot_size_match.group(1)}")
        if target_match:
            print(f"   • Target: ₹{target_match.group(1)}")
        if stoploss_match:
            print(f"   • Stoploss: ₹{stoploss_match.group(1)}")
        if closing_match:
            print(f"   • Yesterday's Closing: ₹{closing_match.group(1)}")
            
    except Exception as e:
        print(f"❌ Error reading current parameters: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "show":
        show_current_parameters()
    else:
        update_daily_parameters() 
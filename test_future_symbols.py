#!/usr/bin/env python3
"""
Test to find correct Bank Nifty Future symbols
"""

import pandas as pd
import re
from datetime import datetime

def test_future_symbols():
    print("🔍 Testing Bank Nifty Future Symbols")
    print("=" * 40)
    
    try:
        # Read the contract master file
        df = pd.read_csv("NFO.csv")
        print(f"✅ Contract master loaded: {len(df)} contracts")
        
        # Filter Bank Nifty futures
        banknifty_futures = df[(df['Symbol'] == 'BANKNIFTY') & (df['Instrument Type'] == 'FUTIDX')].copy()
        print(f"📊 Found {len(banknifty_futures)} Bank Nifty futures")
        
        if banknifty_futures.empty:
            print("❌ No Bank Nifty futures found!")
            return
        
        # Show all Bank Nifty futures
        print("\n📋 Available Bank Nifty Futures:")
        print("-" * 40)
        for idx, row in banknifty_futures.iterrows():
            print(f"Symbol: {row['Trading Symbol']}")
            print(f"  Expiry: {row.get('Expiry', 'N/A')}")
            print(f"  Strike: {row.get('Strike Price', 'N/A')}")
            print()
        
        # Try to find the current active future
        today = datetime.now().date()
        print(f"📅 Today's date: {today}")
        
        # Extract expiry dates
        def extract_expiry(ts):
            m = re.search(r'BANKNIFTY(\d{2}[A-Z]{3}\d{2})F', ts)
            if m:
                try:
                    return datetime.strptime(m.group(1), "%d%b%y").date()
                except:
                    return None
            return None
        
        banknifty_futures['expiry'] = banknifty_futures['Trading Symbol'].apply(extract_expiry)
        
        # Filter valid expiries
        valid_futures = banknifty_futures[banknifty_futures['expiry'].notna()]
        
        if valid_futures.empty:
            print("❌ No valid expiry dates found!")
            return
        
        # Find current/next expiry
        current_futures = valid_futures[valid_futures['expiry'] >= today]
        
        if current_futures.empty:
            print("❌ No current/upcoming futures found!")
            return
        
        # Sort by expiry and get the nearest
        current_futures = current_futures.sort_values('expiry')
        nearest_future = current_futures.iloc[0]
        
        print(f"🎯 Recommended Future Symbol: {nearest_future['Trading Symbol']}")
        print(f"   Expiry: {nearest_future['expiry']}")
        print(f"   Days to expiry: {(nearest_future['expiry'] - today).days}")
        
        # Show all current futures
        print(f"\n📋 Current/Upcoming Bank Nifty Futures:")
        print("-" * 40)
        for idx, row in current_futures.iterrows():
            days_to_expiry = (row['expiry'] - today).days
            print(f"Symbol: {row['Trading Symbol']}")
            print(f"  Expiry: {row['expiry']} ({days_to_expiry} days)")
            print()
        
    except FileNotFoundError:
        print("❌ NFO.csv file not found!")
        print("Please download the contract master file first.")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_future_symbols() 
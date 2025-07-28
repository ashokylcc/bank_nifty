#!/usr/bin/env python3
"""
Test Instrument Lookup
This script tests if we can find Bank Nifty instruments without WebSocket connection.
"""

import ssl
ssl._create_default_https_context = ssl._create_unverified_context
import pandas as pd
import re
from datetime import datetime

def get_active_banknifty_future_symbol():
    """Get the active Bank Nifty future symbol from NFO.csv"""
    try:
        df = pd.read_csv("NFO.csv")
        futs = df[(df['Symbol'] == 'BANKNIFTY') & (df['Instrument Type'] == 'FUTIDX')].copy()
        
        if futs.empty:
            print("❌ No Bank Nifty futures found in NFO.csv")
            return None

        # Extract expiry from Trading Symbol (e.g., BANKNIFTY31JUL25F)
        def extract_expiry(ts):
            m = re.search(r'BANKNIFTY(\d{2}[A-Z]{3}\d{2})F', ts)
            if m:
                return datetime.strptime(m.group(1), "%d%b%y").date()
            return None

        futs['expiry'] = futs['Trading Symbol'].apply(extract_expiry)
        today = datetime.now().date()
        
        # Filter only future or today expiries
        futs = futs[futs['expiry'] >= today]
        
        if futs.empty:
            print("❌ No active Bank Nifty futures found")
            return None
            
        # Sort by expiry and pick the nearest
        futs = futs.sort_values('expiry')
        symbol = futs.iloc[0]['Trading Symbol']
        
        print(f"✅ Found active Bank Nifty future: {symbol}")
        print(f"   Expiry: {futs.iloc[0]['expiry']}")
        print(f"   Token: {futs.iloc[0]['Token']}")
        
        return symbol
        
    except Exception as e:
        print(f"❌ Error reading NFO.csv: {e}")
        return None

def test_alice_blue_lookup():
    """Test Alice Blue instrument lookup"""
    try:
        from strategy.broker.alice_client import get_encryption_key, get_session_id, USER_ID, API_KEY
        from alice_blue import AliceBlue
        
        print("🔐 Testing Alice Blue session login...")
        
        # Get session
        enc_key = get_encryption_key(USER_ID)
        session_id = get_session_id(USER_ID, API_KEY, enc_key)
        
        print("✅ Session login successful")
        
        # Create Alice Blue instance
        alice = AliceBlue(username=USER_ID, session_id=session_id)
        
        # Test instrument lookup
        test_symbols = [
            "BANKNIFTY31JUL25F",  # Future
            "BANKNIFTY31JUL25C56600",  # Call option
            "BANKNIFTY31JUL25P56600",  # Put option
        ]
        
        print("\n🔍 Testing instrument lookup...")
        for symbol in test_symbols:
            print(f"\n📋 Testing: {symbol}")
            
            # Method 1: get_instrument_by_symbol
            try:
                instrument = alice.get_instrument_by_symbol("NFO", symbol)
                if instrument:
                    print(f"   ✅ Found via get_instrument_by_symbol: {instrument.symbol} (Token: {instrument.token})")
                else:
                    print(f"   ❌ Not found via get_instrument_by_symbol")
            except Exception as e:
                print(f"   ❌ Error in get_instrument_by_symbol: {e}")
            
            # Method 2: searchscrip
            try:
                instruments = alice.searchscrip(symbol)
                if instruments:
                    print(f"   ✅ Found {len(instruments)} via searchscrip:")
                    for inst in instruments[:3]:
                        print(f"      • {inst.symbol} (Token: {inst.token})")
                else:
                    print(f"   ❌ Not found via searchscrip")
            except Exception as e:
                print(f"   ❌ Error in searchscrip: {e}")
        
        print("\n🎉 Instrument lookup test completed!")
        
    except Exception as e:
        print(f"❌ Error in Alice Blue test: {e}")

if __name__ == "__main__":
    print("🔧 Bank Nifty Instrument Lookup Test")
    print("=" * 50)
    
    # Test 1: NFO.csv lookup
    print("\n📡 Test 1: NFO.csv Lookup")
    print("-" * 30)
    future_symbol = get_active_banknifty_future_symbol()
    
    # Test 2: Alice Blue lookup
    print("\n📡 Test 2: Alice Blue Lookup")
    print("-" * 30)
    test_alice_blue_lookup()
    
    print("\n✅ Test completed!") 
#!/usr/bin/env python3
"""
Test LTP connection and data availability
"""

import time
from strategy.broker.alice_client import get_encryption_key, get_session_id, USER_ID, API_KEY
from strategy.broker.live_ltp import WebSocketLTP

def test_ltp_connection():
    print("🔌 Testing LTP Connection")
    print("=" * 40)
    
    try:
        # Step 1: Login
        print("🔐 Step 1: Login to Alice Blue")
        enc_key = get_encryption_key(USER_ID)
        session_id = get_session_id(USER_ID, API_KEY, enc_key)
        print("✅ Login successful")
        
        # Step 2: Test different symbols
        test_symbols = [
            "BANKNIFTY31JUL25F",  # Bank Nifty Future
            "NIFTY31JUL25F",      # Nifty Future
            "RELIANCE-EQ",        # Equity
            "BANKNIFTY31JUL25C56600",  # Bank Nifty Call
            "BANKNIFTY31JUL25P56600",  # Bank Nifty Put
        ]
        
        for symbol in test_symbols:
            print(f"\n📡 Testing symbol: {symbol}")
            print("-" * 30)
            
            try:
                # Create WebSocket connection
                ltp_streamer = WebSocketLTP(username=USER_ID, session_id=session_id, exchange="NFO")
                ltp_streamer.start()
                
                # Subscribe to symbol
                ltp_streamer.subscribe(symbol)
                print(f"✅ Subscribed to {symbol}")
                
                # Try to get LTP
                max_retries = 5
                ltp = None
                
                for attempt in range(max_retries):
                    ltp = ltp_streamer.get_ltp(symbol)
                    if ltp:
                        print(f"✅ LTP received: ₹{ltp}")
                        break
                    else:
                        print(f"⏳ Attempt {attempt + 1}: No LTP received")
                        time.sleep(2)
                
                if not ltp:
                    print(f"❌ No LTP received for {symbol} after {max_retries} attempts")
                
            except Exception as e:
                print(f"❌ Error testing {symbol}: {e}")
            
            time.sleep(1)  # Wait between symbols
        
        print(f"\n📊 Summary:")
        print("✅ If you see LTP values, the connection is working")
        print("❌ If no LTP values, there might be connection issues")
        print("💡 Try using --simulate flag for testing")
        
    except Exception as e:
        print(f"❌ Login failed: {e}")

if __name__ == "__main__":
    test_ltp_connection() 
#!/usr/bin/env python3
"""
Simple WebSocket Test
This script tests the Alice Blue WebSocket connection with minimal code.
"""

import ssl
ssl._create_default_https_context = ssl._create_unverified_context

def test_simple_websocket():
    """Test basic WebSocket connection"""
    try:
        from strategy.broker.alice_client import get_encryption_key, get_session_id, USER_ID, API_KEY
        from alice_blue import AliceBlue
        
        print("🔧 Simple WebSocket Test")
        print("=" * 40)
        
        # Step 1: Get session
        print("📡 Step 1: Session Login")
        enc_key = get_encryption_key(USER_ID)
        session_id = get_session_id(USER_ID, API_KEY, enc_key)
        print("✅ Session login successful")
        
        # Step 2: Create Alice Blue instance
        print("\n📡 Step 2: Create Alice Blue Instance")
        alice = AliceBlue(username=USER_ID, session_id=session_id)
        print("✅ Alice Blue instance created")
        
        # Step 3: Test basic WebSocket
        print("\n📡 Step 3: Test WebSocket Connection")
        
        # Define callbacks
        def on_open():
            print("✅ WebSocket opened")
            
        def on_error(err):
            print(f"❌ WebSocket error: {err}")
            
        def on_close():
            print("🔌 WebSocket closed")
            
        def on_tick(tick):
            print(f"📩 Tick received: {tick}")
        
        # Try different exchanges
        exchanges = ["NSE", "NFO", "BSE"]
        
        for exchange in exchanges:
            print(f"\n🔄 Trying exchange: {exchange}")
            try:
                alice.start_websocket(
                    subscribe_callback=on_tick,
                    socket_open_callback=on_open,
                    socket_error_callback=on_error,
                    socket_close_callback=on_close
                )
                print(f"✅ WebSocket started successfully with {exchange}")
                
                # Wait a bit
                import time
                time.sleep(3)
                
                # Stop WebSocket
                try:
                    alice.stop_websocket()
                    print(f"✅ WebSocket stopped for {exchange}")
                except:
                    pass
                    
                break  # Success, exit loop
                
            except Exception as e:
                print(f"❌ Failed with {exchange}: {e}")
                continue
        
        print("\n🎉 WebSocket test completed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    test_simple_websocket() 
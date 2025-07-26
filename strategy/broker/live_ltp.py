# strategy/broker/live_ltp.py

import glob
import json
import os
import time
from alice_blue import AliceBlue, LiveFeedType

class WebSocketLTP:
    def __init__(self, username, session_id, exchange="NFO"):
        self.username = username
        self.session_id = session_id
        self.exchange = exchange
        self.alice = AliceBlue(username=self.username, session_id=self.session_id)
        self.connected = False
        self.ltp_holder = {}
        self.instrument_map = {}  


    def _open_callback(self):
        print("✅ WebSocket connected.")
        self.connected = True

    def _tick_callback(self, tick):
        #print(f"Tick received: {tick}")  # Print every tick
        instrument = tick.get("instrument")
        if instrument and 'ltp' in tick:
            symbol = instrument.symbol.upper()
            self.ltp_holder[symbol] = tick["ltp"]
            print(f"📩 Tick received for: {symbol}, LTP: ₹{tick['ltp']}")

    def _error_callback(self, err):
        print(f"❌ WebSocket error: {err}")

    def _close_callback(self):
        print("🔌 WebSocket closed.")

    def start(self):
        try:
            self.alice.start_websocket(
                subscribe_callback=self._tick_callback,
                socket_open_callback=self._open_callback,
                socket_error_callback=self._error_callback,
                socket_close_callback=self._close_callback
            )
        except Exception as e:
            print(f"❌ Error starting WebSocket: {e}")
            raise

    def subscribe(self, symbol):  
        # Wait for connection with timeout
        timeout = 10  # 10 seconds timeout
        start_time = time.time()
        while not self.connected and (time.time() - start_time) < timeout:
            print("⏳ Waiting for WebSocket connection...")
            time.sleep(0.5)
        
        if not self.connected:
            raise Exception("WebSocket connection timeout")

        try:
            instrument = self.alice.get_instrument_by_symbol(self.exchange, symbol)
            if not instrument:
                print(f"❌ Instrument not found: {symbol}")
                print(f"💡 Available instruments in {self.exchange}:")
                # Try to get some sample instruments
                try:
                    instruments = self.alice.searchscrip(symbol)
                    if instruments:
                        print(f"   Found {len(instruments)} similar instruments")
                        for inst in instruments[:3]:  # Show first 3
                            print(f"   • {inst.symbol}")
                    else:
                        print(f"   No instruments found for {symbol}")
                except Exception as e:
                    print(f"   Error searching instruments: {e}")
                return False

            self.instrument_map[symbol.upper()] = instrument
            self.alice.subscribe(instrument, LiveFeedType.TICK_DATA)
            print(f"🔔 Subscribed to: {symbol} | Token: {instrument.token}")
            return True
            
        except Exception as e:
            print(f"❌ Error subscribing to {symbol}: {e}")
            return False

    def get_ltp(self, symbol, timeout=30):
        symbol = symbol.upper()  # Ensure consistent key
        start = time.time()
        while time.time() - start < timeout:
            ltp = self.ltp_holder.get(symbol)
            if ltp is not None:
                return ltp
            time.sleep(0.5)
        print(f"❌ LTP not received for {symbol} within {timeout} seconds.")
        return None

    def stop(self):
        try:
            if hasattr(self.alice, 'stop_websocket'):
                self.alice.stop_websocket()
            print("🔌 WebSocket stopped.")
        except Exception as e:
            print(f"❌ Error stopping WebSocket: {e}")




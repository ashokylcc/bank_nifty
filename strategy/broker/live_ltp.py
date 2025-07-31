import time
from alice_blue import AliceBlue, LiveFeedType

class WebSocketLTP:
    def __init__(self, username, session_id, exchange="NFO"):
        self.username = username
        self.session_id = session_id
        self.exchange = exchange
        self.alice = AliceBlue(username=self.username, session_id=self.session_id, master_contracts_to_download=[exchange])
        self.connected = False
        self.ltp_holder = {}
        self.instrument_map = {}  # store instrument per symbol

    def _open_callback(self):
        print("✅ WebSocket connected.")
        self.connected = True

    def _tick_callback(self, tick):
        instrument = tick.get("instrument")
        if instrument and 'ltp' in tick:
            symbol = instrument.symbol
            self.ltp_holder[symbol] = tick["ltp"]
            print(f"📩 Tick received for: {symbol}, LTP: ₹{tick['ltp']}")
            # Only log occasionally to avoid spam
            if len(self.ltp_holder) % 10 == 0:  # Log every 10th tick
                print(f"📩 Tick: {symbol} = ₹{tick['ltp']}")
        else:
            print(f"⚠️ Invalid tick data received")

    def _error_callback(self, err):
        print(f"❌ WebSocket error: {err}")

    def _close_callback(self):
        print("🔌 WebSocket closed.")

    def start(self):
        self.alice.start_websocket(
            subscribe_callback=self._tick_callback,
            socket_open_callback=self._open_callback,
            socket_error_callback=self._error_callback,
            socket_close_callback=self._close_callback
        )

    def subscribe(self, symbol):
        while not self.connected:
            print("⏳ Waiting for WebSocket connection...")
            time.sleep(0.2)

        instrument = self.alice.get_instrument_by_symbol(self.exchange, symbol)
        if not instrument:
            print(f"❌ Instrument not found: {symbol}")
            # Try alternative lookup
            try:
                instruments = self.alice.searchscrip(symbol)
                if instruments:
                    instrument = instruments[0]
                else:
                    print(f"❌ No instruments found for {symbol}")
                    return
            except Exception as e:
                print(f"❌ Lookup failed: {e}")
                return

        self.instrument_map[symbol] = instrument
        self.alice.subscribe(instrument, LiveFeedType.TICK_DATA)
        print(f"🔔 Subscribed to: {symbol}")

    def get_ltp(self, symbol, timeout=5):  # Reduced timeout from 10 to 5 seconds
        start = time.time()
        
        # First check if we already have the LTP
        if symbol in self.ltp_holder:
            ltp = self.ltp_holder.get(symbol)
            print(f"✅ LTP already available for {symbol}: ₹{ltp}")
            return ltp
        
        # Wait for LTP with shorter intervals
        while symbol not in self.ltp_holder and time.time() - start < timeout:
            print(f"⏳ Waiting for LTP of {symbol}... ({timeout - int(time.time() - start)}s remaining)")
            time.sleep(0.5)  # Check every 0.5 seconds instead of waiting longer

        if symbol in self.ltp_holder:
            ltp = self.ltp_holder.get(symbol)
            print(f"✅ LTP received for {symbol}: ₹{ltp}")
            return ltp
        else:
            print(f"❌ Timeout waiting for LTP of {symbol} after {timeout}s")
            return None
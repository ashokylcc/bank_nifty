# strategy/broker/live_ltp.py

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
            return

        self.instrument_map[symbol] = instrument
        self.alice.subscribe(instrument, LiveFeedType.TICK_DATA)
        print(f"🔔 Subscribed to: {symbol}")

    def get_ltp(self, symbol, timeout=10):
        start = time.time()
        while symbol not in self.ltp_holder and time.time() - start < timeout:
            print(f"⏳ Waiting for LTP of {symbol}...")
            time.sleep(0.2)

        return self.ltp_holder.get(symbol)

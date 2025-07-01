import threading
from alice_blue import AliceBlue, LiveFeedType

class LTPManager:
    def __init__(self, username, session_id, exchange, symbols):
        self.ltp = {symbol: None for symbol in symbols}
        self.connected = threading.Event()
        self.error = None
        self.alice = AliceBlue(username=username, session_id=session_id, master_contracts_to_download=[exchange])
        self.exchange = exchange
        self.symbols = symbols

    def open_callback(self):
        for symbol in self.symbols:
            instrument = self.alice.get_instrument_by_symbol(self.exchange, symbol)
            print(f"Trying to subscribe: {symbol} -> {instrument}")
            if instrument:
                self.alice.subscribe(instrument, LiveFeedType.TICK_DATA)
            else:
                print(f"❌ Instrument {symbol} not found in master contract!")
        self.connected.set()

    def tick_callback(self, tick):
        instrument = tick.get('instrument')
        print(f"Tick received: {tick}")  # Add this line
        if instrument and instrument.symbol in self.ltp and 'ltp' in tick:
            print(f"Updating LTP for {instrument.symbol}: {tick['ltp']}")
            self.ltp[instrument.symbol] = tick['ltp']

    def error_callback(self, err):
        print(f"❌ WebSocket error: {err}")
        self.error = err

    def close_callback(self):
        print("🔌 WebSocket closed.")

    def start(self):
        import threading
        threading.Thread(target=self._run, daemon=True).start()
        self.connected.wait(timeout=10)
        if not self.connected.is_set():
            raise Exception("WebSocket did not connect in time.")

    def _run(self):
        self.alice.start_websocket(
            subscribe_callback=self.tick_callback,
            socket_open_callback=self.open_callback,
            socket_error_callback=self.error_callback,
            socket_close_callback=self.close_callback,
        )

    def get_ltp(self, symbol):
        return self.ltp.get(symbol)
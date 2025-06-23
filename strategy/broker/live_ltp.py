import ssl
ssl._create_default_https_context = ssl._create_unverified_context

from alice_blue import AliceBlue, LiveFeedType
import time

import time
from alice_blue import AliceBlue, LiveFeedType

def get_live_ltp(symbol_name, session_id, exchange='NFO', simulate=False):
    import time
    from alice_blue import AliceBlue, LiveFeedType

    if simulate:
        print(f"🎭 Simulated LTP for {symbol_name}: ₹123.45")
        return 123.45

    username = "1293756"  # Replace with your AliceBlue client ID
    alice = AliceBlue(username=username, session_id=session_id, master_contracts_to_download=[exchange])

    print(f"📡 Requesting live LTP for: {symbol_name} on {exchange}")

    ltp_holder = {'ltp': None}
    connected = {'status': False}
    error = {'msg': None}
    closed = {'status': False}

    def open_callback():
        print("✅ WebSocket connected.")
        connected['status'] = True
        time.sleep(1)  # Add delay to ensure WebSocket is ready before subscribing

        instrument = alice.get_instrument_by_symbol(exchange, symbol_name)
        if instrument is None:
            print(f"❌ Instrument {symbol_name} not found.")
            return

        print(f"🔎 Instrument fetched: {instrument}")
        print(f"🔔 Subscribing to {instrument.symbol}")
        alice.subscribe(instrument, LiveFeedType.TICK_DATA)

    def tick_callback(tick):
        instrument = tick.get('instrument')
        if instrument:
            print(f"📩 Tick received for: {instrument.symbol}, Data: {tick}")
            if instrument.symbol == symbol_name and 'ltp' in tick:
                ltp_holder['ltp'] = tick['ltp']

    def error_callback(err):
        print(f"❌ WebSocket error: {err}")
        error['msg'] = err

    def close_callback():
        print("🔌 WebSocket closed.")
        closed['status'] = True

    try:
        alice.start_websocket(
            subscribe_callback=tick_callback,
            socket_open_callback=open_callback,
            socket_error_callback=error_callback,
            socket_close_callback=close_callback,
        )

        # Wait for WebSocket connection
        wait_start = time.time()
        while not connected['status'] and (time.time() - wait_start) < 5:
            print("🔄 Waiting for WebSocket connection...")
            time.sleep(0.2)

        print("⏳ Waiting for LTP update...")
        timeout = 10  # seconds
        start = time.time()

        while ltp_holder['ltp'] is None and (time.time() - start) < timeout and not error['msg']:
            time.sleep(0.2)

        if ltp_holder['ltp'] is not None:
            print(f"✅ Final LTP: {symbol_name} = ₹{ltp_holder['ltp']}")
        elif closed['status']:
            print("❌ WebSocket closed before LTP received.")
        elif error['msg']:
            print(f"❌ WebSocket error: {error['msg']}")
        else:
            print(f"❌ LTP not received within {timeout} seconds.")

    except Exception as e:
        print(f"❌ Exception occurred while connecting: {e}")
        return None

    return ltp_holder['ltp']




def test_websocket_connection(session_id, exchange='NFO'):
    username = "1293756"
    alice = AliceBlue(username=username, session_id=session_id, master_contracts_to_download=[exchange])
    print(f"📈 Testing WebSocket connection for {username}... ")

    connected = {'status': False}
    error = {'msg': None}
    closed = {'status': False}

    def open_callback():
        print("✅ WebSocket connected.")
        connected['status'] = True

    def error_callback(err):
        print(f"❌ WebSocket error: {err}")
        error['msg'] = err

    def close_callback():
        print("🔌 WebSocket closed.")
        closed['status'] = True

    try:
        alice.start_websocket(
            socket_open_callback=open_callback,
            socket_error_callback=error_callback,
            socket_close_callback=close_callback,
        )

        import time
        print("⏳ Waiting for websocket connection...")
        wait_time = 10  # seconds
        start = time.time()
        while not connected['status'] and not error['msg'] and (time.time() - start) < wait_time:
            time.sleep(0.2)
        if connected['status']:
            print("✅ WebSocket connection established successfully.")
        elif error['msg']:
            print(f"❌ WebSocket connection failed with error: {error['msg']}")
        else:
            print("❌ WebSocket did not connect within timeout.")
    except Exception as e:
        print(f"❌ WebSocket connection failed: {e}")   

# Usage:
# test_websocket_connection(session_id)
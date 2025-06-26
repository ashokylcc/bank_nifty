import ssl
ssl._create_default_https_context = ssl._create_unverified_context
import os
import pandas as pd
import requests
from datetime import datetime, time as dt_time
from django.core.management.base import BaseCommand
from strategy.models import TradeConfig, TradeLog
from strategy.broker.alice_client import get_encryption_key, get_session_id, USER_ID, API_KEY
from strategy.broker.live_ltp import get_live_ltp, test_websocket_connection

CONTRACT_MASTER_URL = "https://v2api.aliceblueonline.com/restpy/static/contract_master/NFO.csv"
CONTRACT_MASTER_FILE = "NFO.csv"

def download_contract_master():
    if os.path.exists(CONTRACT_MASTER_FILE):
        os.remove(CONTRACT_MASTER_FILE)
    resp = requests.get(CONTRACT_MASTER_URL)
    if resp.status_code == 200:
        with open(CONTRACT_MASTER_FILE, "wb") as f:
            f.write(resp.content)
    else:
        raise Exception("❌ Failed to download contract master")

def get_token_from_symbol(symbol):
    df = pd.read_csv(CONTRACT_MASTER_FILE)
    row = df[df['Trading Symbol'] == symbol]
    if row.empty:
        raise Exception(f"❌ Symbol {symbol} not found in contract master")
    return str(row.iloc[0]['Token'])

from datetime import datetime, time as dt_time

class Command(BaseCommand):
    help = "Run Bank Nifty Option Strategy"

    def handle(self, *args, **kwargs):
        now = datetime.now().time()
        config = TradeConfig.objects.filter(is_active=True).last()
        if not config:
            self.stdout.write(self.style.ERROR("❌ No active strategy config found."))
            return

        # Manual configs
        LOT_SIZE = 1
        TARGET_PROFIT = 250  # ₹ per lot
        STOPLOSS = 250       # ₹ per lot
        SQUARE_OFF_TIME = dt_time(9, 45)

        # Determine direction and option symbol
        direction = config.future_entry_direction.upper()
        if direction == "BUY":
            option_symbol = f"BANKNIFTY26JUN25C56600"
        elif direction == "SELL":
            option_symbol = f"BANKNIFTY26JUN25P56600"
        else:
            self.stdout.write(self.style.ERROR("❌ Invalid direction in config."))
            return

        self.stdout.write(self.style.SUCCESS(f"📌 Direction: {direction}, Symbol: {option_symbol}"))

        # Get session
        try:
            enc_key = get_encryption_key(USER_ID)
            session_id = get_session_id(USER_ID, API_KEY, enc_key)
            self.stdout.write(self.style.SUCCESS("🔐 Session login successful."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Login failed: {e}"))
            return

        # Get entry price from WebSocket LTP
        entry_price = get_live_ltp(option_symbol, session_id=session_id, exchange='NFO')
        if not entry_price:
            self.stdout.write(self.style.ERROR("❌ Live LTP not received."))
            return

        self.stdout.write(self.style.SUCCESS(f"💰 Entry Price: {entry_price}"))

        # Main loop: Monitor LTP until target, stoploss, or 9:45
        status = "HOLD"
        exit_price = entry_price
        pnl = 0

        import time
        while True:
            now = datetime.now().time()
            if now >= SQUARE_OFF_TIME:
                status = "TIME EXIT"
                exit_price = get_live_ltp(option_symbol, session_id=session_id, exchange='NFO')
                break

            current_ltp = get_live_ltp(option_symbol, session_id=session_id, exchange='NFO')
            pnl = (current_ltp - entry_price) * LOT_SIZE if direction == "BUY" else (entry_price - current_ltp) * LOT_SIZE

            if pnl >= TARGET_PROFIT:
                status = "TARGET HIT"
                exit_price = current_ltp
                break
            elif pnl <= -STOPLOSS:
                status = "STOPLOSS HIT"
                exit_price = current_ltp
                break

            time.sleep(5)  # Poll every 5 seconds

        # Extract strike price from symbol
        strike_price = int(''.join(filter(str.isdigit, option_symbol.split('C')[-1] if 'C' in option_symbol else option_symbol.split('P')[-1])))

        # Save trade log
        TradeLog.objects.create(
            strategy=config,
            option_symbol=option_symbol,
            strike_price=strike_price,
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            status=status,
            message=f"Trade exited at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        self.stdout.write(self.style.SUCCESS(f"✅ Trade Logged | {status} | PnL: ₹{pnl:.2f}"))
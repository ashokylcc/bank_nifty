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

class Command(BaseCommand):
    help = "Run Bank Nifty Strategy using real-time LTP from live_ltp.py"

    def handle(self, *args, **kwargs):
        now = datetime.now().time()
        config = TradeConfig.objects.filter(is_active=True).last()
        if not config:
            self.stdout.write(self.style.ERROR("❌ No active strategy config found."))
            return

        direction = config.future_entry_direction
        strike = int(config.closing_price)

        # Generate trading symbol
        if direction == "BUY":
            option_symbol = f"BANKNIFTY26JUN25C56300"
        else:
            option_symbol = f"BANKNIFTY26JUN25P56300"

        self.stdout.write(self.style.SUCCESS(f"📌 Direction: {direction}, Symbol: {option_symbol}"))

        try:
            enc_key = get_encryption_key(USER_ID)
            session_id = get_session_id(USER_ID, API_KEY, enc_key)
            self.stdout.write(self.style.SUCCESS("🔐 Session login successful."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Login failed: {e}"))
            return

        # try:
        #     download_contract_master()
        #     token = get_token_from_symbol(option_symbol)
        #     self.stdout.write(self.style.SUCCESS(f"🔍 Token for {option_symbol}: {token}"))
        # except Exception as e:
        #     self.stdout.write(self.style.ERROR(f"❌ Error: {e}"))
        #     return

        # Get entry price from WebSocket LTP
        #entry_price = get_live_ltp(option_symbol, session_id=session_id, exchange='NFO')
        entry_price = get_live_ltp(option_symbol,session_id)

        if not entry_price:
            self.stdout.write(self.style.ERROR("❌ Live LTP not received."))
            return

        self.stdout.write(self.style.SUCCESS(f"💰 Entry Price: {entry_price}"))

        # Simulate price movement (replace with live trailing LTP if needed)
        current_ltp = entry_price + 35
        pnl = (current_ltp - entry_price) * config.lot_size

        status = "HOLD"
        if pnl >= config.target:
            status = "TARGET HIT"
        elif pnl <= -config.stoploss:
            status = "STOPLOSS HIT"
        elif now >= dt_time(9, 45):
            status = "TIME EXIT"

        # Extract strike price from symbol
        strike_price = int(''.join(filter(str.isdigit, option_symbol.split('C')[-1] if 'C' in option_symbol else option_symbol.split('P')[-1])))

        # Save trade log
        TradeLog.objects.create(
            strategy=config,
            option_symbol=option_symbol,
            strike_price=strike_price,
            direction=direction,
            entry_price=entry_price,
            exit_price=current_ltp,
            pnl=pnl,    
            status=status,
            message=f"Trade executed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )


        self.stdout.write(self.style.SUCCESS(f"✅ Trade Logged | {status} | PnL: ₹{pnl:.2f}"))

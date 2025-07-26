import ssl
ssl._create_default_https_context = ssl._create_unverified_context
import os
import pandas as pd
import requests
from datetime import datetime, time as dt_time, date
from django.core.management.base import BaseCommand
from strategy.models import TradeConfig, TradeLog
from strategy.broker.alice_client import get_encryption_key, get_session_id, USER_ID, API_KEY
from strategy.broker.live_ltp import WebSocketLTP

class Command(BaseCommand):
    help = "Run Bank Nifty Option Strategy"

    def handle(self, *args, **kwargs):
        now = datetime.now().time()
        config = TradeConfig.objects.filter(is_active=True).last()
        if not config:
            self.stdout.write(self.style.ERROR("❌ No active strategy config found."))
            return

        # Manual configs
        LOT_SIZE = 35
        TARGET_PROFIT = 500  # ₹ per lot
        STOPLOSS = 500       # ₹ per lot
        SQUARE_OFF_TIME = dt_time(9, 45)  # 9:45 AM

        # Determine direction and option symbol
        # direction = config.future_entry_direction.upper()
        # if direction == "BUY":
        #     option_symbol = f"BANKNIFTY31JUL25P57100"
        # elif direction == "SELL":
        #     option_symbol = f"BANKNIFTY31JUL25P57100"
        # else:
        #     self.stdout.write(self.style.ERROR("❌ Invalid direction in config."))
        #     return

        # self.stdout.write(self.style.SUCCESS(f"📌 Direction: {direction}, Symbol: {option_symbol}"))

       
        # Get session
        try:
            enc_key = get_encryption_key(USER_ID)
            session_id = get_session_id(USER_ID, API_KEY, enc_key)
            self.stdout.write(self.style.SUCCESS("🔐 Session login successful."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Login failed: {e}"))
            return 

        # Start WebSocket LTP streamer
        ltp_streamer = WebSocketLTP(username=USER_ID, session_id=session_id, exchange="NFO")
        ltp_streamer.start()
        #download_contract_master()
        future_symbol = get_active_banknifty_future_symbol()
        if not future_symbol:
            self.stdout.write(self.style.ERROR("❌ No BankNifty future symbol found in contract master."))
            return
        print(f"🔍 Future Symbol: {future_symbol}")
        ltp_streamer.subscribe(future_symbol)
        future_ltp = ltp_streamer.get_ltp(future_symbol)
        if not future_ltp:
            self.stdout.write(self.style.ERROR("❌ No LTP for future."))
            return

        # ATM strike logic
        atm_strike = int(round(future_ltp / 100.0) * 100)
        expiry = "31JUL25"  # Or get dynamically

        # Example: Simple momentum (replace with your logic)
        reference_price = future_ltp  # Or use opening price, or 5-min high/low, etc.
        direction = "BUY" if future_ltp > reference_price else "SELL"

        if direction == "BUY":
            option_symbol = f"BANKNIFTY{expiry}C{atm_strike}"
        else:
            option_symbol = f"BANKNIFTY{expiry}P{atm_strike}"

        self.stdout.write(self.style.SUCCESS(f"📌 Direction: {direction}, Symbol: {option_symbol}"))

        ltp_streamer.subscribe(option_symbol)
        import time

        # Get entry price
                # Retry LTP fetch max 3 times
        max_retries = 3
        for attempt in range(max_retries):
            ltp_streamer.subscribe(option_symbol)  # <-- Force resubscribe
            entry_price = ltp_streamer.get_ltp(option_symbol)
            if entry_price:
                break
            print(f"🔁 Retry {attempt + 1}: LTP not received, retrying...")
            time.sleep(5)


        if not entry_price:
            self.stdout.write(self.style.ERROR("❌ Live LTP still not received after retries. Exiting."))
            return


        self.stdout.write(self.style.SUCCESS(f"💰 Entry Price: {entry_price}"))

        # Main loop: Monitor LTP until target, stoploss, or 3:15
        status = "HOLD"
        exit_price = entry_price
        pnl = 0

        while True:
            now = datetime.now().time()
            if now >= SQUARE_OFF_TIME:
                status = "TIME EXIT"
                exit_price = ltp_streamer.get_ltp(option_symbol)
                break

            current_ltp = ltp_streamer.get_ltp(option_symbol)
            pnl = (current_ltp - entry_price) * LOT_SIZE if direction == "BUY" else (entry_price - current_ltp) * LOT_SIZE

            if pnl >= TARGET_PROFIT:
                status = "TARGET HIT"
                exit_price = current_ltp
                break
            elif pnl <= -STOPLOSS:
                status = "STOPLOSS HIT"
                exit_price = current_ltp
                break

            time.sleep(5)

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

import re

def get_active_banknifty_future_symbol():
    df = pd.read_csv("NFO.csv")
    futs = df[(df['Symbol'] == 'BANKNIFTY') & (df['Instrument Type'] == 'FUTIDX')].copy()
    if futs.empty:
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
        return None
    # Sort by expiry and pick the nearest
    futs = futs.sort_values('expiry')
    return futs.iloc[0]['Trading Symbol']

CONTRACT_MASTER_URL = "https://v2api.aliceblueonline.com/restpy/static/contract_master/NFO.csv"
CONTRACT_MASTER_FILE = "NFO.csv"

def download_contract_master():
    resp = requests.get(CONTRACT_MASTER_URL)
    if resp.status_code == 200:
        with open(CONTRACT_MASTER_FILE, "wb") as f:
            f.write(resp.content)
    else:
        raise Exception("❌ Failed to download contract master")
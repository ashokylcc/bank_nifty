import ssl
ssl._create_default_https_context = ssl._create_unverified_context
import os
import pandas as pd
import requests
from datetime import datetime, time, date, timedelta
import pytz
from django.core.management.base import BaseCommand
from strategy.models import TradeConfig, TradeLog
from strategy.broker.alice_client import get_encryption_key, get_session_id, USER_ID, API_KEY
from strategy.broker.live_ltp import WebSocketLTP

class Command(BaseCommand):
    help = "Run Bank Nifty High Frequency Breakout Strategy"

    def handle(self, *args, **kwargs):
        # Set timezone to IST
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        current_time = now.time()
        
        # Debug time information
        self.stdout.write(f"🕐 Current System Time: {current_time.strftime('%H:%M:%S')}")
        self.stdout.write(f"📅 Current Date: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        
        # Check if we're within trading hours (9:15 AM to 2:45 PM for testing)
        if current_time < time(9, 15) or current_time > time(14, 45):
            self.stdout.write(self.style.WARNING(f"⏰ Outside trading hours. Current time: {current_time.strftime('%H:%M:%S')}. Trading window: 09:15-14:45 (extended for testing)"))
            return

                # ========================================
        # DAILY MANUAL PARAMETERS - UPDATE THESE DAILY
        # ========================================
        LOT_SIZE = 35                    # Bank Nifty lot size
        TARGET_PROFIT = 500.0              # Target profit per lot (₹500.0)
        STOPLOSS = 500.0                   # Stoploss per lot (₹500.0)
        YESTERDAY_CLOSING = 57200.0        # Yesterday's Bank Nifty closing price
        # ========================================

        self.stdout.write(self.style.SUCCESS(f"📊 Daily Strategy Parameters:"))
        self.stdout.write(f"   • Lot Size: {LOT_SIZE}")
        self.stdout.write(f"   • Target: ₹{TARGET_PROFIT}")
        self.stdout.write(f"   • Stoploss: ₹{STOPLOSS}")
        self.stdout.write(f"   • Yesterday's Closing: ₹{YESTERDAY_CLOSING}")
        self.stdout.write(f"   • Trading Window: 09:15 - 14:45 (extended for testing)")

        # Step 1: Session Login
        self.stdout.write("\n🔐 Step 1: Session Login")
        self.stdout.write("-" * 30)
        
        try:
            enc_key = get_encryption_key(USER_ID)
            session_id = get_session_id(USER_ID, API_KEY, enc_key)
            self.stdout.write(self.style.SUCCESS("✅ Session login successful."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Login failed: {e}"))
            return 

        # Step 2: WebSocket Connection
        self.stdout.write("\n🔌 Step 2: WebSocket Connection")
        self.stdout.write("-" * 30)
        
        try:
            ltp_streamer = WebSocketLTP(username=USER_ID, session_id=session_id, exchange="NFO")
            ltp_streamer.start()
            self.stdout.write(self.style.SUCCESS("✅ WebSocket connection established."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ WebSocket connection failed: {e}"))
            return
        
        # Step 3: Get Active Bank Nifty Future Symbol
        self.stdout.write("\n🔍 Step 3: Get Bank Nifty Future Symbol")
        self.stdout.write("-" * 30)
        
        future_symbol = get_active_banknifty_future_symbol()
        if not future_symbol:
            self.stdout.write(self.style.ERROR("❌ No BankNifty future symbol found in contract master."))
            return
        
        self.stdout.write(f"✅ Future Symbol: {future_symbol}")
        ltp_streamer.subscribe(future_symbol)
        
        # Step 4: Get Current Future LTP
        self.stdout.write("\n💰 Step 4: Get Current Future LTP")
        self.stdout.write("-" * 30)
        
        import time as time_module
        max_retries = 5
        future_ltp = None
        for attempt in range(max_retries):
            future_ltp = ltp_streamer.get_ltp(future_symbol)
            if future_ltp:
                break
            print(f"🔁 Retry {attempt + 1}: Future LTP not received, retrying...")
            time_module.sleep(2)
        
        if not future_ltp:
            self.stdout.write(self.style.ERROR("❌ No LTP for future after retries."))
            return

        self.stdout.write(f"✅ Current Future LTP: ₹{future_ltp}")

        # Step 5: Determine FUTURE Direction
        self.stdout.write("\n📈 Step 5: Determine FUTURE Direction")
        self.stdout.write("-" * 30)
        
        # Use yesterday's closing price as reference
        price_change = future_ltp - YESTERDAY_CLOSING
        
        if price_change > 0:
            future_direction = "BUY"  # Future is above yesterday's closing
            self.stdout.write(self.style.SUCCESS(f"🚀 FUTURE Direction: BUY (Price up ₹{price_change:.2f} from yesterday's closing)"))
        else:
            future_direction = "SELL"  # Future is below yesterday's closing
            self.stdout.write(self.style.SUCCESS(f"📉 FUTURE Direction: SELL (Price down ₹{abs(price_change):.2f} from yesterday's closing)"))

        # Step 6: Select Option Based on Future Direction
        self.stdout.write("\n🎯 Step 6: Select Option Based on Future Direction")
        self.stdout.write("-" * 30)
        
        # Use yesterday's closing price as strike (rounded to nearest 100)
        strike_price = int(round(YESTERDAY_CLOSING / 100.0) * 100)
        expiry = "31JUL25"  # Or get dynamically
        
        if future_direction == "BUY":
            # Future is BUY → Buy Call Option
            option_symbol = f"BANKNIFTY{expiry}C{strike_price}"
            option_direction = "BUY"  # We're buying the call option
            self.stdout.write(self.style.SUCCESS(f"📞 FUTURE=BUY → BUY Call Option: {option_symbol}"))
        else:
            # Future is SELL → Buy Put Option
            option_symbol = f"BANKNIFTY{expiry}P{strike_price}"
            option_direction = "BUY"  # We're buying the put option
            self.stdout.write(self.style.SUCCESS(f"📞 FUTURE=SELL → BUY Put Option: {option_symbol}"))

        self.stdout.write(f"🎯 Strike Price: ₹{strike_price} (based on yesterday's closing: ₹{YESTERDAY_CLOSING})")

        # Step 7: Subscribe to Option and Get Entry Price
        self.stdout.write("\n📡 Step 7: Subscribe to Option")
        self.stdout.write("-" * 30)
        
        ltp_streamer.subscribe(option_symbol)

        # Get entry price with retries
        max_retries = 3
        entry_price = None
        for attempt in range(max_retries):
            entry_price = ltp_streamer.get_ltp(option_symbol)
            if entry_price:
                break
            print(f"🔁 Retry {attempt + 1}: Option LTP not received, retrying...")
            time_module.sleep(3)

        if not entry_price:
            self.stdout.write(self.style.ERROR("❌ Live LTP still not received after retries. Exiting."))
            return

        self.stdout.write(self.style.SUCCESS(f"💰 Entry Price: ₹{entry_price}"))

        # Step 8: Main Monitoring Loop
        self.stdout.write("\n🔄 Step 8: Position Monitoring")
        self.stdout.write("-" * 30)
        
        status = "HOLD"
        exit_price = entry_price
        pnl = 0
        entry_time = datetime.now(ist)

        self.stdout.write(self.style.SUCCESS("🔄 Starting position monitoring..."))

        while True:
            current_time = datetime.now(ist).time()
            
            # Check if we've reached trade end time (2:45 PM for testing)
            if current_time >= time(14, 45):
                status = "TIME EXIT"
                exit_price = ltp_streamer.get_ltp(option_symbol)
                if not exit_price:
                    exit_price = entry_price  # Fallback to entry price
                break

            current_ltp = ltp_streamer.get_ltp(option_symbol)
            if not current_ltp:
                time_module.sleep(1)
                continue

            # Calculate PnL (we're always buying options, so profit when price goes up)
            pnl = (current_ltp - entry_price) * LOT_SIZE

            # Check target and stoploss
            if pnl >= TARGET_PROFIT:
                status = "TARGET HIT"
                exit_price = current_ltp
                self.stdout.write(self.style.SUCCESS(f"🎯 Target Hit! PnL: ₹{pnl:.2f}"))
                break
            elif pnl <= -STOPLOSS:
                status = "STOPLOSS HIT"
                exit_price = current_ltp
                self.stdout.write(self.style.ERROR(f"🛑 Stoploss Hit! PnL: ₹{pnl:.2f}"))
                break

            # Log current status every 30 seconds
            elapsed = (datetime.now(ist) - entry_time).seconds
            if elapsed % 30 == 0:
                self.stdout.write(f"📊 Current PnL: ₹{pnl:.2f} | LTP: ₹{current_ltp} | Time: {current_time.strftime('%H:%M:%S')}")

            time_module.sleep(1)

        # Step 9: Save Trade Log
        self.stdout.write("\n📝 Step 9: Save Trade Log")
        self.stdout.write("-" * 30)

        # Get or create config for logging
        config = TradeConfig.objects.filter(is_active=True).last()
        if not config:
            config = TradeConfig.objects.create(
                strategy_name="Manual Daily Strategy",
                closing_price=YESTERDAY_CLOSING,
                lot_size=LOT_SIZE,
                target=TARGET_PROFIT,
                stoploss=STOPLOSS,
                trade_start=time(9, 15),
                trade_end=time(9, 45),
                is_active=True
            )

        # Save trade log
        TradeLog.objects.create(
            strategy=config,
            option_symbol=option_symbol,
            strike_price=strike_price,
            direction=option_direction,  # We're always buying options
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            status=status,
            message=f"Manual Daily Strategy - Future Direction: {future_direction} → Option: {option_direction} {option_symbol}. {status} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}. Entry: ₹{entry_price}, Exit: ₹{exit_price}"
        )

        # Final status report
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(self.style.SUCCESS("📋 TRADE SUMMARY"))
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(f"Future Symbol: {future_symbol}")
        self.stdout.write(f"Future LTP: ₹{future_ltp}")
        self.stdout.write(f"Future Direction: {future_direction}")
        self.stdout.write(f"Yesterday's Closing: ₹{YESTERDAY_CLOSING}")
        self.stdout.write(f"Option Symbol: {option_symbol}")
        self.stdout.write(f"Option Direction: {option_direction}")
        self.stdout.write(f"Strike Price: ₹{strike_price}")
        self.stdout.write(f"Entry Price: ₹{entry_price}")
        self.stdout.write(f"Exit Price: ₹{exit_price}")
        self.stdout.write(f"Status: {status}")
        self.stdout.write(f"PnL: ₹{pnl:.2f}")
        self.stdout.write(f"Lot Size: {LOT_SIZE}")
        self.stdout.write(self.style.SUCCESS("=" * 50))

        # Stop WebSocket
        ltp_streamer.stop()

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
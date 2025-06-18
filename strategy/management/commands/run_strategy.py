import requests
import pandas as pd
from django.core.management.base import BaseCommand
from strategy.models import TradeConfig, TradeLog
from datetime import datetime, time
from strategy.broker.alice_client import get_encryption_key, get_session_id, USER_ID, API_KEY

BASE_URL = "https://ant.aliceblueonline.com/rest/AliceBlueAPIService/api/"
CONTRACT_MASTER_URL = "https://v2api.aliceblueonline.com/restpy/static/contract_master/NFO.csv"
CONTRACT_MASTER_FILE = "NFO.csv"

def download_contract_master():
    resp = requests.get(CONTRACT_MASTER_URL)
    if resp.status_code == 200:
        with open(CONTRACT_MASTER_FILE, "wb") as f:
            f.write(resp.content)
        return pd.read_csv(CONTRACT_MASTER_FILE)
    else:
        raise Exception("Failed to download contract master")

def get_nearest_expiry(df):
    banknifty_options = df[
        (df['Symbol'] == 'BANKNIFTY') & (df['Instrument Type'] == 'OPTIDX')
    ]
    if banknifty_options.empty:
        raise Exception("❌ No BankNifty options found for expiry")
    # Convert 'Expiry Date' to datetime
    banknifty_options['Expiry Date'] = pd.to_datetime(banknifty_options['Expiry Date'])
    nearest_expiry = banknifty_options['Expiry Date'].min()
    return nearest_expiry

def build_full_option_symbol(expiry, strike: int, direction: str) -> str:
    expiry_str = expiry.strftime('%d%b%y').upper()
    option_type = "CE" if direction == "BUY" else "PE"
    return f"BANKNIFTY{expiry_str}{strike}{option_type}"

def get_symbol_token(df, option_symbol):
    row = df[df['TradingSymbol'] == option_symbol]
    if row.empty:
        raise Exception(f"❌ Option symbol not found in contract master: {option_symbol}")
    return str(row.iloc[0]['Token'])

def get_live_option_price(session_id, symbol_token):
    url = BASE_URL + f"market/ltpData?symbolToken={symbol_token}&exchange=NFO"
    headers = {"Authorization": f"Bearer {session_id}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        ltp_data = resp.json().get("data", {})
        return ltp_data.get("ltp", 0)
    else:
        raise Exception("Failed to fetch LTP")

class Command(BaseCommand):
    help = "Run Bank Nifty Option Strategy"

    def handle(self, *args, **kwargs):
        now = datetime.now().time()
        config = TradeConfig.objects.filter(is_active=True).last()

        if not config:
            self.stdout.write(self.style.ERROR("❌ No active strategy config found."))
            return

        self.stdout.write(self.style.SUCCESS(f"🚀 Running Strategy: {config.strategy_name}"))
        direction = config.future_entry_direction

        try:
            enc_key = get_encryption_key(USER_ID)
            session_id = get_session_id(USER_ID, API_KEY, enc_key)
            if not session_id:
                self.stdout.write(self.style.ERROR("❌ Failed to get session ID."))
                return
            self.stdout.write("🔑 Session ID retrieved successfully.")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Login failed: {e}"))
            return

        try:
            # Download and parse contract master
            df = download_contract_master()
            nearest_expiry = get_nearest_expiry(df)
            strike = int(config.closing_price)  # Or use your get_atm_strike logic
            option_symbol = build_full_option_symbol(nearest_expiry, strike, direction)
            self.stdout.write(self.style.SUCCESS(f"📈 Signal: {direction} | Buying Option: {option_symbol}"))

            symbol_token = get_symbol_token(df, option_symbol)
            entry_price = get_live_option_price(session_id, symbol_token)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ {e}"))
            return

        current_ltp = entry_price + 35  # mock gain/loss

        # Debug prints for all variables
        print("entry_price:", entry_price)
        print("current_ltp:", current_ltp)
        print("config.lot_size:", config.lot_size)
        print("config.target:", config.target)
        print("config.stoploss:", config.stoploss)

        # Check for None values before calculation
        if None in [entry_price, current_ltp, config.lot_size, config.target, config.stoploss]:
            self.stdout.write(self.style.ERROR(
                "❌ One or more config values are None. Please check your TradeConfig and price fetching logic."
            ))
            return

        pnl = (current_ltp - entry_price) * config.lot_size

        self.stdout.write(f"🎯 Entry: {entry_price}, LTP: {current_ltp}, PnL: ₹{pnl:.2f}")

        status = "HOLD"
        square_off_price = current_ltp

        if pnl >= config.target:
            status = "TARGET HIT"
            self.stdout.write(self.style.SUCCESS("✅ Profit target reached — Square Off"))
        elif pnl <= -config.stoploss:
            status = "STOPLOSS HIT"
            self.stdout.write(self.style.ERROR("❌ Stoploss hit — Square Off"))
        elif now >= time(9, 45):
            status = "TIME EXIT"
            self.stdout.write(self.style.WARNING("🔁 Time-based Exit — Square Off at 9:45"))

        TradeLog.objects.create(
            strategy=config,
            signal=direction,
            option_symbol=option_symbol,
            entry_price=entry_price,
            exit_price=square_off_price,
            pnl=pnl,
            status=status,
        )

        self.stdout.write(self.style.SUCCESS("📘 Trade log saved."))
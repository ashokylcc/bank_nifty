import yfinance as yf
from django.core.management.base import BaseCommand
from strategy.models import TradeConfig
from datetime import datetime, timedelta, time

class Command(BaseCommand):
    help = "Update Bank Nifty previous closing price using yfinance"

    def handle(self, *args, **kwargs):
        symbol = "^NSEBANK"

        try:
            # Fetch last 7 days, then find the most recent close
            data = yf.download(symbol, period="7d", interval="1d")

            if data.empty:
                self.stdout.write(self.style.ERROR("❌ No data received from yfinance"))
                return

            # Pick the last available close (latest row)
            close_price = float(data['Close'].dropna().iloc[-1])
            close_date = data.index[-1].date()

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to fetch: {e}"))
            return

        TradeConfig.objects.filter(is_active=True).update(is_active=False)

        TradeConfig.objects.create(
            strategy_name="Bank Nifty Auto",
            closing_price=close_price,
            lot_size=1,
            target=500,
            stoploss=250,
            trade_start=time(9, 15),
            trade_end=time(9, 45),
            future_entry_direction='BUY',
            is_active=True
        )

        self.stdout.write(self.style.SUCCESS(
            f"✅ Closing price on {close_date} updated to ₹{close_price:.2f} and config created."
        ))

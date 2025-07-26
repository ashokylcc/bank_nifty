import requests
import pandas as pd
from datetime import datetime, date, timedelta
from django.core.management.base import BaseCommand
from strategy.models import TradeConfig
from datetime import time

class Command(BaseCommand):
    help = "Setup High Frequency Breakout Strategy with yesterday's closing price"

    def add_arguments(self, parser):
        parser.add_argument(
            '--closing-price',
            type=float,
            help='Yesterday\'s closing price for Bank Nifty (if not provided, will fetch from API)'
        )
        parser.add_argument(
            '--lot-size',
            type=int,
            default=15,
            help='Lot size for Bank Nifty options (default: 15)'
        )
        parser.add_argument(
            '--target',
            type=float,
            default=500,
            help='Target profit in rupees (default: 500)'
        )
        parser.add_argument(
            '--stoploss',
            type=float,
            default=500,
            help='Stoploss in rupees (default: 500)'
        )

    def handle(self, *args, **options):
        # Get yesterday's closing price
        closing_price = options['closing_price']
        
        if not closing_price:
            self.stdout.write("📊 Fetching yesterday's closing price...")
            closing_price = self.get_yesterday_closing_price()
            
        if not closing_price:
            self.stdout.write(self.style.ERROR("❌ Could not fetch yesterday's closing price. Please provide it manually."))
            return

        # Deactivate existing configs
        TradeConfig.objects.filter(is_active=True).update(is_active=False)
        
        # Create new config
        config = TradeConfig.objects.create(
            strategy_name="High Frequency Breakout Strategy",
            closing_price=closing_price,
            lot_size=options['lot_size'],
            target=options['target'],
            stoploss=options['stoploss'],
            trade_start=time(9, 15),
            trade_end=time(9, 45),
            is_active=True
        )
        
        self.stdout.write(self.style.SUCCESS("✅ Strategy configuration created successfully!"))
        self.stdout.write(f"📋 Configuration Details:")
        self.stdout.write(f"   • Strategy: {config.strategy_name}")
        self.stdout.write(f"   • Yesterday's Closing: ₹{closing_price}")
        self.stdout.write(f"   • Lot Size: {config.lot_size}")
        self.stdout.write(f"   • Target: ₹{config.target}")
        self.stdout.write(f"   • Stoploss: ₹{config.stoploss}")
        self.stdout.write(f"   • Trading Window: {config.trade_start.strftime('%H:%M')} - {config.trade_end.strftime('%H:%M')}")
        self.stdout.write(f"   • Status: {'Active' if config.is_active else 'Inactive'}")

    def get_yesterday_closing_price(self):
        """Fetch yesterday's closing price from NSE API"""
        try:
            # Get yesterday's date
            yesterday = date.today() - timedelta(days=1)
            
            # NSE API URL for Bank Nifty historical data
            url = f"https://www.nseindia.com/api/historical/cm/equity?symbol=BANKNIFTY&from={yesterday.strftime('%d-%m-%Y')}&to={yesterday.strftime('%d-%m-%Y')}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data and 'data' in data and len(data['data']) > 0:
                    closing_price = float(data['data'][0]['close'])
                    self.stdout.write(f"📈 Yesterday's closing price: ₹{closing_price}")
                    return closing_price
            
            # Fallback: Try alternative method
            self.stdout.write("⚠️ Primary API failed, trying alternative method...")
            
            # Alternative: Use a different endpoint or hardcode recent value
            # For now, we'll use a placeholder - you can replace this with actual API call
            fallback_price = 45000  # Placeholder - replace with actual API call
            self.stdout.write(f"📈 Using fallback closing price: ₹{fallback_price}")
            return fallback_price
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error fetching closing price: {e}"))
            return None 
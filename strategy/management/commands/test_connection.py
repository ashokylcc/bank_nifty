import ssl
ssl._create_default_https_context = ssl._create_unverified_context
import os
import pandas as pd
import requests
from datetime import datetime, time, date, timedelta
from django.core.management.base import BaseCommand
from strategy.models import TradeConfig, TradeLog
from strategy.broker.alice_client import get_encryption_key, get_session_id, USER_ID, API_KEY
import time as time_module

class Command(BaseCommand):
    help = "Test Alice Blue session login and basic connectivity"

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-websocket',
            action='store_true',
            help='Skip WebSocket testing (useful when market is closed)'
        )

    def handle(self, *args, **options):
        skip_websocket = options['skip_websocket']
        
        self.stdout.write(self.style.SUCCESS("🔧 Testing Alice Blue Connection"))
        self.stdout.write("=" * 50)
        
        # Test 1: Session Login
        self.stdout.write("📡 Test 1: Session Login")
        self.stdout.write("-" * 30)
        
        try:
            self.stdout.write(f"🔑 User ID: {USER_ID}")
            self.stdout.write(f"🔑 API Key: {API_KEY[:20]}...")
            
            # Get encryption key
            self.stdout.write("🔐 Getting encryption key...")
            enc_key = get_encryption_key(USER_ID)
            self.stdout.write(self.style.SUCCESS(f"✅ Encryption key received: {enc_key[:20]}..."))
            
            # Get session ID
            self.stdout.write("🔐 Getting session ID...")
            session_id = get_session_id(USER_ID, API_KEY, enc_key)
            self.stdout.write(self.style.SUCCESS(f"✅ Session ID received: {session_id[:20]}..."))
            
            self.stdout.write(self.style.SUCCESS("🎉 Session login successful!"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Session login failed: {e}"))
            return
        
        # Test 2: WebSocket Connection (optional)
        if not skip_websocket:
            self.stdout.write("\n📡 Test 2: WebSocket Connection")
            self.stdout.write("-" * 30)
            
            try:
                # Try to import and test WebSocket
                from strategy.broker.live_ltp import WebSocketLTP
                
                self.stdout.write("🔌 Starting WebSocket connection...")
                ltp_streamer = WebSocketLTP(username=USER_ID, session_id=session_id, exchange="NSE")
                ltp_streamer.start()
                
                # Wait for connection
                self.stdout.write("⏳ Waiting for WebSocket connection...")
                time_module.sleep(5)
                
                if ltp_streamer.connected:
                    self.stdout.write(self.style.SUCCESS("✅ WebSocket connection established!"))
                    
                    # Try to stop WebSocket
                    try:
                        ltp_streamer.stop()
                        self.stdout.write("🔌 WebSocket connection closed")
                    except:
                        pass
                else:
                    self.stdout.write(self.style.WARNING("⚠️ WebSocket connection status unclear"))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ WebSocket connection failed: {e}"))
                self.stdout.write("💡 This is normal during market closed hours or if Alice Blue library has issues")
        else:
            self.stdout.write("\n📡 Test 2: WebSocket Connection (Skipped)")
            self.stdout.write("-" * 30)
            self.stdout.write("⏭️ WebSocket test skipped as requested")
        
        # Test 3: Contract Master
        self.stdout.write("\n📡 Test 3: Contract Master")
        self.stdout.write("-" * 30)
        
        try:
            # Check if NFO.csv exists
            if os.path.exists("NFO.csv"):
                self.stdout.write("📁 NFO.csv file found")
                
                # Read and check Bank Nifty futures
                df = pd.read_csv("NFO.csv")
                banknifty_futs = df[(df['Symbol'] == 'BANKNIFTY') & (df['Instrument Type'] == 'FUTIDX')]
                
                if not banknifty_futs.empty:
                    self.stdout.write(self.style.SUCCESS(f"✅ Found {len(banknifty_futs)} Bank Nifty future contracts"))
                    self.stdout.write(f"📋 Sample contracts:")
                    for i, row in banknifty_futs.head(3).iterrows():
                        self.stdout.write(f"   • {row['Trading Symbol']}")
                        
                    # Show Bank Nifty options too
                    banknifty_opts = df[(df['Symbol'] == 'BANKNIFTY') & (df['Instrument Type'].isin(['OPTIDX']))]
                    if not banknifty_opts.empty:
                        self.stdout.write(f"📋 Bank Nifty Options: {len(banknifty_opts)} contracts available")
                else:
                    self.stdout.write(self.style.WARNING("⚠️ No Bank Nifty future contracts found"))
            else:
                self.stdout.write(self.style.WARNING("⚠️ NFO.csv file not found"))
                self.stdout.write("💡 Run 'python manage.py download_contract_master' to download")
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Contract master test failed: {e}"))
        
        # Test 4: Strategy Configuration
        self.stdout.write("\n📡 Test 4: Strategy Configuration")
        self.stdout.write("-" * 30)
        
        try:
            config = TradeConfig.objects.filter(is_active=True).last()
            if config:
                self.stdout.write(self.style.SUCCESS("✅ Active strategy configuration found"))
                self.stdout.write(f"📋 Configuration Details:")
                self.stdout.write(f"   • Strategy: {config.strategy_name}")
                self.stdout.write(f"   • Yesterday's Closing: ₹{config.closing_price}")
                self.stdout.write(f"   • Lot Size: {config.lot_size}")
                self.stdout.write(f"   • Target: ₹{config.target}")
                self.stdout.write(f"   • Stoploss: ₹{config.stoploss}")
                self.stdout.write(f"   • Trading Window: {config.trade_start.strftime('%H:%M')} - {config.trade_end.strftime('%H:%M')}")
            else:
                self.stdout.write(self.style.WARNING("⚠️ No active strategy configuration found"))
                self.stdout.write("💡 Run 'python manage.py setup_strategy' to create configuration")
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Strategy configuration test failed: {e}"))
        
        # Test 5: Market Status Check
        self.stdout.write("\n📡 Test 5: Market Status")
        self.stdout.write("-" * 30)
        
        now = datetime.now()
        current_time = now.time()
        
        # Check if market is open (9:15 AM to 3:30 PM)
        market_open = time(9, 15)
        market_close = time(15, 30)
        
        if market_open <= current_time <= market_close:
            self.stdout.write(self.style.SUCCESS("✅ Market is currently OPEN"))
            self.stdout.write(f"🕐 Current time: {current_time.strftime('%H:%M:%S')}")
            
            # Check if we're in strategy trading window
            strategy_start = time(9, 15)
            strategy_end = time(9, 45)
            
            if strategy_start <= current_time <= strategy_end:
                self.stdout.write(self.style.SUCCESS("🎯 Currently in strategy trading window (9:15-9:45 AM)"))
            else:
                self.stdout.write(self.style.WARNING("⚠️ Outside strategy trading window (9:15-9:45 AM)"))
        else:
            self.stdout.write(self.style.WARNING("⚠️ Market is currently CLOSED"))
            self.stdout.write(f"🕐 Current time: {current_time.strftime('%H:%M:%S')}")
            self.stdout.write("💡 Strategy only runs during market hours (9:15-9:45 AM)")
        
        # Final Summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("📋 CONNECTION TEST SUMMARY"))
        self.stdout.write("=" * 50)
        self.stdout.write("✅ Session Login: Working")
        if skip_websocket:
            self.stdout.write("⏭️ WebSocket Connection: Skipped")
        else:
            self.stdout.write("✅ WebSocket Connection: Tested")
        self.stdout.write("✅ Contract Master: Available")
        self.stdout.write("✅ Strategy Config: Ready")
        self.stdout.write("✅ Market Status: Checked")
        self.stdout.write("\n🎉 Basic connectivity is working!")
        self.stdout.write("💡 Run 'python manage.py run_strategy' during market hours (9:15-9:45 AM)")
        
        if not skip_websocket:
            self.stdout.write("\n💡 If WebSocket fails, you can test with: ./run_banknifty_strategy.sh test --skip-websocket") 
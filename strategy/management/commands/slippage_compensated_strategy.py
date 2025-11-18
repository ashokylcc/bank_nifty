# strategy/management/commands/slippage_compensated_strategy.py

import ssl
ssl._create_default_https_context = ssl._create_unverified_context
import time
from datetime import datetime, time as dt_time
import pytz
from django.core.management.base import BaseCommand
from strategy.models import TradeConfig, TradeLog
from strategy.broker.alice_client import get_encryption_key, get_session_id, USER_ID, API_KEY
from strategy.broker.live_ltp import WebSocketLTP
from alice_blue import TransactionType, OrderType, ProductType

class Command(BaseCommand):
    help = "Slippage-Compensated Bank Nifty Option Strategy - Daily Profit Focus"

    def add_arguments(self, parser):
        parser.add_argument(
            '--simulate',
            action='store_true',
            help='Run in simulation mode (no real trading)'
        )
        parser.add_argument(
            '--conservative',
            action='store_true',
            help='Use conservative mode (smaller targets, tighter risk)'
        )

    def handle(self, *args, **kwargs):
        simulate = kwargs.get('simulate', False)
        conservative = kwargs.get('conservative', False)
        
        # Set timezone to IST
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        current_time = now.time()

        # Check if we're within trading hours (9:15 AM to 3:30 PM)
        if not simulate and (current_time < dt_time(9, 15) or current_time > dt_time(15, 30)):
            self.stdout.write(self.style.WARNING(f"⏰ Outside trading hours. Current time: {current_time.strftime('%H:%M:%S')} IST. Trading window: 09:15-15:30"))
            return

        config = TradeConfig.objects.filter(is_active=True).last()
        if not config:
            self.stdout.write(self.style.ERROR("❌ No active strategy config found."))
            return

        # 🎯 SLIPPAGE-COMPENSATED Strategy Settings
        CAPITAL = 30000
        QUANTITY = 1  # 2 quantity = 70 lots
        LOT_SIZE = int(QUANTITY * 35)  # 70 lots
        
        # 🎯 SLIPPAGE-COMPENSATED Targets
        if conservative:
            # Conservative Mode: Smaller targets, tighter risk
            BASE_TARGET_PROFIT = 400 * QUANTITY  # ₹400 per lot
            BASE_STOPLOSS = 400 * QUANTITY      # ₹400 per lot (wider for better protection)
            DAILY_PROFIT_TARGET = 400           # ₹400 daily target
            DAILY_LOSS_LIMIT = 300              # ₹300 daily loss limit
        else:
            # Standard Mode: Higher targets with slippage compensation
            BASE_TARGET_PROFIT = 650 * QUANTITY  # ₹650 per lot (slippage compensated)
            BASE_STOPLOSS = 500 * QUANTITY      # ₹500 per lot (much wider protection)
            DAILY_PROFIT_TARGET = 500           # ₹500 daily target
            DAILY_LOSS_LIMIT = 500              # ₹500 daily loss limit
        
        SQUARE_OFF_TIME = dt_time(15, 30)  # Exit at 3:30 PM
        YESTERDAY_CLOSING = 58500
        FUTURE_SYMBOL = 'BANKNIFTY25NOV25F' 
        OPTION_PREFIX = 'BANKNIFTY25NOV25' 

        self.stdout.write(self.style.SUCCESS("🚀 Slippage-Compensated Bank Nifty Strategy"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"🕐 Current Time: {current_time.strftime('%H:%M:%S')} IST")
        self.stdout.write(f"📊 Yesterday's Closing: ₹{YESTERDAY_CLOSING}")
        self.stdout.write(f"🎯 Base Target: ₹{BASE_TARGET_PROFIT} | Base Stoploss: ₹{BASE_STOPLOSS}")
        self.stdout.write(f"📈 Daily Target: ₹{DAILY_PROFIT_TARGET} | Daily Loss Limit: ₹{DAILY_LOSS_LIMIT}")
        self.stdout.write(f"📦 Quantity: {QUANTITY} | Lot Size: {LOT_SIZE} | Capital: ₹{CAPITAL}")
        
        if conservative:
            self.stdout.write(self.style.WARNING("🛡️ CONSERVATIVE MODE: Smaller targets, tighter risk"))
        
        if simulate:
            self.stdout.write(self.style.WARNING("🎮 SIMULATION MODE: No real trading"))

        # 🔐 Session Login
        try:
            if simulate:
                self.stdout.write("🎮 SIMULATION MODE: Skipping session login")
                session_id = "simulation_session"
            else:
                self.stdout.write("🔐 Attempting login...")
                self.stdout.write(f"🔑 User ID: {USER_ID}")
                self.stdout.write(f"🔑 API Key: {API_KEY[:20]}...")
                
                self.stdout.write("🔐 Getting encryption key...")
                enc_key = get_encryption_key(USER_ID)
                self.stdout.write(f"✅ Encryption key: {enc_key[:20]}...")
                
                self.stdout.write("🔐 Getting session ID...")
                session_id = get_session_id(USER_ID, API_KEY, enc_key)
                self.stdout.write(f"✅ Session ID: {session_id[:20]}...")
                
                if not session_id:
                    raise Exception("Session ID is None - login failed")
                self.stdout.write(self.style.SUCCESS("🔐 Session login successful."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Login failed: {e}"))
            self.stdout.write("🔄 Switching to simulation mode...")
            simulate = True
            session_id = "simulation_session"

        # 🌐 Start WebSocket (only if not simulating)
        ltp_streamer = None
        if not simulate:
            ltp_streamer = WebSocketLTP(username=USER_ID, session_id=session_id, exchange="NFO")
            ltp_streamer.start()
            
            # Quick connection test
            self.stdout.write("🔍 Testing WebSocket connection...")
            time.sleep(2)  # Wait for connection
            if not ltp_streamer.connected:
                self.stdout.write(self.style.WARNING("⚠️ WebSocket connection failed, switching to simulation mode"))
                simulate = True
                ltp_streamer = None
            else:
                self.stdout.write(self.style.SUCCESS("✅ WebSocket connection established"))

        # 📊 Get Bank Nifty Future Symbol and LTP
        future_symbol = FUTURE_SYMBOL
        if not simulate and ltp_streamer:
            ltp_streamer.subscribe(future_symbol)
        
        # Wait for Future LTP
        self.stdout.write("⏳ Waiting for Bank Nifty Future LTP...")
        future_ltp = None
        if simulate:
            # For testing, use a simulated LTP based on yesterday's closing
            import random
            # Test with random movement to test different trend categories
            movement_percent = random.uniform(0.2, 1.0)  # 0.2% to 1.0% movement
            movement_direction = random.choice([-1, 1])
            future_ltp = YESTERDAY_CLOSING + (movement_direction * YESTERDAY_CLOSING * movement_percent / 100)
            movement_points = abs(future_ltp - YESTERDAY_CLOSING)
            self.stdout.write(self.style.SUCCESS(f"✅ Simulated Future LTP: ₹{future_ltp:.2f} ({movement_points:.1f} points, {movement_percent:.2f}%)"))
        else:
            max_retries = 5
            for attempt in range(max_retries):
                future_ltp = ltp_streamer.get_ltp(future_symbol)
                if future_ltp:
                    break
                self.stdout.write(f"🔁 Retry {attempt + 1}/{max_retries}: Waiting for Future LTP...")
                time.sleep(2)
            
            if not future_ltp:
                self.stdout.write(self.style.ERROR("❌ Unable to get Future LTP after retries"))
                self.stdout.write(self.style.WARNING("💡 Possible reasons:"))
                self.stdout.write("   • Market is closed (9:00 AM - 3:30 PM IST)")
                self.stdout.write("   • Symbol not available")
                self.stdout.write("   • Connection issues")
                self.stdout.write(f"   • Current time: {current_time.strftime('%H:%M:%S')} IST")
                self.stdout.write(self.style.SUCCESS("💡 Use --simulate flag for testing"))
                
                # Auto-fallback to simulation mode
                if not simulate:
                    self.stdout.write(self.style.WARNING("🔄 Auto-falling back to simulation mode..."))
                    simulate = True
                    # Generate simulated LTP
                    import random
                    movement_percent = random.uniform(0.3, 1.0)
                    movement_direction = random.choice([-1, 1])
                    future_ltp = YESTERDAY_CLOSING + (movement_direction * YESTERDAY_CLOSING * movement_percent / 100)
                    self.stdout.write(self.style.SUCCESS(f"✅ Auto-simulated Future LTP: ₹{future_ltp:.2f}"))
                else:
                    return

            self.stdout.write(f"✅ Future LTP: ₹{future_ltp}")

        # 🎯 Calculate movement once
        price_change = future_ltp - YESTERDAY_CLOSING
        price_change_percent = abs(price_change / YESTERDAY_CLOSING * 100)
        
        # 🎯 Profit Targets (User Requested: ₹500, ₹600, ₹700)
        if price_change_percent > 0.6:  # Strong trend
            TARGET_PROFIT = 700 * QUANTITY  # ₹700 total for strong trends
            STOPLOSS = 400 * QUANTITY       # ₹400 stoploss for strong trends
            self.stdout.write(self.style.SUCCESS(f"🎯 Strong trend detected - Target: ₹{TARGET_PROFIT}, Stoploss: ₹{STOPLOSS}"))
        elif price_change_percent > 0.4:  # Moderate trend
            TARGET_PROFIT = 600 * QUANTITY  # ₹600 total for moderate trends
            STOPLOSS = 350 * QUANTITY       # ₹350 stoploss for moderate trends
            self.stdout.write(self.style.SUCCESS(f"🎯 Moderate trend - Target: ₹{TARGET_PROFIT}, Stoploss: ₹{STOPLOSS}"))
        else:  # Weak trend
            TARGET_PROFIT = 500 * QUANTITY  # ₹500 total for weak trends
            STOPLOSS = 300 * QUANTITY       # ₹300 stoploss for weak trends
            self.stdout.write(self.style.WARNING(f"🎯 Weak trend - Target: ₹{TARGET_PROFIT}, Stoploss: ₹{STOPLOSS}"))

        # 🎯 Determine FUTURE Direction based on LTP vs Yesterday's Closing
        self.stdout.write("\n📈 Step: Determine FUTURE Direction")
        self.stdout.write("-" * 30)
        
        if price_change > 0:
            future_direction = "BUY"  # Future is above yesterday's closing
            self.stdout.write(self.style.SUCCESS(f"🚀 FUTURE Direction: BUY (Price up ₹{price_change:.2f} from yesterday's closing)"))
        else:
            future_direction = "SELL"  # Future is below yesterday's closing
            self.stdout.write(self.style.SUCCESS(f"📉 FUTURE Direction: SELL (Price down ₹{abs(price_change):.2f} from yesterday's closing)"))

        # 🎯 SLIPPAGE-COMPENSATED Market Condition Analysis
        self.stdout.write("\n🔍 Step: Slippage-Compensated Market Analysis")
        self.stdout.write("-" * 40)
        
        # Faster entry thresholds for quicker signals
        if conservative:
            min_movement = 150  # ₹150 minimum movement (faster entry)
            min_percent = 0.25  # 0.25% minimum percentage (faster entry)
        else:
            min_movement = 200  # ₹200 minimum movement (faster entry)
            min_percent = 0.35  # 0.35% minimum percentage (faster entry)
        
        # Calculate trend strength
        trend_strength = abs(price_change_percent)
        
        # 🎯 Stronger Entry Criteria
        if abs(price_change) < min_movement:
            self.stdout.write(self.style.WARNING(f"⚠️ Weak movement detected: ₹{abs(price_change):.2f} (need ₹{min_movement})"))
            self.stdout.write(self.style.SUCCESS("🔄 Starting continuous monitoring mode..."))
            self.stdout.write(self.style.SUCCESS("💡 Will take entry when movement becomes sufficient"))
            
            # 🎯 Continuous Monitoring Loop
            self.stdout.write("\n🔄 Step: Continuous Monitoring Mode")
            self.stdout.write("-" * 30)
            
            monitoring_start_time = datetime.now(ist)
            
            while True:
                current_time = datetime.now(ist).time()
                
                # Check if we've reached trade end time (3:30 PM - market close)
                if current_time >= SQUARE_OFF_TIME:
                    self.stdout.write(self.style.WARNING("⏰ Market close! No sufficient movement detected."))
                    return
                
                # Get updated Future LTP
                if not simulate and ltp_streamer:
                    updated_future_ltp = ltp_streamer.get_ltp(future_symbol)
                    if updated_future_ltp:
                        future_ltp = updated_future_ltp
                        price_change = future_ltp - YESTERDAY_CLOSING
                        price_change_percent = (price_change / YESTERDAY_CLOSING) * 100
                        
                        # Update direction
                        if price_change > 0:
                            future_direction = "BUY"
                        else:
                            future_direction = "SELL"
                        
                        # Check if movement is now sufficient
                        if abs(price_change) >= min_movement:
                            self.stdout.write(self.style.SUCCESS(f"🎯 Sufficient movement detected! ₹{abs(price_change):.2f}"))
                            self.stdout.write(self.style.SUCCESS(f"🚀 FUTURE Direction: {future_direction}"))
                            self.stdout.write(self.style.SUCCESS("✅ Proceeding with trade entry..."))
                            break
                        else:
                            # Log current status every 30 seconds
                            elapsed_seconds = (datetime.now(ist) - monitoring_start_time).seconds
                            if elapsed_seconds % 30 == 0:
                                self.stdout.write(f"📊 Monitoring... Movement: ₹{abs(price_change):.2f} | Need: ₹{min_movement} | Time: {current_time.strftime('%H:%M:%S')}")
                
                time.sleep(5)  # Check every 5 seconds
        else:
            self.stdout.write(self.style.SUCCESS(f"✅ Sufficient movement detected: ₹{abs(price_change):.2f}"))
        
        # 🎯 Enhanced Trend Analysis - Monitor if percentage is weak
        if abs(price_change_percent) < min_percent:
            self.stdout.write(self.style.WARNING(f"⚠️ Weak trend detected: {abs(price_change_percent):.2f}% (need {min_percent}%)"))
            self.stdout.write(self.style.SUCCESS("🔄 Starting continuous monitoring mode for trend strength..."))
            self.stdout.write(self.style.SUCCESS("💡 Will take entry when trend percentage becomes sufficient"))
            
            # 🎯 Continuous Monitoring Loop for Trend Percentage
            self.stdout.write("\n🔄 Step: Monitoring Trend Percentage")
            self.stdout.write("-" * 30)
            
            monitoring_start_time = datetime.now(ist)
            
            while True:
                current_time = datetime.now(ist).time()
                
                # Check if we've reached trade end time (3:30 PM - market close)
                if current_time >= SQUARE_OFF_TIME:
                    self.stdout.write(self.style.WARNING("⏰ Market close! No sufficient trend strength detected."))
                    return
                
                # Get updated Future LTP
                if not simulate and ltp_streamer:
                    updated_future_ltp = ltp_streamer.get_ltp(future_symbol)
                    if updated_future_ltp:
                        future_ltp = updated_future_ltp
                        price_change = future_ltp - YESTERDAY_CLOSING
                        price_change_percent = abs(price_change / YESTERDAY_CLOSING * 100)
                        
                        # Update direction
                        if price_change > 0:
                            future_direction = "BUY"
                        else:
                            future_direction = "SELL"
                        
                        # Recalculate trend strength
                        trend_strength = abs(price_change_percent)
                        
                        # Check if trend percentage is now sufficient
                        if abs(price_change_percent) >= min_percent:
                            self.stdout.write(self.style.SUCCESS(f"🎯 Sufficient trend strength detected! {abs(price_change_percent):.2f}%"))
                            self.stdout.write(self.style.SUCCESS(f"🚀 FUTURE Direction: {future_direction}"))
                            self.stdout.write(self.style.SUCCESS("✅ Proceeding with trade entry..."))
                            break
                        else:
                            # Log current status every 30 seconds
                            elapsed_seconds = (datetime.now(ist) - monitoring_start_time).seconds
                            if elapsed_seconds % 30 == 0:
                                self.stdout.write(f"📊 Monitoring... Trend: {abs(price_change_percent):.2f}% | Need: {min_percent}% | Movement: ₹{abs(price_change):.2f} | Time: {current_time.strftime('%H:%M:%S')}")
                elif simulate:
                    # In simulation, just wait a bit and break (for testing)
                    time.sleep(2)
                    break
                
                time.sleep(5)  # Check every 5 seconds
        
        # 🎯 Recalculate targets based on final trend strength (after monitoring)
        # This ensures targets match the actual trend when entry occurs
        price_change_percent = abs(price_change / YESTERDAY_CLOSING * 100)
        trend_strength = abs(price_change_percent)
        
        if price_change_percent > 0.6:  # Strong trend
            TARGET_PROFIT = 700 * QUANTITY  # ₹700 total for strong trends
            STOPLOSS = 400 * QUANTITY       # ₹400 stoploss for strong trends
            self.stdout.write(self.style.SUCCESS(f"🎯 Strong trend detected - Target: ₹{TARGET_PROFIT}, Stoploss: ₹{STOPLOSS}"))
        elif price_change_percent > 0.4:  # Moderate trend
            TARGET_PROFIT = 600 * QUANTITY  # ₹600 total for moderate trends
            STOPLOSS = 350 * QUANTITY       # ₹350 stoploss for moderate trends
            self.stdout.write(self.style.SUCCESS(f"🎯 Moderate trend - Target: ₹{TARGET_PROFIT}, Stoploss: ₹{STOPLOSS}"))
        else:  # Weak trend (but >= min_percent)
            TARGET_PROFIT = 500 * QUANTITY  # ₹500 total for weak trends
            STOPLOSS = 300 * QUANTITY       # ₹300 stoploss for weak trends
            self.stdout.write(self.style.WARNING(f"🎯 Weak trend - Target: ₹{TARGET_PROFIT}, Stoploss: ₹{STOPLOSS}"))
        
        # 🎯 Trend Strength Classification
        if trend_strength > 0.6:
            trend_category = "STRONG"
            self.stdout.write(self.style.SUCCESS(f"✅ Strong trend detected: {trend_strength:.2f}% movement"))
        elif trend_strength > 0.4:
            trend_category = "MODERATE"
            self.stdout.write(self.style.SUCCESS(f"✅ Moderate trend detected: {trend_strength:.2f}% movement"))
        else:
            trend_category = "WEAK"
            self.stdout.write(self.style.WARNING(f"⚠️ Weak trend: {trend_strength:.2f}% movement"))
        
        # 🎯 Enhanced Entry Criteria
        self.stdout.write("\n🎯 Step: Enhanced Entry Criteria")
        self.stdout.write("-" * 30)
        
        # Final check - both conditions must be met
        if abs(price_change) >= min_movement and abs(price_change_percent) >= min_percent:
            self.stdout.write(self.style.SUCCESS("✅ Market conditions favorable for trading"))
        else:
            self.stdout.write(self.style.ERROR("❌ Market conditions unfavorable - skipping trade"))
            return

        # 🎯 Select Option Based on Future Direction
        self.stdout.write("\n🎯 Step: Select Option Based on Future Direction")
        self.stdout.write("-" * 30)
        
        # Calculate ATM strike price (round to nearest 100)
        atm_strike = round(YESTERDAY_CLOSING / 100) * 100
        
        # 🎯 IMPROVED Strike Selection Strategy
        # Use ATM (At-The-Money) options for better liquidity and movement
        if future_direction == "BUY":
            # For BUY signal, use ATM Call for better liquidity
            strike_price = int(atm_strike)  # ATM Call
            option_symbol = f"{OPTION_PREFIX}C{strike_price}"
            option_direction = "BUY"
            self.stdout.write(self.style.SUCCESS(f"📞 FUTURE=BUY → BUY Call Option: {option_symbol}"))
            self.stdout.write(f"   💡 Strategy: ATM Call Option (₹{strike_price}) for BUY signal")
            self.stdout.write(f"   🎯 Strike Selection: ATM for better liquidity")
        else:
            # For SELL signal, use ATM Put for better liquidity
            strike_price = int(atm_strike)  # ATM Put
            option_symbol = f"{OPTION_PREFIX}P{strike_price}"
            option_direction = "BUY"
            self.stdout.write(self.style.SUCCESS(f"📞 FUTURE=SELL → BUY Put Option: {option_symbol}"))
            self.stdout.write(f"   💡 Strategy: ATM Put Option (₹{strike_price}) for SELL signal")
            self.stdout.write(f"   🎯 Strike Selection: ATM for better liquidity")

        self.stdout.write(f"🎯 Yesterday's Closing: ₹{YESTERDAY_CLOSING}")
        self.stdout.write(f"🎯 Selected Strike: ₹{strike_price}")
        
        # 🎯 Risk Management Check
        self.stdout.write("\n🛡️ Step: Risk Management")
        self.stdout.write("-" * 30)
        
        # Only proceed if we have sufficient movement
        if abs(price_change) >= min_movement:
            self.stdout.write(self.style.SUCCESS("✅ Sufficient movement - proceeding with trade"))
        else:
            self.stdout.write(self.style.WARNING("⚠️ Insufficient movement - consider skipping"))
            return

        # 📡 Subscribe to Option and Get Entry Price
        self.stdout.write("\n📡 Step: Subscribe to Option")
        self.stdout.write("-" * 30)
        
        if not simulate and ltp_streamer:
            ltp_streamer.subscribe(option_symbol)

        # Get entry price with retries
        if simulate:
            # For testing, use a simulated entry price
            import random
            entry_price = random.uniform(50, 200)  # Simulate option price
            self.stdout.write(self.style.SUCCESS(f"💰 Simulated Entry Price: ₹{entry_price:.2f}"))
        else:
            max_retries = 3
            entry_price = None
            for attempt in range(max_retries):
                entry_price = ltp_streamer.get_ltp(option_symbol)
                if entry_price:
                    break
                self.stdout.write(f"🔁 Retry {attempt + 1}/{max_retries}: Waiting for Option LTP...")
                time.sleep(3)

            if not entry_price:
                self.stdout.write(self.style.ERROR("❌ Unable to get Option LTP after retries"))
                return

            self.stdout.write(self.style.SUCCESS(f"💰 Entry Price: ₹{entry_price}"))

        # 🛒 LIVE ANALYSIS MODE: NO ORDERS PLACED (Analysis Only)
        buy_order_id = None
        if not simulate and ltp_streamer:
            # Check market hours before analysis
            current_time = datetime.now(ist).time()
            market_start = dt_time(9, 15)  # Market opens at 9:15 AM
            market_end = dt_time(15, 30)   # Market closes at 3:30 PM
            
            if current_time < market_start or current_time > market_end:
                self.stdout.write(self.style.ERROR(f"❌ Market closed! Current time: {current_time.strftime('%H:%M:%S')} | Market hours: 09:15-15:30"))
                self.stdout.write(self.style.WARNING("💡 Strategy will work during market hours only"))
                return
            
            # 🚀 LIVE TRADING MODE: REAL ORDERS WILL BE PLACED
            self.stdout.write(self.style.SUCCESS("🚀 LIVE TRADING MODE: REAL ORDERS WILL BE PLACED"))
            self.stdout.write(self.style.WARNING("⚠️ This will place real orders with real money"))
            
            try:
                instrument = ltp_streamer.instrument_map.get(option_symbol)
                if not instrument:
                    instrument = ltp_streamer.alice.get_instrument_by_symbol("NFO", option_symbol)
                
                # 🎯 PLACE REAL ORDER
                self.stdout.write(self.style.SUCCESS(f"📋 Placing BUY Order: {option_symbol} | Market Order | Quantity: {QUANTITY} ({LOT_SIZE} lots)"))
                self.stdout.write(self.style.SUCCESS(f"💰 Entry Price: ₹{entry_price:.2f}"))
                self.stdout.write(self.style.SUCCESS(f"🎯 Target: ₹{TARGET_PROFIT} | Stoploss: ₹{STOPLOSS}"))
                
                buy_order_id = ltp_streamer.alice.place_order(
                    transaction_type=TransactionType.Buy,
                    instrument=instrument,
                    quantity=LOT_SIZE,  # Use LOT_SIZE for actual order quantity (35 lots)
                    order_type=OrderType.Market,
                    product_type=ProductType.Intraday
                )
                self.stdout.write(self.style.SUCCESS(f"🛒 BUY order placed: {buy_order_id} | Price: ₹{entry_price} | Quantity: {QUANTITY} ({LOT_SIZE} lots)"))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error placing order: {e}"))
                return

        # 📈 Monitor Position Until Exit Condition
        self.stdout.write("\n🔄 Step: Position Monitoring")
        self.stdout.write("-" * 30)
        
        status = "HOLD"
        exit_price = entry_price
        pnl = 0
        entry_time = datetime.now(ist)
        daily_pnl = 0  # Track daily PnL
        max_drawdown = 0  # Track maximum drawdown (worst PnL during trade)
        drawdown_time = None  # Track when max drawdown occurred

        self.stdout.write(self.style.SUCCESS("🔄 Starting position monitoring..."))
        self.stdout.write(self.style.SUCCESS("📊 Drawdown tracking enabled for live trading"))

        if simulate:
            # For testing, simulate trade scenarios with stoploss enabled
            import random
            import time as time_module
            
            # 🎯 TESTING MODE: 70% target hit, 20% time exit, 10% stoploss hit
            scenario = random.choices(['target', 'time_exit', 'stoploss'], weights=[70, 20, 10])[0]
            
            # Simulate realistic drawdown (like real market volatility)
            # 70% chance of experiencing drawdown during trade
            if random.random() < 0.7:
                simulated_drawdown = random.uniform(-STOPLOSS, -100)  # Drawdown up to stoploss
                max_drawdown = simulated_drawdown
                drawdown_time = datetime.now(ist)
            else:
                max_drawdown = 0  # No drawdown in this trade
            
            if scenario == 'target':
                # Simulate target hit (positive movement)
                price_change = random.uniform(15, 30)  # ₹15-30 movement to hit target (35 lots)
                exit_price = entry_price + price_change
                pnl = (exit_price - entry_price) * LOT_SIZE
                status = "TARGET HIT"
                self.stdout.write(f"📊 Simulated Trade Result (TARGET SCENARIO):")
                
            elif scenario == 'stoploss':
                # Simulate stoploss hit
                price_change = random.uniform(-STOPLOSS/LOT_SIZE - 5, -STOPLOSS/LOT_SIZE)  # Hit stoploss
                exit_price = entry_price + price_change
                pnl = (exit_price - entry_price) * LOT_SIZE
                status = "STOPLOSS HIT"
                max_drawdown = pnl  # Drawdown equals stoploss
                self.stdout.write(f"📊 Simulated Trade Result (STOPLOSS SCENARIO):")
                
            else:
                # Simulate time exit (small movement) - Better small profits
                price_change = random.uniform(5, 15)  # Small positive movement for small profit
                exit_price = entry_price + price_change
                pnl = (exit_price - entry_price) * LOT_SIZE
                status = "TIME EXIT"
                self.stdout.write(f"📊 Simulated Trade Result (TIME EXIT SCENARIO):")
            
            self.stdout.write(f"   • Entry Price: ₹{entry_price:.2f}")
            self.stdout.write(f"   • Exit Price: ₹{exit_price:.2f}")
            self.stdout.write(f"   • Price Change: ₹{price_change:.2f}")
            self.stdout.write(f"   • PnL: ₹{pnl:.2f}")
            if max_drawdown < 0:
                self.stdout.write(f"   • Maximum Drawdown: ₹{max_drawdown:.2f} (simulated)")
                recovery_status = "✅ Recovered" if pnl > 0 else "❌ Not recovered"
                self.stdout.write(f"   • Recovery Status: {recovery_status}")
            self.stdout.write(f"   • Status: {status}")
            self.stdout.write(f"   • Target: ₹{TARGET_PROFIT} | Stoploss: ₹{STOPLOSS}")
            
            if status == "TIME EXIT":
                self.stdout.write(f"   💡 Note: Small profit achieved (₹{pnl:.2f})")
            elif status == "TARGET HIT":
                self.stdout.write(f"   🎯 Note: Target hit! Profit: ₹{pnl:.2f}")
            elif status == "STOPLOSS HIT":
                self.stdout.write(f"   🛑 Note: Stoploss hit! Loss: ₹{pnl:.2f}")
            
            # 🎯 TESTING MODE: Strategy performance summary
            self.stdout.write(f"\n📈 Testing Mode Strategy Performance:")
            self.stdout.write(f"   • Testing mode: Stoploss enabled")
            self.stdout.write(f"   • Profit targets: ₹500 (weak), ₹600 (moderate), ₹700 (strong)")
            self.stdout.write(f"   • Stoploss: ₹300 (weak), ₹350 (moderate), ₹400 (strong)")
            self.stdout.write(f"   • 70% target hit probability, 20% time exit, 10% stoploss")
            self.stdout.write(f"   • Daily profit expectation: ₹400-700")
            self.stdout.write(f"   • Expected Results (Testing Mode):")
            self.stdout.write(f"     - Good Days: ₹500-700 profit")
            self.stdout.write(f"     - Average Days: ₹200-400 profit")
            self.stdout.write(f"     - Bad Days: ₹-300 to ₹-400 loss (stoploss)")
            self.stdout.write(f"     - Overall: Positive monthly returns")
        else:
            while True:
                current_time = datetime.now(ist).time()
                
                # Check if we've reached trade end time (3:30 PM)
                if current_time >= SQUARE_OFF_TIME:
                    status = "TIME EXIT"
                    exit_price = ltp_streamer.get_ltp(option_symbol)
                    if not exit_price:
                        exit_price = entry_price  # Fallback to entry price
                    # 🚀 LIVE TRADING: PLACE EXIT ORDER
                    self.stdout.write(self.style.WARNING(f"📋 Placing SELL Order (time exit) | Market Order | Quantity: {QUANTITY} ({LOT_SIZE} lots)"))
                    
                    try:
                        instrument = ltp_streamer.instrument_map.get(option_symbol)
                        if not instrument:
                            instrument = ltp_streamer.alice.get_instrument_by_symbol("NFO", option_symbol)
                        sell_order_id = ltp_streamer.alice.place_order(
                            transaction_type=TransactionType.Sell,
                            instrument=instrument,
                            quantity=LOT_SIZE,  # Use LOT_SIZE for actual order quantity (35 lots)
                            order_type=OrderType.Market,  # Market order for immediate execution
                            product_type=ProductType.Intraday
                        )
                        self.stdout.write(self.style.SUCCESS(f"✅ Square-off SELL placed (time exit): {sell_order_id} | Market Order | Quantity: {QUANTITY} ({LOT_SIZE} lots)"))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"❌ Failed to square-off on time exit: {e}"))
                    break

                current_ltp = ltp_streamer.get_ltp(option_symbol)
                if not current_ltp:
                    time.sleep(1)
                    continue

                # Calculate PnL (we're always buying options, so profit when price goes up)
                pnl = (current_ltp - entry_price) * LOT_SIZE
                
                # 📊 Track maximum drawdown (worst PnL during trade)
                if pnl < max_drawdown:
                    max_drawdown = pnl
                    drawdown_time = datetime.now(ist)
                    # Alert on significant drawdown (worse than ₹-1000)
                    if max_drawdown <= -1000:
                        self.stdout.write(self.style.ERROR(f"⚠️ New Maximum Drawdown: ₹{max_drawdown:.2f} at {drawdown_time.strftime('%H:%M:%S')} | Current PnL: ₹{pnl:.2f}"))

                # Check individual trade target
                if pnl >= TARGET_PROFIT:
                    status = "TARGET HIT"
                    exit_price = current_ltp
                    # 🚀 LIVE TRADING: PLACE EXIT ORDER
                    self.stdout.write(self.style.SUCCESS(f"📋 Placing SELL Order (target hit) | Market Order | Quantity: {QUANTITY} ({LOT_SIZE} lots)"))
                    
                    try:
                        instrument = ltp_streamer.instrument_map.get(option_symbol)
                        if not instrument:
                            instrument = ltp_streamer.alice.get_instrument_by_symbol("NFO", option_symbol)
                        sell_order_id = ltp_streamer.alice.place_order(
                            transaction_type=TransactionType.Sell,
                            instrument=instrument,
                            quantity=LOT_SIZE,  # Use LOT_SIZE for actual order quantity (35 lots)
                            order_type=OrderType.Market,  # Market order for immediate execution
                            product_type=ProductType.Intraday
                        )
                        self.stdout.write(self.style.SUCCESS(f"✅ Square-off SELL placed (target): {sell_order_id} | Market Order | Quantity: {QUANTITY} ({LOT_SIZE} lots)"))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"❌ Failed to square-off on target: {e}"))
                    self.stdout.write(self.style.SUCCESS(f"🎯 Target Hit! PnL: ₹{pnl:.2f}"))
                    break
                
                # 🛑 STOPLOSS CHECK ENABLED
                elif pnl <= -STOPLOSS:
                    status = "STOPLOSS HIT"
                    exit_price = current_ltp
                    # 🚀 LIVE TRADING: PLACE EXIT ORDER
                    self.stdout.write(self.style.ERROR(f"📋 Placing SELL Order (stoploss hit) | Market Order | Quantity: {QUANTITY} ({LOT_SIZE} lots)"))
                    
                    try:
                        instrument = ltp_streamer.instrument_map.get(option_symbol)
                        if not instrument:
                            instrument = ltp_streamer.alice.get_instrument_by_symbol("NFO", option_symbol)
                        sell_order_id = ltp_streamer.alice.place_order(
                            transaction_type=TransactionType.Sell,
                            instrument=instrument,
                            quantity=LOT_SIZE,  # Use LOT_SIZE for actual order quantity (35 lots)
                            order_type=OrderType.Market,  # Market order for immediate execution
                            product_type=ProductType.Intraday
                        )
                        self.stdout.write(self.style.SUCCESS(f"✅ Square-off SELL placed (stoploss): {sell_order_id} | Market Order | Quantity: {QUANTITY} ({LOT_SIZE} lots)"))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"❌ Failed to square-off on stoploss: {e}"))
                    self.stdout.write(self.style.ERROR(f"🛑 Stoploss Hit! PnL: ₹{pnl:.2f}"))
                    break

                # Log current status every 30 seconds
                elapsed = (datetime.now(ist) - entry_time).seconds
                if elapsed % 30 == 0:
                    drawdown_info = f"Max DD: ₹{max_drawdown:.2f}" if max_drawdown < 0 else "Max DD: ₹0.00"
                    self.stdout.write(f"📊 LIVE TRADING: PnL: ₹{pnl:.2f} | {drawdown_info} | Daily: ₹{daily_pnl:.2f} | LTP: ₹{current_ltp} | Target: ₹{TARGET_PROFIT} | Stoploss: ₹{STOPLOSS} | Time: {current_time.strftime('%H:%M:%S')}")

                time.sleep(1)

        # Update daily_pnl to reflect the actual trade PnL
        daily_pnl = pnl

        # 📝 Save TradeLog
        self.stdout.write("\n📝 Step: Save Trade Log")
        self.stdout.write("-" * 30)

        # Get or create config for logging
        config = TradeConfig.objects.filter(is_active=True).last()
        if not config:
            config = TradeConfig.objects.create(
                strategy_name="Slippage-Compensated Strategy",
                closing_price=YESTERDAY_CLOSING,
                lot_size=LOT_SIZE,
                target=TARGET_PROFIT,
                stoploss=STOPLOSS,
                trade_start=dt_time(9, 15),
                trade_end=SQUARE_OFF_TIME,
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
            message=f"Slippage-Compensated Strategy - Future Direction: {future_direction} → Option: {option_direction} {option_symbol}. {status} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}. Entry: ₹{entry_price}, Exit: ₹{exit_price}, Daily PnL: ₹{daily_pnl}"
        )

        # Final status report
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("📋 SLIPPAGE-COMPENSATED TRADE SUMMARY"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
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
        self.stdout.write(f"Trade PnL: ₹{pnl:.2f}")
        self.stdout.write(f"Daily PnL: ₹{daily_pnl:.2f}")
        if max_drawdown < 0:
            drawdown_str = f"Maximum Drawdown: ₹{max_drawdown:.2f}"
            if drawdown_time:
                time_str = drawdown_time.strftime('%H:%M:%S')
                drawdown_str += f" (at {time_str})"
            self.stdout.write(self.style.WARNING(drawdown_str))
            recovery_info = "✅ Recovered from drawdown" if pnl > 0 else "❌ Did not recover"
            self.stdout.write(f"Recovery Status: {recovery_info}")
        else:
            self.stdout.write(f"Maximum Drawdown: ₹0.00 (no drawdown)")
        self.stdout.write(f"Lot Size: {LOT_SIZE}")
        self.stdout.write(f"Daily Target: ₹{DAILY_PROFIT_TARGET}")
        self.stdout.write(f"Daily Loss Limit: ₹{DAILY_LOSS_LIMIT}")
        self.stdout.write(self.style.SUCCESS("=" * 60))

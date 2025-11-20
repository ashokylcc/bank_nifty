"""
Management command to run BankNifty Momentum Breakout Strategy
"""
import os
import time
import logging
import sys
from decimal import Decimal
from datetime import time as dt_time
from typing import List
import pytz
from django.core.management.base import BaseCommand
from django.conf import settings
from trading.models import Strategy, TradeLog
from trading.services.strategy_engine import StrategyEngine
from trading.services.concurrency_guard import ConcurrencyGuard
from trading.services.data_ingest_live import LiveDataIngestService
from trading.services.candle_aggregator import CandleAggregator
from trading.services.heikin_ashi import HeikinAshiCalculator
from trading.services.super_trend import SuperTrendCalculator
from trading.utils.time_helpers import get_ist_now

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run BankNifty Momentum Breakout Strategy'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run in dry-run mode (no real orders)',
        )
        parser.add_argument(
            '--loop',
            action='store_true',
            help='Run continuously (loop mode)',
        )
        parser.add_argument(
            '--simulate',
            action='store_true',
            help='Run in simulation mode (use CSV data)',
        )
        parser.add_argument(
            '--csv',
            type=str,
            help='Path to CSV file for simulation (required with --simulate)',
        )
        parser.add_argument(
            '--once',
            action='store_true',
            help='Run single cycle and exit (useful with --simulate)',
        )
        parser.add_argument(
            '--strategy-id',
            type=int,
            help='Strategy ID to run (default: latest active strategy)',
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=5,
            help='Loop interval in seconds (default: 5)',
        )
        parser.add_argument(
            '--live-data',
            action='store_true',
            help='Use live WebSocket data (real market prices, mock execution)',
        )
    
    def handle(self, *args, **options):
        # Concurrency guard - ensure single authoritative process
        guard = ConcurrencyGuard()
        
        # Check if another instance is running
        if guard.is_another_instance_running():
            self.stdout.write(self.style.ERROR(
                "❌ Another strategy runner is already running!"
            ))
            self.stdout.write("Only one strategy runner should be active at a time.")
            self.stdout.write("Stop the other instance or check for stale lock file.")
            sys.exit(1)
        
        # Acquire lock
        try:
            with guard:
                self._run_strategy(options)
        except RuntimeError as e:
            self.stdout.write(self.style.ERROR(f"❌ {e}"))
            sys.exit(1)
    
    def _run_strategy(self, options):
        """Run strategy (called within lock context)"""
        # Determine dry-run mode
        dry_run = options.get('dry_run', True)
        
        # Check environment variables
        env_dry_run = os.getenv('DRY_RUN', 'true').lower() == 'true'
        confirm_real = os.getenv('CONFIRM_REAL_TRADES', 'false').lower() == 'true'
        
        # Final dry-run decision
        if not dry_run and not env_dry_run and confirm_real:
            dry_run = False
            self.stdout.write(self.style.WARNING("⚠️  LIVE TRADING MODE - Real orders will be placed!"))
        else:
            dry_run = True
            self.stdout.write(self.style.SUCCESS("✅ DRY-RUN MODE - No real orders"))
        
        # Get strategy
        strategy_id = options.get('strategy_id')
        if strategy_id:
            try:
                strategy = Strategy.objects.get(id=strategy_id)
            except Strategy.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"❌ Strategy with ID {strategy_id} not found"))
                return
        else:
            strategy = Strategy.objects.filter(enabled=True).last()
            if not strategy:
                self.stdout.write(self.style.ERROR("❌ No active strategy found"))
                self.stdout.write("Create a strategy in Django Admin and enable it")
                return
        
        self.stdout.write(self.style.SUCCESS(f"📊 Running Strategy: {strategy.name}"))
        self.stdout.write(f"   Enabled: {strategy.enabled}")
        self.stdout.write(f"   Capital: ₹{strategy.capital}")
        self.stdout.write(f"   Risk per trade: {strategy.risk_per_trade_pct}%")
        self.stdout.write(f"   Max daily loss: ₹{strategy.max_daily_loss}")
        
        if not strategy.enabled:
            self.stdout.write(self.style.WARNING("⚠️  Strategy is disabled (kill switch)"))
            self.stdout.write("Enable it in Django Admin to start trading")
            return
        
        # Handle simulation mode
        simulate = options.get('simulate', False)
        csv_path = options.get('csv')
        
        if simulate:
            if not csv_path:
                self.stdout.write(self.style.ERROR("❌ --csv path required when using --simulate"))
                return
            
            if not os.path.exists(csv_path):
                self.stdout.write(self.style.ERROR(f"❌ CSV file not found: {csv_path}"))
                return
            
            self.stdout.write(self.style.SUCCESS(f"🎮 SIMULATION MODE: Loading data from {csv_path}"))
            dry_run = True  # Force dry-run in simulation
        
        # Determine if using live data (can't use both live data and CSV simulation)
        use_live_data = options.get('live_data', False)
        if use_live_data and simulate:
            self.stdout.write(self.style.ERROR("❌ Cannot use both --live-data and --simulate"))
            self.stdout.write("Use --live-data for real WebSocket data or --simulate for CSV data")
            return
        
        # Auto-detect: Check if credentials are available and enable live data automatically
        if not use_live_data and not simulate:
            try:
                from strategy.broker.alice_client import USER_ID, API_KEY
                if USER_ID and API_KEY:
                    self.stdout.write(self.style.SUCCESS("🔍 Auto-detected Alice Blue credentials - enabling WebSocket"))
                    use_live_data = True
            except (ImportError, AttributeError):
                pass  # No credentials, will use stub mode
        
        # Initialize strategy engine
        engine = StrategyEngine(strategy, dry_run=dry_run, use_live_data=use_live_data)
        engine.initialize()
        
        # Load CSV data if in simulation mode
        if simulate:
            try:
                engine.data_service.load_from_csv(csv_path)
                self.stdout.write(self.style.SUCCESS(f"✅ Loaded {len(engine.data_service.candles)} candles from CSV"))
                
                # Set mock LTP from latest candle for simulation
                if engine.data_service.candles:
                    latest_candle = engine.data_service.candles[-1]
                    if hasattr(engine.execution_adapter, 'set_mock_ltp'):
                        engine.execution_adapter.set_mock_ltp("BANKNIFTY", latest_candle.close)
                        self.stdout.write(self.style.SUCCESS(f"✅ Set mock LTP: ₹{latest_candle.close}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error loading CSV: {e}"))
                return
        
        # Connect to live data if enabled (after CSV loading check)
        if use_live_data:
            self.stdout.write(self.style.SUCCESS("📡 Connecting to live WebSocket feed..."))
            self.stdout.write("🔐 Attempting login (using credentials from alice_client.py)...")
            
            # Get the correct BankNifty futures symbol
            from trading.utils.expiry_functions import get_banknifty_futures_symbol
            futures_symbol = get_banknifty_futures_symbol()
            self.stdout.write(f"📊 BankNifty Futures Symbol: {futures_symbol}")
            
            # Store futures symbol in engine for later use (to match option expiry)
            if hasattr(engine, 'futures_symbol'):
                engine.futures_symbol = futures_symbol
            else:
                setattr(engine, 'futures_symbol', futures_symbol)
            
            # Also store in data_service if available
            if hasattr(engine, 'data_service'):
                setattr(engine.data_service, 'futures_symbol', futures_symbol)
            
            if hasattr(engine.data_service, 'connect'):
                if engine.data_service.connect():
                    self.stdout.write(self.style.SUCCESS("✅ Connected to live data feed"))
                    
                    # Wait for WebSocket to be ready (same pattern as run_strategy.py)
                    self.stdout.write("🔍 Testing WebSocket connection...")
                    time.sleep(3)  # Wait longer for connection to establish
                    
                    # Check connection status (try multiple ways)
                    is_connected = False
                    if hasattr(engine.data_service, '_connected'):
                        is_connected = engine.data_service._connected
                    elif hasattr(engine.data_service, 'is_connected'):
                        is_connected = engine.data_service.is_connected()
                    elif hasattr(engine.data_service, 'alice_client'):
                        is_connected = engine.data_service.alice_client is not None
                    
                    if is_connected:
                        self.stdout.write(self.style.SUCCESS("✅ WebSocket connection established"))
                        
                        # Subscribe to BankNifty futures (using correct symbol format)
                        if hasattr(engine.data_service, 'subscribe'):
                            try:
                                engine.data_service.subscribe(futures_symbol)
                                self.stdout.write(self.style.SUCCESS(f"🔔 Subscribed to {futures_symbol}"))
                                
                                # Wait a bit more for first ticks
                                time.sleep(2)
                                
                                # Verify subscription by checking if we get LTP
                                test_ltp = engine.data_service.get_latest_ltp(futures_symbol)
                                if test_ltp:
                                    self.stdout.write(self.style.SUCCESS(f"✅ Real WebSocket connected - receiving live ticks (LTP: ₹{test_ltp:,.2f})"))
                                else:
                                    self.stdout.write(self.style.WARNING("⚠️  WebSocket connected but no LTP received yet - will retry"))
                            except Exception as e:
                                self.stdout.write(self.style.ERROR(f"❌ Failed to subscribe: {e}"))
                                logger.error(f"Subscription error: {e}")
                    else:
                        self.stdout.write(self.style.WARNING("⚠️  WebSocket not connected yet - using stub mode"))
                        # Stub mode - set test LTP for demonstration
                        test_ltp = Decimal("58423.50")
                        if hasattr(engine.data_service, 'set_test_ltp'):
                            engine.data_service.set_test_ltp("BANKNIFTY", test_ltp)
                            engine.data_service.set_test_ltp(futures_symbol, test_ltp)
                            self.stdout.write(self.style.SUCCESS(f"📊 Test LTP set: ₹{test_ltp:,.2f} (stub mode)"))
                else:
                    self.stdout.write(self.style.ERROR("❌ Failed to connect to live data feed"))
                    return
            else:
                self.stdout.write(self.style.WARNING("⚠️  Live data service not available"))
        
        loop_mode = options.get('loop', False)
        once_mode = options.get('once', False)
        interval = options.get('interval', 5)
        
        # ========================================
        # Strategy Parameters (Unified - Same as Backtest)
        # ========================================
        # ✅ IMPROVED: Wider stoploss (1.2%) and target set to 60 points
        # Target: 60 points profit (approximately 0.1% of BankNifty price)
        TARGET_POINTS = Decimal('60')             # Target: 60 points profit
        TARGET_PCT = Decimal('0.1') / 100         # Approximate percentage (will be calculated dynamically)
        STOPLOSS_PCT = Decimal('1.2') / 100       # Stoploss: -1.2% (wider to reduce premature exits)
        TRAILING_TRIGGER_PCT = Decimal('0.5') / 100  # Trailing SL triggers after +0.5%
        LOT_SIZE = 35                             # ✅ BankNifty lot size (fixed)
        SQUARE_OFF_TIME = dt_time(15, 30)         # Auto exit at 3:30 PM
        TRADE_START_TIME = dt_time(9, 30)         # Trading window start (9:30 AM)
        TRADE_END_TIME = dt_time(15, 30)          # Trading window end (3:30 PM - market close)
        
        # ✅ IMPROVED: Better entry filters (RSI > 50 for BUY, < 50 for SELL)
        # Use values from strategy if available, otherwise use defaults
        RSI_BUY_MIN = Decimal(str(strategy.rsi_buy_min)) if hasattr(strategy, 'rsi_buy_min') and strategy.rsi_buy_min else Decimal('50')
        RSI_BUY_MAX = Decimal(str(strategy.rsi_buy_max)) if hasattr(strategy, 'rsi_buy_max') and strategy.rsi_buy_max else Decimal('70')
        RSI_SELL_MIN = Decimal(str(strategy.rsi_sell_min)) if hasattr(strategy, 'rsi_sell_min') and strategy.rsi_sell_min else Decimal('30')
        RSI_SELL_MAX = Decimal(str(strategy.rsi_sell_max)) if hasattr(strategy, 'rsi_sell_max') and strategy.rsi_sell_max else Decimal('50')
        EMA_GAP_REQUIRED = Decimal('0.0001')     # Very lenient: 0.01% gap (allows breakouts when price action is clear, even if EMAs lag)
        
        # ✅ NEW: Time-based exit parameters
        TIME_EXIT_MINUTES = 12                    # Exit if trade is older than 12 minutes and profit < threshold
        TIME_EXIT_PROFIT_THRESHOLD = Decimal('0.3') / 100  # If profit < 0.3% after 12 minutes, exit
        
        # Simplified momentum breakout parameters
        self.capital = float(strategy.capital)
        self.lot_size = LOT_SIZE
        self.stoploss_pct = STOPLOSS_PCT
        self.target_pct = TARGET_PCT
        self.trailing_trigger_pct = TRAILING_TRIGGER_PCT
        self.current_position = None
        self.current_stoploss_pct = STOPLOSS_PCT  # Dynamic stoploss (for trailing)
        self.position_just_entered = False  # Flag to skip exit checks in the same cycle as entry
        self.last_trade_exit_time = None  # Track when last trade exited (for cooldown)
        # Get cooldown period from strategy config (default: 5 minutes)
        self.trade_cooldown_minutes = getattr(strategy, 'trade_cooldown_minutes', 5)
        
        # Store optimized filter parameters as instance variables (so they can be used in _check_momentum_filters)
        self.rsi_buy_min = RSI_BUY_MIN
        self.rsi_buy_max = RSI_BUY_MAX  # ✅ NEW: Upper limit to avoid overbought entries
        self.rsi_sell_min = RSI_SELL_MIN  # ✅ NEW: Lower limit to avoid oversold entries
        self.rsi_sell_max = RSI_SELL_MAX
        self.ema_gap_required = EMA_GAP_REQUIRED
        self.trade_start_time = TRADE_START_TIME
        self.trade_end_time = TRADE_END_TIME
        self.time_exit_minutes = TIME_EXIT_MINUTES
        self.time_exit_profit_threshold = TIME_EXIT_PROFIT_THRESHOLD
        # ✅ NEW: Heikin Ashi 15-min + Super Trend setup
        # Using ATR period 5 to start trading earlier (~11:00 AM instead of 12:45 PM)
        # This allows buying CALL options at lower prices and catching trends early
        # ATR period 5 needs 6 candles (90 minutes) - minimum viable for accurate signals
        self.candle_aggregator = CandleAggregator(candle_interval_minutes=15)
        self.heikin_ashi_calc = HeikinAshiCalculator()
        self.super_trend_calc = SuperTrendCalculator(atr_period=5, multiplier=Decimal('3.0'))
        self.previous_super_trend = None  # Track previous Super Trend for signal detection
        # Track consecutive red/green candles to avoid false exits on temporary pullbacks
        self.consecutive_red_candles = 0  # Count consecutive red Super Trend candles
        self.consecutive_green_candles = 0  # Count consecutive green Super Trend candles
        self.target_points = TARGET_POINTS  # Target: 60 points profit
        
        # Keep old variables for backward compatibility (will be phased out)
        self.price_samples = []  # Track last 3 prices for range detection (from futures)
        self.price_history = []  # Track price history for EMA/RSI calculations (keep last 50)
        self.range_high = None
        self.range_low = None
        self.range_established = False  # Flag to track if range has been established
        
        # Option trading setup
        from trading.services.strike_selector import StrikeSelector
        self.strike_selector = StrikeSelector()
        self.option_ltp_cache = {}  # Track option LTPs: {symbol: ltp}
        
        # Restore open position from database if exists
        self._restore_open_position(strategy)
        
        try:
            if once_mode or (simulate and not loop_mode):
                # Run single cycle
                self.stdout.write(self.style.SUCCESS("▶️  Running single cycle"))
                results = engine.run_single_cycle()
                self._log_cycle_results(results)
            elif loop_mode:
                self.stdout.write(self.style.SUCCESS(f"🔄 Starting continuous loop (interval: {interval}s)"))
                self.stdout.write("Press Ctrl+C to stop")
                
                cycle_count = 0
                # Store engine reference for status logging
                self._engine = engine
                
                # Market close time (3:30 PM IST)
                market_close_time = dt_time(15, 30)
                market_open_time = dt_time(9, 15)  # Market opens at 9:15 AM IST
                ist = pytz.timezone('Asia/Kolkata')
                
                while True:
                    try:
                        current_time_ist = get_ist_now()
                        current_time = current_time_ist.time()
                        
                        # Check if market is not yet open (before 9:15 AM)
                        if current_time < market_open_time:
                            # Wait for market to open - don't exit, just wait
                            cycle_count += 1
                            if cycle_count % 12 == 0:  # Log every 60 seconds (12 * 5s interval)
                                self.stdout.write(f"⏳ Waiting for market to open... Current time: {current_time.strftime('%H:%M:%S')} IST | Market opens at 9:15 AM")
                            time.sleep(interval)
                            continue
                        
                        # Check if market is closed (3:30 PM IST)
                        if current_time >= market_close_time:
                            self.stdout.write(self.style.WARNING("🕒 Market closed (3:30 PM) – stopping strategy safely."))
                            
                            # Close any open position
                            if self.current_position:
                                option_symbol = self.current_position.get("symbol")
                                if option_symbol:
                                    option_ltp = self._get_option_ltp(option_symbol, engine)
                                    if option_ltp:
                                        self._simulate_exit(option_ltp, "MARKET_CLOSE", engine)
                            
                            # Close WebSocket connection if available
                            if hasattr(engine, 'data_service'):
                                if hasattr(engine.data_service, 'disconnect'):
                                    try:
                                        engine.data_service.disconnect()
                                        self.stdout.write(self.style.SUCCESS("✅ WebSocket connection closed"))
                                    except Exception as e:
                                        logger.warning(f"Error closing WebSocket: {e}")
                                elif hasattr(engine.data_service, 'alice_client'):
                                    try:
                                        if hasattr(engine.data_service.alice_client, 'stop_websocket'):
                                            engine.data_service.alice_client.stop_websocket()
                                        self.stdout.write(self.style.SUCCESS("✅ WebSocket connection closed"))
                                    except Exception as e:
                                        logger.warning(f"Error closing WebSocket: {e}")
                            
                            # Exit loop gracefully
                            break
                        
                        # Get latest Futures LTP from WebSocket (always track futures)
                        futures_ltp = self._get_latest_ltp(engine)
                        
                        if futures_ltp:
                            # ✅ NEW: Add LTP to candle aggregator (15-minute candles)
                            new_candle = self.candle_aggregator.add_ltp(futures_ltp, current_time_ist)
                            
                            # If new candle created (every 15 minutes)
                            if new_candle:
                                # Convert to Heikin Ashi
                                ha_candle = self.heikin_ashi_calc.add_candle(new_candle)
                                
                                # Calculate Super Trend
                                super_trend = self.super_trend_calc.add_candle(ha_candle)
                                
                                if super_trend:
                                    # Detect signal change
                                    signal_change = super_trend.get('signal_change', 'HOLD')
                                    
                                    # Track consecutive candles to avoid false exits on pullbacks
                                    current_color = super_trend['color']
                                    if current_color == 'GREEN':
                                        self.consecutive_green_candles += 1
                                        self.consecutive_red_candles = 0  # Reset red counter
                                    elif current_color == 'RED':
                                        self.consecutive_red_candles += 1
                                        self.consecutive_green_candles = 0  # Reset green counter
                                    
                                    # Log Super Trend status
                                    st_color_emoji = "🟢" if super_trend['color'] == 'GREEN' else "🔴"
                                    logger.info(
                                        f"Super Trend: Value=₹{super_trend['value']:.2f}, "
                                        f"Color={super_trend['color']}, Signal={signal_change}, "
                                        f"Consecutive Red={self.consecutive_red_candles}, Green={self.consecutive_green_candles}"
                                    )
                                    
                                    # Display Super Trend update
                                    if signal_change != 'HOLD':
                                        self.stdout.write(self.style.SUCCESS(
                                            f"📊 Super Trend {st_color_emoji}: {super_trend['color']} | "
                                            f"Value: ₹{super_trend['value']:.2f} | Signal: {signal_change} | "
                                            f"Consecutive: Red={self.consecutive_red_candles}, Green={self.consecutive_green_candles}"
                                        ))
                                    
                                    # Check for entry signal (only if not in trade and signal changed)
                                    if not self.current_position and signal_change == 'BUY':
                                        # Super Trend turned GREEN - BUY CALL
                                        self._handle_super_trend_entry('BUY', futures_ltp, engine, strategy, super_trend)
                                    elif not self.current_position and signal_change == 'SELL':
                                        # Super Trend turned RED - BUY PUT
                                        self._handle_super_trend_entry('SELL', futures_ltp, engine, strategy, super_trend)
                                    
                                    # Update previous Super Trend
                                    self.previous_super_trend = super_trend
                            
                            # Keep old logic for backward compatibility (will be removed later)
                            # Track futures price samples for range detection (keep last 3)
                            self.price_samples.append(futures_ltp)
                            if len(self.price_samples) > 3:
                                self.price_samples.pop(0)
                            
                            # Track price history for EMA/RSI calculations (keep last 50)
                            self.price_history.append(futures_ltp)
                            if len(self.price_history) > 50:
                                self.price_history.pop(0)
                            
                            # Detect breakout after at least 3 data points (using futures LTP)
                            # Only allow new entries during trading window (9:30 AM - 11:00 AM)
                            current_time = get_ist_now().time()
                            is_in_trading_window = (current_time >= self.trade_start_time and 
                                                   current_time <= self.trade_end_time)
                            
                            # Establish range once when we have 3 samples (regardless of trading window)
                            # Require minimum range size (0.05% or 10 points) to ensure meaningful breakouts
                            # Note: Range can be established outside trading window, but trades only during window
                            if len(self.price_samples) == 3 and not self.range_established and not self.current_position:
                                temp_range_high = max(self.price_samples)
                                temp_range_low = min(self.price_samples)
                                range_size = temp_range_high - temp_range_low
                                range_pct = (range_size / temp_range_low * 100) if temp_range_low > 0 else Decimal('0')
                                
                                # Minimum range requirement: at least 0.05% or 10 points
                                min_range_pct = Decimal('0.05')
                                min_range_points = Decimal('10')
                                
                                if range_pct >= min_range_pct or range_size >= min_range_points:
                                    # Valid range - establish it
                                    self.range_high = temp_range_high
                                    self.range_low = temp_range_low
                                    self.range_established = True
                                    
                                    # Calculate dynamic breakout percentage for display
                                    range_width = self.range_high - self.range_low
                                    if range_width < 40:
                                        breakout_pct = Decimal('0.0005')
                                    elif 40 <= range_width <= 80:
                                        breakout_pct = Decimal('0.001')
                                    else:
                                        breakout_pct = Decimal('0.0015')
                                    
                                    window_status = "✅ Ready for trading" if is_in_trading_window else "⏳ Waiting for trading window (9:30 AM - 3:30 PM)"
                                    self.stdout.write(self.style.SUCCESS(
                                        f"✅ Range established: ₹{self.range_low:,.2f} - ₹{self.range_high:,.2f} ({range_pct:.2f}%) | "
                                        f"Dynamic Breakout %: {breakout_pct*100:.2f}% | Range width: {range_width:.0f} pts | {window_status}"
                                    ))
                                else:
                                    # Range too small - keep collecting samples (remove oldest, will add new one next cycle)
                                    self.price_samples.pop(0)
                                    # Don't establish range yet - wait for more variation
                                    if cycle_count % 12 == 0:  # Log every ~1 minute (12 cycles * 5s = 60s)
                                        self.stdout.write(self.style.WARNING(
                                            f"⏳ Waiting for sufficient price variation to establish range (current: {range_pct:.3f}%, need: {min_range_pct}% or {min_range_points} points)"
                                        ))
                            
                            # Check for breakout if range is established and no current position
                            # Detect breakouts anytime (for monitoring), but only execute trades during trading window
                            # Also check if cooldown period has passed since last trade exit
                            cooldown_passed = True
                            if self.last_trade_exit_time:
                                time_since_exit = current_time_ist - self.last_trade_exit_time
                                cooldown_seconds = self.trade_cooldown_minutes * 60
                                if time_since_exit.total_seconds() < cooldown_seconds:
                                    cooldown_passed = False
                                    remaining_seconds = int(cooldown_seconds - time_since_exit.total_seconds())
                                    if cycle_count % 12 == 0:  # Log every 12 cycles (~1 minute)
                                        self.stdout.write(self.style.WARNING(
                                            f"⏸️  Cooldown active: {remaining_seconds}s remaining before next trade allowed"
                                        ))
                            
                            if self.range_established and not self.current_position and cooldown_passed:
                                # ========================================
                                # Dynamic Breakout Logic
                                # ========================================
                                range_width = self.range_high - self.range_low
                                
                                # Determine dynamic breakout percentage based on range width
                                if range_width < 40:
                                    breakout_pct = Decimal('0.0005')  # 0.05%
                                elif 40 <= range_width <= 80:
                                    breakout_pct = Decimal('0.001')   # 0.1%
                                else:  # range_width > 80
                                    breakout_pct = Decimal('0.0015')  # 0.15%
                                
                                # Store breakout_pct for logging
                                self.breakout_pct = breakout_pct
                                self.range_width = range_width
                                
                                # Calculate breakout thresholds using dynamic percentage
                                buy_breakout_level = self.range_high * (Decimal('1') + breakout_pct)
                                sell_breakout_level = self.range_low * (Decimal('1') - breakout_pct)
                                
                                # Calculate distance to breakout (for periodic logging)
                                distance_to_buy = ((futures_ltp - buy_breakout_level) / buy_breakout_level * 100) if buy_breakout_level > 0 else Decimal('0')
                                distance_to_sell = ((sell_breakout_level - futures_ltp) / sell_breakout_level * 100) if sell_breakout_level > 0 else Decimal('0')
                                
                                # Log proximity to breakout every 12 cycles (~1 minute) if price is near range boundaries
                                if cycle_count % 12 == 0:
                                    # Check "Very close" first (most urgent) - within 0.05% of breakout level
                                    if futures_ltp >= buy_breakout_level * Decimal('0.9995') and futures_ltp < buy_breakout_level:
                                        points_needed = buy_breakout_level - futures_ltp
                                        self.stdout.write(self.style.WARNING(
                                            f"🔥 Very close to BUY breakout: Price ₹{futures_ltp:,.2f} | Need ₹{buy_breakout_level:,.2f} (+₹{points_needed:,.2f} or {distance_to_buy:+.3f}%)"
                                        ))
                                    elif futures_ltp <= sell_breakout_level * Decimal('1.0005') and futures_ltp > sell_breakout_level:
                                        points_needed = futures_ltp - sell_breakout_level
                                        self.stdout.write(self.style.WARNING(
                                            f"🔥 Very close to SELL breakout: Price ₹{futures_ltp:,.2f} | Need ₹{sell_breakout_level:,.2f} (-₹{points_needed:,.2f} or {distance_to_sell:+.3f}%)"
                                        ))
                                    # Check if price is at or above range high (approaching buy breakout)
                                    elif futures_ltp >= self.range_high and futures_ltp < buy_breakout_level:
                                        points_needed = buy_breakout_level - futures_ltp
                                        self.stdout.write(self.style.WARNING(
                                            f"📈 Approaching BUY breakout: Price ₹{futures_ltp:,.2f} | Range High: ₹{self.range_high:,.2f} | Need ₹{buy_breakout_level:,.2f} (+₹{points_needed:,.2f} or {distance_to_buy:+.3f}%)"
                                        ))
                                    # Check if price is at or below range low (approaching sell breakout)
                                    elif futures_ltp <= self.range_low and futures_ltp > sell_breakout_level:
                                        points_needed = futures_ltp - sell_breakout_level
                                        self.stdout.write(self.style.WARNING(
                                            f"📉 Approaching SELL breakout: Price ₹{futures_ltp:,.2f} | Range Low: ₹{self.range_low:,.2f} | Need ₹{sell_breakout_level:,.2f} (-₹{points_needed:,.2f} or {distance_to_sell:+.3f}%)"
                                        ))
                                
                                # Breakout detection: futures price >= high * 1.001 (BUY) or <= low * 0.999 (SELL)
                                breakout_signal = None
                                if futures_ltp >= buy_breakout_level:
                                    breakout_signal = "BUY"
                                elif futures_ltp <= sell_breakout_level:
                                    breakout_signal = "SELL"
                                
                                # If breakout detected
                                if breakout_signal:
                                    if is_in_trading_window:
                                        # During trading window: apply momentum filters and execute trade
                                        filter_result = self._check_momentum_filters(breakout_signal, futures_ltp, self.price_history, return_details=True)
                                        if isinstance(filter_result, dict):
                                            # Filters failed - show why
                                            if not filter_result.get('passed', False):
                                                reasons = filter_result.get('reasons', [])
                                                self.stdout.write(self.style.WARNING(
                                                    f"⚠️  Breakout detected ({breakout_signal}) but momentum filters failed: {', '.join(reasons)}"
                                                ))
                                            else:
                                                # Filters passed - proceed with trade
                                                self._handle_breakout(breakout_signal, futures_ltp, engine, strategy)
                                        elif filter_result:
                                            # Legacy: boolean True means passed
                                            self._handle_breakout(breakout_signal, futures_ltp, engine, strategy)
                                        else:
                                            # Filters failed (legacy boolean False)
                                            self.stdout.write(self.style.WARNING(
                                                f"⚠️  Breakout detected ({breakout_signal}) but momentum filters failed"
                                            ))
                                    else:
                                        # Outside trading window: just log the breakout (for monitoring)
                                        breakout_pct = ((futures_ltp - self.range_high) / self.range_high * 100) if breakout_signal == "BUY" else ((self.range_low - futures_ltp) / self.range_low * 100)
                                        self.stdout.write(self.style.WARNING(
                                            f"📊 Breakout detected ({breakout_signal}) but outside trading window (9:30 AM - 3:30 PM) | Price: ₹{futures_ltp:,.2f} | Breakout: {breakout_pct:+.2f}%"
                                        ))
                            
                            # If in trade → check exit conditions (using option LTP)
                            if self.current_position:
                                entry = self.current_position
                                option_symbol = entry.get("symbol")
                                
                                if option_symbol:
                                    # Skip exit checks if position was just entered in this cycle
                                    if self.position_just_entered:
                                        # Reset flag for next cycle
                                        self.position_just_entered = False
                                    else:
                                        # Get option LTP
                                        option_ltp = self._get_option_ltp(option_symbol, engine)
                                        
                                        if option_ltp:
                                            entry_price = Decimal(str(entry["entry_price"]))
                                            position_side = entry.get("side", "")
                                            
                                            # Calculate P&L percentage (options always bought, so profit when price goes up)
                                            pnl_pct = (option_ltp - entry_price) / entry_price if entry_price > 0 else Decimal('0')
                                            
                                            # Apply trailing stoploss logic
                                            self._update_trailing_stoploss(option_ltp, entry_price, position_side)
                                            
                                            # Get current stoploss (may have been updated by trailing logic)
                                            current_stoploss = Decimal(str(self.current_stoploss_pct))
                                            
                                            # Calculate stoploss price for direct comparison (more accurate)
                                            if "CE" in position_side:  # BUY CALL - stoploss when price goes down
                                                stoploss_price = entry_price * (Decimal('1') - current_stoploss)
                                                price_below_stoploss = option_ltp <= stoploss_price
                                            else:  # BUY PUT - stoploss when price goes up (PUT loses value when underlying goes up)
                                                stoploss_price = entry_price * (Decimal('1') - current_stoploss)
                                                price_below_stoploss = option_ltp <= stoploss_price
                                            
                                            # ✅ NEW: Calculate target in points (60 points)
                                            # Target: 60 points profit
                                            target_points = self.target_points
                                            target_price = entry_price + target_points  # For CALL: price goes up
                                            if "PE" in position_side:  # For PUT: price goes up when futures goes down
                                                target_price = entry_price + target_points  # Same calculation
                                            
                                            # Also calculate percentage for logging
                                            target_pct = (target_points / entry_price * 100) if entry_price > 0 else Decimal('0')
                                            is_close_to_target = option_ltp >= target_price * Decimal('0.99')  # Within 1% of target
                                            
                                            if cycle_count % 6 == 0 or is_close_to_target:  # Log every 6 cycles or when close to target
                                                pnl_points = option_ltp - entry_price
                                                logger.info(
                                                    f"Exit check: Entry=₹{entry_price:.2f}, Current=₹{option_ltp:.2f}, "
                                                    f"Target=₹{target_price:.2f} ({target_points} pts), "
                                                    f"P&L={pnl_points:.2f} pts ({pnl_pct*100:.2f}%), "
                                                    f"Stoploss%={current_stoploss*100:.2f}%"
                                                )
                                                # Also print to console when close to target
                                                if is_close_to_target:
                                                    self.stdout.write(self.style.WARNING(
                                                        f"🎯 Close to TARGET: Current ₹{option_ltp:.2f} | Target ₹{target_price:.2f} ({target_points} pts) | P&L {pnl_points:.2f} pts ({pnl_pct*100:.2f}%)"
                                                    ))
                                            
                                            # ✅ NEW: Check Super Trend reversal exit first (highest priority)
                                            # ✅ IMPROVED: Require 2 consecutive red/green candles to avoid false exits on pullbacks
                                            super_trend_exit = False
                                            current_st = self.super_trend_calc.get_last_super_trend()
                                            if current_st and self.previous_super_trend:
                                                # Check if Super Trend changed color (reversal)
                                                if "CE" in position_side:  # BUY CALL
                                                    # Exit if Super Trend turns RED AND we have 2 consecutive red candles
                                                    # This avoids exiting on temporary pullbacks (single red candle)
                                                    if current_st['color'] == 'RED' and self.consecutive_red_candles >= 2:
                                                        super_trend_exit = True
                                                        logger.info(
                                                            f"Super Trend reversal for CALL: 2 consecutive red candles detected "
                                                            f"(Red count: {self.consecutive_red_candles})"
                                                        )
                                                elif "PE" in position_side:  # BUY PUT
                                                    # Exit if Super Trend turns GREEN AND we have 2 consecutive green candles
                                                    # This avoids exiting on temporary pullbacks (single green candle)
                                                    if current_st['color'] == 'GREEN' and self.consecutive_green_candles >= 2:
                                                        super_trend_exit = True
                                                        logger.info(
                                                            f"Super Trend reversal for PUT: 2 consecutive green candles detected "
                                                            f"(Green count: {self.consecutive_green_candles})"
                                                        )
                                            
                                            # Also check if current Super Trend color doesn't match position (with 2 consecutive candles requirement)
                                            if not super_trend_exit and current_st:
                                                if "CE" in position_side and current_st['color'] == 'RED':
                                                    # CALL position but Super Trend is RED (downtrend)
                                                    # Require 2 consecutive red candles to confirm reversal
                                                    if self.consecutive_red_candles >= 2:
                                                        super_trend_exit = True
                                                elif "PE" in position_side and current_st['color'] == 'GREEN':
                                                    # PUT position but Super Trend is GREEN (uptrend)
                                                    # Require 2 consecutive green candles to confirm reversal
                                                    if self.consecutive_green_candles >= 2:
                                                        super_trend_exit = True
                                            
                                            if super_trend_exit:
                                                pnl_points = option_ltp - entry_price
                                                logger.info(
                                                    f"🔄 Super Trend reversal: Exiting at ₹{option_ltp:.2f} "
                                                    f"(Entry: ₹{entry_price:.2f}, P&L: {pnl_points:.2f} pts, {pnl_pct*100:.2f}%)"
                                                )
                                                self.stdout.write(self.style.WARNING(
                                                    f"🔄 SUPER TREND REVERSAL! Exiting at ₹{option_ltp:.2f} "
                                                    f"(Entry: ₹{entry_price:.2f}, Profit: {pnl_points:.2f} pts, {pnl_pct*100:.2f}%)"
                                                ))
                                                self._simulate_exit(option_ltp, "TRAILING", engine)
                                            # ✅ NEW: Check target in points (60 points)
                                            elif option_ltp >= target_price:
                                                pnl_points = option_ltp - entry_price
                                                logger.info(f"✅ TARGET HIT: P&L={pnl_points:.2f} pts ({pnl_pct*100:.2f}%) >= Target={target_points} pts")
                                                self.stdout.write(self.style.SUCCESS(
                                                    f"🎯 TARGET REACHED! Exiting at ₹{option_ltp:.2f} (Entry: ₹{entry_price:.2f}, Profit: {pnl_points:.2f} pts, {pnl_pct*100:.2f}%)"
                                                ))
                                                self._simulate_exit(option_ltp, "TARGET", engine)
                                            elif pnl_pct >= Decimal(str(self.target_pct)):  # Fallback to percentage if points not hit
                                                logger.info(f"✅ TARGET HIT: P&L%={pnl_pct*100:.2f}% >= Target%={self.target_pct*100:.2f}%")
                                                self.stdout.write(self.style.SUCCESS(
                                                    f"🎯 TARGET REACHED! Exiting at ₹{option_ltp:.2f} (Entry: ₹{entry_price:.2f}, Profit: {pnl_pct*100:.2f}%)"
                                                ))
                                                self._simulate_exit(option_ltp, "TARGET", engine)
                                            elif pnl_pct <= -current_stoploss or price_below_stoploss:
                                                # Log stoploss details for debugging
                                                logger.info(
                                                    f"Stoploss triggered: Entry=₹{entry_price:.2f}, "
                                                    f"Stoploss Price=₹{stoploss_price:.2f}, "
                                                    f"Current=₹{option_ltp:.2f}, "
                                                    f"P&L%={pnl_pct*100:.2f}%, "
                                                    f"Stoploss%={current_stoploss*100:.2f}%"
                                                )
                                                self._simulate_exit(option_ltp, "STOPLOSS", engine)
                                            # ✅ NEW: Conditional time-based exit (if profit < threshold after 12 minutes)
                                            elif self._check_time_based_exit(entry, current_time_ist, pnl_pct):
                                                logger.info(
                                                    f"Time-based exit: Trade age > {self.time_exit_minutes} min, "
                                                    f"Profit {pnl_pct*100:.2f}% < threshold {self.time_exit_profit_threshold*100:.2f}%"
                                                )
                                                self._simulate_exit(option_ltp, "TIME", engine)
                                            # Time-based exit (square-off time) - only if we're past square-off time
                                            elif current_time_ist.time() >= strategy.square_off_time:
                                                self._simulate_exit(option_ltp, "TIME", engine)
                        
                        cycle_count += 1
                        
                        # Print status every cycle with momentum details
                        current_time_str = current_time_ist.strftime('%H:%M:%S')
                        status_parts = []
                        
                        if futures_ltp:
                            status_parts.append(f"Futures: ₹{futures_ltp:,.2f}")
                            
                            # ✅ NEW: Show Super Trend status
                            current_st = self.super_trend_calc.get_last_super_trend()
                            if current_st:
                                st_color_emoji = "🟢" if current_st['color'] == 'GREEN' else "🔴"
                                status_parts.append(f"Super Trend: {st_color_emoji} ₹{current_st['value']:,.2f} ({current_st['color']})")
                            
                            # Show candle count
                            candle_count = len(self.candle_aggregator.candles)
                            if candle_count > 0:
                                status_parts.append(f"Candles: {candle_count}")
                            
                            # Calculate and show momentum indicators if we have enough data (for reference)
                            if len(self.price_history) >= 20:
                                from trading.services.momentum import compute_ema, compute_rsi
                                ema5 = compute_ema(self.price_history, 5)
                                ema20 = compute_ema(self.price_history, 20)
                                rsi = compute_rsi(self.price_history, 14)
                                
                                if ema5 and ema20 and rsi:
                                    ema_gap_pct = ((ema5 - ema20) / ema20 * 100) if ema20 > 0 else Decimal('0')
                                    status_parts.append(f"RSI: {rsi:.1f} | EMA5: ₹{ema5:,.2f} | EMA20: ₹{ema20:,.2f} | Gap: {ema_gap_pct:.2f}%")
                            
                            # Show range if established (legacy, will be phased out)
                            if self.range_high and self.range_low:
                                range_pct = ((self.range_high - self.range_low) / self.range_low * 100) if self.range_low > 0 else Decimal('0')
                                status_parts.append(f"Range: ₹{self.range_low:,.2f}-₹{self.range_high:,.2f} ({range_pct:.2f}%)")
                            
                            # Show position status
                            if self.current_position:
                                status_parts.append("📊 IN TRADE")
                            
                        if self.current_position:
                            option_symbol = self.current_position.get("symbol")
                            option_ltp = self._get_option_ltp(option_symbol, engine) if option_symbol else None
                            if option_ltp:
                                entry_price = Decimal(str(self.current_position["entry_price"]))
                                total_units = self.current_position.get("total_units", self.lot_size)
                                position_side = self.current_position.get("side", "BUY_CE")
                                pnl_pct = ((option_ltp - entry_price) / entry_price * 100) if entry_price > 0 else Decimal('0')
                                pnl_value = self._calculate_pnl(entry_price, option_ltp, position_side, total_units)
                                status_parts.append(f"Option: ₹{option_ltp:,.2f} | P&L: ₹{pnl_value:,.2f} ({pnl_pct:+.2f}%)")
                        
                        if status_parts:
                            self.stdout.write(f"[{current_time_str}] Cycle #{cycle_count} | {' | '.join(status_parts)}")
                        else:
                            self.stdout.write(f"[{current_time_str}] Cycle #{cycle_count} | Waiting for LTP...")
                        
                        time.sleep(interval)
                    except KeyboardInterrupt:
                        self.stdout.write(self.style.WARNING("\n⏹️  Stopping strategy..."))
                        break
            else:
                self.stdout.write(self.style.SUCCESS("▶️  Running single cycle"))
                results = engine.run_single_cycle()
                self._log_cycle_results(results)
        
        finally:
            engine.shutdown()
            self.stdout.write(self.style.SUCCESS("✅ Strategy stopped"))
    
    def _log_cycle_results(self, results: dict, cycle_count: int = 0):
        """Log cycle results"""
        from trading.utils.time_helpers import get_ist_now
        
        # Show periodic status (every 12 cycles = ~1 minute at 5s interval)
        show_status = cycle_count % 12 == 0 if cycle_count > 0 else False
        
        # Always show if something happened
        has_activity = (results['range_captured'] or results['breakout_detected'] or 
                       results['signal_created'] or results['trade_executed'] or 
                       results['trades_exited'] > 0)
        
        if has_activity or show_status:
            current_time = get_ist_now().strftime("%H:%M:%S")
            if cycle_count > 0:
                self.stdout.write(f"\n[{current_time}] Cycle #{cycle_count}")
            
        if results['range_captured']:
                self.stdout.write(self.style.SUCCESS("  ✅ Range captured"))
        if results['breakout_detected']:
                self.stdout.write(self.style.SUCCESS("  🎯 Breakout detected"))
        if results['signal_created']:
                self.stdout.write(self.style.SUCCESS("  📝 Signal created"))
        if results['trade_executed']:
                self.stdout.write(self.style.SUCCESS("  ✅ Trade executed"))
        if results['trades_exited'] > 0:
            self.stdout.write(self.style.SUCCESS(f"  🔚 {results['trades_exited']} trade(s) exited"))
        
        # Show status summary if no activity but periodic update
        if show_status and not has_activity:
                # Get engine status
                engine = getattr(self, '_engine', None)
                if engine:
                    range_status = "✅" if engine.range_captured else "⏳"
                    open_trades = len(engine.open_trades) if hasattr(engine, 'open_trades') else 0
                    
                    # Get LIVE LTP (try multiple sources)
                    ltp = None
                    futures_symbol = getattr(engine, 'futures_symbol', None)
                    
                    # Try 1: From futures symbol (preferred)
                    if futures_symbol and hasattr(engine, 'data_service'):
                        if hasattr(engine.data_service, 'ltp_cache') and futures_symbol in engine.data_service.ltp_cache:
                            ltp = engine.data_service.ltp_cache[futures_symbol]
                        elif hasattr(engine.data_service, 'get_latest_ltp'):
                            ltp = engine.data_service.get_latest_ltp(futures_symbol)
                    
                    # Try 2: From "BANKNIFTY" (spot/fallback)
                    if ltp is None and hasattr(engine, 'data_service'):
                        if hasattr(engine.data_service, 'ltp_cache') and "BANKNIFTY" in engine.data_service.ltp_cache:
                            ltp = engine.data_service.ltp_cache["BANKNIFTY"]
                        elif hasattr(engine.data_service, 'get_latest_ltp'):
                            ltp = engine.data_service.get_latest_ltp("BANKNIFTY")
                    
                    # Try 3: From execution adapter (with data_service)
                    if ltp is None and hasattr(engine, 'execution_adapter') and hasattr(engine, 'data_service'):
                        if futures_symbol:
                            ltp = engine.execution_adapter.get_ltp(futures_symbol, data_service=engine.data_service)
                        if ltp is None:
                            ltp = engine.execution_adapter.get_ltp("BANKNIFTY", data_service=engine.data_service)
                    
                    # Try 4: From execution adapter cache
                    if ltp is None and hasattr(engine, 'execution_adapter'):
                        if futures_symbol:
                            ltp = engine.execution_adapter.get_ltp(futures_symbol)
                        if ltp is None:
                            ltp = engine.execution_adapter.get_ltp("BANKNIFTY")
                    
                    # Display status with LTP
                    if ltp is not None:
                        symbol_display = futures_symbol if futures_symbol else "BANKNIFTY"
                        self.stdout.write(f"  Status: Range {range_status} | Open trades: {open_trades} | LIVE LTP ({symbol_display}): ₹{ltp:,.2f}")
                    else:
                        self.stdout.write(f"  Status: Range {range_status} | Open trades: {open_trades} | LTP: Waiting for data...")
                else:
                    self.stdout.write("  ⏳ Waiting for market activity...")
    
    def _get_latest_ltp(self, engine):
        """Get latest LTP from WebSocket or data service"""
        latest_ltp = None
        
        # Try futures symbol first
        futures_symbol = getattr(engine, 'futures_symbol', None)
        if futures_symbol:
            if hasattr(engine, 'data_service'):
                # Try 1: Direct LTP cache lookup
                if hasattr(engine.data_service, 'ltp_cache') and futures_symbol in engine.data_service.ltp_cache:
                    latest_ltp = engine.data_service.ltp_cache[futures_symbol]
                    if latest_ltp:
                        return Decimal(str(latest_ltp))
                
                # Try 2: get_latest_ltp method
                if latest_ltp is None and hasattr(engine.data_service, 'get_latest_ltp'):
                    latest_ltp = engine.data_service.get_latest_ltp(futures_symbol)
                    if latest_ltp:
                        return Decimal(str(latest_ltp))
                
                # Try 3: If LiveDataIngestService, check if we need to subscribe
                if latest_ltp is None and isinstance(engine.data_service, LiveDataIngestService):
                    # Check if subscribed
                    if hasattr(engine.data_service, 'subscribed_symbols'):
                        if futures_symbol not in engine.data_service.subscribed_symbols:
                            # Auto-subscribe if not already subscribed
                            try:
                                engine.data_service.subscribe(futures_symbol)
                                logger.info(f"Auto-subscribed to {futures_symbol} for LTP retrieval")
                                time.sleep(1)  # Wait a moment for first tick
                                # Try again after subscription
                                if hasattr(engine.data_service, 'ltp_cache') and futures_symbol in engine.data_service.ltp_cache:
                                    latest_ltp = engine.data_service.ltp_cache[futures_symbol]
                                    if latest_ltp:
                                        return Decimal(str(latest_ltp))
                            except Exception as e:
                                logger.warning(f"Auto-subscription failed: {e}")
        
        # Fallback to execution adapter
        if latest_ltp is None and hasattr(engine, 'execution_adapter'):
            if futures_symbol:
                latest_ltp = engine.execution_adapter.get_ltp(futures_symbol, data_service=engine.data_service)
            if latest_ltp is None:
                latest_ltp = engine.execution_adapter.get_ltp("BANKNIFTY", data_service=engine.data_service)
        
        return Decimal(str(latest_ltp)) if latest_ltp else None
    
    def _update_trailing_stoploss(self, current_price: Decimal, entry_price: Decimal, position_side: str):
        """
        ✅ IMPROVED: Hybrid trailing stoploss with progressive levels
        
        Logic:
        - Initial SL = -1.2%
        - If profit > +0.5% → move SL to -0.5%
        - If profit > +1.0% → move SL to +0.1% (breakeven+)
        - If profit > +1.5% → move SL to +0.5% (lock in profit)
        - If profit > +2.5% → move SL to +1.0% (lock in more profit)
        
        Args:
            current_price: Current option LTP
            entry_price: Entry price
            position_side: "BUY_CE" or "BUY_PE"
        """
        # Calculate current profit percentage
        if "CE" in position_side:  # BUY CALL - profit when price goes up
            pnl_pct = (current_price - entry_price) / entry_price
        else:  # BUY PUT - profit when price goes down
            pnl_pct = (entry_price - current_price) / entry_price
        
        # Determine new stoploss level based on profit
        new_stoploss_pct = None
        
        if pnl_pct >= Decimal('0.025'):  # Profit >= +2.5%
            new_stoploss_pct = Decimal('0.01')  # Move SL to +1.0% (lock in 1% profit)
            logger.info(f"📈 Trailing SL: Profit {pnl_pct*100:.2f}% >= 2.5% → Move SL to +1.0%")
        elif pnl_pct >= Decimal('0.015'):  # Profit >= +1.5%
            new_stoploss_pct = Decimal('0.005')  # Move SL to +0.5% (lock in 0.5% profit)
            logger.info(f"📈 Trailing SL: Profit {pnl_pct*100:.2f}% >= 1.5% → Move SL to +0.5%")
        elif pnl_pct >= Decimal('0.01'):  # Profit >= +1.0%
            new_stoploss_pct = Decimal('0.001')  # Move SL to +0.1% (breakeven+)
            logger.info(f"📈 Trailing SL: Profit {pnl_pct*100:.2f}% >= 1.0% → Move SL to +0.1%")
        elif pnl_pct >= Decimal('0.005'):  # Profit >= +0.5%
            new_stoploss_pct = Decimal('0.005')  # Move SL to -0.5% (reduce loss threshold)
            logger.info(f"📈 Trailing SL: Profit {pnl_pct*100:.2f}% >= 0.5% → Move SL to -0.5%")
        
        # Update stoploss if we have a new level and it's better (less negative or positive)
        if new_stoploss_pct is not None:
            # For CALL: new_stoploss_pct should be less negative (or positive) than current
            # For PUT: same logic applies
            current_abs = abs(self.current_stoploss_pct)
            new_abs = abs(new_stoploss_pct)
            
            # Update if new stoploss is better (less negative or positive)
            # Better means: if new is positive, always update; if both negative, update if new is less negative
            should_update = False
            if new_stoploss_pct >= 0:  # New stoploss is positive (breakeven+)
                should_update = True
            elif self.current_stoploss_pct < 0 and new_stoploss_pct < 0:  # Both negative
                should_update = new_abs < current_abs  # Update if new is less negative
            
            if should_update:
                self.current_stoploss_pct = -new_stoploss_pct if new_stoploss_pct < 0 else new_stoploss_pct
                logger.info(f"✅ Trailing stoploss updated: {self.current_stoploss_pct*100:.2f}% (was {current_abs*100:.2f}%)")
    
    def _check_momentum_filters(self, signal_type: str, current_price: Decimal, price_history: List[Decimal], return_details: bool = False):
        """
        Check momentum filters before entry - OPTIMIZED:
        - BUY: EMA5 > EMA20 * (1 + EMA_GAP_REQUIRED) AND RSI > RSI_BUY_MIN
        - SELL: EMA5 < EMA20 * (1 - EMA_GAP_REQUIRED) AND RSI < RSI_SELL_MAX
        
        Args:
            signal_type: 'BUY' or 'SELL'
            current_price: Current futures price
            price_history: List of price history
            return_details: If True, returns dict with details; if False, returns bool
        
        Returns:
            bool or dict: If return_details=False, returns True/False. If True, returns dict with 'passed', 'reasons', 'rsi', 'ema5', 'ema20', etc.
        """
        if len(price_history) < 20: # Need at least 20 prices for EMA20
            if return_details:
                return {'passed': False, 'reasons': ['Insufficient price history (need 20, have {})'.format(len(price_history))]}
            return False
        
        from trading.services.momentum import compute_ema, compute_rsi
        
        ema5 = compute_ema(price_history, 5)
        ema20 = compute_ema(price_history, 20)
        rsi = compute_rsi(price_history, 14)
        
        if ema5 is None or ema20 is None or rsi is None:
            if return_details:
                return {'passed': False, 'reasons': ['Could not calculate indicators (EMA5={}, EMA20={}, RSI={})'.format(ema5, ema20, rsi)]}
            return False
        
        # Use instance variables (set from constants at top)
        rsi_buy_min = getattr(self, 'rsi_buy_min', Decimal('60'))
        rsi_sell_max = getattr(self, 'rsi_sell_max', Decimal('40'))
        ema_gap = getattr(self, 'ema_gap_required', Decimal('0.002'))
        
        reasons = []
        
        if signal_type == "BUY":
            # ✅ IMPROVED: BUY: EMA5 > EMA20 * (1 + gap) AND RSI > rsi_buy_min AND RSI < rsi_buy_max
            ema_condition = ema5 > ema20 * (Decimal('1') + ema_gap)
            rsi_buy_max = getattr(self, 'rsi_buy_max', Decimal('70'))
            rsi_condition_min = rsi > rsi_buy_min
            rsi_condition_max = rsi < rsi_buy_max  # ✅ NEW: Avoid overbought entries
            rsi_condition = rsi_condition_min and rsi_condition_max
            
            if not ema_condition:
                ema_gap_actual = ((ema5 - ema20) / ema20 * 100) if ema20 > 0 else Decimal('0')
                reasons.append(f"EMA gap too small (need {ema_gap*100:.2f}%, have {ema_gap_actual:.2f}%)")
            if not rsi_condition_min:
                reasons.append(f"RSI too low (need >{rsi_buy_min}, have {rsi:.1f})")
            if not rsi_condition_max:
                reasons.append(f"RSI too high/overbought (need <{rsi_buy_max}, have {rsi:.1f})")
            
            passed = ema_condition and rsi_condition
            
            if return_details:
                return {
                    'passed': passed,
                    'reasons': reasons,
                    'rsi': rsi,
                    'ema5': ema5,
                    'ema20': ema20,
                    'ema_gap_pct': ((ema5 - ema20) / ema20 * 100) if ema20 > 0 else Decimal('0'),
                    'rsi_condition': rsi_condition,
                    'rsi_condition_min': rsi_condition_min,
                    'rsi_condition_max': rsi_condition_max,
                    'ema_condition': ema_condition
                }
            return passed
            
        elif signal_type == "SELL":
            # ✅ IMPROVED: SELL: EMA5 < EMA20 * (1 - gap) AND RSI > rsi_sell_min AND RSI < rsi_sell_max
            ema_condition = ema5 < ema20 * (Decimal('1') - ema_gap)
            rsi_sell_min = getattr(self, 'rsi_sell_min', Decimal('30'))
            rsi_condition_min = rsi > rsi_sell_min  # ✅ NEW: Avoid oversold entries
            rsi_condition_max = rsi < rsi_sell_max
            rsi_condition = rsi_condition_min and rsi_condition_max
            
            if not ema_condition:
                ema_gap_actual = ((ema5 - ema20) / ema20 * 100) if ema20 > 0 else Decimal('0')
                reasons.append(f"EMA gap too small (need <{-ema_gap*100:.2f}%, have {ema_gap_actual:.2f}%)")
            if not rsi_condition_min:
                reasons.append(f"RSI too low/oversold (need >{rsi_sell_min}, have {rsi:.1f})")
            if not rsi_condition_max:
                reasons.append(f"RSI too high (need <{rsi_sell_max}, have {rsi:.1f})")
            
            passed = ema_condition and rsi_condition
            
            if return_details:
                return {
                    'passed': passed,
                    'reasons': reasons,
                    'rsi': rsi,
                    'ema5': ema5,
                    'ema20': ema20,
                    'ema_gap_pct': ((ema5 - ema20) / ema20 * 100) if ema20 > 0 else Decimal('0'),
                    'rsi_condition': rsi_condition,
                    'rsi_condition_min': rsi_condition_min,
                    'rsi_condition_max': rsi_condition_max,
                    'ema_condition': ema_condition
                }
            return passed
        
        if return_details:
            return {'passed': False, 'reasons': ['Invalid signal type: {}'.format(signal_type)]}
        return False
    
    def _check_trend_reversal_exit(self, entry: dict, futures_ltp: Decimal, position_side: str) -> bool:
        """
        ✅ ENHANCED: Check if momentum is weakening (for trend-following exit)
        
        Logic (MORE SENSITIVE - exits on RSI alone):
        - For BUY_CE (CALL): Exit if RSI < 50 (momentum weakening, catches reversals faster)
        - For BUY_PE (PUT): Exit if RSI > 50 (momentum weakening, catches reversals faster)
        
        Why RSI alone?
        - RSI is a leading indicator (reacts faster than EMA)
        - EMA is a lagging indicator (reacts slower)
        - Exiting on RSI alone catches momentum loss earlier
        - Would have exited Trade #43 at ₹446-447 instead of ₹442.90
        
        Args:
            entry: Current position dict
            futures_ltp: Current futures LTP
            position_side: "BUY_CE" or "BUY_PE"
        
        Returns:
            bool: True if momentum weakening detected, False otherwise
        """
        if not self.price_history or len(self.price_history) < 20:
            return False
        
        from trading.services.momentum import compute_rsi
        
        rsi = compute_rsi(self.price_history, 14)
        
        if rsi is None:
            return False
        
        # Check momentum weakening based on position side
        if "CE" in position_side:  # BUY CALL - exit if momentum weakening
            # Exit if RSI < 50 (momentum weakening, catches reversals faster)
            if rsi < Decimal('50'):
                logger.info(
                    f"🔄 Momentum weakening for CALL: RSI ({rsi:.1f}) < 50 "
                    f"(exiting early to protect profit)"
                )
                return True
        else:  # BUY PUT - exit if momentum weakening
            # Exit if RSI > 50 (momentum weakening, catches reversals faster)
            if rsi > Decimal('50'):
                logger.info(
                    f"🔄 Momentum weakening for PUT: RSI ({rsi:.1f}) > 50 "
                    f"(exiting early to protect profit)"
                )
                return True
        
        return False
    
    def _check_time_based_exit(self, entry: dict, current_time, pnl_pct: Decimal) -> bool:
        """
        ✅ NEW: Check if trade should exit based on time and profit threshold
        
        Logic:
        - If trade is older than TIME_EXIT_MINUTES (12 minutes)
        - AND profit < TIME_EXIT_PROFIT_THRESHOLD (0.3%)
        - Then exit (prevent holding losing trades too long)
        
        Args:
            entry: Current position dict with 'entry_time'
            current_time: Current datetime
            pnl_pct: Current profit percentage
        
        Returns:
            bool: True if should exit, False otherwise
        """
        if not entry or 'entry_time' not in entry:
            return False
        
        entry_time = entry.get('entry_time')
        if not entry_time:
            return False
        
        # Calculate trade age in minutes
        time_diff = current_time - entry_time
        trade_age_minutes = time_diff.total_seconds() / 60
        
        # Check if trade is older than threshold
        if trade_age_minutes >= self.time_exit_minutes:
            # Check if profit is below threshold
            if pnl_pct < self.time_exit_profit_threshold:
                return True
        
        return False
    
    def _handle_breakout(self, breakout_signal, futures_ltp, engine, strategy):
        """Handle breakout: Select option and enter trade
        
        Args:
            breakout_signal: 'BUY' or 'SELL'
            futures_ltp: Current futures LTP
            engine: Strategy engine instance
            strategy: Strategy model instance
        """
        try:
            # Get futures symbol to match option expiry
            futures_symbol = getattr(engine, 'futures_symbol', None)
            if not futures_symbol:
                # Try to get from data service or engine attributes
                if hasattr(engine, 'data_service') and hasattr(engine.data_service, 'futures_symbol'):
                    futures_symbol = engine.data_service.futures_symbol
            
            # Select option symbol based on breakout signal
            # BUY breakout → Buy ATM CALL (CE)
            # SELL breakout → Buy ATM PUT (PE)
            # Use yesterday's closing price for ATM strike selection
            strike_reference_price = futures_ltp  # Default to current futures LTP
            if strategy.yesterday_closing_price:
                strike_reference_price = Decimal(str(strategy.yesterday_closing_price))
                self.stdout.write(self.style.SUCCESS(
                    f"📊 Using yesterday's closing price for ATM strike: ₹{strike_reference_price:,.2f}"
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f"⚠️  Yesterday's closing price not set in strategy. Using current futures LTP: ₹{strike_reference_price:,.2f}"
                ))
            
            option_symbol, strike, expiry_date = self.strike_selector.select_strike(
                spot_price=strike_reference_price,  # Use yesterday's closing for ATM strike
                signal_type=breakout_signal,
                strong_momentum=False,  # Use ATM for simplicity
                futures_symbol=futures_symbol  # Pass futures symbol to match expiry
            )
            
            self.stdout.write(self.style.SUCCESS(
                f"\n🎯 Breakout detected: {breakout_signal} | Futures LTP: ₹{futures_ltp:,.2f}"
            ))
            self.stdout.write(self.style.SUCCESS(
                f"📊 Selected Option: {option_symbol} | Strike: {strike} | Expiry: {expiry_date}"
            ))
            
            # Subscribe to option symbol for LTP
            if hasattr(engine, 'data_service') and hasattr(engine.data_service, 'subscribe'):
                try:
                    engine.data_service.subscribe(option_symbol)
                    self.stdout.write(self.style.SUCCESS(f"🔔 Subscribed to {option_symbol}"))
                    time.sleep(1)  # Wait for first tick
                except Exception as e:
                    logger.warning(f"Failed to subscribe to {option_symbol}: {e}")
                    self.stdout.write(self.style.WARNING(f"⚠️  Subscription warning for {option_symbol}: {e}"))
            
            # Wait a moment for first LTP
            time.sleep(1)
            
            # Get option LTP
            option_ltp = self._get_option_ltp(option_symbol, engine)
            
            # Validate LTP - reject if it's the fallback price (₹100.00) and symbol wasn't found
            if option_ltp and option_ltp == Decimal('100.00'):
                # Check if symbol was actually found in data service
                symbol_found = False
                if hasattr(engine, 'data_service'):
                    if hasattr(engine.data_service, 'ltp_cache') and option_symbol in engine.data_service.ltp_cache:
                        symbol_found = True
                    elif hasattr(engine.data_service, 'get_latest_ltp'):
                        test_ltp = engine.data_service.get_latest_ltp(option_symbol)
                        if test_ltp and test_ltp != Decimal('100.00'):
                            symbol_found = True
                            option_ltp = test_ltp
                
                if not symbol_found:
                    self.stdout.write(self.style.ERROR(
                        f"❌ Option symbol {option_symbol} not found in market. Using fallback price ₹100.00 is not valid for trading. Skipping trade."
                    ))
                    self.stdout.write(self.style.WARNING(
                        f"💡 Possible reasons: Expiry date {expiry_date} may not be available, or strike {strike} may not exist."
                    ))
                    return
            
            if option_ltp:
                # Determine position side
                position_side = "BUY_CE" if breakout_signal == "BUY" else "BUY_PE"
                
                # Simulate entry
                self._simulate_entry(position_side, option_symbol, option_ltp, futures_ltp, strike, expiry_date, engine, strategy)
            else:
                self.stdout.write(self.style.WARNING(
                    f"⚠️  Option LTP not available for {option_symbol}, retrying..."
                ))
                # Retry once
                time.sleep(2)
                option_ltp = self._get_option_ltp(option_symbol, engine)
                
                # Validate again after retry
                if option_ltp and option_ltp == Decimal('100.00'):
                    symbol_found = False
                    if hasattr(engine, 'data_service'):
                        if hasattr(engine.data_service, 'ltp_cache') and option_symbol in engine.data_service.ltp_cache:
                            symbol_found = True
                        elif hasattr(engine.data_service, 'get_latest_ltp'):
                            test_ltp = engine.data_service.get_latest_ltp(option_symbol)
                            if test_ltp and test_ltp != Decimal('100.00'):
                                symbol_found = True
                                option_ltp = test_ltp
                    
                    if not symbol_found:
                        self.stdout.write(self.style.ERROR(
                            f"❌ Option symbol {option_symbol} not found after retry. Skipping trade."
                        ))
                        return
                
                if option_ltp:
                    position_side = "BUY_CE" if breakout_signal == "BUY" else "BUY_PE"
                    self._simulate_entry(position_side, option_symbol, option_ltp, futures_ltp, strike, expiry_date, engine, strategy)
                else:
                    self.stdout.write(self.style.ERROR(
                        f"❌ Could not get option LTP for {option_symbol}, skipping trade"
                    ))
        except Exception as e:
            logger.error(f"Error handling breakout: {e}")
            self.stdout.write(self.style.ERROR(f"❌ Error handling breakout: {e}"))
    
    def _handle_super_trend_entry(self, signal_type, futures_ltp, engine, strategy, super_trend):
        """
        Handle Super Trend entry signal
        
        Args:
            signal_type: 'BUY' or 'SELL'
            futures_ltp: Current futures LTP
            engine: Strategy engine instance
            strategy: Strategy model instance
            super_trend: Super Trend dict
        """
        try:
            # Check if already in trade
            if self.current_position:
                logger.info(f"Already in trade, skipping Super Trend {signal_type} signal")
                return
            
            # Check cooldown period
            if self.last_trade_exit_time:
                time_since_exit = get_ist_now() - self.last_trade_exit_time
                cooldown_seconds = self.trade_cooldown_minutes * 60
                if time_since_exit.total_seconds() < cooldown_seconds:
                    remaining_seconds = int(cooldown_seconds - time_since_exit.total_seconds())
                    logger.info(f"Cooldown active: {remaining_seconds}s remaining, skipping Super Trend {signal_type} signal")
                    return
            
            # Check trading window
            current_time = get_ist_now().time()
            is_in_trading_window = (current_time >= self.trade_start_time and 
                                   current_time <= self.trade_end_time)
            
            if not is_in_trading_window:
                logger.info(f"Outside trading window, skipping Super Trend {signal_type} signal")
                return
            
            # Get futures symbol
            futures_symbol = getattr(engine, 'futures_symbol', None)
            if not futures_symbol:
                if hasattr(engine, 'data_service') and hasattr(engine.data_service, 'futures_symbol'):
                    futures_symbol = engine.data_service.futures_symbol
            
            # Select option symbol
            strike_reference_price = futures_ltp
            if strategy.yesterday_closing_price:
                strike_reference_price = Decimal(str(strategy.yesterday_closing_price))
            
            option_symbol, strike, expiry_date = self.strike_selector.select_strike(
                spot_price=strike_reference_price,
                signal_type=signal_type,
                strong_momentum=False,
                futures_symbol=futures_symbol
            )
            
            self.stdout.write(self.style.SUCCESS(
                f"\n🎯 Super Trend Signal: {signal_type} | Futures LTP: ₹{futures_ltp:,.2f}"
            ))
            self.stdout.write(self.style.SUCCESS(
                f"📊 Super Trend: ₹{super_trend['value']:.2f} | Color: {super_trend['color']}"
            ))
            self.stdout.write(self.style.SUCCESS(
                f"📊 Selected Option: {option_symbol} | Strike: {strike} | Expiry: {expiry_date}"
            ))
            
            # Subscribe to option symbol
            if hasattr(engine, 'data_service') and hasattr(engine.data_service, 'subscribe'):
                try:
                    engine.data_service.subscribe(option_symbol)
                    self.stdout.write(self.style.SUCCESS(f"🔔 Subscribed to {option_symbol}"))
                    time.sleep(1)
                except Exception as e:
                    logger.warning(f"Failed to subscribe to {option_symbol}: {e}")
            
            time.sleep(1)
            
            # Get option LTP
            option_ltp = self._get_option_ltp(option_symbol, engine)
            
            # Validate LTP
            if option_ltp and option_ltp == Decimal('100.00'):
                symbol_found = False
                if hasattr(engine, 'data_service'):
                    if hasattr(engine.data_service, 'ltp_cache') and option_symbol in engine.data_service.ltp_cache:
                        symbol_found = True
                    elif hasattr(engine.data_service, 'get_latest_ltp'):
                        test_ltp = engine.data_service.get_latest_ltp(option_symbol)
                        if test_ltp and test_ltp != Decimal('100.00'):
                            symbol_found = True
                            option_ltp = test_ltp
                
                if not symbol_found:
                    self.stdout.write(self.style.ERROR(
                        f"❌ Option symbol {option_symbol} not found. Skipping trade."
                    ))
                    return
            
            if option_ltp:
                position_side = "BUY_CE" if signal_type == "BUY" else "BUY_PE"
                self._simulate_entry(position_side, option_symbol, option_ltp, futures_ltp, strike, expiry_date, engine, strategy)
            else:
                self.stdout.write(self.style.WARNING(
                    f"⚠️  Option LTP not available for {option_symbol}, skipping trade"
                ))
        except Exception as e:
            logger.error(f"Error handling Super Trend entry: {e}")
            self.stdout.write(self.style.ERROR(f"❌ Error handling Super Trend entry: {e}"))
    
    def _get_option_ltp(self, option_symbol, engine):
        """Get option LTP from WebSocket or data service"""
        option_ltp = None
        
        # Try from data service LTP cache
        if hasattr(engine, 'data_service'):
            if hasattr(engine.data_service, 'ltp_cache') and option_symbol in engine.data_service.ltp_cache:
                option_ltp = engine.data_service.ltp_cache[option_symbol]
                self.option_ltp_cache[option_symbol] = option_ltp
            elif hasattr(engine.data_service, 'get_latest_ltp'):
                option_ltp = engine.data_service.get_latest_ltp(option_symbol)
                if option_ltp:
                    self.option_ltp_cache[option_symbol] = option_ltp
        
        # Fallback to execution adapter
        if option_ltp is None and hasattr(engine, 'execution_adapter'):
            option_ltp = engine.execution_adapter.get_ltp(option_symbol, data_service=engine.data_service)
            if option_ltp:
                self.option_ltp_cache[option_symbol] = option_ltp
        
        # Fallback to cache
        if option_ltp is None and option_symbol in self.option_ltp_cache:
            option_ltp = self.option_ltp_cache[option_symbol]
        
        return Decimal(str(option_ltp)) if option_ltp else None
    
    def _simulate_entry(self, position_side, option_symbol, option_ltp, futures_ltp, strike, expiry_date, engine, strategy):
        """Simulate option trade entry"""
        entry_time = get_ist_now()
        
        # Determine display side and mode
        display_side = "BUY CALL" if "CE" in position_side else "BUY PUT"
        mode = "DRY-RUN" if os.getenv('DRY_RUN', 'true').lower() == 'true' else "LIVE"
        
        # Calculate momentum indicators for entry display
        momentum_info = ""
        if len(self.price_history) >= 20:
            from trading.services.momentum import compute_ema, compute_rsi
            ema5 = compute_ema(self.price_history, 5)
            ema20 = compute_ema(self.price_history, 20)
            rsi = compute_rsi(self.price_history, 14)
            
            if ema5 and ema20 and rsi:
                ema_gap_pct = ((ema5 - ema20) / ema20 * 100) if ema20 > 0 else Decimal('0')
                momentum_info = f" | RSI: {rsi:.1f} | EMA5: ₹{ema5:,.2f} | EMA20: ₹{ema20:,.2f} | Gap: {ema_gap_pct:.2f}%"
        
        # Use fixed number of lots from strategy configuration (default: 1 lot)
        num_lots = strategy.num_lots if hasattr(strategy, 'num_lots') and strategy.num_lots else 1
        total_units = num_lots * self.lot_size
        total_investment = option_ltp * Decimal(str(total_units))
        
        # Store lot_size in position for P&L calculation
        lot_size = self.lot_size
        
        # Calculate target and stoploss prices
        target_price = option_ltp * (Decimal('1') + Decimal(str(self.target_pct)))
        stoploss_price = option_ltp * (Decimal('1') - Decimal(str(self.stoploss_pct)))
        
        self.stdout.write(self.style.SUCCESS(
            f"\n{'='*80}"
        ))
        self.stdout.write(self.style.SUCCESS(
            f"🚀 [{mode}] ENTRY {display_side} | {entry_time.strftime('%H:%M:%S')}"
        ))
        self.stdout.write(self.style.SUCCESS(
            f"   Symbol: {option_symbol} | Strike: {strike} | Expiry: {expiry_date}"
        ))
        self.stdout.write(self.style.SUCCESS(
            f"   Entry Price: ₹{option_ltp:,.2f} | Futures LTP: ₹{futures_ltp:,.2f}"
        ))
        self.stdout.write(self.style.SUCCESS(
            f"   Position: {num_lots} lot(s) × {self.lot_size} = {total_units} units | Investment: ₹{total_investment:,.2f}"
        ))
        self.stdout.write(self.style.SUCCESS(
            f"   Target: ₹{target_price:,.2f} (+{self.target_pct*100:.2f}%) | Stoploss: ₹{stoploss_price:,.2f} (-{self.stoploss_pct*100:.2f}%)"
        ))
        if momentum_info:
            self.stdout.write(self.style.SUCCESS(
                f"   Momentum: {momentum_info.strip(' | ')}"
            ))
        if self.range_high and self.range_low:
            range_pct = ((self.range_high - self.range_low) / self.range_low * 100) if self.range_low > 0 else Decimal('0')
            range_width = self.range_high - self.range_low
            breakout_pct = getattr(self, 'breakout_pct', Decimal('0.001')) * 100
            self.stdout.write(self.style.SUCCESS(
                f"   Range: ₹{self.range_low:,.2f} - ₹{self.range_high:,.2f} ({range_pct:.2f}%) | "
                f"Dynamic Breakout %: {breakout_pct:.2f}% | Range width: {range_width:.0f} pts"
            ))
        self.stdout.write(self.style.SUCCESS(
            f"{'='*80}\n"
        ))
        
        # Log to CSV
        self._log_trade_entry(position_side, option_symbol, option_ltp, futures_ltp, strike, entry_time)
        
        # Save to TradeLog model FIRST (pass total_units to store as entry_quantity)
        # This creates the trade_log and sets self.trade_log_id
        self._save_trade_log_entry(position_side, option_symbol, option_ltp, futures_ltp, strike, expiry_date, entry_time, strategy, total_units)
        
        # NOW create current_position with the CORRECT trade_log_id (after it's been set)
        self.current_position = {
            "side": position_side,
            "symbol": option_symbol,
            "entry_price": float(option_ltp),
            "futures_ltp": float(futures_ltp),
            "strike": strike,
            "expiry_date": expiry_date,
            "time": entry_time,
            "entry_time": entry_time,
            "trade_log_id": getattr(self, 'trade_log_id', None),  # This will now have the correct ID
            "total_units": total_units,  # Store total units for P&L calculation (num_lots * lot_size)
            "num_lots": num_lots,  # Store number of lots
            "lot_size": lot_size  # Store lot_size for reference
        }
        
        # Reset trailing stoploss to initial value on new entry
        self.current_stoploss_pct = self.stoploss_pct
        # Reset consecutive candle counters on new entry
        self.consecutive_red_candles = 0
        self.consecutive_green_candles = 0
        
        # Set flag to skip exit checks in the same cycle as entry
        self.position_just_entered = True
    
    def _restore_open_position(self, strategy):
        """Restore open position from database if strategy was restarted"""
        try:
            # Find the most recent open trade for this strategy
            open_trade = TradeLog.objects.filter(
                strategy=strategy,
                is_open=True
            ).order_by('-entry_time').first()
            
            if open_trade:
                # Calculate total units
                num_lots = getattr(strategy, 'num_lots', 1)
                lot_size = open_trade.entry_quantity or self.lot_size
                total_units = lot_size * num_lots
                
                # Restore position from database
                self.current_position = {
                    "side": open_trade.entry_side,
                    "symbol": open_trade.entry_symbol,
                    "entry_price": float(open_trade.entry_price),
                    "strike": open_trade.strike,
                    "expiry_date": open_trade.expiry_date,
                    "total_units": total_units,
                    "lot_size": lot_size,
                    "num_lots": num_lots,
                    "entry_time": open_trade.entry_time,
                    "trade_log_id": open_trade.id
                }
                self.position_just_entered = False  # Don't skip exit checks for restored position
                
                self.stdout.write(self.style.SUCCESS(
                    f"🔄 Restored open position: {open_trade.entry_symbol} @ ₹{open_trade.entry_price} "
                    f"(Entry: {open_trade.entry_time.strftime('%H:%M:%S')})"
                ))
                logger.info(f"Restored open position: {open_trade.entry_symbol} @ ₹{open_trade.entry_price}")
            else:
                self.current_position = None
        except Exception as e:
            logger.error(f"Error restoring open position: {e}")
            self.current_position = None
    
    def _calculate_pnl(self, entry_price: Decimal, exit_price: Decimal, side: str, lot_size: int = 35) -> Decimal:
        """
        Unified P&L calculation function (same as backtest).
        
        Args:
            entry_price: Entry price per unit
            exit_price: Exit price per unit
            side: 'BUY_CE' or 'BUY_PE' (options are always bought)
            lot_size: Lot size (default: 35 for BankNifty)
        
        Returns:
            Decimal: Total P&L in ₹ (rounded to 2 decimal places)
        """
        if side == "BUY_CE" or side == "BUY":
            # CALL: profit when price goes up
            pnl = (exit_price - entry_price) * lot_size
        else:
            # PUT: profit when price goes down (but we still buy, so same formula)
            pnl = (exit_price - entry_price) * lot_size
        return round(pnl, 2)
    
    def _simulate_exit(self, option_ltp, reason, engine):
        """Simulate option trade exit"""
        if not self.current_position:
            return
        
        entry = self.current_position
        entry_price = Decimal(str(entry["entry_price"]))
        exit_price = Decimal(str(option_ltp))
        option_symbol = entry.get("symbol", "UNKNOWN")
        position_side = entry.get("side", "BUY_CE")
        
        # Get total_units from position (num_lots * lot_size)
        total_units = entry.get("total_units", self.lot_size)
        if not total_units or total_units <= 0:
            # Fallback: use num_lots and lot_size if total_units is missing
            num_lots = entry.get("num_lots", 1)
            lot_size = entry.get("lot_size", self.lot_size)
            total_units = num_lots * lot_size
        
        # Ensure total_units is valid
        if total_units <= 0:
            logger.warning(f"Invalid total_units: {total_units}, using default lot_size: {self.lot_size}")
            total_units = self.lot_size
        
        # Calculate P&L using unified function (use total_units from position)
        pnl_value = self._calculate_pnl(entry_price, exit_price, position_side, int(total_units))
        
        # Get lot_size for display
        lot_size = entry.get('lot_size', self.lot_size)
        
        exit_time = get_ist_now()
        
        # Get current futures LTP for reference
        current_futures_ltp = self._get_latest_ltp(engine)
        
        # Determine display side
        display_side = "CALL" if "CE" in entry.get("side", "") else "PUT"
        
        # Determine mode (LIVE or DRY-RUN)
        mode = "LIVE" if os.getenv('DRY_RUN', 'true').lower() != 'true' else "DRY-RUN"
        
        # Calculate stoploss price for display (if STOPLOSS reason)
        stoploss_info = ""
        if reason == "STOPLOSS":
            stoploss_pct = Decimal(str(self.stoploss_pct))
            stoploss_price = entry_price * (Decimal('1') - stoploss_pct)
            slippage = exit_price - stoploss_price
            slippage_pct = (slippage / stoploss_price * 100) if stoploss_price > 0 else Decimal('0')
            stoploss_info = f" | Stoploss Price: ₹{stoploss_price:,.2f} | Slippage: ₹{slippage:,.2f} ({slippage_pct:+.2f}%)"
        
        self.stdout.write(self.style.SUCCESS(
            f"💰 [{mode}] EXIT {display_side} @ ₹{exit_price:,.2f} | P&L: ₹{pnl_value:,.2f} | Lot: {lot_size} | Reason: {reason}{stoploss_info}"
        ))
        if current_futures_ltp:
            self.stdout.write(self.style.SUCCESS(
                f"   Symbol: {option_symbol} | Futures LTP: ₹{current_futures_ltp:,.2f} | Strike: {entry.get('strike', 'N/A')} | Entry: ₹{entry_price:,.2f}\n"
            ))
        
        # Log to CSV
        self._log_trade_exit(entry, exit_price, pnl_value, reason, exit_time)
        
        # Update TradeLog model
        self._update_trade_log_exit(entry, exit_price, pnl_value, reason, exit_time, engine)
        
        self.current_position = None
        self.position_just_entered = False  # Reset flag when position is closed
        
        # Record exit time for cooldown period
        self.last_trade_exit_time = exit_time
        
        # Reset range for next trade opportunity
        self.range_established = False
        self.range_high = None
        self.range_low = None
        self.price_samples = []  # Reset price samples for new range detection
        self.stdout.write(self.style.SUCCESS(
            f"🔄 Range reset - Cooldown period: {self.trade_cooldown_minutes} minutes before next trade allowed"
        ))
    
    def _log_trade_entry(self, position_side, option_symbol, option_ltp, futures_ltp, strike, entry_time):
        """Log option trade entry to CSV"""
        try:
            # Use settings.BASE_DIR if available, otherwise calculate from file path
            try:
                BASE_DIR = settings.BASE_DIR
            except:
                from pathlib import Path
                BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
            
            log_dir = os.path.join(BASE_DIR, 'trade_logs')
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, 'trade_log.csv')
            
            # Write header if file doesn't exist
            if not os.path.exists(log_file):
                with open(log_file, 'w') as f:
                    f.write("timestamp,mode,side,symbol,strike,entry_price,exit_price,pnl,lot_size,reason,breakout_pct,range_width\n")
            
            # Determine mode
            mode = "LIVE" if os.getenv('DRY_RUN', 'true').lower() != 'true' else "DRY-RUN"
            
            # Get breakout_pct and range_width if available
            breakout_pct = getattr(self, 'breakout_pct', Decimal('0.001')) * 100  # Convert to percentage
            range_width = getattr(self, 'range_width', Decimal('0'))
            
            with open(log_file, 'a') as f:
                f.write(
                    f"{entry_time.strftime('%Y-%m-%d %H:%M:%S')},"
                    f"{mode},{position_side},{option_symbol},{strike},"
                    f"{float(option_ltp):.2f},,{self.lot_size},ENTRY,{breakout_pct:.4f},{range_width:.0f}\n"
                )
        except Exception as e:
            logger.warning(f"Error logging trade entry: {e}")
    
    def _log_trade_exit(self, entry, exit_price, pnl, reason, exit_time):
        """Log option trade exit to CSV"""
        try:
            # Use settings.BASE_DIR if available, otherwise calculate from file path
            try:
                BASE_DIR = settings.BASE_DIR
            except:
                from pathlib import Path
                BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
            
            log_dir = os.path.join(BASE_DIR, 'trade_logs')
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, 'trade_log.csv')
            
            # Determine mode
            mode = "LIVE" if os.getenv('DRY_RUN', 'true').lower() != 'true' else "DRY-RUN"
            
            # Get current futures LTP
            current_futures_ltp = entry.get('futures_ltp', 0)
            
            # Get breakout_pct and range_width if available
            breakout_pct = getattr(self, 'breakout_pct', Decimal('0.001')) * 100  # Convert to percentage
            range_width = getattr(self, 'range_width', Decimal('0'))
            
            # Get lot_size from entry or use default
            lot_size = entry.get('lot_size', self.lot_size)
            
            with open(log_file, 'a') as f:
                f.write(
                    f"{exit_time.strftime('%Y-%m-%d %H:%M:%S')},"
                    f"{mode},{entry['side']},{entry.get('symbol', 'UNKNOWN')},{entry.get('strike', 'N/A')},"
                    f"{entry['entry_price']:.2f},{float(exit_price):.2f},{pnl:.2f},"
                    f"{lot_size},{reason},{breakout_pct:.4f},{range_width:.0f}\n"
                )
        except Exception as e:
            logger.warning(f"Error logging trade exit: {e}")
    
    def _save_trade_log_entry(self, position_side, option_symbol, option_ltp, futures_ltp, strike, expiry_date, entry_time, strategy, total_units=None):
        """Save trade entry to TradeLog model"""
        try:
            # Determine if this is a dry-run
            dry_run = os.getenv('DRY_RUN', 'true').lower() == 'true'
            
            # Use total_units if provided, otherwise fallback to lot_size
            entry_quantity = total_units if total_units else self.lot_size
            
            # Create TradeLog entry
            trade_log = TradeLog.objects.create(
                strategy=strategy,
                entry_time=entry_time,
                entry_price=option_ltp,  # Store entry price
                entry_symbol=option_symbol,
                entry_side=position_side,
                entry_quantity=entry_quantity,  # Store total_units (num_lots * lot_size)
                strike=strike,
                expiry_date=expiry_date,
                futures_ltp_entry=futures_ltp,
                is_open=True,
                dry_run=dry_run
            )
            
            # Store trade_log ID in current_position for later update
            if not hasattr(self, 'trade_log_id'):
                self.trade_log_id = None
            self.trade_log_id = trade_log.id
            
            logger.info(f"✅ TradeLog entry created: ID={trade_log.id}, Symbol={option_symbol}")
        except Exception as e:
            logger.error(f"Error saving trade log entry: {e}")
    
    def _update_trade_log_exit(self, entry, exit_price, pnl_value, reason, exit_time, engine):
        """Update TradeLog with exit details"""
        try:
            # Get trade_log_id from entry or use stored ID
            trade_log_id = entry.get('trade_log_id') or getattr(self, 'trade_log_id', None)
            
            if not trade_log_id:
                # Try to find by entry_symbol and entry_time
                option_symbol = entry.get('symbol')
                entry_time = entry.get('entry_time')
                if option_symbol and entry_time:
                    trade_log = TradeLog.objects.filter(
                        entry_symbol=option_symbol,
                        entry_time=entry_time,
                        is_open=True
                    ).order_by('-entry_time').first()
                    if trade_log:
                        trade_log_id = trade_log.id
                    else:
                        logger.warning(f"Could not find TradeLog for exit: {option_symbol} @ {entry_time}")
                        return
                else:
                    logger.warning("Could not update TradeLog: missing trade_log_id or entry details")
                    return
            
            # Get current futures LTP
            current_futures_ltp = self._get_latest_ltp(engine)
            
            # Map exit reason
            exit_reason_map = {
                'TARGET': 'TARGET',
                'STOPLOSS': 'STOPLOSS',
                'TIME': 'TIME',
                'MARKET_CLOSE': 'MARKET_CLOSE',
                'MANUAL': 'MANUAL',
                'TRAILING': 'TRAILING'
            }
            mapped_reason = exit_reason_map.get(reason, 'MANUAL')
            
            # Update TradeLog
            trade_log = TradeLog.objects.get(id=trade_log_id)
            
            # Validate that the trade_log matches the entry symbol (safety check)
            option_symbol = entry.get('symbol')
            if option_symbol and trade_log.entry_symbol != option_symbol:
                logger.error(
                    f"⚠️ TradeLog ID {trade_log_id} symbol mismatch! "
                    f"Expected: {option_symbol}, Found: {trade_log.entry_symbol}. "
                    f"Trying to find correct trade..."
                )
                # Try to find the correct trade by symbol and entry_time
                correct_trade = TradeLog.objects.filter(
                    entry_symbol=option_symbol,
                    entry_time=entry.get('entry_time'),
                    is_open=True
                ).order_by('-entry_time').first()
                if correct_trade:
                    trade_log = correct_trade
                    logger.info(f"✅ Found correct trade: ID={correct_trade.id}")
                else:
                    logger.error(f"❌ Could not find correct trade for {option_symbol}")
                    return
            
            # Use database entry_price for accurate pnl_points calculation
            db_entry_price = Decimal(str(trade_log.entry_price))
            exit_price_decimal = Decimal(str(exit_price))
            pnl_points = exit_price_decimal - db_entry_price
            
            # Use database entry_quantity for P&L calculation (for consistency)
            # Recalculate pnl_value using database entry_quantity to ensure accuracy
            db_entry_quantity = trade_log.entry_quantity or self.lot_size
            recalculated_pnl_value = pnl_points * db_entry_quantity
            
            trade_log.exit_time = exit_time
            trade_log.exit_price = exit_price_decimal  # Update exit price
            trade_log.exit_reason = mapped_reason
            trade_log.pnl_points = pnl_points
            trade_log.pnl_value = recalculated_pnl_value  # Use recalculated P&L for consistency
            trade_log.futures_ltp_exit = current_futures_ltp if current_futures_ltp else None
            trade_log.is_open = False
            trade_log.save()
            
            logger.info(f"✅ TradeLog exit updated: ID={trade_log_id}, P&L=₹{recalculated_pnl_value:,.2f}, Reason={mapped_reason}")
        except TradeLog.DoesNotExist:
            logger.warning(f"TradeLog ID {trade_log_id} not found for exit update")
        except Exception as e:
            logger.error(f"Error updating trade log exit: {e}")


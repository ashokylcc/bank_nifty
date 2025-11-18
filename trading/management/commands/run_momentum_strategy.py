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
        TARGET_PCT = Decimal('1.5') / 100        # Target: +1.5%
        STOPLOSS_PCT = Decimal('0.7') / 100       # Stoploss: -0.7%
        TRAILING_TRIGGER_PCT = Decimal('0.5') / 100  # Trailing SL triggers after +0.5%
        LOT_SIZE = 35                             # ✅ BankNifty lot size (fixed)
        SQUARE_OFF_TIME = dt_time(15, 30)         # Auto exit at 3:30 PM
        TRADE_START_TIME = dt_time(9, 30)         # Trading window start (9:30 AM)
        TRADE_END_TIME = dt_time(15, 30)          # Trading window end (3:30 PM - market close)
        
        # Optimized Entry Filters (very lenient to allow breakouts)
        RSI_BUY_MIN = Decimal('55')              # Lenient: 55 (allows more BUY signals)
        RSI_SELL_MAX = Decimal('50')             # Lenient: 50 (allows more SELL signals)
        EMA_GAP_REQUIRED = Decimal('0.0001')     # Very lenient: 0.01% gap (allows breakouts when price action is clear, even if EMAs lag)
        
        # Simplified momentum breakout parameters
        self.capital = float(strategy.capital)
        self.lot_size = LOT_SIZE
        self.stoploss_pct = STOPLOSS_PCT
        self.target_pct = TARGET_PCT
        self.trailing_trigger_pct = TRAILING_TRIGGER_PCT
        self.current_position = None
        self.current_stoploss_pct = STOPLOSS_PCT  # Dynamic stoploss (for trailing)
        self.position_just_entered = False  # Flag to skip exit checks in the same cycle as entry
        
        # Store optimized filter parameters as instance variables (so they can be used in _check_momentum_filters)
        self.rsi_buy_min = RSI_BUY_MIN
        self.rsi_sell_max = RSI_SELL_MAX
        self.ema_gap_required = EMA_GAP_REQUIRED
        self.trade_start_time = TRADE_START_TIME
        self.trade_end_time = TRADE_END_TIME
        self.price_samples = []  # Track last 3 prices for range detection (from futures)
        self.price_history = []  # Track price history for EMA/RSI calculations (keep last 50)
        self.range_high = None
        self.range_low = None
        self.range_established = False  # Flag to track if range has been established
        
        # Option trading setup
        from trading.services.strike_selector import StrikeSelector
        self.strike_selector = StrikeSelector()
        self.option_ltp_cache = {}  # Track option LTPs: {symbol: ltp}
        
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
                        
                        # Get latest Futures LTP from WebSocket (for momentum detection)
                        futures_ltp = self._get_latest_ltp(engine)
                        
                        if futures_ltp:
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
                            if self.range_established and not self.current_position:
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
                                            
                                            # Check exit conditions
                                            if pnl_pct >= Decimal(str(self.target_pct)):
                                                self._simulate_exit(option_ltp, "TARGET", engine)
                                            elif pnl_pct <= -current_stoploss:
                                                self._simulate_exit(option_ltp, "STOPLOSS", engine)
                                            # Time-based exit (square-off time) - only if we're past square-off time
                                            elif current_time_ist.time() >= strategy.square_off_time:
                                                self._simulate_exit(option_ltp, "TIME", engine)
                        
                        cycle_count += 1
                        
                        # Print status every cycle with momentum details
                        current_time_str = current_time_ist.strftime('%H:%M:%S')
                        status_parts = []
                        
                        if futures_ltp:
                            status_parts.append(f"Futures: ₹{futures_ltp:,.2f}")
                            
                            # Calculate and show momentum indicators if we have enough data
                            if len(self.price_history) >= 20:
                                from trading.services.momentum import compute_ema, compute_rsi
                                ema5 = compute_ema(self.price_history, 5)
                                ema20 = compute_ema(self.price_history, 20)
                                rsi = compute_rsi(self.price_history, 14)
                                
                                if ema5 and ema20 and rsi:
                                    ema_gap_pct = ((ema5 - ema20) / ema20 * 100) if ema20 > 0 else Decimal('0')
                                    status_parts.append(f"RSI: {rsi:.1f} | EMA5: ₹{ema5:,.2f} | EMA20: ₹{ema20:,.2f} | Gap: {ema_gap_pct:.2f}%")
                            
                            # Show range if established
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
        Update trailing stoploss dynamically based on profit
        
        For BUY CALL: if current_price > entry_price * 1.005, move stoploss to current_price * 0.995
        For BUY PUT: if current_price < entry_price * 0.995, move stoploss to current_price * 1.005
        
        Args:
            current_price: Current option LTP
            entry_price: Entry price
            position_side: "BUY_CE" or "BUY_PE"
        """
        trigger_multiplier = Decimal('1') + Decimal(str(self.trailing_trigger_pct))  # 1.005 for +0.5%
        trigger_multiplier_down = Decimal('1') - Decimal(str(self.trailing_trigger_pct))  # 0.995 for -0.5%
        
        if "CE" in position_side:  # BUY CALL
            # If current price is 0.5% above entry, activate trailing stoploss
            if current_price > entry_price * trigger_multiplier:
                # New stoploss: 0.5% below current price (protect 0.5% profit)
                new_stoploss_price = current_price * trigger_multiplier_down
                new_stoploss_pct = abs((new_stoploss_price - entry_price) / entry_price)
                
                # Only move stoploss up (less negative), never down
                if new_stoploss_pct < abs(self.current_stoploss_pct):
                    self.current_stoploss_pct = -new_stoploss_pct  # Negative because it's a loss threshold
                    logger.debug(f"📈 Trailing stoploss updated for CALL: {self.current_stoploss_pct*100:.2f}%")
        
        elif "PE" in position_side:  # BUY PUT
            # If current price is 0.5% below entry, activate trailing stoploss
            # Note: For PUT, profit when price goes DOWN, so we check if current < entry * 0.995
            if current_price < entry_price * trigger_multiplier_down:
                # New stoploss: 0.5% above current price (protect 0.5% profit)
                new_stoploss_price = current_price * trigger_multiplier  # 1.005
                new_stoploss_pct = abs((new_stoploss_price - entry_price) / entry_price)
                
                # Only move stoploss up (less negative), never down
                if new_stoploss_pct < abs(self.current_stoploss_pct):
                    self.current_stoploss_pct = -new_stoploss_pct  # Negative because it's a loss threshold
                    logger.debug(f"📉 Trailing stoploss updated for PUT: {self.current_stoploss_pct*100:.2f}%")
    
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
            # BUY: EMA5 > EMA20 * (1 + gap) AND RSI > rsi_buy_min
            ema_condition = ema5 > ema20 * (Decimal('1') + ema_gap)
            rsi_condition = rsi > rsi_buy_min
            
            if not ema_condition:
                ema_gap_actual = ((ema5 - ema20) / ema20 * 100) if ema20 > 0 else Decimal('0')
                reasons.append(f"EMA gap too small (need {ema_gap*100:.2f}%, have {ema_gap_actual:.2f}%)")
            if not rsi_condition:
                reasons.append(f"RSI too low (need >{rsi_buy_min}, have {rsi:.1f})")
            
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
                    'ema_condition': ema_condition
                }
            return passed
            
        elif signal_type == "SELL":
            # SELL: EMA5 < EMA20 * (1 - gap) AND RSI < rsi_sell_max
            ema_condition = ema5 < ema20 * (Decimal('1') - ema_gap)
            rsi_condition = rsi < rsi_sell_max
            
            if not ema_condition:
                ema_gap_actual = ((ema5 - ema20) / ema20 * 100) if ema20 > 0 else Decimal('0')
                reasons.append(f"EMA gap too small (need <{-ema_gap*100:.2f}%, have {ema_gap_actual:.2f}%)")
            if not rsi_condition:
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
                    'ema_condition': ema_condition
                }
            return passed
        
        if return_details:
            return {'passed': False, 'reasons': ['Invalid signal type: {}'.format(signal_type)]}
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
            option_symbol, strike, expiry_date = self.strike_selector.select_strike(
                spot_price=futures_ltp,
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
        
        # Calculate position size and risk
        risk_amount = Decimal(str(self.capital)) * Decimal(str(self.stoploss_pct))
        stoploss_per_unit = option_ltp * Decimal(str(self.stoploss_pct))
        risk_per_lot = stoploss_per_unit * Decimal(str(self.lot_size))
        num_lots = int(risk_amount / risk_per_lot) if risk_per_lot > 0 else 1
        num_lots = max(1, num_lots)
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
        
        self.current_position = {
            "side": position_side,
            "symbol": option_symbol,
            "entry_price": float(option_ltp),
            "futures_ltp": float(futures_ltp),
            "strike": strike,
            "expiry_date": expiry_date,
            "time": entry_time,
            "entry_time": entry_time,
            "trade_log_id": getattr(self, 'trade_log_id', None),  # Store for exit update
            "total_units": total_units,  # Store total units for P&L calculation
            "num_lots": num_lots  # Store number of lots
        }
        
        # Reset trailing stoploss to initial value on new entry
        self.current_stoploss_pct = self.stoploss_pct
        
        # Set flag to skip exit checks in the same cycle as entry
        self.position_just_entered = True
        
        # Log to CSV
        self._log_trade_entry(position_side, option_symbol, option_ltp, futures_ltp, strike, entry_time)
        
        # Save to TradeLog model
        self._save_trade_log_entry(position_side, option_symbol, option_ltp, futures_ltp, strike, expiry_date, entry_time, strategy)
    
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
        total_units = entry.get("total_units", self.lot_size)
        
        # Calculate P&L using unified function (use total_units from position)
        total_units = entry.get("total_units", self.lot_size)
        # Use total_units for P&L calculation (which is num_lots * lot_size)
        pnl_value = self._calculate_pnl(entry_price, exit_price, position_side, total_units)
        
        # Get lot_size for display
        lot_size = entry.get('lot_size', self.lot_size)
        
        exit_time = get_ist_now()
        
        # Get current futures LTP for reference
        current_futures_ltp = self._get_latest_ltp(engine)
        
        # Determine display side
        display_side = "CALL" if "CE" in entry.get("side", "") else "PUT"
        
        # Determine mode (LIVE or DRY-RUN)
        mode = "LIVE" if os.getenv('DRY_RUN', 'true').lower() != 'true' else "DRY-RUN"
        
        self.stdout.write(self.style.SUCCESS(
            f"💰 [{mode}] EXIT {display_side} @ ₹{exit_price:,.2f} | P&L: ₹{pnl_value:,.2f} | Lot: {lot_size} | Reason: {reason}"
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
        
        # Reset range for next trade opportunity
        self.range_established = False
        self.range_high = None
        self.range_low = None
        self.price_samples = []  # Reset price samples for new range detection
        self.stdout.write(self.style.SUCCESS("🔄 Range reset - ready for next trade opportunity"))
    
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
    
    def _save_trade_log_entry(self, position_side, option_symbol, option_ltp, futures_ltp, strike, expiry_date, entry_time, strategy):
        """Save trade entry to TradeLog model"""
        try:
            # Determine if this is a dry-run
            dry_run = os.getenv('DRY_RUN', 'true').lower() == 'true'
            
            # Create TradeLog entry
            trade_log = TradeLog.objects.create(
                strategy=strategy,
                entry_time=entry_time,
                entry_price=option_ltp,
                entry_symbol=option_symbol,
                entry_side=position_side,
                entry_quantity=self.lot_size,
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
            
            # Calculate P&L points
            entry_price = Decimal(str(entry["entry_price"]))
            exit_price_decimal = Decimal(str(exit_price))
            pnl_points = exit_price_decimal - entry_price
            
            # Update TradeLog
            trade_log = TradeLog.objects.get(id=trade_log_id)
            trade_log.exit_time = exit_time
            trade_log.exit_price = exit_price_decimal
            trade_log.exit_reason = mapped_reason
            trade_log.pnl_points = pnl_points
            trade_log.pnl_value = Decimal(str(pnl_value))
            trade_log.futures_ltp_exit = current_futures_ltp if current_futures_ltp else None
            trade_log.is_open = False
            trade_log.save()
            
            logger.info(f"✅ TradeLog exit updated: ID={trade_log_id}, P&L=₹{pnl_value:,.2f}, Reason={mapped_reason}")
        except TradeLog.DoesNotExist:
            logger.warning(f"TradeLog ID {trade_log_id} not found for exit update")
        except Exception as e:
            logger.error(f"Error updating trade log exit: {e}")


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
            
            if hasattr(engine.data_service, 'connect'):
                if engine.data_service.connect():
                    self.stdout.write(self.style.SUCCESS("✅ Connected to live data feed"))
                    
                    # Wait for WebSocket to be ready (same pattern as run_strategy.py)
                    self.stdout.write("🔍 Testing WebSocket connection...")
                    time.sleep(2)  # Wait for connection (like run_strategy.py)
                    
                    if engine.data_service._connected:
                        self.stdout.write(self.style.SUCCESS("✅ WebSocket connection established"))
                        
                        # Subscribe to BankNifty futures (using correct symbol format)
                        if hasattr(engine.data_service, 'subscribe'):
                            engine.data_service.subscribe(futures_symbol)
                            self.stdout.write(self.style.SUCCESS(f"🔔 Subscribed to {futures_symbol}"))
                            
                            # Note: We don't subscribe to "BANKNIFTY" spot as it's not available in NFO
                            # The futures contract provides the LTP we need
                            
                            # Wait a bit more for first ticks
                            time.sleep(1)
                            self.stdout.write(self.style.SUCCESS("✅ Real WebSocket connected - receiving live ticks"))
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
        # Strategy Parameters (Configurable) - OPTIMIZED
        # ========================================
        TARGET_PCT = Decimal('1.5') / 100        # Target: +1.5%
        STOPLOSS_PCT = Decimal('1.0') / 100       # Stoploss: -1.0% (widened from -0.7%)
        TRAILING_TRIGGER_PCT = Decimal('0.5') / 100  # Trailing SL triggers after +0.5%
        LOT_SIZE = 35                             # ✅ Correct BankNifty lot size
        SQUARE_OFF_TIME = dt_time(15, 30)         # Auto exit at 3:30 PM
        TRADE_START_TIME = dt_time(9, 30)         # Trading window start (9:30 AM)
        TRADE_END_TIME = dt_time(11, 0)          # Trading window end (11:00 AM - extended for more opportunities)
        
        # Optimized Entry Filters (balanced - not too strict, not too loose)
        RSI_BUY_MIN = Decimal('56')              # Balanced: 56 (between 55 and 58)
        RSI_SELL_MAX = Decimal('44')             # Balanced: 44 (between 45 and 42)
        EMA_GAP_REQUIRED = Decimal('0.0012')     # Balanced: 0.12% gap (between 0.1% and 0.15%)
        
        # Simplified momentum breakout parameters
        self.capital = float(strategy.capital)
        self.lot_size = LOT_SIZE
        self.stoploss_pct = STOPLOSS_PCT
        self.target_pct = TARGET_PCT
        self.trailing_trigger_pct = TRAILING_TRIGGER_PCT
        self.current_position = None
        self.current_stoploss_pct = STOPLOSS_PCT  # Dynamic stoploss (for trailing)
        
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
                            
                            # Detect breakout after at least 3 data points (using futures LTP)
                            # Only allow new entries during trading window (9:30 AM - 11:00 AM)
                            current_time = get_ist_now().time()
                            is_in_trading_window = (current_time >= self.trade_start_time and 
                                                   current_time <= self.trade_end_time)
                            
                            if len(self.price_samples) == 3 and not self.current_position and is_in_trading_window:
                                self.range_high = max(self.price_samples)
                                self.range_low = min(self.price_samples)
                                
                                # Breakout detection: futures price >= high * 1.001 (BUY) or <= low * 0.999 (SELL)
                                breakout_signal = None
                                if futures_ltp >= self.range_high * Decimal('1.001'):
                                    breakout_signal = "BUY"
                                elif futures_ltp <= self.range_low * Decimal('0.999'):
                                    breakout_signal = "SELL"
                                
                                # If breakout detected, apply momentum filters before entry
                                if breakout_signal:
                                    # Check momentum filters (optimized - stricter)
                                    if not self._check_momentum_filters(breakout_signal, futures_ltp, self.price_history):
                                        logger.debug(f"Momentum filters failed for {breakout_signal} signal - skipping entry")
                                        continue
                                    
                                    # Filters passed - proceed with trade
                                    self._handle_breakout(breakout_signal, futures_ltp, engine, strategy)
                            
                            # If in trade → check exit conditions (using option LTP)
                            if self.current_position:
                                entry = self.current_position
                                option_symbol = entry.get("symbol")
                                
                                if option_symbol:
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
                                        # Time-based exit (square-off time)
                                        elif current_time_ist.time() >= strategy.square_off_time:
                                            self._simulate_exit(option_ltp, "TIME", engine)
                        
                        cycle_count += 1
                        
                        # Print status every 12 cycles (~1 minute at 5s interval)
                        if cycle_count % 12 == 0:
                            current_time_str = current_time_ist.strftime('%H:%M:%S')
                            status_parts = []
                            
                            if futures_ltp:
                                status_parts.append(f"Futures LTP: ₹{futures_ltp:,.2f}")
                            
                            if self.current_position:
                                option_symbol = self.current_position.get("symbol")
                                option_ltp = self._get_option_ltp(option_symbol, engine) if option_symbol else None
                                if option_ltp:
                                    status_parts.append(f"Option ({option_symbol}): ₹{option_ltp:,.2f}")
                            
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
                if hasattr(engine.data_service, 'ltp_cache') and futures_symbol in engine.data_service.ltp_cache:
                    latest_ltp = engine.data_service.ltp_cache[futures_symbol]
                elif hasattr(engine.data_service, 'get_latest_ltp'):
                    latest_ltp = engine.data_service.get_latest_ltp(futures_symbol)
        
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
    
    def _check_momentum_filters(self, signal_type: str, current_price: Decimal, price_history: List[Decimal]) -> bool:
        """
        Check momentum filters before entry - OPTIMIZED:
        - BUY: EMA5 > EMA20 * (1 + EMA_GAP_REQUIRED) AND RSI > RSI_BUY_MIN
        - SELL: EMA5 < EMA20 * (1 - EMA_GAP_REQUIRED) AND RSI < RSI_SELL_MAX
        """
        if len(price_history) < 20: # Need at least 20 prices for EMA20
            return False
        
        from trading.services.momentum import compute_ema, compute_rsi
        
        ema5 = compute_ema(price_history, 5)
        ema20 = compute_ema(price_history, 20)
        rsi = compute_rsi(price_history, 14)
        
        if ema5 is None or ema20 is None or rsi is None:
            return False
        
        # Use instance variables (set from constants at top)
        rsi_buy_min = getattr(self, 'rsi_buy_min', Decimal('60'))
        rsi_sell_max = getattr(self, 'rsi_sell_max', Decimal('40'))
        ema_gap = getattr(self, 'ema_gap_required', Decimal('0.002'))
        
        if signal_type == "BUY":
            # BUY: EMA5 > EMA20 * (1 + gap) AND RSI > rsi_buy_min
            ema_condition = ema5 > ema20 * (Decimal('1') + ema_gap)
            rsi_condition = rsi > rsi_buy_min
            return ema_condition and rsi_condition
        elif signal_type == "SELL":
            # SELL: EMA5 < EMA20 * (1 - gap) AND RSI < rsi_sell_max
            ema_condition = ema5 < ema20 * (Decimal('1') - ema_gap)
            rsi_condition = rsi < rsi_sell_max
            return ema_condition and rsi_condition
        
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
            # Select option symbol based on breakout signal
            # BUY breakout → Buy ATM CALL (CE)
            # SELL breakout → Buy ATM PUT (PE)
            option_symbol, strike, expiry_date = self.strike_selector.select_strike(
                spot_price=futures_ltp,
                signal_type=breakout_signal,
                strong_momentum=False  # Use ATM for simplicity
            )
            
            self.stdout.write(self.style.SUCCESS(
                f"\n🎯 Breakout detected: {breakout_signal} | Futures LTP: ₹{futures_ltp:,.2f}"
            ))
            self.stdout.write(self.style.SUCCESS(
                f"📊 Selected Option: {option_symbol} | Strike: {strike} | Expiry: {expiry_date}"
            ))
            
            # Subscribe to option symbol for LTP
            if hasattr(engine, 'data_service') and hasattr(engine.data_service, 'subscribe'):
                engine.data_service.subscribe(option_symbol)
                self.stdout.write(self.style.SUCCESS(f"🔔 Subscribed to {option_symbol}"))
            
            # Wait a moment for first LTP
            time.sleep(1)
            
            # Get option LTP
            option_ltp = self._get_option_ltp(option_symbol, engine)
            
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
        
        self.stdout.write(self.style.SUCCESS(
            f"\n🚀 [{mode}] ENTRY {display_side} | Symbol: {option_symbol} | Price: ₹{option_ltp:,.2f}"
        ))
        self.stdout.write(self.style.SUCCESS(
            f"   Futures LTP: ₹{futures_ltp:,.2f} | Strike: {strike} | Expiry: {expiry_date} | Lot Size: {self.lot_size}"
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
            "trade_log_id": getattr(self, 'trade_log_id', None)  # Store for exit update
        }
        
        # Reset trailing stoploss to initial value on new entry
        self.current_stoploss_pct = self.stoploss_pct
        
        # Log to CSV
        self._log_trade_entry(position_side, option_symbol, option_ltp, futures_ltp, strike, entry_time)
        
        # Save to TradeLog model
        self._save_trade_log_entry(position_side, option_symbol, option_ltp, futures_ltp, strike, expiry_date, entry_time, strategy)
    
    def _calculate_pnl(self, entry_price: Decimal, exit_price: Decimal, side: str) -> Decimal:
        """
        Calculate total profit/loss in ₹ for one BankNifty options trade.
        
        Args:
            entry_price: Entry price per unit
            exit_price: Exit price per unit
            side: 'BUY_CE' or 'BUY_PE' (options are always bought)
        
        Returns:
            Decimal: Total P&L in ₹ (rounded to 2 decimal places)
        """
        # Options are always bought, so profit when price goes up
        pnl_per_unit = exit_price - entry_price
        pnl_total = pnl_per_unit * Decimal(str(self.lot_size))
        return round(pnl_total, 2)
    
    def _simulate_exit(self, option_ltp, reason, engine):
        """Simulate option trade exit"""
        if not self.current_position:
            return
        
        entry = self.current_position
        entry_price = Decimal(str(entry["entry_price"]))
        exit_price = Decimal(str(option_ltp))
        option_symbol = entry.get("symbol", "UNKNOWN")
        position_side = entry.get("side", "BUY_CE")
        
        # Calculate P&L using unified function
        pnl_value = self._calculate_pnl(entry_price, exit_price, position_side)
        
        exit_time = get_ist_now()
        
        # Get current futures LTP for reference
        current_futures_ltp = self._get_latest_ltp(engine)
        
        # Determine display side
        display_side = "CALL" if "CE" in entry.get("side", "") else "PUT"
        
        self.stdout.write(self.style.SUCCESS(
            f"💰 [DRY-RUN] EXIT {display_side} | Symbol: {option_symbol} | Price: ₹{exit_price:,.2f} | Reason: {reason}"
        ))
        if current_futures_ltp:
            self.stdout.write(self.style.SUCCESS(
                f"   Futures LTP: ₹{current_futures_ltp:,.2f} | Strike: {entry.get('strike', 'N/A')}"
            ))
        self.stdout.write(self.style.SUCCESS(
            f"📊 P&L: ₹{pnl_value:,.2f} | Entry: ₹{entry_price:,.2f} | Exit: ₹{exit_price:,.2f} | Lot Size: {self.lot_size}\n"
        ))
        
        # Log to CSV
        self._log_trade_exit(entry, exit_price, pnl_value, reason, exit_time)
        
        # Update TradeLog model
        self._update_trade_log_exit(entry, exit_price, pnl_value, reason, exit_time, engine)
        
        self.current_position = None
    
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
                    f.write("timestamp,side,symbol,action,option_entry_price,futures_ltp,strike,exit_price,pnl,reason\n")
            
            with open(log_file, 'a') as f:
                f.write(
                    f"{entry_time.strftime('%Y-%m-%d %H:%M:%S')},"
                    f"{position_side},{option_symbol},ENTRY,{float(option_ltp):.2f},"
                    f"{float(futures_ltp):.2f},{strike},,,\n"
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
            
            # Get current futures LTP
            current_futures_ltp = entry.get('futures_ltp', 0)
            
            with open(log_file, 'a') as f:
                f.write(
                    f"{exit_time.strftime('%Y-%m-%d %H:%M:%S')},"
                    f"{entry['side']},{entry.get('symbol', 'UNKNOWN')},EXIT,{entry['entry_price']:.2f},"
                    f"{current_futures_ltp:.2f},{entry.get('strike', 'N/A')},"
                    f"{float(exit_price):.2f},{pnl:.2f},{reason}\n"
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


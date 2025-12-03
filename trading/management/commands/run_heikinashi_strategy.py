"""
Heikin Ashi + SuperTrend + MACD Strategy - Live Trading & Dry-Run
"""
import os
import sys
import time
import logging
import threading
from decimal import Decimal
from datetime import datetime, time as dt_time, timedelta
from typing import Optional, Dict
from django.core.management.base import BaseCommand
from django.utils import timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading.services.candle_aggregator import CandleAggregator
from trading.services.heikin_ashi import HeikinAshiCalculator
from trading.services.super_trend import SuperTrendCalculator
from trading.services.macd import MACDCalculator
from trading.services.strike_selector import StrikeSelector
from trading.utils.time_helpers import get_ist_now
from trading.utils.expiry_functions import get_banknifty_futures_symbol, round_to_nearest_strike
from trading.services.heikinashi_utils import calculate_pnl, trend_reversal_detected, get_trade_log_fields
from trading.models import Strategy, TradeLog

logger = logging.getLogger(__name__)

# Constants
LOT_SIZE = 35
BASE_DAILY_TARGET_PER_LOT = Decimal('1000')  # ₹1000 profit target per 35 quantity
DAILY_STOP_LOSS_FACTOR = Decimal('0.5')  # 50% of the daily profit target
PER_TRADE_PROFIT_TARGET = Decimal('500')  # ₹500 profit target per trade
TARGET_POINTS = 60  # Futures target: +60 points
OPTION_TARGET_PCT = Decimal('0.15')  # 15% option premium gain
PROFIT_TARGET_RUPEES = Decimal('1300')  # ₹1300 profit target (absolute P&L) - DEPRECATED
STOPLOSS_OPTION_PCT = Decimal('0.30')  # -30% option premium
STOPLOSS_FUTURES_POINTS = 30  # 30 points adverse movement
SQUARE_OFF_TIME = dt_time(15, 20)  # 3:20 PM
TRADE_START_TIME = dt_time(9, 15)  # 9:15 AM (exchange open)
TRADE_END_TIME = dt_time(15, 30)  # 3:30 PM (for testing - allows full trading day)

# Forming candle entry parameters
FORMING_CANDLE_BUFFER_SECONDS = 5  # Wait a few seconds after new candle starts
FORMING_CANDLE_MIN_TICKS = 3  # Require minimum ticks before trusting HA color


class HeikinAshiStrategy:
    """Heikin Ashi strategy implementation"""
    
    def __init__(
        self,
        dry_run: bool = True,
        strategy_name: str = "Heikin Ashi Strategy",
        debug: bool = False,
        candle_source: str = "futures",
        stdout_callback=None,
        quantity: int = LOT_SIZE,
    ):
        self.dry_run = dry_run
        self.strategy_name = strategy_name
        self.strategy_obj = None
        self.debug = debug
        self.debug_log_file = None
        self.candle_source = candle_source  # "futures" or "spot"
        self.stdout_callback = stdout_callback  # Callback to write to terminal
        
        # Indicators
        self.candle_aggregator = CandleAggregator(candle_interval_minutes=15)
        self.heikin_ashi_calc = HeikinAshiCalculator()
        self.super_trend_calc = SuperTrendCalculator(atr_period=10, multiplier=Decimal('3.0'))
        self.macd_calc = MACDCalculator(fast_period=12, slow_period=26, signal_period=9)
        self.strike_selector = StrikeSelector()
        
        # State tracking
        self.current_position: Optional[Dict] = None
        self.previous_ha: Optional[Dict] = None  # Only track HA for reversal detection
        self.last_entry_candle_start: Optional[datetime] = None
        self.last_hold_check_candle_start: Optional[datetime] = None
        self.entry_candle_ha_color: Optional[str] = None  # Track HA color at entry for intra-candle reversal
        self.candle_count = 0  # Track candle number for debug
        self.quantity = quantity if quantity and quantity > 0 else LOT_SIZE
        if self.quantity % LOT_SIZE != 0:
            logger.warning(
                f"Quantity {self.quantity} is not a multiple of base lot size {LOT_SIZE}. Proceeding anyway."
            )
        
        # Daily performance controls
        self.daily_pnl = Decimal('0')
        
        # Initialize with default constants (will be loaded from DB later if strategy_obj is set)
        self.per_trade_profit_target = PER_TRADE_PROFIT_TARGET
        self.target_points = TARGET_POINTS
        self.option_target_pct = OPTION_TARGET_PCT
        self.stoploss_option_pct = STOPLOSS_OPTION_PCT
        self.stoploss_futures_points = STOPLOSS_FUTURES_POINTS
        self.square_off_time = SQUARE_OFF_TIME
        self.trade_start_time = TRADE_START_TIME
        self.trade_end_time = TRADE_END_TIME
        
        # Calculate daily targets (will be updated from DB if available)
        quantity_factor = Decimal(str(self.quantity)) / Decimal(str(LOT_SIZE))
        self.daily_profit_target = quantity_factor * BASE_DAILY_TARGET_PER_LOT
        self.daily_stop_loss = self.daily_profit_target * DAILY_STOP_LOSS_FACTOR
        self.trading_halted_for_day = False
        logger.info(
            f"🎯 Daily controls: Qty={self.quantity} → Target ₹{self.daily_profit_target:.2f}, "
            f"Stop-loss -₹{self.daily_stop_loss:.2f}"
        )
    
    def _load_parameters_from_db(self):
        """Load all parameters from database if strategy_obj is available"""
        if not self.strategy_obj:
            return
        
        try:
            self.strategy_obj.refresh_from_db()
            
            # Load daily target parameters
            if hasattr(self.strategy_obj, 'base_daily_target_per_lot') and self.strategy_obj.base_daily_target_per_lot:
                base_daily_target = Decimal(str(self.strategy_obj.base_daily_target_per_lot))
            else:
                base_daily_target = BASE_DAILY_TARGET_PER_LOT
            
            if hasattr(self.strategy_obj, 'daily_stop_loss_factor') and self.strategy_obj.daily_stop_loss_factor:
                daily_stop_factor = Decimal(str(self.strategy_obj.daily_stop_loss_factor))
            else:
                daily_stop_factor = DAILY_STOP_LOSS_FACTOR
            
            # Recalculate daily targets
            quantity_factor = Decimal(str(self.quantity)) / Decimal(str(LOT_SIZE))
            self.daily_profit_target = quantity_factor * base_daily_target
            self.daily_stop_loss = self.daily_profit_target * daily_stop_factor
            
            # Load per-trade parameters
            # Interpret DB per_trade_profit_target as **per-lot** base target (for 1× LOT_SIZE).
            # Scale it by quantity_factor so that target becomes “₹X per lot”:
            #   e.g. 1 lot (35 qty)  -> X
            #        2 lots (70 qty) -> 2X, etc.
            if hasattr(self.strategy_obj, 'per_trade_profit_target') and self.strategy_obj.per_trade_profit_target:
                base_per_trade_target = Decimal(str(self.strategy_obj.per_trade_profit_target))
            else:
                base_per_trade_target = PER_TRADE_PROFIT_TARGET
            self.per_trade_profit_target = quantity_factor * base_per_trade_target
            
            if hasattr(self.strategy_obj, 'target_points') and self.strategy_obj.target_points:
                self.target_points = int(self.strategy_obj.target_points)
            
            if hasattr(self.strategy_obj, 'option_target_pct') and self.strategy_obj.option_target_pct:
                self.option_target_pct = Decimal(str(self.strategy_obj.option_target_pct))
            
            if hasattr(self.strategy_obj, 'stoploss_option_pct') and self.strategy_obj.stoploss_option_pct:
                self.stoploss_option_pct = Decimal(str(self.strategy_obj.stoploss_option_pct))
            
            if hasattr(self.strategy_obj, 'stoploss_futures_points') and self.strategy_obj.stoploss_futures_points:
                self.stoploss_futures_points = int(self.strategy_obj.stoploss_futures_points)
            
            # Load time parameters
            if hasattr(self.strategy_obj, 'square_off_time_ha') and self.strategy_obj.square_off_time_ha:
                self.square_off_time = self.strategy_obj.square_off_time_ha
            
            if hasattr(self.strategy_obj, 'trade_start_time_ha') and self.strategy_obj.trade_start_time_ha:
                self.trade_start_time = self.strategy_obj.trade_start_time_ha
            
            if hasattr(self.strategy_obj, 'trade_end_time_ha') and self.strategy_obj.trade_end_time_ha:
                self.trade_end_time = self.strategy_obj.trade_end_time_ha
            
            logger.info(
                f"📊 Parameters loaded from DB: Per-trade target ₹{self.per_trade_profit_target:.2f}, "
                f"Daily target ₹{self.daily_profit_target:.2f}, Stop-loss -₹{self.daily_stop_loss:.2f}"
            )
        except Exception as e:
            logger.warning(f"Could not load parameters from DB, using defaults: {e}")
        
        # WebSocket data
        self.futures_ltp: Optional[Decimal] = None
        self.option_ltp: Optional[Decimal] = None
        self.futures_symbol: Optional[str] = None
        self.option_symbol: Optional[str] = None
        
        # Alice Blue client
        self.alice_client = None
        self.ws_connected = False
        
        # Initialize debug log file
        if self.debug:
            log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'logs')
            os.makedirs(log_dir, exist_ok=True)
            self.debug_log_file = os.path.join(log_dir, 'indicator_debug.csv')
            # Write CSV header with bucket timestamps
            with open(self.debug_log_file, 'w') as f:
                f.write("candle_num,bucket_start,bucket_end,timestamp,raw_open,raw_high,raw_low,raw_close,ha_open,ha_high,ha_low,ha_close,ha_color,st_value,st_direction,macd_line,signal_line,histogram,trend_decision\n")
    
    def initialize_alice_blue(self):
        """Initialize Alice Blue WebSocket connection"""
        try:
            from alice_blue import AliceBlue, LiveFeedType
            from strategy.broker.alice_client import USER_ID, API_KEY, get_encryption_key, get_session_id
            
            username = USER_ID
            api_key = API_KEY
            
            enc_key = get_encryption_key(username)
            session_id = get_session_id(username, api_key, enc_key)
            
            self.alice_client = AliceBlue(
                username=username,
                session_id=session_id,
                master_contracts_to_download=['NFO']
            )
            
            # Start WebSocket
            self.alice_client.start_websocket(
                subscribe_callback=self._tick_callback,
                socket_open_callback=self._ws_open_callback,
                socket_error_callback=self._ws_error_callback,
                socket_close_callback=self._ws_close_callback
            )
            
            # Wait for connection
            time.sleep(2)
            
            # Get futures symbol
            self.futures_symbol = get_banknifty_futures_symbol()
            
            # Subscribe to futures
            if self.futures_symbol:
                futures_instrument = self.alice_client.get_instrument_by_symbol('NFO', self.futures_symbol)
                if futures_instrument:
                    self.alice_client.subscribe(futures_instrument, LiveFeedType.TICK_DATA)
                    logger.info(f"✅ Subscribed to futures: {self.futures_symbol}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Alice Blue: {e}")
            return False
    
    def load_historical_candles(self):
        """Load historical candles from previous trading day to initialize indicators"""
        try:
            from datetime import timedelta, date
            from alice_blue import HistoricalDataType
            import pandas as pd
            
            if not self.alice_client:
                logger.warning("Alice Blue client not initialized, skipping historical data load")
                return
            
            # Get yesterday's date (skip weekends)
            today = get_ist_now().date()
            yesterday = today - timedelta(days=1)
            while yesterday.weekday() >= 5:  # Saturday = 5, Sunday = 6
                yesterday = yesterday - timedelta(days=1)
            
            # Get BankNifty futures instrument
            all_instruments = self.alice_client.search_instruments('NFO', 'BANKNIFTY')
            banknifty_futures = [
                inst for inst in all_instruments
                if inst.symbol.startswith('BANKNIFTY') and inst.symbol.endswith('F')
            ]
            
            if not banknifty_futures:
                logger.warning("Could not find BankNifty futures instrument")
                return
            
            instrument = banknifty_futures[0]
            
            # Fetch 1-minute data from yesterday (12:00 PM to 3:30 PM)
            start_time = datetime.combine(yesterday, datetime.min.time()).replace(hour=12, minute=0)
            end_time = datetime.combine(yesterday, datetime.min.time()).replace(hour=15, minute=30)
            
            logger.info(f"📊 Loading historical candles from {yesterday.strftime('%Y-%m-%d')} (12:00 PM - 3:30 PM)...")
            
            # Fetch historical data
            historical_data = self.alice_client.historical_data(
                instrument=instrument,
                ffrom=start_time,
                to=end_time,
                type=HistoricalDataType.Minute
            )
            
            if not historical_data:
                logger.warning("No historical data returned")
                return
            
            # Convert to DataFrame
            if isinstance(historical_data, dict):
                if 'result' in historical_data:
                    df = pd.DataFrame(historical_data['result'])
                else:
                    df = pd.DataFrame(historical_data)
            else:
                df = pd.DataFrame(historical_data)
            
            if df.empty:
                logger.warning("Historical data is empty")
                return
            
            # Convert to 15-minute candles
            df['datetime'] = pd.to_datetime(df.get('datetime', df.get('time', df.index)))
            df = df.set_index('datetime')
            df_15min = df.resample('15min').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            
            # Load historical candles (HA only needs 1 candle, but load more for better context)
            min_candles_needed = 50  # Load last 50 candles for context
            candles_to_load = min(min_candles_needed, len(df_15min))
            df_15min = df_15min.tail(candles_to_load)
            
            if len(df_15min) < 1:
                logger.warning(f"No historical candles available")
                return
            
            if len(df_15min) < 10:
                logger.info(f"⚠️  Limited historical candles: {len(df_15min)} (HA will work, but more candles provide better context)")
            
            logger.info(f"📊 Loading {len(df_15min)} historical candles for indicator warmup...")
            
            # Initialize calculators with historical candles
            candles_loaded = 0
            
            for idx, row in df_15min.iterrows():
                candle = {
                    'open': Decimal(str(row['open'])),
                    'high': Decimal(str(row['high'])),
                    'low': Decimal(str(row['low'])),
                    'close': Decimal(str(row['close'])),
                    'timestamp': idx.to_pydatetime(),
                    'start_time': idx.to_pydatetime(),
                    'end_time': idx.to_pydatetime(),
                    'volume': int(row.get('volume', 0))
                }
                
                # Get raw OHLC
                raw_open = candle['open']
                raw_high = candle['high']
                raw_low = candle['low']
                raw_close = candle['close']
                
                # Add to aggregator
                self.candle_aggregator.candles.append(candle)
                
                # Convert to Heikin Ashi
                ha_candle = self.heikin_ashi_calc.add_candle(candle)
                ha_open = ha_candle['ha_open']
                ha_high = ha_candle['ha_high']
                ha_low = ha_candle['ha_low']
                ha_close = ha_candle['ha_close']
                ha_color = ha_candle.get('ha_color', 'RED' if ha_close < ha_open else 'GREEN')  # TradingView-style HA color
                
                # Debug output for historical candles (only last 30 to match requirement)
                if self.debug and candles_loaded >= len(df_15min) - 30:  # Show last 30 historical candles
                    # Simple trend decision based only on HA
                    trend_decision = 'UPTREND' if ha_color == 'GREEN' else 'DOWNTREND'
                    self.debug_heikin_ashi(
                        idx=candles_loaded + 1,
                        o=raw_open, h=raw_high, l=raw_low, c=raw_close,
                        ha_open=ha_open, ha_high=ha_high, ha_low=ha_low, ha_close=ha_close,
                        ha_color=ha_color,
                        st_value=None,  # Not used in simplified strategy
                        st_signal="N/A",
                        macd=None, signal_line=None, histogram=None,
                        trend_decision=trend_decision,
                        start_time=candle.get('start_time'),
                        end_time=candle.get('end_time')
                    )
                
                candles_loaded += 1
            
            logger.info(
                f"✅ Loaded {candles_loaded} historical candles. "
                f"Heikin-Ashi: ✅ Ready"
            )
            
        except ImportError as e:
            logger.warning(f"Could not import required modules for historical data: {e}")
        except Exception as e:
            logger.warning(f"Error loading historical candles: {e}")
    
    def _ws_open_callback(self):
        """WebSocket opened"""
        self.ws_connected = True
        logger.info("✅ WebSocket connected")
    
    def _ws_error_callback(self, error):
        """WebSocket error"""
        logger.error(f"❌ WebSocket error: {error}")
        self.ws_connected = False
    
    def _ws_close_callback(self):
        """WebSocket closed"""
        logger.warning("🔌 WebSocket closed")
        self.ws_connected = False
    
    def _tick_callback(self, tick):
        """Handle WebSocket tick data"""
        try:
            instrument = tick.get('instrument')
            if instrument and 'ltp' in tick:
                symbol = instrument.symbol
                ltp = Decimal(str(tick['ltp']))
                
                if symbol == self.futures_symbol:
                    self.futures_ltp = ltp
                elif symbol == self.option_symbol:
                    self.option_ltp = ltp
        except Exception as e:
            logger.error(f"Error processing tick: {e}")
    
    def get_option_ltp(self) -> Optional[Decimal]:
        """Get option LTP from WebSocket or API"""
        if self.option_ltp:
            return self.option_ltp
        
        # Try to get from API if WebSocket not available
        if self.alice_client and self.option_symbol:
            try:
                option_instrument = self.alice_client.get_instrument_by_symbol('NFO', self.option_symbol)
                if option_instrument:
                    # Get LTP from API
                    quote = self.alice_client.get_quote(option_instrument)
                    if quote and 'ltp' in quote:
                        return Decimal(str(quote['ltp']))
            except Exception as e:
                logger.debug(f"Could not get option LTP from API: {e}")
        
        return None
    
    def _forming_candle_ready(self, forming_candle: Dict) -> bool:
        """Check if forming candle has enough data to evaluate"""
        if not forming_candle:
            return False
        
        start_time = forming_candle.get('start_time')
        if not start_time:
            return False
        
        now = get_ist_now()
        elapsed = (now - start_time).total_seconds()
        volume = forming_candle.get('volume', 0)
        
        if elapsed < FORMING_CANDLE_BUFFER_SECONDS:
            return False
        
        if volume < FORMING_CANDLE_MIN_TICKS:
            return False
        
        return True
    
    def _calculate_forming_ha(self, forming_candle: Dict) -> Optional[Dict]:
        """Calculate HA values for the current forming candle"""
        if not forming_candle:
            return None
        
        previous_ha = self.heikin_ashi_calc.get_last_candle()
        
        # Ensure previous HA is from the same trading day
        if previous_ha:
            from trading.utils.time_helpers import IST
            prev_time = previous_ha.get('end_time') or previous_ha.get('timestamp')
            form_time = forming_candle.get('start_time') or forming_candle.get('timestamp')
            
            if prev_time and form_time:
                try:
                    # Ensure both are timezone-aware datetimes
                    if not isinstance(prev_time, datetime):
                        if isinstance(prev_time, str):
                            from dateutil import parser
                            prev_time = parser.parse(prev_time)
                        if prev_time.tzinfo is None:
                            prev_time = IST.localize(prev_time)
                    
                    if not isinstance(form_time, datetime):
                        if isinstance(form_time, str):
                            from dateutil import parser
                            form_time = parser.parse(form_time)
                        if form_time.tzinfo is None:
                            form_time = IST.localize(form_time)
                    
                    # Check if same trading day
                    if isinstance(prev_time, datetime) and isinstance(form_time, datetime):
                        prev_date = prev_time.date()
                        form_date = form_time.date()
                        if prev_date != form_date:
                            # Different trading day - TradingView continues HA across days
                            # So we should use previous day's last HA for continuity (TradingView style)
                            # Only reset if there's a gap > 2 hours (overnight/weekend)
                            time_diff = form_time - prev_time
                            if time_diff > timedelta(hours=18):  # More than overnight gap (weekend/holiday)
                                logger.debug(f"Large gap detected ({time_diff}), resetting HA for forming candle")
                                previous_ha = None
                            else:
                                # Overnight gap - continue HA (TradingView style)
                                logger.debug(f"Overnight gap ({prev_date} → {form_date}), continuing HA from previous day")
                                # Keep previous_ha to maintain continuity
                except Exception as e:
                    # If we can't verify, reset to be safe
                    logger.debug(f"Could not verify same-day HA, resetting: {e}")
                    previous_ha = None
        
        from trading.services.heikin_ashi import calculate_heikin_ashi
        return calculate_heikin_ashi(forming_candle, previous_ha)
    
    def check_entry_conditions(self) -> Optional[str]:
        """
        Check entry conditions: Monitor price movement DURING candle formation.
        Enter when current LTP moves above previous high or below previous low.
        This provides more trading opportunities than waiting for gap at candle open.
        """
        if self.trading_halted_for_day:
            return None
        
        if self.current_position:
            return None
        
        # Need futures LTP to check breakout
        if not self.futures_ltp:
            return None
        
        forming_candle = self.candle_aggregator.get_current_forming_candle()
        if not forming_candle:
            return None
        
        start_time = forming_candle.get('start_time')
        if not start_time:
            return None
        
        # If strategy just started mid-candle, wait for the NEXT 15m candle
        if self.last_entry_candle_start is None:
            self.last_entry_candle_start = start_time
            logger.info(
                f"⏳ Waiting for next candle: current bucket starting "
                f"{start_time.strftime('%H:%M')} already in progress"
            )
            return None
        
        # Ensure we only process each candle once (track which candle we're monitoring)
        if self.last_entry_candle_start and start_time <= self.last_entry_candle_start:
            return None
        
        current_time_obj = get_ist_now().time()
        if current_time_obj < self.trade_start_time or current_time_obj > self.trade_end_time:
            logger.info(
                f"⏸️  Entry blocked: Outside trading window "
                f"{current_time_obj.strftime('%H:%M:%S')} "
                f"(Window: {self.trade_start_time.strftime('%H:%M')} - {self.trade_end_time.strftime('%H:%M')})"
            )
            return None
        
        # Wait for forming candle to have minimum data (avoid false signals)
        if not self._forming_candle_ready(forming_candle):
            return None
        
        previous_candle = self.candle_aggregator.get_last_candle()
        if not previous_candle:
            return None
        
        prev_high = previous_candle.get('high')
        prev_low = previous_candle.get('low')
        if prev_high is None or prev_low is None:
            return None
        
        # OPTION 2: Check if current LTP moves above/below previous high/low DURING candle formation
        current_ltp = self.futures_ltp
        
        # Log previous candle details for debugging
        prev_candle_time = previous_candle.get('start_time') or previous_candle.get('timestamp')
        prev_time_str = prev_candle_time.strftime('%H:%M') if prev_candle_time else 'N/A'
        logger.info(
            f"🔍 Entry Check: Current LTP {current_ltp:.2f} | "
            f"Prev Candle [{prev_time_str}]: High {prev_high:.2f}, Low {prev_low:.2f}"
        )
        
        signal = None
        if current_ltp > prev_high:
            signal = 'BUY'
            self.entry_candle_ha_color = 'GREEN'
            logger.info(
                f"📈 Breakout DURING candle: LTP {current_ltp:.2f} > Prev High {prev_high:.2f} → BUY CALL"
            )
        elif current_ltp < prev_low:
            signal = 'SELL'
            self.entry_candle_ha_color = 'RED'
            logger.info(
                f"📉 Breakdown DURING candle: LTP {current_ltp:.2f} < Prev Low {prev_low:.2f} → BUY PUT"
            )
        else:
            logger.debug(
                f"⏸️  No breakout: LTP {current_ltp:.2f} is between Prev High {prev_high:.2f} and Low {prev_low:.2f}"
            )
        
        if signal:
            self.last_entry_candle_start = start_time
            return signal
        
        return None
    
    def check_reversal_on_new_candle(self):
        """
        When holding a position, evaluate the next candle's early HA color.
        If it flips against the current position, exit immediately.
        This checks when a NEW candle starts (not intra-candle).
        """
        if not self.current_position:
            self.last_hold_check_candle_start = None
            return
        
        forming_candle = self.candle_aggregator.get_current_forming_candle()
        if not forming_candle:
            return
        
        start_time = forming_candle.get('start_time')
        if not start_time:
            return
        
        # Only check when a NEW candle starts (not the same candle we entered on)
        if self.last_hold_check_candle_start and start_time <= self.last_hold_check_candle_start:
            return
        
        if not self._forming_candle_ready(forming_candle):
            return
        
        forming_ha = self._calculate_forming_ha(forming_candle)
        if not forming_ha:
            return
        
        ha_color = forming_ha.get('ha_color', 'GREEN' if forming_ha['ha_close'] > forming_ha['ha_open'] else 'RED')
        side = self.current_position['side']
        
        exit_required = False
        if side == 'BUY_CE' and ha_color == 'RED':
            logger.info("🔁 New candle turned RED → Exit CALL position")
            exit_required = True
        elif side == 'BUY_PE' and ha_color == 'GREEN':
            logger.info("🔁 New candle turned GREEN → Exit PUT position")
            exit_required = True
        
        self.last_hold_check_candle_start = start_time
        
        if exit_required:
            self.exit_trade('TREND_REVERSAL')
    
    def check_intra_candle_reversal(self):
        """
        Continuously monitor the forming candle's HA color while in a position.
        If the forming candle's HA color flips against the current position within the same candle,
        exit immediately. This handles intra-candle reversals.
        """
        if not self.current_position:
            return
        
        # Need entry candle HA color to detect reversal
        if not self.entry_candle_ha_color:
            return
        
        forming_candle = self.candle_aggregator.get_current_forming_candle()
        if not forming_candle:
            return
        
        # Only check if we have enough data (same buffer as entry)
        if not self._forming_candle_ready(forming_candle):
            return
        
        forming_ha = self._calculate_forming_ha(forming_candle)
        if not forming_ha:
            return
        
        current_ha_color = forming_ha.get('ha_color', 'GREEN' if forming_ha['ha_close'] > forming_ha['ha_open'] else 'RED')
        side = self.current_position['side']
        
        # Check if HA color flipped against the entry signal
        exit_required = False
        if side == 'BUY_CE':
            # Entered on GREEN, but now forming candle is RED
            if self.entry_candle_ha_color == 'GREEN' and current_ha_color == 'RED':
                logger.info("🔄 Intra-candle reversal: Forming candle flipped RED → Exit CALL position")
                exit_required = True
        elif side == 'BUY_PE':
            # Entered on RED, but now forming candle is GREEN
            if self.entry_candle_ha_color == 'RED' and current_ha_color == 'GREEN':
                logger.info("🔄 Intra-candle reversal: Forming candle flipped GREEN → Exit PUT position")
                exit_required = True
        
        if exit_required:
            self.exit_trade('TREND_REVERSAL')
    
    def monitor_daily_limits(self):
        """
        Continuously enforce daily profit target and stop-loss.
        When either threshold is reached, stop trading for the day and
        flatten any open position immediately.
        """
        if self.trading_halted_for_day:
            if self.current_position:
                logger.info("⚠️ Trading halted for day but position still open → exiting now")
                self.exit_trade('DAILY_HALT')
            return
        
        if self.daily_pnl >= self.daily_profit_target:
            self.trading_halted_for_day = True
            logger.info("🎯 Daily target hit. Trading halted.")
            if self.stdout_callback:
                self.stdout_callback("🎯 Daily target hit. Trading halted.")
            if self.current_position:
                logger.info("🎯 Exiting open position due to daily profit target")
                self.exit_trade('DAILY_TARGET')
            return
        
        if self.daily_pnl <= -self.daily_stop_loss:
            self.trading_halted_for_day = True
            logger.info("🛑 Daily stop-loss hit. Trading halted.")
            if self.stdout_callback:
                self.stdout_callback("🛑 Daily stop-loss hit. Trading halted.")
            if self.current_position:
                logger.info("🛑 Exiting open position due to daily stop-loss")
                self.exit_trade('DAILY_STOP')
    
    def enter_trade(self, signal: str, futures_ltp: Decimal) -> bool:
        """
        Enter a trade
        
        Args:
            signal: 'BUY' for CALL, 'SELL' for PUT
            futures_ltp: Current futures LTP
        
        Returns:
            bool: True if entry successful
        """
        if self.trading_halted_for_day:
            logger.info("🚫 Trading halted for the day. Entry skipped.")
            return False
        
        if self.current_position:
            logger.warning("Already in a position, skipping entry")
            return False
        
        try:
            # Get yesterday's closing price from strategy model for ATM strike selection
            # Refresh strategy object from database to get latest value
            if self.strategy_obj:
                self.strategy_obj.refresh_from_db()
            
            # Field name: yesterday_closing_price (Django model field)
            yesterday_close = None
            if self.strategy_obj:
                # Check if field exists and has a value
                if hasattr(self.strategy_obj, 'yesterday_closing_price'):
                    field_value = getattr(self.strategy_obj, 'yesterday_closing_price', None)
                    if field_value is not None and field_value != '':
                        yesterday_close = Decimal(str(field_value))
                        logger.info(f"✅ Using yesterday's futures close from Strategy model: ₹{yesterday_close:.2f}")
                    else:
                        logger.warning(f"⚠️  yesterday_closing_price is None or empty in Strategy model (ID: {self.strategy_obj.id})")
                else:
                    logger.warning(f"⚠️  Strategy model does not have 'yesterday_closing_price' field")
            
            if yesterday_close is None:
                # Fallback: Use current futures LTP (not ideal, but better than nothing)
                yesterday_close = futures_ltp
                logger.warning(f"⚠️  WARN: Using current futures LTP as fallback: ₹{yesterday_close:.2f}")
            
            # Calculate ATM strike: round(yesterday_close / 100) * 100
            atm_strike = round_to_nearest_strike(yesterday_close, step=100)
            
            # Select strike using ATM
            option_symbol, strike, expiry_date = self.strike_selector.select_strike(
                spot_price=atm_strike,  # Use ATM strike calculated from yesterday's close
                signal_type=signal,
                strong_momentum=False,
                futures_symbol=self.futures_symbol
            )
            
            # Override strike to ensure we use ATM
            if strike != atm_strike:
                logger.info(f"Adjusting strike from {strike} to ATM {atm_strike}")
                strike = atm_strike
                # Rebuild option symbol with correct strike
                from trading.utils.expiry_functions import build_option_symbol
                option_type = 'C' if signal == 'BUY' else 'P'
                option_symbol = build_option_symbol(expiry_date, strike, option_type)
            
            # Get option LTP
            self.option_symbol = option_symbol
            
            # Subscribe to option WebSocket
            if self.alice_client:
                try:
                    from alice_blue import LiveFeedType
                    option_instrument = self.alice_client.get_instrument_by_symbol('NFO', option_symbol)
                    if option_instrument:
                        self.alice_client.subscribe(option_instrument, LiveFeedType.TICK_DATA)
                        time.sleep(0.5)  # Wait for subscription
                except Exception as e:
                    logger.warning(f"Could not subscribe to option: {e}")
            
            option_ltp = self.get_option_ltp()
            if not option_ltp:
                logger.error(f"Could not get option LTP for {option_symbol}")
                return False
            
            # Place order (or simulate)
            entry_time = get_ist_now()
            side = 'BUY_CE' if signal == 'BUY' else 'BUY_PE'
            
            if not self.dry_run:
                # Place real order
                try:
                    option_instrument = self.alice_client.get_instrument_by_symbol('NFO', option_symbol)
                    order = self.alice_client.place_order(
                        instrument=option_instrument,
                        transaction_type=self.alice_client.TRANSACTION_TYPE_BUY,
                        quantity=self.quantity,
                        order_type=self.alice_client.ORDER_TYPE_MARKET,
                        product_type=self.alice_client.PRODUCT_TYPE_INTRADAY
                    )
                    logger.info(f"✅ Order placed: {order}")
                except Exception as e:
                    logger.error(f"Failed to place order: {e}")
                    return False
            
            # Store position
            self.current_position = {
                'entry_time': entry_time,
                'entry_future_price': futures_ltp,
                'entry_premium': option_ltp,
                'option_symbol': option_symbol,
                'strike': strike,
                'side': side,
                'expiry_date': expiry_date,
                'lot_size': self.quantity
            }
            
            # Update previous HA for reversal detection
            self.previous_ha = self.heikin_ashi_calc.get_last_candle()
            
            # Save trade to database immediately on entry (with is_open=True)
            if self.strategy_obj:
                try:
                    TradeLog.objects.create(
                        strategy=self.strategy_obj,
                        entry_time=entry_time,
                        exit_time=None,  # Will be set on exit
                        entry_price=option_ltp,
                        exit_price=None,  # Will be set on exit
                        entry_symbol=option_symbol,
                        entry_side=side,
                        strike=strike,
                        expiry_date=expiry_date,
                        futures_ltp_entry=futures_ltp,
                        futures_ltp_exit=None,  # Will be set on exit
                        exit_reason=None,  # Will be set on exit
                        pnl_value=None,  # Will be calculated on exit
                        pnl_points=None,  # Will be calculated on exit
                        is_open=True,  # Mark as open position
                        dry_run=self.dry_run
                    )
                    logger.info(f"✅ Trade saved to database (is_open=True)")
                except Exception as e:
                    logger.error(f"Failed to save trade log on entry: {e}")
            
            # Log entry
            entry_msg = (
                f"{'[DRY-RUN]' if self.dry_run else '[LIVE]'} "
                f"ENTRY: {side} {option_symbol} @ ₹{option_ltp:.2f} "
                f"(Futures: ₹{futures_ltp:.2f}, Strike: {strike})"
            )
            logger.info(entry_msg)
            
            # Display clear entry message in terminal
            if self.stdout_callback:
                entry_display = (
                    f"\n{'='*80}\n"
                    f"✅ ENTRY EXECUTED\n"
                    f"{'='*80}\n"
                    f"Signal: {side}\n"
                    f"Option: {option_symbol}\n"
                    f"Entry Price: ₹{option_ltp:.2f}\n"
                    f"Futures LTP: ₹{futures_ltp:.2f}\n"
                    f"Strike: {strike}\n"
                    f"Entry Time: {entry_time.strftime('%Y-%m-%d %H:%M:%S')} IST\n"
                    f"{'='*80}\n"
                )
                self.stdout_callback(entry_display)
            
            return True
            
        except Exception as e:
            logger.error(f"Error entering trade: {e}")
            return False
    
    def check_exit_conditions(self) -> Optional[str]:
        """
        Check exit conditions
        
        Returns:
            Exit reason string or None
        """
        if not self.current_position:
            return None
        
        entry = self.current_position
        entry_future_price = entry['entry_future_price']
        entry_premium = entry['entry_premium']
        side = entry['side']
        
        # Get current prices
        if not self.futures_ltp:
            return None
        
        current_futures_ltp = self.futures_ltp
        current_option_ltp = self.get_option_ltp()
        
        if not current_option_ltp:
            return None
        
        # Calculate current trade P&L
        pnl_amount = calculate_pnl(
            entry_premium,
            current_option_ltp,
            side,
            self.quantity
        )
        
        # 1. PER-TRADE PROFIT TARGET: Exit when current trade reaches target
        if pnl_amount >= self.per_trade_profit_target:
            logger.info(
                f"🎯 Per-trade profit target reached: P&L ₹{pnl_amount:.2f} >= ₹{self.per_trade_profit_target:.2f}"
            )
            return 'PROFIT_TARGET'
        
        # EXIT CONDITIONS DISABLED: Only exit on next candle trend reversal (handled elsewhere)
        # The following exit logics are intentionally disabled but kept for reference:
        # - Futures profit target
        # - Absolute profit target (old ₹1300)
        # - Option percentage target
        # - Completed-candle HA reversal
        # - Option/Futures stop-loss
        #
        # Reason: User requested exits on per-trade ₹500 target OR next candle trend reversal.
        # Safety exits (daily target/stop-loss, time exit) are handled outside this method.
        
        # 2. TIME EXIT (3:20 PM) - Note: This is also checked continuously in main loop
        # Keeping this check here for safety, but main loop check takes priority
        current_time = get_ist_now()
        if current_time.time() >= self.square_off_time:
            logger.info(f"⏰ TIME EXIT triggered in check_exit_conditions: {current_time.time()} >= {self.square_off_time}")
            return 'TIME'
        
        return None
    
    def exit_trade(self, exit_reason: str) -> bool:
        """
        Exit current trade
        
        Args:
            exit_reason: Reason for exit
        
        Returns:
            bool: True if exit successful
        """
        if not self.current_position:
            return False
        
        entry = self.current_position
        exit_time = get_ist_now()
        exit_future_price = self.futures_ltp or entry['entry_future_price']
        exit_premium = self.get_option_ltp() or entry['entry_premium']
        
        # Calculate P&L
        pnl_amount = calculate_pnl(
            entry['entry_premium'],
            exit_premium,
            entry['side'],
            self.quantity
        )
        pnl_percent = ((exit_premium - entry['entry_premium']) / entry['entry_premium'] * 100) if entry['entry_premium'] > 0 else Decimal('0')
        
        # Calculate detailed metrics for exit message
        futures_move = exit_future_price - entry['entry_future_price']
        option_move = exit_premium - entry['entry_premium']
        option_move_pct = ((exit_premium - entry['entry_premium']) / entry['entry_premium'] * 100) if entry['entry_premium'] > 0 else Decimal('0')
        
        # Calculate specific trigger values for detailed explanation
        exit_details = ""
        if exit_reason == 'PROFIT_TARGET':
            exit_details = f"P&L reached ₹{pnl_amount:.2f} (Per-trade target: ₹{PER_TRADE_PROFIT_TARGET:.2f})"
        elif exit_reason == 'FUTURES_TARGET':
            if 'CE' in entry['side']:
                futures_profit = exit_future_price - entry['entry_future_price']
            else:
                futures_profit = entry['entry_future_price'] - exit_future_price
            exit_details = f"Futures moved {futures_profit:.2f} points (Target: +{TARGET_POINTS} points)"
        elif exit_reason == 'OPTION_TARGET':
            exit_details = f"Option gained {option_move_pct:.2f}% (Target: +{OPTION_TARGET_PCT*100:.0f}%)"
        elif exit_reason == 'TREND_REVERSAL':
            current_ha = self.heikin_ashi_calc.get_last_candle()
            if current_ha:
                ha_color = current_ha.get('ha_color', 'RED' if current_ha['ha_close'] < current_ha['ha_open'] else 'GREEN')
                if 'CE' in entry['side']:
                    exit_details = f"HA turned RED (downtrend reversal) - CALL exit"
                else:
                    exit_details = f"HA turned GREEN (uptrend reversal) - PUT exit"
        elif exit_reason == 'STOPLOSS':
            option_loss_pct = ((entry['entry_premium'] - exit_premium) / entry['entry_premium'] * 100) if entry['entry_premium'] > 0 else Decimal('0')
            if 'CE' in entry['side']:
                futures_loss = entry['entry_future_price'] - exit_future_price
            else:
                futures_loss = exit_future_price - entry['entry_future_price']
            
            if option_loss_pct >= STOPLOSS_OPTION_PCT * 100:
                exit_details = f"Option lost {option_loss_pct:.2f}% (Stop-loss: -{STOPLOSS_OPTION_PCT*100:.0f}%)"
            else:
                exit_details = f"Futures moved {futures_loss:.2f} points against (Stop-loss: -{STOPLOSS_FUTURES_POINTS} points)"
        elif exit_reason == 'TIME':
            exit_details = f"Square-off time reached ({self.square_off_time.strftime('%H:%M')} IST)"
        else:
            exit_details = f"Exit reason: {exit_reason}"
        
        # Place exit order (or simulate)
        if not self.dry_run:
            try:
                option_instrument = self.alice_client.get_instrument_by_symbol('NFO', entry['option_symbol'])
                order = self.alice_client.place_order(
                    instrument=option_instrument,
                    transaction_type=self.alice_client.TRANSACTION_TYPE_SELL,
                    quantity=self.quantity,
                    order_type=self.alice_client.ORDER_TYPE_MARKET,
                    product_type=self.alice_client.PRODUCT_TYPE_INTRADAY
                )
                logger.info(f"✅ Exit order placed: {order}")
            except Exception as e:
                logger.error(f"Failed to place exit order: {e}")
        
        # Log trade
        trade_log = get_trade_log_fields(
            mode='DRY-RUN' if self.dry_run else 'LIVE',
            entry_time=entry['entry_time'],
            exit_time=exit_time,
            entry_future_price=entry['entry_future_price'],
            exit_future_price=exit_future_price,
            entry_premium=entry['entry_premium'],
            exit_premium=exit_premium,
            option_symbol=entry['option_symbol'],
            strike=entry['strike'],
            side=entry['side'],
            exit_reason=exit_reason,
            pnl_amount=pnl_amount,
            pnl_percent=pnl_percent,
            lot_size=self.quantity
        )
        
        # Update trade in database (find existing open trade and update it)
        if self.strategy_obj:
            try:
                # Find the open trade for this position
                open_trade = TradeLog.objects.filter(
                    strategy=self.strategy_obj,
                    entry_symbol=entry['option_symbol'],
                    entry_side=entry['side'],
                    is_open=True,
                    dry_run=self.dry_run
                ).order_by('-entry_time').first()
                
                if open_trade:
                    # Update existing trade
                    open_trade.exit_time = exit_time
                    open_trade.exit_price = exit_premium
                    open_trade.futures_ltp_exit = exit_future_price
                    open_trade.exit_reason = exit_reason
                    open_trade.pnl_value = pnl_amount
                    open_trade.pnl_points = exit_premium - entry['entry_premium']
                    open_trade.is_open = False
                    open_trade.save()
                    logger.info(f"✅ Trade updated in database (closed)")
                else:
                    # If no open trade found, create a new one (fallback)
                    logger.warning("No open trade found, creating new trade log on exit")
                    TradeLog.objects.create(
                        strategy=self.strategy_obj,
                        entry_time=entry['entry_time'],
                        exit_time=exit_time,
                        entry_price=entry['entry_premium'],
                        exit_price=exit_premium,
                        entry_symbol=entry['option_symbol'],
                        entry_side=entry['side'],
                        strike=entry['strike'],
                        expiry_date=entry['expiry_date'],
                        futures_ltp_entry=entry['entry_future_price'],
                        futures_ltp_exit=exit_future_price,
                        exit_reason=exit_reason,
                        pnl_value=pnl_amount,
                        pnl_points=exit_premium - entry['entry_premium'],
                        is_open=False,
                        dry_run=self.dry_run
                    )
            except Exception as e:
                logger.error(f"Failed to update trade log on exit: {e}")
        
        # Map exit reasons to clear explanations
        exit_reason_explanations = {
            'PROFIT_TARGET': f'Per-trade profit target reached (₹{PER_TRADE_PROFIT_TARGET:.2f})',
            'FUTURES_TARGET': f'Futures profit target reached (+{TARGET_POINTS} points)',
            'OPTION_TARGET': f'Option profit target reached (+{OPTION_TARGET_PCT*100:.0f}%)',
            'TREND_REVERSAL': 'Heikin-Ashi trend reversal detected',
            'STOPLOSS': f'Stop-loss triggered',
            'TIME': f'Time-based exit (Square-off at {self.square_off_time.strftime("%H:%M")} IST)',
            'DAILY_TARGET': 'Daily profit target hit',
            'DAILY_STOP': 'Daily stop-loss hit',
            'DAILY_HALT': 'Trading halted for the day'
        }
        
        # Get detailed exit information
        exit_explanation = exit_reason_explanations.get(exit_reason, exit_reason)
        
        # Log exit
        exit_msg = (
            f"{'[DRY-RUN]' if self.dry_run else '[LIVE]'} "
            f"EXIT: {exit_reason} | P&L: ₹{pnl_amount:.2f} ({pnl_percent:.2f}%)"
        )
        logger.info(exit_msg)
        
        # Display clear exit message in terminal
        if self.stdout_callback:
            # Determine P&L color/style
            pnl_sign = "✅" if pnl_amount >= 0 else "❌"
            pnl_color = "PROFIT" if pnl_amount >= 0 else "LOSS"
            
            exit_display = (
                f"\n{'='*80}\n"
                f"🚪 EXIT EXECUTED\n"
                f"{'='*80}\n"
                f"Exit Reason: {exit_reason} - {exit_explanation}\n"
                f"Details: {exit_details}\n"
                f"{'-'*80}\n"
                f"Option: {entry['option_symbol']}\n"
                f"Side: {entry['side']}\n"
                f"Entry Price: ₹{entry['entry_premium']:.2f}\n"
                f"Exit Price: ₹{exit_premium:.2f}\n"
                f"Option Move: ₹{option_move:.2f} ({option_move_pct:+.2f}%)\n"
                f"{'-'*80}\n"
                f"Entry Futures: ₹{entry['entry_future_price']:.2f}\n"
                f"Exit Futures: ₹{exit_future_price:.2f}\n"
                f"Futures Move: {futures_move:+.2f} points\n"
                f"{'-'*80}\n"
                f"Entry Time: {entry['entry_time'].strftime('%Y-%m-%d %H:%M:%S')} IST\n"
                f"Exit Time: {exit_time.strftime('%Y-%m-%d %H:%M:%S')} IST\n"
                f"Duration: {exit_time - entry['entry_time']}\n"
                f"{'-'*80}\n"
                f"{pnl_sign} P&L: ₹{pnl_amount:.2f} ({pnl_percent:+.2f}%) - {pnl_color}\n"
                f"{'='*80}\n"
            )
            self.stdout_callback(exit_display)
        
        # Update daily P&L and enforce halt thresholds
        self.daily_pnl += pnl_amount
        logger.info(
            f"📊 Daily P&L updated: ₹{self.daily_pnl:.2f} / Target ₹{self.daily_profit_target:.2f} | "
            f"Stop -₹{self.daily_stop_loss:.2f}"
        )
        if self.daily_pnl >= self.daily_profit_target and not self.trading_halted_for_day:
            self.trading_halted_for_day = True
            logger.info("🎯 Daily target hit. Trading halted.")
            if self.stdout_callback:
                self.stdout_callback("🎯 Daily target hit. Trading halted.")
        elif self.daily_pnl <= -self.daily_stop_loss and not self.trading_halted_for_day:
            self.trading_halted_for_day = True
            logger.info("🛑 Daily stop-loss hit. Trading halted.")
            if self.stdout_callback:
                self.stdout_callback("🛑 Daily stop-loss hit. Trading halted.")
        
        # Clear position
        self.current_position = None
        self.entry_candle_ha_color = None  # Reset entry HA color tracking
        self.option_symbol = None
        self.option_ltp = None
        
        # After exit, wait for next candle before allowing new entry
        # This ensures we don't immediately re-enter on the same candle
        forming_candle = self.candle_aggregator.get_current_forming_candle()
        if forming_candle:
            start_time = forming_candle.get('start_time')
            if start_time:
                self.last_entry_candle_start = start_time
                logger.info(f"⏸️  After exit, waiting for next candle (current: {start_time.strftime('%H:%M')})")
        
        return True
    
    def get_trend_decision(self, ha_candle, st, macd_dict) -> str:
        """
        Determine trend decision based on indicators
        
        Returns:
            'UPTREND', 'DOWNTREND', or 'NO-TREND'
        """
        if not ha_candle or not st or not macd_dict:
            return 'NO-TREND'
        
        # HA trend is determined ONLY by HA_Close vs HA_Open (TradingView style)
        ha_trend = ha_candle.get('ha_color', 'RED' if ha_candle['ha_close'] < ha_candle['ha_open'] else 'GREEN')
        ha_green = (ha_trend == 'GREEN')
        
        st_green = st.get('color') == 'GREEN'
        macd_bullish = macd_dict['macd_line'] > macd_dict['signal_line']
        
        # UPTREND: All three conditions must be true
        if ha_green and st_green and macd_bullish:
            return 'UPTREND'
        
        ha_red = (ha_trend == 'RED')
        st_red = st.get('color') == 'RED'
        macd_bearish = macd_dict['macd_line'] < macd_dict['signal_line']
        
        # DOWNTREND: All three conditions must be true
        if ha_red and st_red and macd_bearish:
            return 'DOWNTREND'
        
        # Mixed signals = NO-TREND
        return 'NO-TREND'
    
    def debug_heikin_ashi(self, idx, o, h, l, c, ha_open, ha_high, ha_low, ha_close, ha_color,
                          st_value, st_signal, macd, signal_line, histogram, trend_decision, 
                          start_time=None, end_time=None):
        """
        Debug function to print detailed indicator values for matching with mobile chart
        Also logs to CSV if debug mode is enabled
        """
        if self.debug:
            print("\n================= DEBUG CANDLE =================")
            print(f"Candle #{idx}")
            
            # Show bucket timestamps
            if start_time and end_time:
                start_str = start_time.strftime('%Y-%m-%d %H:%M:%S IST') if isinstance(start_time, datetime) else str(start_time)
                end_str = end_time.strftime('%Y-%m-%d %H:%M:%S IST') if isinstance(end_time, datetime) else str(end_time)
                print(f"Bucket: {start_str} - {end_str}")
            
            print(f"\nRAW OHLC:")
            print(f"  O: {o:.2f}")
            print(f"  H: {h:.2f}")
            print(f"  L: {l:.2f}")
            print(f"  C: {c:.2f}")
            
            print(f"\nHEIKIN ASHI:")
            print(f"  HA_O: {ha_open:.2f}")
            print(f"  HA_H: {ha_high:.2f}")
            print(f"  HA_L: {ha_low:.2f}")
            print(f"  HA_C: {ha_close:.2f}")
            print(f"  HA_Color: {ha_color}")
            
            print(f"\nSUPER TREND(10,3):")
            if st_value is not None:
                print(f"  Value: {st_value:.2f}")
                print(f"  Direction: {st_signal}")
            else:
                print(f"  Value: N/A")
                print(f"  Direction: N/A")
            
            print(f"\nMACD(12,26,9):")
            if macd is not None and signal_line is not None:
                print(f"  MACD_LINE: {macd:.2f}")
                print(f"  SIGNAL: {signal_line:.2f}")
                print(f"  HISTOGRAM: {histogram:.2f}")
            else:
                print(f"  MACD_LINE: N/A")
                print(f"  SIGNAL: N/A")
                print(f"  HISTOGRAM: N/A")
            
            print(f"\nTREND DECISION:")
            print(f"  {trend_decision}")
            print("=================================================\n")
        
        # Log to CSV
        if self.debug and self.debug_log_file:
            try:
                import csv
                timestamp_str = get_ist_now().strftime('%Y-%m-%d %H:%M:%S')
                start_str = start_time.strftime('%Y-%m-%d %H:%M:%S') if start_time and isinstance(start_time, datetime) else ""
                end_str = end_time.strftime('%Y-%m-%d %H:%M:%S') if end_time and isinstance(end_time, datetime) else ""
                with open(self.debug_log_file, 'a') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        idx,
                        start_str,
                        end_str,
                        timestamp_str,
                        f"{o:.2f}",
                        f"{h:.2f}",
                        f"{l:.2f}",
                        f"{c:.2f}",
                        f"{ha_open:.2f}",
                        f"{ha_high:.2f}",
                        f"{ha_low:.2f}",
                        f"{ha_close:.2f}",
                        ha_color,  # HA color (GREEN/RED)
                        f"{st_value:.2f}" if st_value is not None else "N/A",
                        st_signal or "N/A",
                        f"{macd:.2f}" if macd is not None else "N/A",
                        f"{signal_line:.2f}" if signal_line is not None else "N/A",
                        f"{histogram:.2f}" if histogram is not None else "N/A",
                        trend_decision
                    ])
            except Exception as e:
                logger.error(f"Failed to write debug log: {e}")
    
    def process_ltp(self, ltp: Decimal, timestamp: datetime):
        """
        Process new LTP tick
        
        Args:
            ltp: Last traded price
            timestamp: Timestamp
        """
        # Add to candle aggregator (creates 15-min candles)
        new_candle = self.candle_aggregator.add_ltp(ltp, timestamp)
        
        # Only process after a new candle is created (15-min candle close)
        if new_candle:
            # Get raw OHLC values
            raw_open = new_candle['open']
            raw_high = new_candle['high']
            raw_low = new_candle['low']
            raw_close = new_candle['close']
            
            # Convert to Heikin Ashi
            ha_candle = self.heikin_ashi_calc.add_candle(new_candle)
            ha_open = ha_candle['ha_open']
            ha_high = ha_candle['ha_high']
            ha_low = ha_candle['ha_low']
            ha_close = ha_candle['ha_close']
            ha_color = ha_candle.get('ha_color', 'RED' if ha_close < ha_open else 'GREEN')  # TradingView-style HA color
            
            # Determine trend decision based ONLY on Heikin-Ashi
            trend_decision = 'UPTREND' if ha_color == 'GREEN' else 'DOWNTREND'
            
            # Increment candle count
            self.candle_count += 1
            
            # Debug output for each new candle
            if self.debug:
                self.debug_heikin_ashi(
                    idx=self.candle_count,
                    o=raw_open, h=raw_high, l=raw_low, c=raw_close,
                    ha_open=ha_open, ha_high=ha_high, ha_low=ha_low, ha_close=ha_close,
                    ha_color=ha_color,
                    st_value=None,  # Not used in simplified strategy
                    st_signal="N/A",
                    macd=None, signal_line=None, histogram=None,
                    trend_decision=trend_decision,
                    start_time=new_candle.get('start_time'),
                    end_time=new_candle.get('end_time')
                )
            
            # Check entry/exit using next-candle logic
            if not self.current_position:
                signal = self.check_entry_conditions()
                if signal and self.futures_ltp:
                    self.enter_trade(signal, self.futures_ltp)
            else:
                # Monitor the newly forming candle for reversal
                self.check_reversal_on_new_candle()
            
            # Check additional exit conditions (targets, SL, etc.)
            if self.current_position:
                exit_reason = self.check_exit_conditions()
                if exit_reason:
                    self.exit_trade(exit_reason)
                
                # Update previous HA for next reversal check
                self.previous_ha = self.heikin_ashi_calc.get_last_candle()


class Command(BaseCommand):
    help = "Heikin Ashi + SuperTrend + MACD Strategy - Live Trading & Dry-Run"
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run in dry-run mode (no real orders)'
        )
        parser.add_argument(
            '--loop',
            action='store_true',
            help='Run continuously (default: single cycle)'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=5,
            help='Loop interval in seconds (default: 5)'
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Enable debug mode with detailed indicator output and CSV logging'
        )
        parser.add_argument(
            '--candle-source',
            type=str,
            choices=['futures', 'spot'],
            default='futures',
            help='Candle data source: "futures" (default) or "spot"'
        )
        parser.add_argument(
            '--quantity',
            type=int,
            default=LOT_SIZE,
            help='Total option quantity (multiple of 35). Used for order sizing and daily targets.'
        )
    
    def handle(self, *args, **options):
        dry_run = options.get('dry_run', True)
        loop = options.get('loop', False)
        interval = options.get('interval', 5)
        debug = options.get('debug', False)
        
        mode_str = "DRY-RUN" if dry_run else "LIVE"
        self.stdout.write(self.style.SUCCESS(f"✅ {mode_str} MODE - {'No real orders' if dry_run else 'REAL ORDERS ENABLED'}"))
        if debug:
            self.stdout.write(self.style.SUCCESS("🐛 DEBUG MODE ENABLED - Detailed indicator output and CSV logging"))
        
        # Get or create strategy
        strategy_obj, _ = Strategy.objects.get_or_create(
            name="Heikin Ashi Strategy",
            defaults={'enabled': True}
        )
        
        # Initialize strategy with stdout callback for terminal messages
        candle_source = options.get('candle_source', 'futures')
        
        # Calculate quantity: Use command-line arg if provided, otherwise calculate from DB (lot_size * num_lots)
        quantity_arg = options.get('quantity')
        if quantity_arg and quantity_arg != LOT_SIZE:
            # Explicit quantity provided via command line - use it
            quantity = quantity_arg
            self.stdout.write(
                self.style.SUCCESS(f"📊 Using quantity from command line: {quantity}")
            )
        else:
            # No explicit quantity - calculate from DB
            db_lot_size = strategy_obj.lot_size if strategy_obj.lot_size else LOT_SIZE
            db_num_lots = strategy_obj.num_lots if strategy_obj.num_lots else 1
            quantity = db_lot_size * db_num_lots
            self.stdout.write(
                self.style.SUCCESS(
                    f"📊 Quantity from DB: lot_size={db_lot_size} × num_lots={db_num_lots} = {quantity}"
                )
            )
        
        strategy = HeikinAshiStrategy(
            dry_run=dry_run, 
            strategy_name="Heikin Ashi Strategy", 
            debug=debug,
            candle_source=candle_source,
            stdout_callback=lambda msg: self.stdout.write(self.style.SUCCESS(msg)),
            quantity=quantity
        )
        # Set strategy_obj BEFORE loading parameters (so _load_parameters_from_db can access it)
        strategy.strategy_obj = strategy_obj
        # Reload parameters from DB now that strategy_obj is set (quantity already set, but daily targets need recalculation)
        strategy._load_parameters_from_db()
        self.stdout.write(
            self.style.SUCCESS(
                f"🧮 Quantity: {strategy.quantity} | Daily target ₹{strategy.daily_profit_target:.2f} | "
                f"Stop-loss -₹{strategy.daily_stop_loss:.2f}"
            )
        )
        
        if candle_source:
            self.stdout.write(self.style.SUCCESS(f"📊 Candle source: {candle_source.upper()}"))
        
        if debug and strategy.debug_log_file:
            self.stdout.write(self.style.SUCCESS(f"📝 Debug log: {strategy.debug_log_file}"))
        
        # Initialize Alice Blue
        if not strategy.initialize_alice_blue():
            self.stdout.write(self.style.ERROR("❌ Failed to initialize Alice Blue"))
            return
        
        # Load historical candles to initialize indicators
        self.stdout.write("📊 Loading historical candles to initialize indicators...")
        strategy.load_historical_candles()
        
        # Check if trading window is already closed
        current_time = get_ist_now()
        current_time_obj = current_time.time()
        if current_time_obj > strategy.trade_end_time:
            self.stdout.write(
                self.style.WARNING(
                    f"⏰ Trading window already closed: Current time {current_time_obj.strftime('%H:%M:%S')} > "
                    f"End time {strategy.trade_end_time.strftime('%H:%M:%S')}"
                )
            )
            self.stdout.write(self.style.SUCCESS("✅ Strategy stopped (outside trading window)"))
            return
        
        self.stdout.write("🔄 Starting strategy loop...")
        self.stdout.write("Press Ctrl+C to stop")
        
        try:
            while True:
                current_time = get_ist_now()
                current_time_obj = current_time.time()
                
                # Stop strategy after trade_end_time
                if current_time_obj > strategy.trade_end_time:
                    self.stdout.write(
                        self.style.WARNING(
                            f"\n⏰ Trading window closed: Current time {current_time_obj.strftime('%H:%M:%S')} > "
                            f"End time {strategy.trade_end_time.strftime('%H:%M:%S')}"
                        )
                    )
                    # Exit any open position before stopping
                    if strategy.current_position:
                        strategy.exit_trade('TIME')
                    break
                
                # Check time exit continuously (not just on candle close) - Exit positions at 3:20 PM
                if strategy.current_position:
                    if current_time_obj >= strategy.square_off_time:
                        logger.info(f"⏰ TIME EXIT: Current time {current_time_obj} >= Square-off time {strategy.square_off_time}")
                        strategy.exit_trade('TIME')
                
                # Enforce daily profit/stop limits continuously
                strategy.monitor_daily_limits()
                
                # Process futures LTP
                if strategy.futures_ltp:
                    strategy.process_ltp(strategy.futures_ltp, current_time)
                
                # Check entry conditions continuously (for next candle start entry logic)
                if not strategy.trading_halted_for_day and not strategy.current_position:
                    signal = strategy.check_entry_conditions()
                    if signal and strategy.futures_ltp:
                        strategy.enter_trade(signal, strategy.futures_ltp)
                else:
                    # Monitor for reversals:
                    # 1. Intra-candle reversal (same candle flips) - DISABLED (commented out, not removed)
                    # strategy.check_intra_candle_reversal()
                    # 2. New candle reversal (next candle starts with opposite color)
                    strategy.check_reversal_on_new_candle()
                    
                    # Check exit conditions continuously (profit target, stop-loss, etc.)
                    exit_reason = strategy.check_exit_conditions()
                    if exit_reason:
                        strategy.exit_trade(exit_reason)
                
                # Display status
                status_parts = []
                if strategy.futures_ltp:
                    status_parts.append(f"Futures: ₹{strategy.futures_ltp:,.2f}")
                
                # Show previous completed candle high/low for reference (only from today)
                prev_candle = strategy.candle_aggregator.get_last_candle()
                if prev_candle:
                    # Only show if the candle is from today (not yesterday's historical data)
                    candle_time = prev_candle.get('start_time') or prev_candle.get('timestamp')
                    if candle_time:
                        try:
                            from trading.utils.time_helpers import IST
                            if not isinstance(candle_time, datetime):
                                if isinstance(candle_time, str):
                                    from dateutil import parser
                                    candle_time = parser.parse(candle_time)
                                if candle_time.tzinfo is None:
                                    candle_time = IST.localize(candle_time)
                                else:
                                    candle_time = candle_time.astimezone(IST)
                            
                            today = get_ist_now().date()
                            candle_date = candle_time.date() if isinstance(candle_time, datetime) else None
                            
                            # Only display if candle is from today
                            if candle_date == today:
                                prev_high = prev_candle.get('high')
                                prev_low = prev_candle.get('low')
                                if prev_high is not None and prev_low is not None:
                                    try:
                                        prev_high_float = float(prev_high)
                                        prev_low_float = float(prev_low)
                                        status_parts.append(
                                            f"Prev H/L: {prev_high_float:.2f} / {prev_low_float:.2f}"
                                        )
                                    except (TypeError, ValueError):
                                        pass
                        except Exception:
                            # Fallback: show anyway if date check fails
                            prev_high = prev_candle.get('high')
                            prev_low = prev_candle.get('low')
                            if prev_high is not None and prev_low is not None:
                                try:
                                    prev_high_float = float(prev_high)
                                    prev_low_float = float(prev_low)
                                    status_parts.append(
                                        f"Prev H/L: {prev_high_float:.2f} / {prev_low_float:.2f}"
                                    )
                                except (TypeError, ValueError):
                                    pass
                
                # Show Heikin-Ashi indicator (ONLY indicator used)
                # Calculate both forming candle HA and last completed candle HA for comparison
                current_forming_candle = strategy.candle_aggregator.get_current_forming_candle()
                current_ha_color = None
                last_completed_ha_color = None
                current_ha_candle = None  # Initialize for scope
                
                # Get last completed HA candle
                last_ha = strategy.heikin_ashi_calc.get_last_candle()
                last_ha_date = None
                if last_ha:
                    ha_open = last_ha['ha_open']
                    ha_close = last_ha['ha_close']
                    # Recalculate color to ensure it's correct
                    if ha_close > ha_open:
                        last_completed_ha_color = "GREEN"
                    else:
                        last_completed_ha_color = "RED"
                    
                    # Get date of completed candle for comparison
                    last_ha_time = last_ha.get('end_time') or last_ha.get('timestamp')
                    if last_ha_time:
                        try:
                            from trading.utils.time_helpers import IST
                            if not isinstance(last_ha_time, datetime):
                                if isinstance(last_ha_time, str):
                                    from dateutil import parser
                                    last_ha_time = parser.parse(last_ha_time)
                                if last_ha_time.tzinfo is None:
                                    last_ha_time = IST.localize(last_ha_time)
                            if isinstance(last_ha_time, datetime):
                                last_ha_date = last_ha_time.date()
                        except:
                            pass
                
                if current_forming_candle and strategy.futures_ltp:
                    # Calculate HA for current forming candle using the strategy's method
                    # (which handles same-day checks properly)
                    current_ha_candle = strategy._calculate_forming_ha(current_forming_candle)
                    current_ha_open = current_ha_candle['ha_open']
                    current_ha_close = current_ha_candle['ha_close']
                    
                    # Determine color (TradingView style: GREEN when HA_Close > HA_Open)
                    if current_ha_close > current_ha_open:
                        current_ha_color = "GREEN"
                    else:
                        current_ha_color = "RED"
                    
                    # Debug: Log HA calculation details if debug mode is enabled
                    if strategy.debug:
                        # Convert Decimal to float for formatting
                        form_o = float(current_forming_candle['open'])
                        form_h = float(current_forming_candle['high'])
                        form_l = float(current_forming_candle['low'])
                        form_c = float(current_forming_candle['close'])
                        ha_o = float(current_ha_open)
                        ha_c = float(current_ha_close)
                        
                        # Get previous HA for debug display
                        prev_ha_for_debug = strategy.heikin_ashi_calc.get_last_candle()
                        if prev_ha_for_debug:
                            prev_ha_o = f"{float(prev_ha_for_debug['ha_open']):.2f}"
                            prev_ha_c = f"{float(prev_ha_for_debug['ha_close']):.2f}"
                        else:
                            prev_ha_o = "N/A"
                            prev_ha_c = "N/A"
                        
                        logger.debug(
                            f"Forming Candle HA: O={form_o:.2f}, "
                            f"H={form_h:.2f}, "
                            f"L={form_l:.2f}, "
                            f"C={form_c:.2f} | "
                            f"HA_O={ha_o:.2f}, HA_C={ha_c:.2f}, "
                            f"Color={current_ha_color} | "
                            f"Prev HA: O={prev_ha_o}, C={prev_ha_c}"
                        )
                
                # Display both forming and last completed HA colors so terminal matches chart + TradingView
                if current_ha_color or last_completed_ha_color:
                    if current_ha_candle and current_ha_color:
                        forming_emoji = "🟢" if current_ha_color == 'GREEN' else "🔴"
                        form_ha_o = float(current_ha_candle['ha_open'])
                        form_ha_c = float(current_ha_candle['ha_close'])
                        forming_text = f"{forming_emoji} {current_ha_color} (O:{form_ha_o:.2f} C:{form_ha_c:.2f})"
                    else:
                        forming_text = "⏳"
                    
                    # Check if completed candle is from same day
                    current_date = get_ist_now().date()
                    if last_ha and last_completed_ha_color:
                        completed_emoji = "🟢" if last_completed_ha_color == 'GREEN' else "🔴"
                        last_ha_o = float(last_ha['ha_open'])
                        last_ha_c = float(last_ha['ha_close'])
                        
                        # Show date if different day
                        if last_ha_date and last_ha_date != current_date:
                            date_str = last_ha_date.strftime('%m/%d')
                            completed_text = f"{completed_emoji} {last_completed_ha_color} [{date_str}] (O:{last_ha_o:.2f} C:{last_ha_c:.2f})"
                        else:
                            completed_text = f"{completed_emoji} {last_completed_ha_color} (O:{last_ha_o:.2f} C:{last_ha_c:.2f})"
                    else:
                        completed_text = "⏳"
                    
                    # For first candle of day, emphasize forming candle
                    if last_ha_date and last_ha_date != current_date:
                        # No completed candle from today yet - show only forming
                        status_parts.append(f"HA: {forming_text} (Today's first candle - compare with chart)")
                    else:
                        status_parts.append(f"HA: Forming={forming_text} | Completed={completed_text}")
                else:
                    status_parts.append("HA: ⏳ Initializing...")
                
                if strategy.current_position:
                    entry = strategy.current_position
                    option_ltp = strategy.get_option_ltp() or entry['entry_premium']
                    pnl = calculate_pnl(entry['entry_premium'], option_ltp, entry['side'], strategy.quantity)
                    status_parts.append(
                        f"IN TRADE: {entry['option_symbol']} | Entry: ₹{entry['entry_premium']:.2f} | "
                        f"Current: ₹{option_ltp:.2f} | P&L: ₹{pnl:.2f}"
                    )
                
                status_parts.append(
                    f"Daily P&L: ₹{strategy.daily_pnl:.2f} / ₹{strategy.daily_profit_target:.2f} | "
                    f"Stop: -₹{strategy.daily_stop_loss:.2f}"
                )
                if strategy.trading_halted_for_day:
                    status_parts.append("Status: HALTED")
                
                if status_parts:
                    time_str = current_time.strftime('%H:%M:%S')
                    self.stdout.write(f"[{time_str}] {' | '.join(status_parts)}")
                
                if not loop:
                    break
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\n⏹️  Stopping strategy..."))
            
            # Exit any open position
            if strategy.current_position:
                strategy.exit_trade('TIME')
        
        self.stdout.write(self.style.SUCCESS("✅ Strategy stopped"))


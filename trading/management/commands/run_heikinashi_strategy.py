"""
Heikin Ashi + SuperTrend + MACD Strategy - Live Trading & Dry-Run
"""
import os
import sys
import time
import logging
import threading
from decimal import Decimal
from datetime import datetime, time as dt_time
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
TARGET_POINTS = 60  # Futures target: +60 points
OPTION_TARGET_PCT = Decimal('0.15')  # 15% option premium gain
STOPLOSS_OPTION_PCT = Decimal('0.30')  # -30% option premium
STOPLOSS_FUTURES_POINTS = 30  # 30 points adverse movement
SQUARE_OFF_TIME = dt_time(15, 20)  # 3:20 PM
TRADE_START_TIME = dt_time(9, 15)  # 9:15 AM (exchange open)
TRADE_END_TIME = dt_time(15, 30)  # 3:30 PM (for testing - allows full trading day)


class HeikinAshiStrategy:
    """Heikin Ashi strategy implementation"""
    
    def __init__(self, dry_run: bool = True, strategy_name: str = "Heikin Ashi Strategy", debug: bool = False, candle_source: str = "futures"):
        self.dry_run = dry_run
        self.strategy_name = strategy_name
        self.strategy_obj = None
        self.debug = debug
        self.debug_log_file = None
        self.candle_source = candle_source  # "futures" or "spot"
        
        # Indicators
        self.candle_aggregator = CandleAggregator(candle_interval_minutes=15)
        self.heikin_ashi_calc = HeikinAshiCalculator()
        self.super_trend_calc = SuperTrendCalculator(atr_period=10, multiplier=Decimal('3.0'))
        self.macd_calc = MACDCalculator(fast_period=12, slow_period=26, signal_period=9)
        self.strike_selector = StrikeSelector()
        
        # State tracking
        self.current_position: Optional[Dict] = None
        self.previous_ha: Optional[Dict] = None  # Only track HA for reversal detection
        self.last_candle_time: Optional[datetime] = None
        self.candle_count = 0  # Track candle number for debug
        
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
    
    def check_entry_conditions(self) -> Optional[str]:
        """
        Check entry conditions after 15-min candle close
        Uses ONLY Heikin-Ashi for trend detection
        
        Returns:
            'BUY' for CALL entry (uptrend), 'SELL' for PUT entry (downtrend), None if no entry
        """
        # Get last completed candle
        last_candle = self.candle_aggregator.get_last_candle()
        if not last_candle:
            return None
        
        # Only check after candle close (not during candle formation)
        current_time = get_ist_now()
        candle_end_time = last_candle['end_time']
        
        # If this candle was already processed, skip
        if self.last_candle_time and self.last_candle_time >= candle_end_time:
            return None
        
        # Check trading window: Only allow entries between 9:15 AM - 11:00 AM
        current_time_obj = current_time.time()
        if current_time_obj < TRADE_START_TIME or current_time_obj > TRADE_END_TIME:
            logger.info(f"⏸️  Entry blocked: Outside trading window {current_time_obj.strftime('%H:%M:%S')} (Window: {TRADE_START_TIME.strftime('%H:%M')} - {TRADE_END_TIME.strftime('%H:%M')})")
            return None
        
        # Mark this candle as processed
        self.last_candle_time = candle_end_time
        
        # Get Heikin-Ashi indicator (ONLY indicator used for entry)
        last_ha = self.heikin_ashi_calc.get_last_candle()
        if not last_ha:
            return None
        
        # Get HA color (TradingView style: GREEN when HA_C > HA_O, RED when HA_C < HA_O)
        ha_color = last_ha.get('ha_color', 'RED' if last_ha['ha_close'] < last_ha['ha_open'] else 'GREEN')
        
        # Entry logic based ONLY on Heikin-Ashi:
        # - GREEN (uptrend) → BUY CALL
        # - RED (downtrend) → BUY PUT
        if ha_color == 'GREEN':
            logger.info(f"📈 UPTREND detected (HA: GREEN) → Signal: BUY CALL")
            return 'BUY'  # Uptrend: Buy CALL
        elif ha_color == 'RED':
            logger.info(f"📉 DOWNTREND detected (HA: RED) → Signal: BUY PUT")
            return 'SELL'  # Downtrend: Buy PUT
        
        return None
    
    def enter_trade(self, signal: str, futures_ltp: Decimal) -> bool:
        """
        Enter a trade
        
        Args:
            signal: 'BUY' for CALL, 'SELL' for PUT
            futures_ltp: Current futures LTP
        
        Returns:
            bool: True if entry successful
        """
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
                        quantity=LOT_SIZE,
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
                'lot_size': LOT_SIZE
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
            
            logger.info(
                f"{'[DRY-RUN]' if self.dry_run else '[LIVE]'} "
                f"ENTRY: {side} {option_symbol} @ ₹{option_ltp:.2f} "
                f"(Futures: ₹{futures_ltp:.2f}, Strike: {strike})"
            )
            
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
        
        # 1. TAKE PROFIT - FUTURES +60 POINTS
        if 'CE' in side:  # CALL
            futures_profit = current_futures_ltp - entry_future_price
            if futures_profit >= Decimal(str(TARGET_POINTS)):
                logger.info(f"✅ TARGET REACHED: Futures profit = {futures_profit:.2f} points (Target: {TARGET_POINTS})")
                return 'FUTURES_TARGET'
        else:  # PUT
            futures_profit = entry_future_price - current_futures_ltp
            if futures_profit >= Decimal(str(TARGET_POINTS)):
                logger.info(f"✅ TARGET REACHED: Futures profit = {futures_profit:.2f} points (Target: {TARGET_POINTS})")
                return 'FUTURES_TARGET'
        
        # 2. OPTION PROFIT TARGET (+15%)
        option_pct = (current_option_ltp - entry_premium) / entry_premium
        if option_pct >= OPTION_TARGET_PCT:
            return 'OPTION_TARGET'
        
        # 3. REVERSAL EXIT - Check Heikin-Ashi color reversal (ONLY HA-based)
        current_ha = self.heikin_ashi_calc.get_last_candle()
        
        if current_ha:
            # Get current HA color
            current_ha_color = current_ha.get('ha_color', 'RED' if current_ha['ha_close'] < current_ha['ha_open'] else 'GREEN')
            
            # For CALL (uptrend entry): Exit if HA turns RED (downtrend reversal)
            if 'CE' in side:
                if current_ha_color == 'RED':
                    return 'TREND_REVERSAL'
            
            # For PUT (downtrend entry): Exit if HA turns GREEN (uptrend reversal)
            elif 'PE' in side:
                if current_ha_color == 'GREEN':
                    logger.info(f"🔄 TREND REVERSAL: HA turned GREEN (uptrend) → Exit PUT position")
                    return 'TREND_REVERSAL'
        
        # 4. STOPLOSS
        # Option premium -30%
        option_loss_pct = (entry_premium - current_option_ltp) / entry_premium
        if option_loss_pct >= STOPLOSS_OPTION_PCT:
            return 'STOPLOSS'
        
        # Futures adverse movement 30 points
        if 'CE' in side:  # CALL
            futures_loss = entry_future_price - current_futures_ltp
            if futures_loss >= Decimal(str(STOPLOSS_FUTURES_POINTS)):
                return 'STOPLOSS'
        else:  # PUT
            futures_loss = current_futures_ltp - entry_future_price
            if futures_loss >= Decimal(str(STOPLOSS_FUTURES_POINTS)):
                return 'STOPLOSS'
        
        # 5. TIME EXIT (3:20 PM) - Note: This is also checked continuously in main loop
        # Keeping this check here for safety, but main loop check takes priority
        current_time = get_ist_now()
        if current_time.time() >= SQUARE_OFF_TIME:
            logger.info(f"⏰ TIME EXIT triggered in check_exit_conditions: {current_time.time()} >= {SQUARE_OFF_TIME}")
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
            LOT_SIZE
        )
        pnl_percent = ((exit_premium - entry['entry_premium']) / entry['entry_premium'] * 100) if entry['entry_premium'] > 0 else Decimal('0')
        
        # Place exit order (or simulate)
        if not self.dry_run:
            try:
                option_instrument = self.alice_client.get_instrument_by_symbol('NFO', entry['option_symbol'])
                order = self.alice_client.place_order(
                    instrument=option_instrument,
                    transaction_type=self.alice_client.TRANSACTION_TYPE_SELL,
                    quantity=LOT_SIZE,
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
            lot_size=LOT_SIZE
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
        
        logger.info(
            f"{'[DRY-RUN]' if self.dry_run else '[LIVE]'} "
            f"EXIT: {exit_reason} | P&L: ₹{pnl_amount:.2f} ({pnl_percent:.2f}%)"
        )
        
        # Clear position
        self.current_position = None
        self.option_symbol = None
        self.option_ltp = None
        
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
            
            # Check entry/exit after HA candle is created (only HA-based logic)
            # Check entry (only after candle close)
            if not self.current_position:
                signal = self.check_entry_conditions()
                if signal and self.futures_ltp:
                    self.enter_trade(signal, self.futures_ltp)
            
            # Check exit (time exit is checked continuously in main loop, so skip it here)
            if self.current_position:
                # Check all exit conditions except time (time is checked in main loop)
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
        
        # Initialize strategy
        candle_source = options.get('candle_source', 'futures')
        strategy = HeikinAshiStrategy(
            dry_run=dry_run, 
            strategy_name="Heikin Ashi Strategy", 
            debug=debug,
            candle_source=candle_source
        )
        strategy.strategy_obj = strategy_obj
        
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
        if current_time_obj > TRADE_END_TIME:
            self.stdout.write(
                self.style.WARNING(
                    f"⏰ Trading window already closed: Current time {current_time_obj.strftime('%H:%M:%S')} > "
                    f"End time {TRADE_END_TIME.strftime('%H:%M:%S')}"
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
                
                # Stop strategy after TRADE_END_TIME (3:30 PM)
                if current_time_obj > TRADE_END_TIME:
                    self.stdout.write(
                        self.style.WARNING(
                            f"\n⏰ Trading window closed: Current time {current_time_obj.strftime('%H:%M:%S')} > "
                            f"End time {TRADE_END_TIME.strftime('%H:%M:%S')}"
                        )
                    )
                    # Exit any open position before stopping
                    if strategy.current_position:
                        strategy.exit_trade('TIME')
                    break
                
                # Check time exit continuously (not just on candle close) - Exit positions at 3:20 PM
                if strategy.current_position:
                    if current_time_obj >= SQUARE_OFF_TIME:
                        logger.info(f"⏰ TIME EXIT: Current time {current_time_obj} >= Square-off time {SQUARE_OFF_TIME}")
                        strategy.exit_trade('TIME')
                
                # Process futures LTP
                if strategy.futures_ltp:
                    strategy.process_ltp(strategy.futures_ltp, current_time)
                
                # Display status
                status_parts = []
                if strategy.futures_ltp:
                    status_parts.append(f"Futures: ₹{strategy.futures_ltp:,.2f}")
                
                # Show Heikin-Ashi indicator (ONLY indicator used)
                last_ha = strategy.heikin_ashi_calc.get_last_candle()
                
                if last_ha:
                    # Get HA color (TradingView style: GREEN when HA_C > HA_O, RED when HA_C < HA_O)
                    ha_color = last_ha.get('ha_color', 'RED' if last_ha['ha_close'] < last_ha['ha_open'] else 'GREEN')
                    ha_emoji = "🟢" if ha_color == 'GREEN' else "🔴"
                    status_parts.append(f"HA: {ha_emoji} {ha_color}")
                else:
                    status_parts.append("HA: ⏳ Initializing...")
                
                if strategy.current_position:
                    entry = strategy.current_position
                    option_ltp = strategy.get_option_ltp() or entry['entry_premium']
                    pnl = calculate_pnl(entry['entry_premium'], option_ltp, entry['side'], LOT_SIZE)
                    status_parts.append(
                        f"IN TRADE: {entry['option_symbol']} | Entry: ₹{entry['entry_premium']:.2f} | "
                        f"Current: ₹{option_ltp:.2f} | P&L: ₹{pnl:.2f}"
                    )
                
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


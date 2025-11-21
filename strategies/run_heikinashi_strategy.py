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


class HeikinAshiStrategy:
    """Heikin Ashi strategy implementation"""
    
    def __init__(self, dry_run: bool = True, strategy_name: str = "Heikin Ashi Strategy"):
        self.dry_run = dry_run
        self.strategy_name = strategy_name
        self.strategy_obj = None
        
        # Indicators
        self.candle_aggregator = CandleAggregator(candle_interval_minutes=15)
        self.heikin_ashi_calc = HeikinAshiCalculator()
        self.super_trend_calc = SuperTrendCalculator(atr_period=10, multiplier=Decimal('3.0'))
        self.macd_calc = MACDCalculator(fast_period=12, slow_period=26, signal_period=9)
        self.strike_selector = StrikeSelector()
        
        # State tracking
        self.current_position: Optional[Dict] = None
        self.previous_st: Optional[Dict] = None
        self.previous_ha: Optional[Dict] = None
        self.previous_macd: Optional[Dict] = None
        self.last_candle_time: Optional[datetime] = None
        
        # WebSocket data
        self.futures_ltp: Optional[Decimal] = None
        self.option_ltp: Optional[Decimal] = None
        self.futures_symbol: Optional[str] = None
        self.option_symbol: Optional[str] = None
        
        # Alice Blue client
        self.alice_client = None
        self.ws_connected = False
    
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
        
        Returns:
            'BUY' for CALL entry, 'SELL' for PUT entry, None if no entry
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
        
        # Mark this candle as processed
        self.last_candle_time = candle_end_time
        
        # Get indicators
        last_ha = self.heikin_ashi_calc.get_last_candle()
        last_st = self.super_trend_calc.get_last_super_trend()
        last_macd = self.macd_calc.get_last_macd()
        
        if not last_ha or not last_st or not last_macd:
            return None
        
        # Check UP-TREND ENTRY (BUY CALL)
        # SuperTrend direction = up (GREEN means uptrend)
        st_up = last_st.get('color') == 'GREEN'
        # HA close > HA open (green HA candle)
        ha_green = last_ha['ha_close'] > last_ha['ha_open']
        # MACD line > MACD signal line
        macd_bullish = last_macd['macd_line'] > last_macd['signal_line']
        
        if st_up and ha_green and macd_bullish:
            return 'BUY'
        
        # Check DOWN-TREND ENTRY (BUY PUT)
        # SuperTrend direction = down (RED means downtrend)
        st_down = last_st.get('color') == 'RED'
        # HA close < HA open (red HA candle)
        ha_red = last_ha['ha_close'] < last_ha['ha_open']
        # MACD line < MACD signal line
        macd_bearish = last_macd['macd_line'] < last_macd['signal_line']
        
        if st_down and ha_red and macd_bearish:
            return 'SELL'
        
        # Mixed signals - no entry
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
            # Select strike
            spot_price = futures_ltp  # Use futures LTP as spot proxy
            option_symbol, strike, expiry_date = self.strike_selector.select_strike(
                spot_price=spot_price,
                signal_type=signal,
                strong_momentum=False,
                futures_symbol=self.futures_symbol
            )
            
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
            
            # Update previous indicators for reversal detection
            self.previous_st = self.super_trend_calc.get_last_super_trend()
            self.previous_ha = self.heikin_ashi_calc.get_last_candle()
            self.previous_macd = self.macd_calc.get_last_macd()
            
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
                return 'FUTURES_TARGET'
        else:  # PUT
            futures_profit = entry_future_price - current_futures_ltp
            if futures_profit >= Decimal(str(TARGET_POINTS)):
                return 'FUTURES_TARGET'
        
        # 2. OPTION PROFIT TARGET (+15%)
        option_pct = (current_option_ltp - entry_premium) / entry_premium
        if option_pct >= OPTION_TARGET_PCT:
            return 'OPTION_TARGET'
        
        # 3. REVERSAL EXIT
        current_st = self.super_trend_calc.get_last_super_trend()
        current_ha = self.heikin_ashi_calc.get_last_candle()
        current_macd = self.macd_calc.get_last_macd()
        
        if trend_reversal_detected(
            current_st, self.previous_st,
            current_ha, self.previous_ha,
            current_macd, self.previous_macd
        ):
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
        
        # 5. TIME EXIT (3:20 PM)
        current_time = get_ist_now()
        if current_time.time() >= SQUARE_OFF_TIME:
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
        
        # Save to database
        if self.strategy_obj:
            try:
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
                logger.error(f"Failed to save trade log: {e}")
        
        logger.info(
            f"{'[DRY-RUN]' if self.dry_run else '[LIVE]'} "
            f"EXIT: {exit_reason} | P&L: ₹{pnl_amount:.2f} ({pnl_percent:.2f}%)"
        )
        
        # Clear position
        self.current_position = None
        self.option_symbol = None
        self.option_ltp = None
        
        return True
    
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
            # Convert to Heikin Ashi
            ha_candle = self.heikin_ashi_calc.add_candle(new_candle)
            
            # Calculate SuperTrend
            super_trend = self.super_trend_calc.add_candle(ha_candle)
            
            # Calculate MACD
            macd = self.macd_calc.add_candle(ha_candle)
            
            # Only check entry/exit after indicators are calculated
            if super_trend and macd:
                # Check entry (only after candle close)
                if not self.current_position:
                    signal = self.check_entry_conditions()
                    if signal and self.futures_ltp:
                        self.enter_trade(signal, self.futures_ltp)
                
                # Check exit
                if self.current_position:
                    exit_reason = self.check_exit_conditions()
                    if exit_reason:
                        self.exit_trade(exit_reason)
                    
                    # Update previous indicators for next reversal check
                    self.previous_st = self.super_trend_calc.get_last_super_trend()
                    self.previous_ha = self.heikin_ashi_calc.get_last_candle()
                    self.previous_macd = self.macd_calc.get_last_macd()


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
    
    def handle(self, *args, **options):
        dry_run = options.get('dry_run', True)
        loop = options.get('loop', False)
        interval = options.get('interval', 5)
        
        mode_str = "DRY-RUN" if dry_run else "LIVE"
        self.stdout.write(self.style.SUCCESS(f"✅ {mode_str} MODE - {'No real orders' if dry_run else 'REAL ORDERS ENABLED'}"))
        
        # Get or create strategy
        strategy_obj, _ = Strategy.objects.get_or_create(
            name="Heikin Ashi Strategy",
            defaults={'enabled': True}
        )
        
        # Initialize strategy
        strategy = HeikinAshiStrategy(dry_run=dry_run, strategy_name="Heikin Ashi Strategy")
        strategy.strategy_obj = strategy_obj
        
        # Initialize Alice Blue
        if not strategy.initialize_alice_blue():
            self.stdout.write(self.style.ERROR("❌ Failed to initialize Alice Blue"))
            return
        
        self.stdout.write("🔄 Starting strategy loop...")
        self.stdout.write("Press Ctrl+C to stop")
        
        try:
            while True:
                current_time = get_ist_now()
                
                # Process futures LTP
                if strategy.futures_ltp:
                    strategy.process_ltp(strategy.futures_ltp, current_time)
                
                # Display status
                status_parts = []
                if strategy.futures_ltp:
                    status_parts.append(f"Futures: ₹{strategy.futures_ltp:,.2f}")
                
                # Show indicators
                last_st = strategy.super_trend_calc.get_last_super_trend()
                last_ha = strategy.heikin_ashi_calc.get_last_candle()
                last_macd = strategy.macd_calc.get_last_macd()
                
                if last_st:
                    st_emoji = "🟢" if last_st['color'] == 'GREEN' else "🔴"
                    status_parts.append(f"ST: {st_emoji} {last_st['color']}")
                
                if last_ha:
                    ha_color = "GREEN" if last_ha['ha_close'] > last_ha['ha_open'] else "RED"
                    status_parts.append(f"HA: {ha_color}")
                
                if last_macd:
                    macd_signal = "BULL" if last_macd['macd_line'] > last_macd['signal_line'] else "BEAR"
                    status_parts.append(f"MACD: {macd_signal}")
                
                if strategy.current_position:
                    entry = strategy.current_position
                    option_ltp = strategy.get_option_ltp() or entry['entry_premium']
                    pnl = calculate_pnl(entry['entry_premium'], option_ltp, entry['side'], LOT_SIZE)
                    status_parts.append(f"IN TRADE: {entry['option_symbol']} | P&L: ₹{pnl:.2f}")
                
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


"""
Backtest momentum breakout strategy using historical CSV data
"""
import os
import csv
import logging
from decimal import Decimal
from datetime import datetime, date, time as dt_time
from typing import List, Dict, Optional
from django.core.management.base import BaseCommand
from django.conf import settings
from trading.models import Strategy
from trading.services.strike_selector import StrikeSelector
from trading.services.momentum import compute_ema, compute_rsi
from trading.utils.expiry_functions import round_to_nearest_strike, get_trading_thursday_expiry, build_option_symbol
from trading.utils.time_helpers import get_ist_now

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Backtest momentum breakout strategy on historical BankNifty futures data'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--from',
            type=str,
            required=True,
            dest='from_date',
            help='Start date (YYYY-MM-DD)',
        )
        parser.add_argument(
            '--to',
            type=str,
            required=True,
            dest='to_date',
            help='End date (YYYY-MM-DD)',
        )
        parser.add_argument(
            '--capital',
            type=float,
            default=100000,
            help='Starting capital (default: 100000)',
        )
        parser.add_argument(
            '--csv-file',
            type=str,
            help='CSV file path (default: data/BANKNIFTY_2025_11.csv)',
            default=None
        )
    
    def handle(self, *args, **options):
        from_date_str = options['from_date']
        to_date_str = options['to_date']
        capital = Decimal(str(options['capital']))
        csv_file = options.get('csv_file')
        
        # Parse dates
        try:
            from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
            to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
        except ValueError as e:
            self.stdout.write(self.style.ERROR(f"❌ Invalid date format: {e}"))
            self.stdout.write("Use format: YYYY-MM-DD")
            return
        
        # Determine CSV file path
        if not csv_file:
            try:
                BASE_DIR = settings.BASE_DIR
            except:
                from pathlib import Path
                BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
            
            csv_file = os.path.join(BASE_DIR, 'data', 'BANKNIFTY_2025_11.csv')
        
        if not os.path.exists(csv_file):
            self.stdout.write(self.style.ERROR(f"❌ CSV file not found: {csv_file}"))
            return
        
        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(self.style.SUCCESS("📊 BACKTEST: Momentum Breakout Strategy"))
        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(f"📅 Date Range: {from_date} to {to_date}")
        self.stdout.write(f"💰 Starting Capital: ₹{capital:,.2f}")
        self.stdout.write(f"📄 CSV File: {csv_file}")
        self.stdout.write("")
        
        # Load CSV data
        data_points = self.load_csv_data(csv_file, from_date, to_date)
        
        if not data_points:
            self.stdout.write(self.style.ERROR("❌ No data found in CSV for the specified date range"))
            return
        
        self.stdout.write(f"📊 Loaded {len(data_points)} data points")
        self.stdout.write("")
        
        # Run backtest
        trades = self.run_backtest(data_points, capital, from_date, to_date)
        
        # Calculate summary
        summary = self.calculate_summary(trades, capital)
        
        # Display results
        self.display_summary(summary)
        
        # Save to CSV
        self.save_trades_to_csv(trades)
        
        self.stdout.write(self.style.SUCCESS("\n✅ Backtest completed!"))
    
    def load_csv_data(self, csv_file: str, from_date: date, to_date: date) -> List[Dict]:
        """Load historical data from CSV"""
        data_points = []
        
        try:
            with open(csv_file, 'r') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    # Parse timestamp
                    timestamp_str = row.get('timestamp', '').strip()
                    if not timestamp_str:
                        continue
                    
                    try:
                        # Try ISO format first
                        timestamp = datetime.fromisoformat(timestamp_str.replace(' ', 'T'))
                    except:
                        try:
                            # Try other formats
                            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                        except:
                            try:
                                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
                            except:
                                logger.warning(f"Could not parse timestamp: {timestamp_str}")
                                continue
                    
                    # Filter by date range
                    if timestamp.date() < from_date or timestamp.date() > to_date:
                        continue
                    
                    # Parse OHLC
                    try:
                        open_price = Decimal(str(row.get('open', 0)))
                        high_price = Decimal(str(row.get('high', 0)))
                        low_price = Decimal(str(row.get('low', 0)))
                        close_price = Decimal(str(row.get('close', 0)))
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not parse prices in row: {e}")
                        continue
                    
                    # Use close price as LTP for backtesting
                    data_points.append({
                        'timestamp': timestamp,
                        'ltp': close_price,
                        'open': open_price,
                        'high': high_price,
                        'low': low_price,
                        'close': close_price,
                    })
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error reading CSV: {e}"))
            return []
        
        # Sort by timestamp
        data_points.sort(key=lambda x: x['timestamp'])
        
        return data_points
    
    def run_backtest(self, data_points: List[Dict], capital: Decimal, from_date: date, to_date: date) -> List[Dict]:
        """Run backtest simulation"""
        trades = []
        current_position = None
        price_samples = []  # Track last 3 prices
        price_history = []  # Track price history for EMA/RSI calculations (keep last 50)
        range_high = None
        range_low = None
        range_established = False  # Flag to track if range is established
        last_date = None  # Track last processed date to reset range daily
        yesterday_closing_price = None  # Track yesterday's closing price for ATM strike selection
        
        # ========================================
        # Strategy Parameters (Unified - Same as Live)
        # ========================================
        TARGET_PCT = Decimal('1.5') / 100        # Target: +1.5%
        STOPLOSS_PCT = Decimal('0.7') / 100       # Stoploss: -0.7%
        TRAILING_TRIGGER_PCT = Decimal('0.5') / 100  # Trailing SL triggers after +0.5%
        LOT_SIZE = 35                             # ✅ BankNifty lot size (fixed)
        SQUARE_OFF_TIME = dt_time(15, 30)         # Auto exit at 3:30 PM
        TRADE_START_TIME = dt_time(9, 30)         # Trading window start (9:30 AM)
        TRADE_END_TIME = dt_time(15, 30)          # Trading window end (3:30 PM - market close)
        RISK_PER_TRADE_PCT = Decimal('1.0') / 100  # Risk 1% of capital per trade
        
        # Optimized Entry Filters (very lenient to allow breakouts)
        RSI_BUY_MIN = Decimal('55')              # Lenient: 55 (allows more BUY signals)
        RSI_SELL_MAX = Decimal('50')             # Lenient: 50 (allows more SELL signals)
        EMA_GAP_REQUIRED = Decimal('0.0001')     # Very lenient: 0.01% gap (allows breakouts when price action is clear, even if EMAs lag)
        
        # Strategy parameters
        stoploss_pct = STOPLOSS_PCT
        target_pct = TARGET_PCT
        trailing_trigger_pct = TRAILING_TRIGGER_PCT
        current_stoploss_pct = STOPLOSS_PCT  # Dynamic stoploss (for trailing)
        square_off_time = SQUARE_OFF_TIME
        
        # Initialize strike selector
        strike_selector = StrikeSelector()
        
        self.stdout.write(self.style.SUCCESS("🔄 Running backtest simulation..."))
        self.stdout.write("")
        
        # Process all data points
        for i, data_point in enumerate(data_points):
            timestamp = data_point['timestamp']
            futures_ltp = data_point['ltp']
            current_date = timestamp.date()
            
            # Reset range daily at market open (9:15 AM) or when date changes
            if last_date is None or current_date != last_date:
                # New day - reset range
                if last_date is not None:
                    # Store yesterday's closing price (last price of previous day)
                    # Find the last price of the previous day from data_points
                    prev_day_prices = [dp['ltp'] for dp in data_points[:i] if dp['timestamp'].date() == last_date]
                    if prev_day_prices:
                        yesterday_closing_price = prev_day_prices[-1]  # Last price of previous day
                    
                    # Close any open position from previous day
                    if current_position:
                        # Calculate option exit price using improved model
                        entry_futures_ltp = current_position['futures_ltp_entry']
                        futures_change_pct = (futures_ltp - entry_futures_ltp) / entry_futures_ltp if entry_futures_ltp > 0 else Decimal('0')
                        option_volatility_multiplier = Decimal('4.0')
                        option_change_pct = futures_change_pct * option_volatility_multiplier
                        entry_price = current_position['entry_price']
                        position_side = current_position.get('side', '')
                        
                        if "CE" in position_side:
                            option_exit_price = entry_price * (Decimal('1') + option_change_pct)
                        else:
                            option_exit_price = entry_price * (Decimal('1') - option_change_pct)
                        
                        if option_exit_price < Decimal('0.01'):
                            option_exit_price = Decimal('0.01')
                        
                        exit_trade = {
                            'timestamp': timestamp,
                            'action': 'EXIT',
                            'symbol': current_position['symbol'],
                            'side': current_position['side'],
                            'entry_price': entry_price,
                            'exit_price': option_exit_price,
                            'pnl': self._calculate_pnl(entry_price, option_exit_price, position_side, current_position.get('total_units', LOT_SIZE)),
                            'reason': 'TIME',
                            'lot_size': current_position.get('lot_size', LOT_SIZE),
                            'breakout_pct': current_position.get('breakout_pct', Decimal('0.001')) * 100,
                            'range_width': current_position.get('range_width', Decimal('0'))
                        }
                        trades.append(exit_trade)
                        self._print_exit(exit_trade)
                        current_position = None
                
                # Reset range for new day
                range_established = False
                range_high = None
                range_low = None
                price_samples = []  # Reset price samples for new day
                last_date = current_date
                logger.debug(f"New day: {current_date} - Range reset")
            
            # Check if market closed (3:30 PM)
            if timestamp.time() >= square_off_time:
                # Close any open position
                if current_position:
                    # Calculate option exit price using improved model
                    entry_futures_ltp = current_position['futures_ltp_entry']
                    futures_change_pct = (futures_ltp - entry_futures_ltp) / entry_futures_ltp if entry_futures_ltp > 0 else Decimal('0')
                    option_volatility_multiplier = Decimal('4.0')
                    option_change_pct = futures_change_pct * option_volatility_multiplier
                    entry_price = current_position['entry_price']
                    position_side = current_position.get('side', '')
                    
                    if "CE" in position_side:
                        option_exit_price = entry_price * (Decimal('1') + option_change_pct)
                    else:
                        option_exit_price = entry_price * (Decimal('1') - option_change_pct)
                    
                    if option_exit_price < Decimal('0.01'):
                        option_exit_price = Decimal('0.01')
                    
                    exit_trade = {
                        'timestamp': timestamp,
                        'action': 'EXIT',
                        'symbol': current_position['symbol'],
                        'side': current_position['side'],
                        'entry_price': entry_price,
                        'exit_price': option_exit_price,
                        'pnl': self._calculate_pnl(entry_price, option_exit_price, position_side, current_position.get('total_units', LOT_SIZE)),
                        'reason': 'TIME'
                    }
                    trades.append(exit_trade)
                    self._print_exit(exit_trade)
                    current_position = None
                continue
            
            # Track price samples (last 3) - only during trading hours (9:15 AM - 3:30 PM)
            if timestamp.time() >= dt_time(9, 15):
                price_samples.append(futures_ltp)
                if len(price_samples) > 3:
                    price_samples.pop(0)
            
            # Track price history for EMA/RSI calculations (keep last 50)
            price_history.append(futures_ltp)
            if len(price_history) > 50:
                price_history.pop(0)
            
            # Establish range after at least 3 data points (reset daily)
            if len(price_samples) == 3 and not range_established and not current_position:
                range_high = max(price_samples)
                range_low = min(price_samples)
                range_width = range_high - range_low
                
                # Calculate dynamic breakout percentage for display
                if range_width < 40:
                    breakout_pct = Decimal('0.0005')
                elif 40 <= range_width <= 80:
                    breakout_pct = Decimal('0.001')
                else:
                    breakout_pct = Decimal('0.0015')
                
                range_established = True
                logger.debug(f"Range established on {current_date}: {range_low:.2f} - {range_high:.2f} | Dynamic Breakout %: {breakout_pct*100:.2f}% | Range width: {range_width:.0f} pts")
            
            # Detect breakout (check every price after range is established)
            # Only allow new entries during trading window (9:30 AM - 3:30 PM)
            is_in_trading_window = (timestamp.time() >= TRADE_START_TIME and 
                                   timestamp.time() <= TRADE_END_TIME)
            
            if range_established and not current_position and is_in_trading_window:
                # ========================================
                # Dynamic Breakout Logic (Same as Live)
                # ========================================
                range_width = range_high - range_low
                
                # Determine dynamic breakout percentage based on range width
                if range_width < 40:
                    breakout_pct = Decimal('0.0005')  # 0.05%
                elif 40 <= range_width <= 80:
                    breakout_pct = Decimal('0.001')   # 0.1%
                else:  # range_width > 80
                    breakout_pct = Decimal('0.0015')  # 0.15%
                
                # Breakout detection using dynamic percentage
                breakout_signal = None
                if futures_ltp >= range_high * (Decimal('1') + breakout_pct):
                    breakout_signal = "BUY"
                elif futures_ltp <= range_low * (Decimal('1') - breakout_pct):
                    breakout_signal = "SELL"
                
                # If breakout detected, apply momentum filters before entry
                if breakout_signal:
                    # Check momentum filters (pass constants as parameters)
                    if not self._check_momentum_filters_backtest(breakout_signal, futures_ltp, price_history, 
                                                                  RSI_BUY_MIN, RSI_SELL_MAX, EMA_GAP_REQUIRED):
                        logger.debug(f"Momentum filters failed for {breakout_signal} signal - skipping entry")
                        continue
                    
                    # Select option - Use yesterday's closing price for ATM strike selection
                    strike_reference_price = futures_ltp  # Default to current futures LTP
                    if yesterday_closing_price:
                        strike_reference_price = yesterday_closing_price
                        logger.debug(f"Using yesterday's closing price for ATM strike: {strike_reference_price:.2f}")
                    else:
                        logger.debug(f"Yesterday's closing not available. Using current futures LTP: {strike_reference_price:.2f}")
                    
                    try:
                        option_symbol, strike, expiry_date = strike_selector.select_strike(
                            spot_price=strike_reference_price,  # Use yesterday's closing for ATM strike
                            signal_type=breakout_signal,
                            strong_momentum=False,
                            reference_date=timestamp.date()
                        )
                        
                        # Simulate option entry price (use futures LTP as proxy)
                        # For ATM options, approximate price as 0.2% of futures (rough estimate)
                        option_entry_price = futures_ltp * Decimal('0.002')  # Rough estimate: 0.2% of futures
                        
                        # Calculate position size based on capital and risk
                        # Risk amount = capital * risk_per_trade_pct
                        risk_amount = capital * RISK_PER_TRADE_PCT
                        # Stoploss per unit = entry_price * stoploss_pct
                        stoploss_per_unit = option_entry_price * stoploss_pct
                        # Risk per lot = stoploss_per_unit * LOT_SIZE
                        risk_per_lot = stoploss_per_unit * LOT_SIZE
                        # Number of lots = risk_amount / risk_per_lot (rounded down)
                        if risk_per_lot > 0:
                            num_lots = int(risk_amount / risk_per_lot)
                            num_lots = max(1, num_lots)  # Minimum 1 lot
                        else:
                            num_lots = 1
                        
                        # Total units = num_lots * LOT_SIZE
                        total_units = num_lots * LOT_SIZE
                        
                        current_position = {
                            'entry_time': timestamp,
                            'symbol': option_symbol,
                            'side': f"BUY_CE" if breakout_signal == "BUY" else "BUY_PE",
                            'entry_price': option_entry_price,
                            'futures_ltp_entry': futures_ltp,
                            'strike': strike,
                            'expiry_date': expiry_date,
                            'num_lots': num_lots,
                            'total_units': total_units,
                            'lot_size': LOT_SIZE,
                            'breakout_pct': breakout_pct,
                            'range_width': range_width
                        }
                        
                        # Reset trailing stoploss to initial value on new entry
                        current_stoploss_pct = STOPLOSS_PCT
                        
                        entry_trade = {
                            'timestamp': timestamp,
                            'action': 'ENTRY',
                            'symbol': option_symbol,
                            'side': current_position['side'],
                            'entry_price': option_entry_price,
                            'exit_price': None,
                            'pnl': None,
                            'reason': None,
                            'futures_ltp': futures_ltp,
                            'strike': strike,
                            'lot_size': LOT_SIZE,
                            'breakout_pct': breakout_pct * 100,
                            'range_width': range_width
                        }
                        trades.append(entry_trade)
                        self._print_entry(entry_trade)
                        
                    except Exception as e:
                        logger.error(f"Error selecting option: {e}")
                        continue
            
            # If in trade → check exit conditions
            if current_position:
                # Simulate option LTP with more realistic volatility
                # Options move much more than futures (delta + gamma effect)
                entry_futures_ltp = current_position['futures_ltp_entry']
                futures_change_pct = (futures_ltp - entry_futures_ltp) / entry_futures_ltp if entry_futures_ltp > 0 else Decimal('0')
                
                # For ATM options, approximate delta ~0.5, but with gamma, total move is amplified
                # Use a multiplier to simulate option volatility (typically 3-5x futures move)
                option_volatility_multiplier = Decimal('4.0')  # Options move ~4x the underlying
                option_change_pct = futures_change_pct * option_volatility_multiplier
                
                entry_price = current_position['entry_price']
                position_side = current_position.get('side', '')
                
                # Calculate option exit price based on entry price and change
                if "CE" in position_side:  # CALL: profit when futures goes up
                    option_ltp = entry_price * (Decimal('1') + option_change_pct)
                else:  # PUT: profit when futures goes down
                    option_ltp = entry_price * (Decimal('1') - option_change_pct)
                
                # Ensure option price doesn't go negative
                if option_ltp < Decimal('0.01'):
                    option_ltp = Decimal('0.01')
                
                # Calculate P&L percentage
                pnl_pct = (option_ltp - entry_price) / entry_price if entry_price > 0 else Decimal('0')
                
                # Apply trailing stoploss logic
                current_stoploss_pct = self._update_trailing_stoploss_backtest(
                    option_ltp, entry_price, position_side, current_stoploss_pct, trailing_trigger_pct
                )
                
                # Check exit conditions
                exit_reason = None
                if pnl_pct >= target_pct:
                    exit_reason = 'TARGET'
                elif pnl_pct <= -current_stoploss_pct:
                    exit_reason = 'STOPLOSS'
                elif timestamp.time() >= square_off_time:
                    exit_reason = 'TIME'
                
                if exit_reason:
                    exit_trade = {
                        'timestamp': timestamp,
                        'action': 'EXIT',
                        'symbol': current_position['symbol'],
                        'side': current_position['side'],
                        'entry_price': entry_price,
                        'exit_price': option_ltp,
                        'pnl': self._calculate_pnl(entry_price, option_ltp, position_side, current_position.get('total_units', LOT_SIZE)),
                        'reason': exit_reason,
                        'futures_ltp': futures_ltp,
                        'lot_size': current_position.get('lot_size', LOT_SIZE),
                        'breakout_pct': current_position.get('breakout_pct', Decimal('0.001')) * 100,
                        'range_width': current_position.get('range_width', Decimal('0'))
                    }
                    trades.append(exit_trade)
                    self._print_exit(exit_trade)
                    current_position = None
        
        # Close any remaining open position at the end
        if current_position:
            last_data_point = data_points[-1]
            last_timestamp = last_data_point['timestamp']
            last_futures_ltp = last_data_point['ltp']
            
            # Calculate option exit price using improved model
            entry_futures_ltp = current_position['futures_ltp_entry']
            futures_change_pct = (last_futures_ltp - entry_futures_ltp) / entry_futures_ltp if entry_futures_ltp > 0 else Decimal('0')
            option_volatility_multiplier = Decimal('4.0')
            option_change_pct = futures_change_pct * option_volatility_multiplier
            entry_price = current_position['entry_price']
            position_side = current_position.get('side', '')
            
            if "CE" in position_side:
                option_exit_price = entry_price * (Decimal('1') + option_change_pct)
            else:
                option_exit_price = entry_price * (Decimal('1') - option_change_pct)
            
            if option_exit_price < Decimal('0.01'):
                option_exit_price = Decimal('0.01')
            
            exit_trade = {
                'timestamp': last_timestamp,
                'action': 'EXIT',
                'symbol': current_position['symbol'],
                'side': current_position['side'],
                'entry_price': entry_price,
                'exit_price': option_exit_price,
                'pnl': self._calculate_pnl(entry_price, option_exit_price, position_side, current_position.get('total_units', LOT_SIZE)),
                'reason': 'TIME',
                'lot_size': current_position.get('lot_size', LOT_SIZE),
                'breakout_pct': current_position.get('breakout_pct', Decimal('0.001')) * 100,
                'range_width': current_position.get('range_width', Decimal('0'))
            }
            trades.append(exit_trade)
            self._print_exit(exit_trade)
            current_position = None
        
        return trades
    
    def _check_momentum_filters_backtest(self, signal_type: str, current_price: Decimal, price_history: List[Decimal],
                                         rsi_buy_min: Decimal, rsi_sell_max: Decimal, ema_gap_required: Decimal) -> bool:
        """
        Check momentum filters before entry (for backtest) - OPTIMIZED:
        - BUY: EMA5 > EMA20 * (1 + ema_gap_required) AND RSI > rsi_buy_min
        - SELL: EMA5 < EMA20 * (1 - ema_gap_required) AND RSI < rsi_sell_max
        
        Args:
            signal_type: 'BUY' or 'SELL'
            current_price: Current futures LTP
            price_history: List of historical prices
            rsi_buy_min: Minimum RSI for BUY signals
            rsi_sell_max: Maximum RSI for SELL signals
            ema_gap_required: Required gap between EMA5 and EMA20 (e.g., 0.001 for 0.1%)
        
        Returns:
            bool: True if filters pass, False otherwise
        """
        if len(price_history) < 20:  # Need at least 20 prices for EMA20
            return False
        
        # Calculate EMAs
        ema5 = compute_ema(price_history, 5)
        ema20 = compute_ema(price_history, 20)
        rsi = compute_rsi(price_history, 14)
        
        if ema5 is None or ema20 is None or rsi is None:
            return False
        
        # Use parameters passed from run_backtest (balanced values)
        ema_gap = ema_gap_required
        
        # Apply filters based on signal type
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
    
    def _update_trailing_stoploss_backtest(self, current_price: Decimal, entry_price: Decimal, 
                                           position_side: str, current_stoploss_pct: Decimal, 
                                           trailing_trigger_pct: Decimal) -> Decimal:
        """
        Update trailing stoploss dynamically based on profit (for backtest)
        
        For BUY CALL: if current_price > entry_price * 1.005, move stoploss to current_price * 0.995
        For BUY PUT: if current_price < entry_price * 0.995, move stoploss to current_price * 1.005
        
        Args:
            current_price: Current option LTP
            entry_price: Entry price
            position_side: "BUY_CE" or "BUY_PE"
            current_stoploss_pct: Current stoploss percentage
            trailing_trigger_pct: Trigger percentage for trailing (e.g., 0.005 for 0.5%)
        
        Returns:
            Decimal: Updated stoploss percentage
        """
        trigger_multiplier = Decimal('1') + trailing_trigger_pct  # 1.005 for +0.5%
        trigger_multiplier_down = Decimal('1') - trailing_trigger_pct  # 0.995 for -0.5%
        
        if "CE" in position_side:  # BUY CALL
            # If current price is 0.5% above entry, activate trailing stoploss
            if current_price > entry_price * trigger_multiplier:
                # New stoploss: 0.5% below current price (protect 0.5% profit)
                new_stoploss_price = current_price * trigger_multiplier_down
                new_stoploss_pct = abs((new_stoploss_price - entry_price) / entry_price)
                
                # Only move stoploss up (less negative), never down
                if new_stoploss_pct < abs(current_stoploss_pct):
                    return -new_stoploss_pct  # Negative because it's a loss threshold
        
        elif "PE" in position_side:  # BUY PUT
            # If current price is 0.5% below entry, activate trailing stoploss
            # Note: For PUT, profit when price goes DOWN, so we check if current < entry * 0.995
            if current_price < entry_price * trigger_multiplier_down:
                # New stoploss: 0.5% above current price (protect 0.5% profit)
                new_stoploss_price = current_price * trigger_multiplier  # 1.005
                new_stoploss_pct = abs((new_stoploss_price - entry_price) / entry_price)
                
                # Only move stoploss up (less negative), never down
                if new_stoploss_pct < abs(current_stoploss_pct):
                    return -new_stoploss_pct  # Negative because it's a loss threshold
        
        return current_stoploss_pct
    
    def _calculate_pnl(self, entry_price: Decimal, exit_price: Decimal, side: str, lot_size: int = 35) -> Decimal:
        """
        Unified P&L calculation function (same as live).
        
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
    
    def _print_entry(self, trade: Dict):
        """Print trade entry"""
        side_display = "CALL" if "CE" in trade['side'] else "PUT"
        lot_size = trade.get('lot_size', 35)
        self.stdout.write(
            self.style.SUCCESS(
                f"🚀 [BACKTEST] ENTRY {side_display} {trade['symbol']} @ ₹{trade['entry_price']:,.2f} | Lot: {lot_size}"
            )
        )
    
    def _print_exit(self, trade: Dict):
        """Print trade exit"""
        side_display = "CALL" if "CE" in trade['side'] else "PUT"
        pnl_color = self.style.SUCCESS if trade['pnl'] > 0 else self.style.ERROR
        lot_size = trade.get('lot_size', 35)
        self.stdout.write(
            pnl_color(
                f"💰 [BACKTEST] EXIT {side_display} {trade['symbol']} @ ₹{trade['exit_price']:,.2f} | "
                f"P&L: ₹{trade['pnl']:,.2f} | Lot: {lot_size} | Reason: {trade['reason']}"
            )
        )
    
    def calculate_summary(self, trades: List[Dict], initial_capital: Decimal) -> Dict:
        """Calculate backtest summary metrics"""
        # Separate entry and exit trades
        entry_trades = [t for t in trades if t['action'] == 'ENTRY']
        exit_trades = [t for t in trades if t['action'] == 'EXIT']
        
        total_trades = len(exit_trades)
        
        if total_trades == 0:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_pnl': Decimal('0'),
                'max_drawdown': Decimal('0'),
                'initial_capital': initial_capital,
                'final_capital': initial_capital,
            }
        
        # Calculate P&L metrics
        # Ensure all pnl values are Decimal for consistency
        for trade in exit_trades:
            if trade['pnl'] is not None:
                if not isinstance(trade['pnl'], Decimal):
                    trade['pnl'] = Decimal(str(trade['pnl']))
        
        winning_trades = [t for t in exit_trades if t['pnl'] and t['pnl'] > 0]
        losing_trades = [t for t in exit_trades if t['pnl'] and t['pnl'] < 0]
        
        total_pnl = sum([t['pnl'] for t in exit_trades if t['pnl']])
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
        
        # Calculate max drawdown
        running_pnl = Decimal('0')
        peak_pnl = Decimal('0')
        max_drawdown = Decimal('0')
        
        for trade in exit_trades:
            if trade['pnl']:
                running_pnl += trade['pnl']
                if running_pnl > peak_pnl:
                    peak_pnl = running_pnl
                drawdown = peak_pnl - running_pnl
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
        
        return {
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'max_drawdown': max_drawdown,
            'initial_capital': initial_capital,
            'final_capital': initial_capital + total_pnl,
        }
    
    def display_summary(self, summary: Dict):
        """Display backtest summary"""
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(self.style.SUCCESS("📊 BACKTEST SUMMARY"))
        self.stdout.write(self.style.SUCCESS("=" * 70))
        
        self.stdout.write(f"\n📈 Trade Statistics:")
        self.stdout.write(f"   Total Trades: {summary['total_trades']}")
        self.stdout.write(f"   Winning: {summary['winning_trades']}")
        self.stdout.write(f"   Losing: {summary['losing_trades']}")
        self.stdout.write(f"   Win Rate: {summary['win_rate']:.2f}%")
        
        self.stdout.write(f"\n💰 P&L Metrics:")
        self.stdout.write(f"   Total P&L: ₹{summary['total_pnl']:,.2f}")
        self.stdout.write(f"   Initial Capital: ₹{summary['initial_capital']:,.2f}")
        self.stdout.write(f"   Final Capital: ₹{summary['final_capital']:,.2f}")
        self.stdout.write(f"   Return: {((summary['final_capital'] - summary['initial_capital']) / summary['initial_capital'] * 100):.2f}%")
        
        self.stdout.write(f"\n⚠️  Risk Metrics:")
        self.stdout.write(f"   Max Drawdown: ₹{summary['max_drawdown']:,.2f}")
        
        self.stdout.write("")
    
    def save_trades_to_csv(self, trades: List[Dict]):
        """Save trades to CSV file"""
        try:
            # Determine log directory
            try:
                BASE_DIR = settings.BASE_DIR
            except:
                from pathlib import Path
                BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
            
            log_dir = os.path.join(BASE_DIR, 'trade_logs')
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, 'backtest_log.csv')
            
            # Write CSV
            with open(log_file, 'w', newline='') as f:
                writer = csv.writer(f)
                
                # Header
                writer.writerow(['timestamp', 'side', 'symbol', 'entry_price', 'exit_price', 'pnl', 'reason'])
                
                # Write trades
                for trade in trades:
                    writer.writerow([
                        trade['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                        trade['side'],
                        trade['symbol'],
                        f"{trade['entry_price']:.2f}" if trade['entry_price'] else '',
                        f"{trade['exit_price']:.2f}" if trade['exit_price'] else '',
                        f"{trade['pnl']:.2f}" if trade['pnl'] else '',
                        trade['reason'] or '',
                    ])
            
            self.stdout.write(self.style.SUCCESS(f"💾 Trades saved to: {log_file}"))
        
        except Exception as e:
            logger.error(f"Error saving trades to CSV: {e}")
            self.stdout.write(self.style.ERROR(f"❌ Error saving CSV: {e}"))


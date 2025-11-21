"""
Heikin Ashi + SuperTrend + MACD Strategy - Backtesting
"""
import os
import sys
import csv
import logging
from decimal import Decimal
from datetime import datetime, date
from typing import List, Dict, Optional
from django.core.management.base import BaseCommand

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading.services.candle_aggregator import CandleAggregator
from trading.services.heikin_ashi import HeikinAshiCalculator
from trading.services.super_trend import SuperTrendCalculator
from trading.services.macd import MACDCalculator
from trading.services.strike_selector import StrikeSelector
from trading.services.heikinashi_utils import calculate_pnl, trend_reversal_detected, get_trade_log_fields

logger = logging.getLogger(__name__)

# Constants
LOT_SIZE = 35
TARGET_POINTS = 60
OPTION_TARGET_PCT = Decimal('0.15')
STOPLOSS_OPTION_PCT = Decimal('0.30')
STOPLOSS_FUTURES_POINTS = 30
SQUARE_OFF_TIME = 15 * 60 + 20  # 15:20 in minutes from midnight
OPTION_DELTA = Decimal('0.5')  # Fixed delta for option price approximation


class BacktestHeikinAshiStrategy:
    """Backtest implementation of Heikin Ashi strategy"""
    
    def __init__(self):
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
        
        # Results
        self.trades: List[Dict] = []
    
    def load_csv_data(self, csv_file: str) -> List[Dict]:
        """
        Load 15-minute BankNifty futures data from CSV
        
        Expected CSV format:
        - timestamp,open,high,low,close,volume (or similar)
        
        Returns:
            List of candle dicts
        """
        candles = []
        
        try:
            with open(csv_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Parse timestamp
                    timestamp_str = row.get('timestamp') or row.get('time') or row.get('date')
                    if not timestamp_str:
                        continue
                    
                    try:
                        # Try different timestamp formats
                        if 'T' in timestamp_str:
                            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        else:
                            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                    except:
                        try:
                            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d')
                        except:
                            logger.warning(f"Could not parse timestamp: {timestamp_str}")
                            continue
                    
                    # Parse OHLC
                    open_price = Decimal(str(row.get('open', 0)))
                    high_price = Decimal(str(row.get('high', 0)))
                    low_price = Decimal(str(row.get('low', 0)))
                    close_price = Decimal(str(row.get('close', 0)))
                    
                    if not all([open_price, high_price, low_price, close_price]):
                        continue
                    
                    candle = {
                        'open': open_price,
                        'high': high_price,
                        'low': low_price,
                        'close': close_price,
                        'timestamp': timestamp,
                        'start_time': timestamp,
                        'end_time': timestamp,
                        'volume': int(row.get('volume', 0))
                    }
                    
                    candles.append(candle)
            
            logger.info(f"✅ Loaded {len(candles)} candles from {csv_file}")
            return candles
            
        except Exception as e:
            logger.error(f"Failed to load CSV: {e}")
            return []
    
    def approximate_option_price(self, futures_price: Decimal, strike: int, option_type: str, 
                                futures_change: Decimal = Decimal('0')) -> Decimal:
        """
        Approximate option price using delta
        
        Args:
            futures_price: Current futures price
            strike: Option strike
            option_type: 'C' or 'P'
            futures_change: Change in futures from entry (for P&L calculation)
        
        Returns:
            Approximate option price
        """
        # Simple approximation: intrinsic value + time value estimate
        if option_type == 'C':
            intrinsic = max(futures_price - Decimal(str(strike)), Decimal('0'))
        else:  # PUT
            intrinsic = max(Decimal(str(strike)) - futures_price, Decimal('0'))
        
        # Add time value (rough estimate: 0.2% of futures for ATM)
        time_value = futures_price * Decimal('0.002')
        
        # Adjust for delta (if futures moved, option moves by delta * futures_change)
        delta_adjustment = OPTION_DELTA * futures_change
        
        option_price = intrinsic + time_value + delta_adjustment
        
        # Minimum price
        return max(option_price, Decimal('50'))  # Minimum ₹50
    
    def check_entry_conditions(self, candle_time: datetime) -> Optional[str]:
        """
        Check entry conditions after 15-min candle close
        
        Returns:
            'BUY' for CALL entry, 'SELL' for PUT entry, None if no entry
        """
        if self.current_position:
            return None
        
        # Get indicators
        last_ha = self.heikin_ashi_calc.get_last_candle()
        last_st = self.super_trend_calc.get_last_super_trend()
        last_macd = self.macd_calc.get_last_macd()
        
        if not last_ha or not last_st or not last_macd:
            return None
        
        # Check UP-TREND ENTRY (BUY CALL)
        st_up = last_st.get('color') == 'GREEN'
        ha_green = last_ha['ha_close'] > last_ha['ha_open']
        macd_bullish = last_macd['macd_line'] > last_macd['signal_line']
        
        if st_up and ha_green and macd_bullish:
            return 'BUY'
        
        # Check DOWN-TREND ENTRY (BUY PUT)
        st_down = last_st.get('color') == 'RED'
        ha_red = last_ha['ha_close'] < last_ha['ha_open']
        macd_bearish = last_macd['macd_line'] < last_macd['signal_line']
        
        if st_down and ha_red and macd_bearish:
            return 'SELL'
        
        return None
    
    def enter_trade(self, signal: str, futures_price: Decimal, timestamp: datetime):
        """Enter a trade"""
        if self.current_position:
            return
        
        try:
            # Select strike
            spot_price = futures_price
            option_symbol, strike, expiry_date = self.strike_selector.select_strike(
                spot_price=spot_price,
                signal_type=signal,
                strong_momentum=False,
                reference_date=timestamp.date()
            )
            
            # Approximate option entry price
            option_type = 'C' if signal == 'BUY' else 'P'
            entry_premium = self.approximate_option_price(futures_price, strike, option_type)
            
            # Store position
            self.current_position = {
                'entry_time': timestamp,
                'entry_future_price': futures_price,
                'entry_premium': entry_premium,
                'option_symbol': option_symbol,
                'strike': strike,
                'side': 'BUY_CE' if signal == 'BUY' else 'BUY_PE',
                'expiry_date': expiry_date,
                'lot_size': LOT_SIZE,
                'option_type': option_type
            }
            
            # Update previous indicators
            self.previous_st = self.super_trend_calc.get_last_super_trend()
            self.previous_ha = self.heikin_ashi_calc.get_last_candle()
            self.previous_macd = self.macd_calc.get_last_macd()
            
            logger.debug(
                f"ENTRY: {self.current_position['side']} {option_symbol} @ ₹{entry_premium:.2f} "
                f"(Futures: ₹{futures_price:.2f})"
            )
            
        except Exception as e:
            logger.error(f"Error entering trade: {e}")
    
    def check_exit_conditions(self, current_futures: Decimal, current_time: datetime) -> Optional[str]:
        """Check exit conditions"""
        if not self.current_position:
            return None
        
        entry = self.current_position
        entry_future_price = entry['entry_future_price']
        side = entry['side']
        
        # Calculate futures change
        futures_change = current_futures - entry_future_price
        
        # Approximate current option price
        current_option_ltp = self.approximate_option_price(
            current_futures,
            entry['strike'],
            entry['option_type'],
            futures_change
        )
        
        # 1. TAKE PROFIT - FUTURES +60 POINTS
        if 'CE' in side:  # CALL
            futures_profit = current_futures - entry_future_price
            if futures_profit >= Decimal(str(TARGET_POINTS)):
                return 'FUTURES_TARGET'
        else:  # PUT
            futures_profit = entry_future_price - current_futures
            if futures_profit >= Decimal(str(TARGET_POINTS)):
                return 'FUTURES_TARGET'
        
        # 2. OPTION PROFIT TARGET (+15%)
        option_pct = (current_option_ltp - entry['entry_premium']) / entry['entry_premium']
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
        option_loss_pct = (entry['entry_premium'] - current_option_ltp) / entry['entry_premium']
        if option_loss_pct >= STOPLOSS_OPTION_PCT:
            return 'STOPLOSS'
        
        # Futures adverse movement 30 points
        if 'CE' in side:  # CALL
            futures_loss = entry_future_price - current_futures
            if futures_loss >= Decimal(str(STOPLOSS_FUTURES_POINTS)):
                return 'STOPLOSS'
        else:  # PUT
            futures_loss = current_futures - entry_future_price
            if futures_loss >= Decimal(str(STOPLOSS_FUTURES_POINTS)):
                return 'STOPLOSS'
        
        # 5. TIME EXIT (3:20 PM)
        time_minutes = current_time.hour * 60 + current_time.minute
        if time_minutes >= SQUARE_OFF_TIME:
            return 'TIME'
        
        return None
    
    def exit_trade(self, exit_reason: str, current_futures: Decimal, current_time: datetime):
        """Exit current trade"""
        if not self.current_position:
            return
        
        entry = self.current_position
        
        # Calculate futures change
        futures_change = current_futures - entry['entry_future_price']
        
        # Approximate exit option price
        exit_premium = self.approximate_option_price(
            current_futures,
            entry['strike'],
            entry['option_type'],
            futures_change
        )
        
        # Calculate P&L
        pnl_amount = calculate_pnl(
            entry['entry_premium'],
            exit_premium,
            entry['side'],
            LOT_SIZE
        )
        pnl_percent = ((exit_premium - entry['entry_premium']) / entry['entry_premium'] * 100) if entry['entry_premium'] > 0 else Decimal('0')
        
        # Create trade log
        trade_log = get_trade_log_fields(
            mode='BACKTEST',
            entry_time=entry['entry_time'],
            exit_time=current_time,
            entry_future_price=entry['entry_future_price'],
            exit_future_price=current_futures,
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
        
        self.trades.append(trade_log)
        
        logger.debug(
            f"EXIT: {exit_reason} | P&L: ₹{pnl_amount:.2f} ({pnl_percent:.2f}%)"
        )
        
        # Clear position
        self.current_position = None
    
    def run_backtest(self, candles: List[Dict]) -> List[Dict]:
        """
        Run backtest on historical candles
        
        Args:
            candles: List of 15-minute candle dicts
        
        Returns:
            List of trade logs
        """
        logger.info(f"Starting backtest with {len(candles)} candles...")
        
        for candle in candles:
            timestamp = candle['timestamp']
            close_price = candle['close']
            
            # Process candle (add to aggregator)
            # Since we already have 15-min candles, we'll add them directly
            # But we need to simulate the aggregation process
            
            # Add to Heikin Ashi
            ha_candle = self.heikin_ashi_calc.add_candle(candle)
            
            # Calculate SuperTrend
            super_trend = self.super_trend_calc.add_candle(ha_candle)
            
            # Calculate MACD
            macd = self.macd_calc.add_candle(ha_candle)
            
            # Check entry (only after we have enough data)
            if super_trend and macd:
                if not self.current_position:
                    signal = self.check_entry_conditions(timestamp)
                    if signal:
                        self.enter_trade(signal, close_price, timestamp)
                
                # Check exit
                if self.current_position:
                    exit_reason = self.check_exit_conditions(close_price, timestamp)
                    if exit_reason:
                        self.exit_trade(exit_reason, close_price, timestamp)
                    
                    # Update previous indicators
                    self.previous_st = self.super_trend_calc.get_last_super_trend()
                    self.previous_ha = self.heikin_ashi_calc.get_last_candle()
                    self.previous_macd = self.macd_calc.get_last_macd()
        
        # Exit any remaining position at end
        if self.current_position:
            last_candle = candles[-1]
            self.exit_trade('TIME', last_candle['close'], last_candle['timestamp'])
        
        logger.info(f"✅ Backtest complete: {len(self.trades)} trades")
        return self.trades
    
    def calculate_statistics(self) -> Dict:
        """Calculate backtest statistics"""
        if not self.trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_pnl': Decimal('0'),
                'avg_pnl': Decimal('0'),
                'max_drawdown': Decimal('0')
            }
        
        total_pnl = sum(Decimal(str(t['pnl_amount'])) for t in self.trades)
        winning_trades = [t for t in self.trades if Decimal(str(t['pnl_amount'])) > 0]
        losing_trades = [t for t in self.trades if Decimal(str(t['pnl_amount'])) <= 0]
        
        win_rate = (len(winning_trades) / len(self.trades) * 100) if self.trades else 0
        avg_pnl = total_pnl / len(self.trades) if self.trades else Decimal('0')
        
        # Calculate max drawdown
        cumulative_pnl = Decimal('0')
        max_cumulative = Decimal('0')
        max_drawdown = Decimal('0')
        
        for trade in self.trades:
            cumulative_pnl += Decimal(str(trade['pnl_amount']))
            if cumulative_pnl > max_cumulative:
                max_cumulative = cumulative_pnl
            drawdown = max_cumulative - cumulative_pnl
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return {
            'total_trades': len(self.trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'max_drawdown': max_drawdown
        }
    
    def save_results(self, output_file: str = 'backtest_results.csv'):
        """Save backtest results to CSV"""
        if not self.trades:
            logger.warning("No trades to save")
            return
        
        fieldnames = [
            'mode', 'entry_time', 'exit_time', 'entry_future_price', 'exit_future_price',
            'entry_premium', 'exit_premium', 'option_symbol', 'strike', 'side',
            'exit_reason', 'pnl_amount', 'pnl_percent', 'lot_size'
        ]
        
        try:
            with open(output_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for trade in self.trades:
                    row = {k: str(v) for k, v in trade.items()}
                    writer.writerow(row)
            
            logger.info(f"✅ Results saved to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")


class Command(BaseCommand):
    help = "Heikin Ashi + SuperTrend + MACD Strategy - Backtesting"
    
    def add_arguments(self, parser):
        parser.add_argument(
            'csv_file',
            type=str,
            help='Path to CSV file with 15-minute BankNifty futures data'
        )
        parser.add_argument(
            '--output',
            type=str,
            default='backtest_results.csv',
            help='Output CSV file (default: backtest_results.csv)'
        )
    
    def handle(self, *args, **options):
        csv_file = options['csv_file']
        output_file = options['output']
        
        if not os.path.exists(csv_file):
            self.stdout.write(self.style.ERROR(f"❌ CSV file not found: {csv_file}"))
            return
        
        # Initialize backtest
        backtest = BacktestHeikinAshiStrategy()
        
        # Load data
        self.stdout.write(f"📊 Loading data from {csv_file}...")
        candles = backtest.load_csv_data(csv_file)
        
        if not candles:
            self.stdout.write(self.style.ERROR("❌ No candles loaded"))
            return
        
        # Run backtest
        self.stdout.write("🔄 Running backtest...")
        trades = backtest.run_backtest(candles)
        
        # Calculate statistics
        stats = backtest.calculate_statistics()
        
        # Print summary
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("📊 BACKTEST SUMMARY"))
        self.stdout.write("=" * 80)
        self.stdout.write(f"Total Trades: {stats['total_trades']}")
        self.stdout.write(f"Winning Trades: {stats['winning_trades']}")
        self.stdout.write(f"Losing Trades: {stats['losing_trades']}")
        self.stdout.write(f"Win Rate: {stats['win_rate']:.2f}%")
        self.stdout.write(f"Total P&L: ₹{stats['total_pnl']:,.2f}")
        self.stdout.write(f"Average P&L: ₹{stats['avg_pnl']:,.2f}")
        self.stdout.write(f"Max Drawdown: ₹{stats['max_drawdown']:,.2f}")
        self.stdout.write("=" * 80)
        
        # Save results
        backtest.save_results(output_file)
        self.stdout.write(self.style.SUCCESS(f"✅ Results saved to {output_file}"))


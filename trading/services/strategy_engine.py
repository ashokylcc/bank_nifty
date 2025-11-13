"""
Strategy engine - core orchestration logic
"""
import logging
from typing import Optional, Dict, Tuple
from decimal import Decimal
from datetime import datetime, timedelta

from trading.models import Strategy, Signal, Order, TradeLog, DailyStats
from trading.services.data_ingest import DataIngestService, CandleData
from trading.services.data_ingest_live import LiveDataIngestService
from trading.services.range_detector import RangeDetector
from trading.services.momentum import MomentumCalculator
from trading.services.strike_selector import StrikeSelector
from trading.services.risk_manager import RiskManager
from trading.services.execution_adapter import ExecutionAdapter, get_execution_adapter
from trading.services.idempotent_executor import IdempotentExecutor
from trading.utils.time_helpers import (
    get_ist_now, is_trading_hours, is_range_detection_time,
    is_square_off_time, get_today_date, format_time
)

logger = logging.getLogger(__name__)


class StrategyEngine:
    """
    Main strategy engine that orchestrates the entire trading flow
    """
    
    def __init__(self, strategy: Strategy, execution_adapter: Optional[ExecutionAdapter] = None,
                 dry_run: bool = True, use_live_data: bool = False):
        self.strategy = strategy
        self.dry_run = dry_run
        
        # Initialize data service (live WebSocket or CSV/simulation)
        if use_live_data:
            self.data_service = LiveDataIngestService()
        else:
            self.data_service = DataIngestService()
        self.range_detector = RangeDetector()
        self.momentum_calc = MomentumCalculator(
            ema_fast=self.strategy.ema_fast,
            ema_slow=self.strategy.ema_slow,
            rsi_period=self.strategy.rsi_period
        )
        self.strike_selector = StrikeSelector()
        self.risk_manager = RiskManager(strategy)
        
        # Execution adapter
        if execution_adapter is None:
            adapter_type = "mock" if dry_run else "aliceblue"
            # Configure slippage for mock adapter (0.2% default)
            adapter_kwargs = {}
            if adapter_type == "mock":
                adapter_kwargs = {
                    'slippage_pct': 0.2,  # 0.2% slippage
                    'commission_per_lot': 20.0  # ₹20 per lot
                }
            self.execution_adapter = get_execution_adapter(
                dry_run=dry_run,
                adapter_type=adapter_type,
                **adapter_kwargs
            )
        else:
            self.execution_adapter = execution_adapter
        
        # Idempotent executor (prevents duplicate orders)
        self.idempotent_executor = IdempotentExecutor(self.execution_adapter)
        
        # State
        self.range_captured = False
        self.open_trades = {}
        
        # BankNifty futures symbol (for live data)
        from trading.utils.expiry_functions import get_banknifty_futures_symbol
        self.futures_symbol = get_banknifty_futures_symbol()
    
    def initialize(self):
        """Initialize strategy engine"""
        logger.info(f"Initializing Strategy Engine: {self.strategy.name}")
        logger.info(f"Mode: {'DRY-RUN' if self.dry_run else 'LIVE'}")
        logger.info(f"Strategy Enabled: {self.strategy.enabled}")
        
        # Connect to data service
        self.data_service.connect()
        
        # Reset range detector
        self.range_detector.reset()
        self.range_captured = False
    
    def capture_range(self, force: bool = False) -> bool:
        """
        Step A: Capture first 15-min candle range (9:15-9:30)
        
        Args:
            force: If True, bypass time check (useful for simulation)
        
        Returns:
            bool: True if range captured successfully
        """
        if self.range_captured:
            return True
        
        if not force and not is_range_detection_time(self.strategy):
            return False
        
        # Get first candle
        first_candle = self.data_service.get_first_candle_today()
        
        if first_candle is None:
            # Try to get from recent candles
            candles = self.data_service.get_candles("BANKNIFTY", limit=1)
            if candles:
                first_candle = candles[0]
            else:
                logger.warning("No candle data available for range detection")
                return False
        
        # Capture range
        success = self.range_detector.capture_range(first_candle)
        if success:
            self.range_captured = True
            logger.info(
                f"✅ Range captured: High={first_candle.high}, Low={first_candle.low}, "
                f"Range={first_candle.high - first_candle.low}"
            )
        
        return success
    
    def detect_breakout(self, current_price: Decimal) -> Optional[str]:
        """
        Step B: Detect breakout
        
        Args:
            current_price: Current spot price
        
        Returns:
            str: 'BUY' or 'SELL' if breakout detected, None otherwise
        """
        if not self.range_captured:
            logger.warning("Range not captured yet, cannot detect breakout")
            return None
        
        breakout = self.range_detector.detect_breakout(
            current_price,
            buffer=self.strategy.breakout_buffer
        )
        
        if breakout:
            logger.info(f"🎯 Breakout detected: {breakout} @ {current_price}")
        
        return breakout
    
    def confirm_momentum(self, signal_type: str, current_candle: CandleData) -> Tuple[bool, Dict]:
        """
        Step C: Confirm momentum (require ALL conditions)
        
        Args:
            signal_type: 'BUY' or 'SELL'
            current_candle: Current candle data
        
        Returns:
            Tuple of (is_confirmed, details_dict)
        """
        # Get indicators
        ema_fast = self.momentum_calc.get_ema_fast()
        ema_slow = self.momentum_calc.get_ema_slow()
        rsi = self.momentum_calc.calculate_rsi()
        
        # Calculate momentum score
        score, details = self.momentum_calc.calculate_momentum_score(
            signal_type=signal_type,
            current_candle=current_candle,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            rsi=rsi,
            rsi_buy_min=self.strategy.rsi_buy_min,
            rsi_buy_max=self.strategy.rsi_buy_max,
            rsi_sell_min=self.strategy.rsi_sell_min,
            rsi_sell_max=self.strategy.rsi_sell_max,
            volume_multiplier=self.strategy.volume_multiplier
        )
        
        # Require score == 4 (all conditions met)
        is_confirmed = score == 4
        
        logger.info(
            f"Momentum confirmation: Score={score}/4, Confirmed={is_confirmed}, "
            f"Details={details}"
        )
        
        return is_confirmed, {
            'score': score,
            'details': details,
            'ema_fast': ema_fast,
            'ema_slow': ema_slow,
            'rsi': rsi
        }
    
    def select_strike_and_calculate_risk(self, signal_type: str, spot_price: Decimal,
                                        momentum_info: Dict) -> Dict:
        """
        Step D & E: Select strike and calculate risk
        
        Args:
            signal_type: 'BUY' or 'SELL'
            spot_price: Current spot price
            momentum_info: Momentum confirmation details
        
        Returns:
            Dict with strike, symbol, expiry, stoploss, target, qty
        """
        # Check if strong momentum
        first_high, first_low, range_value = self.range_detector.get_range()
        range_pct = (range_value / spot_price) * Decimal('100') if spot_price > 0 else Decimal('0')
        
        strong_momentum = self.strike_selector.is_strong_momentum(
            range_pct=range_pct,
            rsi=momentum_info.get('rsi')
        )
        
        # Select strike
        option_symbol, strike, expiry_date = self.strike_selector.select_strike(
            spot_price=spot_price,
            signal_type=signal_type,
            strong_momentum=strong_momentum
        )
        
        # Calculate stoploss points
        stoploss_points = self.risk_manager.calculate_stoploss_points(range_value)
        
        # Calculate target points
        target_points = self.risk_manager.calculate_target_points(stoploss_points)
        
        # Calculate position size
        qty = self.risk_manager.calculate_position_size(stoploss_points)
        
        return {
            'option_symbol': option_symbol,
            'strike': strike,
            'expiry_date': expiry_date,
            'stoploss_points': stoploss_points,
            'target_points': target_points,
            'qty': qty,
            'strong_momentum': strong_momentum
        }
    
    def create_signal(self, signal_type: str, spot_price: Decimal,
                     current_candle: CandleData, momentum_info: Dict,
                     strike_info: Dict) -> Signal:
        """
        Create and save signal record
        
        Returns:
            Signal: Created signal instance
        """
        first_high, first_low, range_value = self.range_detector.get_range()
        
        signal = Signal.objects.create(
            strategy=self.strategy,
            signal_type=signal_type,
            first_high=first_high,
            first_low=first_low,
            range_value=range_value,
            breakout_price=spot_price,
            breakout_volume=current_candle.volume,
            avg_volume=sum([c.volume for c in self.data_service.get_candles("BANKNIFTY", limit=5)]) // 5,
            ema_fast_value=momentum_info.get('ema_fast'),
            ema_slow_value=momentum_info.get('ema_slow'),
            rsi_value=momentum_info.get('rsi'),
            momentum_score=momentum_info.get('score', 0),
            spot_price=spot_price,
            selected_strike=strike_info['strike'],
            selected_symbol=strike_info['option_symbol'],
            expiry_date=strike_info['expiry_date'],
            stoploss_points=strike_info['stoploss_points'],
            target_points=strike_info['target_points'],
            calculated_qty=strike_info['qty']
        )
        
        logger.info(f"📝 Signal created: {signal.id} - {signal_type} {signal.selected_symbol}")
        
        return signal
    
    def execute_trade(self, signal: Signal) -> Optional[TradeLog]:
        """
        Step F: Execute trade (place order and create trade log)
        
        Args:
            signal: Signal instance
        
        Returns:
            TradeLog: Created trade log or None if failed
        """
        # Check if we can place trade
        can_trade, reason = self.risk_manager.can_place_trade()
        if not can_trade:
            signal.execution_reason = f"Cannot trade: {reason}"
            signal.save()
            logger.warning(f"❌ Cannot execute trade: {reason}")
            return None
        
        # Get entry price (use LTP)
        entry_price = self.execution_adapter.get_ltp(signal.selected_symbol)
        if entry_price is None:
            entry_price = Decimal('100.00')  # Fallback for mock
        
        # Calculate stoploss and target prices
        if signal.signal_type == 'BUY':
            stoploss_price = entry_price - Decimal(str(signal.stoploss_points))
            target_price = entry_price + Decimal(str(signal.target_points))
        else:  # SELL
            stoploss_price = entry_price + Decimal(str(signal.stoploss_points))
            target_price = entry_price - Decimal(str(signal.target_points))
        
        # Place entry order (idempotent - checks for existing orders)
        order_result = self.idempotent_executor.place_order_idempotent(
            symbol=signal.selected_symbol,
            side=signal.signal_type,
            qty=signal.calculated_qty,
            order_type="MARKET",
            signal_id=signal.id
        )
        
        # Create order record
        entry_order = Order.objects.create(
            signal=signal,
            order_id=order_result['order_id'],
            symbol=signal.selected_symbol,
            side=signal.signal_type,
            quantity=signal.calculated_qty,
            order_type="MARKET",
            status=order_result['status'],
            filled_price=order_result.get('filled_price', entry_price),
            filled_at=get_ist_now() if order_result['status'] == 'FILLED' else None,
            dry_run=self.dry_run,
            execution_adapter=self.execution_adapter.adapter_name
        )
        
        # Update entry price from filled price
        if entry_order.filled_price:
            entry_price = entry_order.filled_price
        
        # Create trade log
        trade = TradeLog.objects.create(
            strategy=self.strategy,
            signal=signal,
            entry_order=entry_order,
            entry_time=get_ist_now(),
            entry_price=entry_price,
            entry_symbol=signal.selected_symbol,
            entry_side=signal.signal_type,
            entry_quantity=signal.calculated_qty,
            stoploss_price=stoploss_price,
            target_price=target_price,
            is_open=True
        )
        
        # Mark signal as executed
        signal.executed = True
        signal.execution_reason = "Trade executed successfully"
        signal.save()
        
        # Store in open trades
        self.open_trades[trade.id] = trade
        
        logger.info(
            f"✅ Trade executed: {trade.id} | {signal.signal_type} {signal.selected_symbol} "
            f"@ {entry_price} | Qty: {signal.calculated_qty} | "
            f"Stoploss: {stoploss_price} | Target: {target_price}"
        )
        
        return trade
    
    def monitor_position(self, trade: TradeLog) -> Optional[str]:
        """
        Monitor open position and check exit conditions
        
        Args:
            trade: TradeLog instance
        
        Returns:
            str: Exit reason if exit triggered, None otherwise
        """
        # Get current LTP
        current_ltp = self.execution_adapter.get_ltp(trade.entry_symbol)
        if current_ltp is None:
            return None
        
        # Calculate current PnL
        if trade.entry_side == 'BUY':
            pnl_points = current_ltp - trade.entry_price
        else:  # SELL
            pnl_points = trade.entry_price - current_ltp
        
        pnl_value = pnl_points * Decimal(str(trade.entry_quantity)) * self.strategy.tick_value
        
        # Check exit conditions
        
        # 1. Target hit
        if trade.entry_side == 'BUY' and current_ltp >= trade.target_price:
            return 'TARGET'
        elif trade.entry_side == 'SELL' and current_ltp <= trade.target_price:
            return 'TARGET'
        
        # 2. Stoploss hit
        if trade.entry_side == 'BUY' and current_ltp <= trade.stoploss_price:
            return 'STOPLOSS'
        elif trade.entry_side == 'SELL' and current_ltp >= trade.stoploss_price:
            return 'STOPLOSS'
        
        # 3. Trailing stoploss (move to breakeven after +1 * initial risk)
        initial_risk = abs(trade.entry_price - trade.stoploss_price)
        if trade.entry_side == 'BUY':
            profit_threshold = trade.entry_price + initial_risk
            if current_ltp >= profit_threshold and not trade.breakeven_triggered:
                # Move stoploss to breakeven
                trade.stoploss_price = trade.entry_price
                trade.breakeven_triggered = True
                trade.save()
                logger.info(f"🔄 Trailing stoploss: Moved to breakeven @ {trade.entry_price}")
        else:  # SELL
            profit_threshold = trade.entry_price - initial_risk
            if current_ltp <= profit_threshold and not trade.breakeven_triggered:
                # Move stoploss to breakeven
                trade.stoploss_price = trade.entry_price
                trade.breakeven_triggered = True
                trade.save()
                logger.info(f"🔄 Trailing stoploss: Moved to breakeven @ {trade.entry_price}")
        
        # 4. Time exit (square-off time)
        if is_square_off_time(self.strategy):
            return 'TIME'
        
        return None
    
    def exit_trade(self, trade: TradeLog, exit_reason: str) -> bool:
        """
        Exit trade (place exit order and update trade log)
        
        Args:
            trade: TradeLog instance
            exit_reason: Exit reason ('TARGET', 'STOPLOSS', 'TIME', 'MANUAL')
        
        Returns:
            bool: True if exit successful
        """
        # Determine exit side (opposite of entry)
        exit_side = 'SELL' if trade.entry_side == 'BUY' else 'BUY'
        
        # Get exit price
        exit_price = self.execution_adapter.get_ltp(trade.entry_symbol)
        if exit_price is None:
            exit_price = trade.target_price if exit_reason == 'TARGET' else trade.stoploss_price
        
        # Place exit order (idempotent - checks for existing orders)
        order_result = self.idempotent_executor.place_order_idempotent(
            symbol=trade.entry_symbol,
            side=exit_side,
            qty=trade.entry_quantity,
            order_type="MARKET",
            signal_id=trade.signal.id if trade.signal else None
        )
        
        # Create exit order record
        exit_order = Order.objects.create(
            signal=trade.signal,
            order_id=order_result['order_id'],
            symbol=trade.entry_symbol,
            side=exit_side,
            quantity=trade.entry_quantity,
            order_type="MARKET",
            status=order_result['status'],
            filled_price=order_result.get('filled_price', exit_price),
            filled_at=get_ist_now() if order_result['status'] == 'FILLED' else None,
            dry_run=self.dry_run,
            execution_adapter=self.execution_adapter.adapter_name
        )
        
        # Update exit price from filled price
        if exit_order.filled_price:
            exit_price = exit_order.filled_price
        
        # Calculate PnL
        if trade.entry_side == 'BUY':
            pnl_points = exit_price - trade.entry_price
        else:  # SELL
            pnl_points = trade.entry_price - exit_price
        
        pnl_value = pnl_points * Decimal(str(trade.entry_quantity)) * self.strategy.tick_value
        
        # Calculate commission
        if hasattr(self.execution_adapter, 'commission_per_lot'):
            # Commission for entry + exit
            commission = Decimal(str(self.execution_adapter.commission_per_lot * trade.entry_quantity * 2))
        else:
            commission = Decimal('0.00')
        
        # Calculate slippage from order result
        if exit_order.filled_price and exit_price:
            # Slippage is the difference between expected and actual fill price
            expected_price = trade.target_price if exit_reason == 'TARGET' else trade.stoploss_price
            slippage_estimate = abs(exit_order.filled_price - expected_price)
        else:
            slippage_estimate = Decimal('0.00')
        
        # Adjust PnL for commission
        pnl_value = pnl_value - commission
        
        # Update trade log
        trade.exit_order = exit_order
        trade.exit_time = get_ist_now()
        trade.exit_price = exit_price
        trade.exit_reason = exit_reason
        trade.pnl_points = pnl_points
        trade.pnl_value = pnl_value
        trade.commission = commission
        trade.slippage_estimate = slippage_estimate
        trade.is_open = False
        trade.save()
        
        # Remove from open trades
        if trade.id in self.open_trades:
            del self.open_trades[trade.id]
        
        logger.info(
            f"🔚 Trade exited: {trade.id} | {exit_reason} | "
            f"Entry: {trade.entry_price} | Exit: {exit_price} | "
            f"PnL: ₹{pnl_value}"
        )
        
        # Update daily stats
        self.update_daily_stats()
        
        return True
    
    def update_daily_stats(self):
        """Update daily statistics"""
        from trading.utils.time_helpers import get_today_date
        
        today = get_today_date()
        
        # Get or create daily stats
        daily_stats, created = DailyStats.objects.get_or_create(
            strategy=self.strategy,
            date=today,
            defaults={'total_pnl': Decimal('0.00')}
        )
        
        # Get today's trades
        today_trades = TradeLog.objects.filter(
            strategy=self.strategy,
            entry_time__date=today,
            is_open=False
        )
        
        # Calculate statistics
        total_trades = today_trades.count()
        winning_trades = today_trades.filter(pnl_value__gt=0).count()
        losing_trades = today_trades.filter(pnl_value__lt=0).count()
        
        total_pnl = sum([t.pnl_value for t in today_trades if t.pnl_value])
        gross_profit = sum([t.pnl_value for t in today_trades if t.pnl_value and t.pnl_value > 0])
        gross_loss = abs(sum([t.pnl_value for t in today_trades if t.pnl_value and t.pnl_value < 0]))
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else Decimal('0.00')
        
        avg_win = gross_profit / winning_trades if winning_trades > 0 else None
        avg_loss = gross_loss / losing_trades if losing_trades > 0 else None
        
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
        
        # Calculate max drawdown
        max_drawdown = Decimal('0.00')
        max_drawdown_time = None
        running_pnl = Decimal('0.00')
        peak_pnl = Decimal('0.00')
        
        for trade in today_trades.order_by('entry_time'):
            if trade.pnl_value:
                running_pnl += trade.pnl_value
                if running_pnl > peak_pnl:
                    peak_pnl = running_pnl
                drawdown = peak_pnl - running_pnl
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                    max_drawdown_time = trade.exit_time
        
        # Update daily stats
        daily_stats.total_trades = total_trades
        daily_stats.winning_trades = winning_trades
        daily_stats.losing_trades = losing_trades
        daily_stats.total_pnl = total_pnl
        daily_stats.gross_profit = gross_profit
        daily_stats.gross_loss = gross_loss
        daily_stats.win_rate = win_rate
        daily_stats.avg_win = avg_win
        daily_stats.avg_loss = avg_loss
        daily_stats.profit_factor = profit_factor
        daily_stats.max_drawdown = max_drawdown
        daily_stats.max_drawdown_time = max_drawdown_time
        daily_stats.save()
        
        logger.info(
            f"📊 Daily stats updated: Trades={total_trades}, PnL=₹{total_pnl}, "
            f"Win Rate={win_rate}%"
        )
    
    def run_single_cycle(self) -> Dict:
        """
        Run a single strategy cycle
        
        Returns:
            Dict with cycle results
        """
        results = {
            'range_captured': False,
            'breakout_detected': False,
            'signal_created': False,
            'trade_executed': False,
            'trades_exited': 0
        }
        
        # Get current spot price (for live data or mock)
        # Try futures symbol first, then fall back to "BANKNIFTY"
        current_price = None
        
        # Try 1: Get from futures symbol (preferred for live data)
        if hasattr(self, 'futures_symbol'):
            current_price = self.execution_adapter.get_ltp(self.futures_symbol, data_service=self.data_service)
            if current_price is None and hasattr(self.data_service, 'ltp_cache') and self.futures_symbol in self.data_service.ltp_cache:
                current_price = self.data_service.ltp_cache[self.futures_symbol]
        
        # Try 2: Get from "BANKNIFTY" (spot or fallback)
        if current_price is None:
            current_price = self.execution_adapter.get_ltp("BANKNIFTY", data_service=self.data_service)
            if current_price is None:
                if hasattr(self.data_service, 'ltp_cache') and "BANKNIFTY" in self.data_service.ltp_cache:
                    current_price = self.data_service.ltp_cache["BANKNIFTY"]
                elif hasattr(self.data_service, 'get_latest_ltp'):
                    current_price = self.data_service.get_latest_ltp("BANKNIFTY")
        
        if current_price is None:
            logger.debug("No current price available, skipping cycle")
            return results
        
        # Step 1: Capture range (if not captured yet)
        if not self.range_captured:
            # Force capture if we have candles (simulation mode)
            force = len(self.data_service.candles) > 0
            if self.capture_range(force=force):
                results['range_captured'] = True
        
        # Step 2: Monitor open positions
        for trade_id, trade in list(self.open_trades.items()):
            exit_reason = self.monitor_position(trade)
            if exit_reason:
                if self.exit_trade(trade, exit_reason):
                    results['trades_exited'] += 1
        
        # Step 3: Check if we can trade (only if range captured)
        if not self.range_captured:
            return results
        
        # Allow trading in simulation mode even if not in trading hours
        if not is_trading_hours(self.strategy) and len(self.data_service.candles) == 0:
            return results
        
        # Check risk limits
        can_trade, reason = self.risk_manager.can_place_trade()
        if not can_trade:
            logger.debug(f"Cannot trade: {reason}")
            return results
        
        # Step 4: Get current price and detect breakout
        # Try futures symbol first, then fallback to "BANKNIFTY"
        spot_price = None
        if hasattr(self, 'futures_symbol'):
            spot_price = self.data_service.get_latest_ltp(self.futures_symbol)
        if spot_price is None:
            spot_price = self.data_service.get_latest_ltp("BANKNIFTY")
        if spot_price is None:
            return results
        
        breakout = self.detect_breakout(spot_price)
        if not breakout:
            return results
        
        results['breakout_detected'] = True
        
        # Step 5: Get current candle for momentum calculation
        candles = self.data_service.get_candles("BANKNIFTY", limit=1)
        if not candles:
            return results
        
        current_candle = candles[0]
        self.momentum_calc.add_candle(current_candle)
        
        # Step 6: Confirm momentum
        is_confirmed, momentum_info = self.confirm_momentum(breakout, current_candle)
        if not is_confirmed:
            logger.info("Momentum not confirmed, skipping trade")
            return results
        
        # Step 7: Select strike and calculate risk
        strike_info = self.select_strike_and_calculate_risk(
            breakout, spot_price, momentum_info
        )
        
        # Step 8: Create signal
        signal = self.create_signal(
            breakout, spot_price, current_candle, momentum_info, strike_info
        )
        results['signal_created'] = True
        
        # Step 9: Execute trade
        trade = self.execute_trade(signal)
        if trade:
            results['trade_executed'] = True
        
        return results
    
    def shutdown(self):
        """Shutdown strategy engine"""
        logger.info("Shutting down strategy engine")
        
        # Exit all open trades at square-off time
        if is_square_off_time(self.strategy):
            for trade_id, trade in list(self.open_trades.items()):
                self.exit_trade(trade, 'TIME')
        
        # Disconnect data service
        self.data_service.disconnect()
        
        logger.info("Strategy engine shut down")


"""
Validation command to check simulation results
"""
import os
from decimal import Decimal
from django.core.management.base import BaseCommand
from trading.models import Strategy, Signal, Order, TradeLog, DailyStats
from trading.utils.expiry_functions import build_option_symbol
from datetime import date


class Command(BaseCommand):
    help = 'Validate simulation results and check all components'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--strategy-id',
            type=int,
            help='Strategy ID to validate (default: latest)',
        )
    
    def handle(self, *args, **options):
        strategy_id = options.get('strategy_id')
        
        if strategy_id:
            try:
                strategy = Strategy.objects.get(id=strategy_id)
            except Strategy.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"❌ Strategy with ID {strategy_id} not found"))
                return
        else:
            strategy = Strategy.objects.last()
            if not strategy:
                self.stdout.write(self.style.ERROR("❌ No strategy found"))
                return
        
        self.stdout.write(self.style.SUCCESS(f"🔍 Validating Strategy: {strategy.name} (ID: {strategy.id})"))
        self.stdout.write("=" * 70)
        
        all_passed = True
        
        # 1. Range Detection Validation
        all_passed = self.validate_range_detection(strategy) and all_passed
        
        # 2. Momentum Score Validation
        all_passed = self.validate_momentum_scores(strategy) and all_passed
        
        # 3. Strike Selection Validation
        all_passed = self.validate_strike_selection(strategy) and all_passed
        
        # 4. Risk Manager Validation
        all_passed = self.validate_risk_manager(strategy) and all_passed
        
        # 5. Execution Adapter Validation
        all_passed = self.validate_execution_adapter(strategy) and all_passed
        
        # 6. TradeLog Fields Validation
        all_passed = self.validate_tradelog_fields(strategy) and all_passed
        
        # 7. DailyStats Validation
        all_passed = self.validate_daily_stats(strategy) and all_passed
        
        self.stdout.write("=" * 70)
        if all_passed:
            self.stdout.write(self.style.SUCCESS("✅ ALL VALIDATIONS PASSED"))
        else:
            self.stdout.write(self.style.ERROR("❌ SOME VALIDATIONS FAILED - Check details above"))
    
    def validate_range_detection(self, strategy):
        """1. Range Detection: Confirm first_high and first_low"""
        self.stdout.write("\n📊 1. Range Detection Validation")
        self.stdout.write("-" * 70)
        
        signals = Signal.objects.filter(strategy=strategy).order_by('timestamp')
        
        if not signals.exists():
            self.stdout.write(self.style.WARNING("⚠️  No signals found - cannot validate range"))
            return True  # Not a failure, just no data
        
        passed = True
        for signal in signals:
            self.stdout.write(f"   Signal {signal.id}:")
            self.stdout.write(f"     First High: ₹{signal.first_high}")
            self.stdout.write(f"     First Low: ₹{signal.first_low}")
            self.stdout.write(f"     Range: ₹{signal.range_value}")
            
            # Validate range calculation
            expected_range = signal.first_high - signal.first_low
            if abs(signal.range_value - expected_range) > Decimal('0.01'):
                self.stdout.write(self.style.ERROR(f"     ❌ Range mismatch: Expected {expected_range}, Got {signal.range_value}"))
                passed = False
            else:
                self.stdout.write(self.style.SUCCESS(f"     ✅ Range calculation correct"))
            
            # Validate values are reasonable
            if signal.first_high <= signal.first_low:
                self.stdout.write(self.style.ERROR(f"     ❌ Invalid range: High ({signal.first_high}) <= Low ({signal.first_low})"))
                passed = False
            else:
                self.stdout.write(self.style.SUCCESS(f"     ✅ Range values valid (High > Low)"))
        
        return passed
    
    def validate_momentum_scores(self, strategy):
        """2. Momentum Score: Check momentum_score == 4 before execution"""
        self.stdout.write("\n🎯 2. Momentum Score Validation")
        self.stdout.write("-" * 70)
        
        signals = Signal.objects.filter(strategy=strategy).order_by('timestamp')
        
        if not signals.exists():
            self.stdout.write(self.style.WARNING("⚠️  No signals found - cannot validate momentum"))
            return True
        
        passed = True
        for signal in signals:
            self.stdout.write(f"   Signal {signal.id} ({signal.signal_type}):")
            self.stdout.write(f"     Momentum Score: {signal.momentum_score}/4")
            self.stdout.write(f"     Executed: {signal.executed}")
            
            if signal.executed:
                if signal.momentum_score != 4:
                    self.stdout.write(self.style.ERROR(
                        f"     ❌ FAILED: Executed signal has momentum_score={signal.momentum_score}, expected 4"
                    ))
                    passed = False
                else:
                    self.stdout.write(self.style.SUCCESS(f"     ✅ Momentum score = 4 (all conditions met)"))
            else:
                if signal.momentum_score == 4:
                    self.stdout.write(self.style.WARNING(
                        f"     ⚠️  Signal has score=4 but not executed (check execution_reason)"
                    ))
                else:
                    self.stdout.write(f"     ℹ️  Signal not executed (score={signal.momentum_score} < 4)")
        
        return passed
    
    def validate_strike_selection(self, strategy):
        """3. Strike Selection: Verify option symbol format"""
        self.stdout.write("\n🎲 3. Strike Selection Validation")
        self.stdout.write("-" * 70)
        
        signals = Signal.objects.filter(strategy=strategy, executed=True).order_by('timestamp')
        
        if not signals.exists():
            self.stdout.write(self.style.WARNING("⚠️  No executed signals found - cannot validate strike selection"))
            return True
        
        passed = True
        for signal in signals:
            self.stdout.write(f"   Signal {signal.id}:")
            self.stdout.write(f"     Symbol: {signal.selected_symbol}")
            self.stdout.write(f"     Strike: {signal.selected_strike}")
            self.stdout.write(f"     Expiry: {signal.expiry_date}")
            
            # Validate symbol format: BANKNIFTY{DD}{MMM}{YY}{C|P}{STRIKE}
            try:
                # Parse symbol
                if not signal.selected_symbol.startswith("BANKNIFTY"):
                    self.stdout.write(self.style.ERROR(f"     ❌ Symbol doesn't start with BANKNIFTY"))
                    passed = False
                    continue
                
                # Extract components
                remaining = signal.selected_symbol[9:]  # After "BANKNIFTY"
                
                # Find option type (C or P)
                if 'C' in remaining:
                    option_type = 'C'
                    parts = remaining.split('C')
                elif 'P' in remaining:
                    option_type = 'P'
                    parts = remaining.split('P')
                else:
                    self.stdout.write(self.style.ERROR(f"     ❌ No option type (C/P) found in symbol"))
                    passed = False
                    continue
                
                date_part = parts[0]
                strike_part = parts[1] if len(parts) > 1 else ""
                
                # Validate strike
                try:
                    strike = int(strike_part)
                    if strike != signal.selected_strike:
                        self.stdout.write(self.style.ERROR(
                            f"     ❌ Strike mismatch: Symbol has {strike}, Signal has {signal.selected_strike}"
                        ))
                        passed = False
                    else:
                        self.stdout.write(self.style.SUCCESS(f"     ✅ Strike matches: {strike}"))
                except ValueError:
                    self.stdout.write(self.style.ERROR(f"     ❌ Invalid strike in symbol: {strike_part}"))
                    passed = False
                
                # Validate option type matches signal type
                expected_type = 'C' if signal.signal_type == 'BUY' else 'P'
                if option_type != expected_type:
                    self.stdout.write(self.style.ERROR(
                        f"     ❌ Option type mismatch: Symbol has {option_type}, Expected {expected_type} for {signal.signal_type}"
                    ))
                    passed = False
                else:
                    self.stdout.write(self.style.SUCCESS(f"     ✅ Option type correct: {option_type}"))
                
                # Validate expiry date format
                if signal.expiry_date:
                    # Rebuild symbol to verify format
                    rebuilt = build_option_symbol(signal.expiry_date, signal.selected_strike, option_type)
                    if rebuilt != signal.selected_symbol:
                        self.stdout.write(self.style.WARNING(
                            f"     ⚠️  Symbol format differs from expected: {rebuilt} vs {signal.selected_symbol}"
                        ))
                    else:
                        self.stdout.write(self.style.SUCCESS(f"     ✅ Symbol format matches README example"))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"     ❌ Error validating symbol: {e}"))
                passed = False
        
        return passed
    
    def validate_risk_manager(self, strategy):
        """4. Risk Manager: Verify qty calculation"""
        self.stdout.write("\n💰 4. Risk Manager Validation")
        self.stdout.write("-" * 70)
        
        signals = Signal.objects.filter(strategy=strategy, executed=True).order_by('timestamp')
        
        if not signals.exists():
            self.stdout.write(self.style.WARNING("⚠️  No executed signals found - cannot validate risk manager"))
            return True
        
        passed = True
        for signal in signals:
            self.stdout.write(f"   Signal {signal.id}:")
            self.stdout.write(f"     Capital: ₹{strategy.capital}")
            self.stdout.write(f"     Risk %: {strategy.risk_per_trade_pct}%")
            self.stdout.write(f"     Stoploss Points: {signal.stoploss_points}")
            self.stdout.write(f"     Tick Value: {strategy.tick_value}")
            self.stdout.write(f"     Calculated Qty: {signal.calculated_qty}")
            
            # Calculate expected qty: floor((capital * risk_pct) / (stoploss_points * tick_value))
            risk_amount = strategy.capital * (strategy.risk_per_trade_pct / Decimal('100'))
            risk_per_lot = Decimal(str(signal.stoploss_points)) * strategy.tick_value
            
            if risk_per_lot == 0:
                self.stdout.write(self.style.ERROR(f"     ❌ Risk per lot is zero (division by zero)"))
                passed = False
                continue
            
            expected_qty = int(risk_amount / risk_per_lot)
            expected_qty = max(1, expected_qty)  # Minimum 1 lot
            
            if signal.calculated_qty != expected_qty:
                self.stdout.write(self.style.ERROR(
                    f"     ❌ Qty mismatch: Expected {expected_qty}, Got {signal.calculated_qty}"
                ))
                self.stdout.write(f"        Formula: floor(({strategy.capital} * {strategy.risk_per_trade_pct}%) / ({signal.stoploss_points} * {strategy.tick_value}))")
                self.stdout.write(f"        = floor({risk_amount} / {risk_per_lot}) = {expected_qty}")
                passed = False
            else:
                self.stdout.write(self.style.SUCCESS(f"     ✅ Qty calculation correct: {expected_qty}"))
        
        return passed
    
    def validate_execution_adapter(self, strategy):
        """5. Execution Adapter: Confirm order flow"""
        self.stdout.write("\n📦 5. Execution Adapter Validation")
        self.stdout.write("-" * 70)
        
        orders = Order.objects.filter(signal__strategy=strategy).order_by('created_at')
        
        if not orders.exists():
            self.stdout.write(self.style.WARNING("⚠️  No orders found - cannot validate execution adapter"))
            return True
        
        passed = True
        for order in orders:
            self.stdout.write(f"   Order {order.order_id}:")
            self.stdout.write(f"     Symbol: {order.symbol}")
            self.stdout.write(f"     Side: {order.side}")
            self.stdout.write(f"     Qty: {order.quantity}")
            self.stdout.write(f"     Status: {order.status}")
            self.stdout.write(f"     Dry Run: {order.dry_run}")
            self.stdout.write(f"     Filled Price: {order.filled_price}")
            
            # Validate dry_run flag
            if not order.dry_run:
                self.stdout.write(self.style.WARNING(f"     ⚠️  Order not in dry-run mode (real order?)"))
            
            # Validate status transition
            if order.status == 'FILLED':
                if order.filled_price is None:
                    self.stdout.write(self.style.ERROR(f"     ❌ FILLED order missing filled_price"))
                    passed = False
                else:
                    self.stdout.write(self.style.SUCCESS(f"     ✅ Order filled at ₹{order.filled_price}"))
            elif order.status == 'PENDING':
                self.stdout.write(f"     ℹ️  Order still pending")
            else:
                self.stdout.write(f"     ℹ️  Order status: {order.status}")
        
        return passed
    
    def validate_tradelog_fields(self, strategy):
        """6. TradeLog Fields: Ensure all fields populated"""
        self.stdout.write("\n📝 6. TradeLog Fields Validation")
        self.stdout.write("-" * 70)
        
        trades = TradeLog.objects.filter(strategy=strategy).order_by('entry_time')
        
        if not trades.exists():
            self.stdout.write(self.style.WARNING("⚠️  No trades found - cannot validate TradeLog"))
            return True
        
        passed = True
        for trade in trades:
            self.stdout.write(f"   Trade {trade.id}:")
            
            # Check entry fields
            missing = []
            if not trade.entry_time:
                missing.append("entry_time")
            if not trade.entry_price:
                missing.append("entry_price")
            if not trade.entry_symbol:
                missing.append("entry_symbol")
            if not trade.entry_side:
                missing.append("entry_side")
            if not trade.entry_quantity:
                missing.append("entry_quantity")
            
            if missing:
                self.stdout.write(self.style.ERROR(f"     ❌ Missing entry fields: {', '.join(missing)}"))
                passed = False
            else:
                self.stdout.write(self.style.SUCCESS(f"     ✅ Entry fields populated"))
                self.stdout.write(f"        Entry: {trade.entry_side} {trade.entry_quantity} {trade.entry_symbol} @ ₹{trade.entry_price} at {trade.entry_time}")
            
            # Check exit fields (if closed)
            if not trade.is_open:
                missing = []
                if not trade.exit_time:
                    missing.append("exit_time")
                if not trade.exit_price:
                    missing.append("exit_price")
                if not trade.exit_reason:
                    missing.append("exit_reason")
                
                if missing:
                    self.stdout.write(self.style.ERROR(f"     ❌ Missing exit fields: {', '.join(missing)}"))
                    passed = False
                else:
                    self.stdout.write(self.style.SUCCESS(f"     ✅ Exit fields populated"))
                    self.stdout.write(f"        Exit: ₹{trade.exit_price} at {trade.exit_time} ({trade.exit_reason})")
                
                # Check P&L fields
                if trade.pnl_points is None:
                    self.stdout.write(self.style.ERROR(f"     ❌ Missing pnl_points"))
                    passed = False
                if trade.pnl_value is None:
                    self.stdout.write(self.style.ERROR(f"     ❌ Missing pnl_value"))
                    passed = False
                
                if trade.pnl_points is not None and trade.pnl_value is not None:
                    self.stdout.write(self.style.SUCCESS(f"     ✅ P&L fields populated"))
                    self.stdout.write(f"        PnL: {trade.pnl_points} points = ₹{trade.pnl_value}")
            else:
                self.stdout.write(f"     ℹ️  Trade still open")
        
        return passed
    
    def validate_daily_stats(self, strategy):
        """7. DailyStats: Verify winrate, total_pnl, max_drawdown"""
        self.stdout.write("\n📊 7. DailyStats Validation")
        self.stdout.write("-" * 70)
        
        stats = DailyStats.objects.filter(strategy=strategy).order_by('-date')
        
        if not stats.exists():
            self.stdout.write(self.style.WARNING("⚠️  No daily stats found - cannot validate"))
            return True
        
        passed = True
        for stat in stats:
            self.stdout.write(f"   Date: {stat.date}")
            self.stdout.write(f"     Total Trades: {stat.total_trades}")
            self.stdout.write(f"     Winning: {stat.winning_trades}, Losing: {stat.losing_trades}")
            self.stdout.write(f"     Win Rate: {stat.win_rate}%")
            self.stdout.write(f"     Total PnL: ₹{stat.total_pnl}")
            self.stdout.write(f"     Max Drawdown: ₹{stat.max_drawdown}")
            
            # Validate win rate calculation
            if stat.total_trades > 0:
                expected_winrate = (stat.winning_trades / stat.total_trades) * 100
                if abs(float(stat.win_rate) - float(expected_winrate)) > 0.01:
                    self.stdout.write(self.style.ERROR(
                        f"     ❌ Win rate mismatch: Expected {expected_winrate:.2f}%, Got {stat.win_rate}%"
                    ))
                    passed = False
                else:
                    self.stdout.write(self.style.SUCCESS(f"     ✅ Win rate calculation correct"))
            
            # Validate trade counts
            if stat.winning_trades + stat.losing_trades > stat.total_trades:
                self.stdout.write(self.style.ERROR(
                    f"     ❌ Trade count mismatch: Winning + Losing ({stat.winning_trades + stat.losing_trades}) > Total ({stat.total_trades})"
                ))
                passed = False
            else:
                self.stdout.write(self.style.SUCCESS(f"     ✅ Trade counts consistent"))
            
            # Validate PnL is reasonable
            if abs(float(stat.total_pnl)) > 1000000:  # ₹10L seems unreasonable for testing
                self.stdout.write(self.style.WARNING(f"     ⚠️  Total PnL seems very high: ₹{stat.total_pnl}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"     ✅ Total PnL seems reasonable"))
            
            # Validate drawdown is non-negative
            if stat.max_drawdown < 0:
                self.stdout.write(self.style.ERROR(f"     ❌ Max drawdown is negative: ₹{stat.max_drawdown}"))
                passed = False
            else:
                self.stdout.write(self.style.SUCCESS(f"     ✅ Max drawdown is non-negative"))
        
        return passed


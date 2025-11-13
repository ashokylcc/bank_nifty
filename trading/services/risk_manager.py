"""
Risk management service - position sizing and risk checks
"""
import logging
from typing import Tuple, Optional
from decimal import Decimal
from trading.models import Strategy, TradeLog

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Manages risk: position sizing, daily loss limits, concurrent trades
    """
    
    def __init__(self, strategy: Strategy):
        self.strategy = strategy
    
    def calculate_position_size(self, stoploss_points: int) -> int:
        """
        Calculate position size based on risk per trade
        
        Formula: Qty = floor( (capital * risk_per_trade_pct) / (stoploss_points * tick_value) )
        
        Args:
            stoploss_points: Stoploss in points
        
        Returns:
            int: Quantity (number of lots)
        """
        if stoploss_points <= 0:
            logger.error(f"Invalid stoploss_points: {stoploss_points}")
            return 0
        
        # Calculate risk amount
        risk_amount = self.strategy.capital * (self.strategy.risk_per_trade_pct / Decimal('100'))
        
        # Calculate risk per lot
        risk_per_lot = Decimal(str(stoploss_points)) * self.strategy.tick_value
        
        if risk_per_lot == 0:
            logger.error("Risk per lot is zero, cannot calculate position size")
            return 0
        
        # Calculate quantity
        qty = int(risk_amount / risk_per_lot)
        
        # Ensure minimum 1 lot
        qty = max(1, qty)
        
        logger.info(
            f"Position size calculation: Capital={self.strategy.capital}, "
            f"Risk%={self.strategy.risk_per_trade_pct}%, Risk Amount={risk_amount}, "
            f"Stoploss Points={stoploss_points}, Risk/Lot={risk_per_lot}, "
            f"Qty={qty}"
        )
        
        return qty
    
    def calculate_stoploss_points(self, range_value: Decimal) -> int:
        """
        Calculate stoploss points from range
        
        Formula: max( floor(range * stoploss_range_multiplier), min_stoploss_points )
        
        Args:
            range_value: Range value (high - low)
        
        Returns:
            int: Stoploss in points
        """
        stoploss_points = int(range_value * self.strategy.stoploss_range_multiplier)
        stoploss_points = max(stoploss_points, self.strategy.min_stoploss_points)
        
        logger.info(
            f"Stoploss calculation: Range={range_value}, "
            f"Multiplier={self.strategy.stoploss_range_multiplier}, "
            f"Min={self.strategy.min_stoploss_points}, "
            f"Stoploss Points={stoploss_points}"
        )
        
        return stoploss_points
    
    def calculate_target_points(self, stoploss_points: int) -> int:
        """
        Calculate target points from stoploss
        
        Formula: target = stoploss * target_multiplier
        
        Args:
            stoploss_points: Stoploss in points
        
        Returns:
            int: Target in points
        """
        target_points = int(stoploss_points * self.strategy.target_multiplier)
        
        logger.info(
            f"Target calculation: Stoploss={stoploss_points}, "
            f"Multiplier={self.strategy.target_multiplier}, "
            f"Target Points={target_points}"
        )
        
        return target_points
    
    def check_daily_loss_limit(self) -> Tuple[bool, Decimal]:
        """
        Check if daily loss limit is breached
        
        Returns:
            Tuple of (can_trade, current_daily_pnl)
        """
        from trading.models import DailyStats
        from trading.utils.time_helpers import get_today_date
        
        today = get_today_date()
        
        # Get today's stats
        daily_stats = DailyStats.objects.filter(
            strategy=self.strategy,
            date=today
        ).first()
        
        if daily_stats is None:
            # No trades today, can trade
            return True, Decimal('0.00')
        
        current_pnl = daily_stats.total_pnl
        can_trade = current_pnl > -self.strategy.max_daily_loss
        
        if not can_trade:
            logger.warning(
                f"Daily loss limit breached: PnL={current_pnl}, "
                f"Limit={-self.strategy.max_daily_loss}"
            )
        
        return can_trade, current_pnl
    
    def check_concurrent_trades(self) -> Tuple[bool, int]:
        """
        Check if maximum concurrent trades limit is reached
        
        Returns:
            Tuple of (can_trade, current_open_trades)
        """
        open_trades = TradeLog.objects.filter(
            strategy=self.strategy,
            is_open=True
        ).count()
        
        can_trade = open_trades < self.strategy.max_concurrent_trades
        
        if not can_trade:
            logger.warning(
                f"Maximum concurrent trades reached: Open={open_trades}, "
                f"Max={self.strategy.max_concurrent_trades}"
            )
        
        return can_trade, open_trades
    
    def can_place_trade(self) -> Tuple[bool, str]:
        """
        Check if trade can be placed (combines all checks)
        
        Returns:
            Tuple of (can_trade, reason)
        """
        # Check daily loss limit
        can_trade, daily_pnl = self.check_daily_loss_limit()
        if not can_trade:
            return False, f"Daily loss limit breached: ₹{daily_pnl}"
        
        # Check concurrent trades
        can_trade, open_trades = self.check_concurrent_trades()
        if not can_trade:
            return False, f"Maximum concurrent trades reached: {open_trades}"
        
        # Check if strategy is enabled
        if not self.strategy.enabled:
            return False, "Strategy is disabled (kill switch)"
        
        return True, "OK"


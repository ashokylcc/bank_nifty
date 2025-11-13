"""
Strike selection service - finds nearest Thursday expiry and ATM strike
"""
import logging
from typing import Tuple, Optional
from decimal import Decimal
from datetime import date
from trading.utils.expiry_functions import (
    get_trading_thursday_expiry,
    get_available_option_expiry,
    build_option_symbol,
    round_to_nearest_strike
)

logger = logging.getLogger(__name__)


class StrikeSelector:
    """
    Selects option strike and expiry for BankNifty
    """
    
    def __init__(self):
        pass
    
    def select_strike(self, spot_price: Decimal, signal_type: str,
                     strong_momentum: bool = False,
                     reference_date: Optional[date] = None) -> Tuple[str, int, date]:
        """
        Select option strike and expiry
        
        Args:
            spot_price: Current spot price
            signal_type: 'BUY' or 'SELL'
            strong_momentum: If True, use ATM ± 100, else ATM
            reference_date: Reference date for expiry calculation (default: today)
        
        Returns:
            Tuple of (option_symbol, strike, expiry_date)
        """
        # Step 1: Get nearest available option expiry from contract master
        # This queries the market to find which expiries are actually available
        expiry_date = get_available_option_expiry(reference_date)
        logger.info(f"Selected expiry date: {expiry_date} (from available market expiries)")
        
        # Step 2: Calculate ATM strike (round to nearest 100)
        atm_strike = round_to_nearest_strike(spot_price, step=100)
        
        # Step 3: Adjust strike based on momentum
        if strong_momentum:
            if signal_type == 'BUY':
                selected_strike = atm_strike + 100  # OTM Call
                logger.info(f"Strong momentum BUY: Using OTM strike {selected_strike} (ATM + 100)")
            else:  # SELL
                selected_strike = atm_strike - 100  # OTM Put
                logger.info(f"Strong momentum SELL: Using OTM strike {selected_strike} (ATM - 100)")
        else:
            selected_strike = atm_strike
            logger.info(f"Normal momentum: Using ATM strike {selected_strike}")
        
        # Step 4: Determine option type
        option_type = 'C' if signal_type == 'BUY' else 'P'
        
        # Step 5: Build option symbol
        option_symbol = build_option_symbol(expiry_date, selected_strike, option_type)
        
        logger.info(
            f"Selected option: {option_symbol} | Strike: {selected_strike} | "
            f"Type: {option_type} | Expiry: {expiry_date}"
        )
        
        return option_symbol, selected_strike, expiry_date
    
    def is_strong_momentum(self, range_pct: Decimal, rsi: Optional[Decimal] = None,
                          threshold: Decimal = Decimal('0.5')) -> bool:
        """
        Determine if momentum is strong
        
        Args:
            range_pct: Range as percentage of spot
            rsi: RSI value (optional)
            threshold: Threshold for strong momentum (default: 0.5%)
        
        Returns:
            bool: True if strong momentum
        """
        # Simple check: range percentage > threshold
        is_strong = range_pct > threshold
        
        # Additional check: RSI near extremes
        if rsi:
            if rsi > Decimal('65') or rsi < Decimal('35'):
                is_strong = True
        
        return is_strong


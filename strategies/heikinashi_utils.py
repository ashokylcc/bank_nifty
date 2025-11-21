"""
Shared utilities for Heikin Ashi strategy (live and backtest)
"""
from decimal import Decimal
from typing import Dict, Optional


def calculate_pnl(entry_price: Decimal, exit_price: Decimal, side: str, lot_size: int = 35) -> Decimal:
    """
    Calculate P&L for a trade
    
    Args:
        entry_price: Entry price
        exit_price: Exit price
        side: 'CALL' or 'PUT' (or 'BUY_CE'/'BUY_PE')
        lot_size: Lot size (default: 35)
    
    Returns:
        Decimal: Total P&L in ₹
    """
    # Normalize side
    if 'CE' in side or side == 'CALL':
        # CALL: profit when exit > entry
        pnl_per_unit = exit_price - entry_price
    elif 'PE' in side or side == 'PUT':
        # PUT: profit when exit < entry (but we buy, so profit when price goes up)
        # Actually for PUT: when underlying goes down, PUT price goes up
        # So same formula: (exit - entry) * lot_size
        pnl_per_unit = exit_price - entry_price
    else:
        raise ValueError(f"Invalid side: {side}")
    
    total_pnl = pnl_per_unit * Decimal(str(lot_size))
    return total_pnl


def trend_reversal_detected(
    current_st: Optional[Dict],
    previous_st: Optional[Dict],
    current_ha: Optional[Dict],
    previous_ha: Optional[Dict],
    current_macd: Optional[Dict],
    previous_macd: Optional[Dict]
) -> bool:
    """
    Detect trend reversal
    
    Returns True if:
    - SuperTrend flips OR
    - HA color flips AND MACD crossover occurs
    
    Args:
        current_st: Current SuperTrend dict
        previous_st: Previous SuperTrend dict
        current_ha: Current Heikin Ashi candle
        previous_ha: Previous Heikin Ashi candle
        current_macd: Current MACD dict
        previous_macd: Previous MACD dict
    
    Returns:
        bool: True if reversal detected
    """
    if not current_st or not previous_st:
        return False
    
    # Check SuperTrend flip
    st_flipped = current_st.get('color') != previous_st.get('color')
    if st_flipped:
        return True
    
    # Check HA color flip AND MACD crossover
    if current_ha and previous_ha:
        current_ha_color = 'GREEN' if current_ha['ha_close'] > current_ha['ha_open'] else 'RED'
        previous_ha_color = 'GREEN' if previous_ha['ha_close'] > previous_ha['ha_open'] else 'RED'
        ha_flipped = current_ha_color != previous_ha_color
        
        if ha_flipped:
            # Check for MACD crossover
            if current_macd and previous_macd:
                # Bullish crossover: MACD crosses above signal
                bullish_cross = (
                    previous_macd['macd_line'] < previous_macd['signal_line'] and
                    current_macd['macd_line'] > current_macd['signal_line']
                )
                # Bearish crossover: MACD crosses below signal
                bearish_cross = (
                    previous_macd['macd_line'] > previous_macd['signal_line'] and
                    current_macd['macd_line'] < current_macd['signal_line']
                )
                
                if bullish_cross or bearish_cross:
                    return True
    
    return False


def get_trade_log_fields(
    mode: str,
    entry_time,
    exit_time,
    entry_future_price: Decimal,
    exit_future_price: Decimal,
    entry_premium: Decimal,
    exit_premium: Decimal,
    option_symbol: str,
    strike: int,
    side: str,
    exit_reason: str,
    pnl_amount: Decimal,
    pnl_percent: Decimal,
    lot_size: int = 35
) -> Dict:
    """
    Get standardized trade log fields
    
    Returns:
        Dict: Trade log fields
    """
    return {
        'mode': mode,
        'entry_time': entry_time,
        'exit_time': exit_time,
        'entry_future_price': entry_future_price,
        'exit_future_price': exit_future_price,
        'entry_premium': entry_premium,
        'exit_premium': exit_premium,
        'option_symbol': option_symbol,
        'strike': strike,
        'side': side,
        'exit_reason': exit_reason,
        'pnl_amount': pnl_amount,
        'pnl_percent': pnl_percent,
        'lot_size': lot_size
    }


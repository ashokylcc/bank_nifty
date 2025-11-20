"""
Super Trend indicator calculation service
"""
import logging
from typing import List, Dict, Optional, Tuple
from decimal import Decimal

logger = logging.getLogger(__name__)


def calculate_atr(candles: List[Dict], period: int = 14) -> Optional[Decimal]:
    """
    Calculate Average True Range (ATR) from Heikin Ashi candles
    
    Formula:
    - TR = max(High - Low, |High - Prev_Close|, |Low - Prev_Close|)
    - ATR = Average of last N TR values
    
    Args:
        candles: List of Heikin Ashi candles
        period: ATR period (default: 14)
    
    Returns:
        Decimal: ATR value or None if insufficient data
    """
    if len(candles) < period + 1:
        return None
    
    # Calculate True Range for each candle
    true_ranges = []
    
    for i in range(1, len(candles)):
        current = candles[i]
        previous = candles[i - 1]
        
        high = Decimal(str(current['ha_high']))
        low = Decimal(str(current['ha_low']))
        prev_close = Decimal(str(previous['ha_close']))
        
        # Calculate True Range
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        
        tr = max(tr1, tr2, tr3)
        true_ranges.append(tr)
    
    if len(true_ranges) < period:
        return None
    
    # Calculate ATR (simple average of last N TR values)
    recent_trs = true_ranges[-period:]
    atr = sum(recent_trs) / Decimal(str(period))
    
    return atr


def calculate_super_trend(
    ha_candle: Dict,
    atr: Decimal,
    previous_st: Optional[Dict] = None,
    multiplier: Decimal = Decimal('3.0')
) -> Dict:
    """
    Calculate Super Trend value and signal
    
    Formula:
    - Basic Upper Band = (High + Low) / 2 + (Multiplier × ATR)
    - Basic Lower Band = (High + Low) / 2 - (Multiplier × ATR)
    - Final Super Trend:
      - If previous ST was above price: ST = Lower Band
      - Else: ST = Upper Band
    - Color:
      - If Close > ST: GREEN (BUY)
      - If Close < ST: RED (SELL)
    
    Args:
        ha_candle: Current Heikin Ashi candle
        atr: ATR value
        previous_st: Previous Super Trend dict (with 'value' and 'color')
        multiplier: Super Trend multiplier (default: 3.0)
    
    Returns:
        Dict: Super Trend dict with value, color, and signal
    """
    high = Decimal(str(ha_candle['ha_high']))
    low = Decimal(str(ha_candle['ha_low']))
    close = Decimal(str(ha_candle['ha_close']))
    
    # Calculate basic bands
    hl_avg = (high + low) / Decimal('2')
    upper_band = hl_avg + (multiplier * atr)
    lower_band = hl_avg - (multiplier * atr)
    
    # Calculate final Super Trend
    if previous_st:
        prev_st_value = Decimal(str(previous_st['value']))
        prev_st_color = previous_st['color']
        
        # Determine which band to use
        if prev_st_color == 'RED':
            # Previous was RED (below price), use Lower Band
            st_value = lower_band
        else:
            # Previous was GREEN (above price), use Upper Band
            st_value = upper_band
        
        # Ensure ST doesn't flip too easily
        if prev_st_color == 'RED' and close > prev_st_value:
            # Price crossed above previous ST, switch to Upper Band
            st_value = upper_band
        elif prev_st_color == 'GREEN' and close < prev_st_value:
            # Price crossed below previous ST, switch to Lower Band
            st_value = lower_band
    else:
        # First calculation: use Upper Band
        st_value = upper_band
    
    # Determine color
    if close > st_value:
        color = 'GREEN'
        signal = 'BUY'
    else:
        color = 'RED'
        signal = 'SELL'
    
    super_trend = {
        'value': st_value,
        'color': color,
        'signal': signal,
        'upper_band': upper_band,
        'lower_band': lower_band,
        'atr': atr,
        'timestamp': ha_candle['timestamp']
    }
    
    return super_trend


def detect_signal_change(current_st: Dict, previous_st: Optional[Dict] = None) -> str:
    """
    Detect signal change from Super Trend
    
    Args:
        current_st: Current Super Trend dict
        previous_st: Previous Super Trend dict
    
    Returns:
        str: 'BUY', 'SELL', or 'HOLD'
    """
    if not previous_st:
        # First signal: return current signal
        return current_st['signal']
    
    prev_color = previous_st['color']
    curr_color = current_st['color']
    
    # Signal change detection
    if prev_color == 'RED' and curr_color == 'GREEN':
        return 'BUY'
    elif prev_color == 'GREEN' and curr_color == 'RED':
        return 'SELL'
    else:
        return 'HOLD'


class SuperTrendCalculator:
    """
    Super Trend calculator that maintains state
    """
    
    def __init__(self, atr_period: int = 14, multiplier: Decimal = Decimal('3.0')):
        """
        Initialize Super Trend calculator
        
        Args:
            atr_period: ATR period (default: 14)
            multiplier: Super Trend multiplier (default: 3.0)
        """
        self.atr_period = atr_period
        self.multiplier = multiplier
        self.super_trends: List[Dict] = []
        self.ha_candles: List[Dict] = []
    
    def add_candle(self, ha_candle: Dict) -> Optional[Dict]:
        """
        Add Heikin Ashi candle and calculate Super Trend
        
        Args:
            ha_candle: Heikin Ashi candle
        
        Returns:
            Dict: Super Trend dict or None if insufficient data
        """
        self.ha_candles.append(ha_candle)
        
        # Keep only last 100 candles
        if len(self.ha_candles) > 100:
            self.ha_candles.pop(0)
        
        # Need at least (atr_period + 1) candles for ATR
        if len(self.ha_candles) < self.atr_period + 1:
            return None
        
        # Calculate ATR
        atr = calculate_atr(self.ha_candles, self.atr_period)
        if atr is None:
            return None
        
        # Get previous Super Trend
        previous_st = self.super_trends[-1] if self.super_trends else None
        
        # Calculate Super Trend
        super_trend = calculate_super_trend(
            ha_candle,
            atr,
            previous_st,
            self.multiplier
        )
        
        # Detect signal change
        signal_change = detect_signal_change(super_trend, previous_st)
        super_trend['signal_change'] = signal_change
        
        self.super_trends.append(super_trend)
        
        # Keep only last 100 Super Trends
        if len(self.super_trends) > 100:
            self.super_trends.pop(0)
        
        return super_trend
    
    def get_last_super_trend(self) -> Optional[Dict]:
        """Get last Super Trend"""
        return self.super_trends[-1] if self.super_trends else None
    
    def get_signal_change(self) -> Optional[str]:
        """Get current signal change"""
        if not self.super_trends:
            return None
        return self.super_trends[-1].get('signal_change', 'HOLD')
    
    def reset(self):
        """Reset calculator"""
        self.super_trends = []
        self.ha_candles = []


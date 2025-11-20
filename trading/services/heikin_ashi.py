"""
Heikin Ashi candle calculation service
"""
import logging
from typing import List, Dict, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)


def calculate_heikin_ashi(regular_candle: Dict, previous_ha_candle: Optional[Dict] = None) -> Dict:
    """
    Calculate Heikin Ashi values from regular candle
    
    Formula:
    - HA_Close = (Open + High + Low + Close) / 4
    - HA_Open = (Previous HA_Open + Previous HA_Close) / 2
    - HA_High = max(High, HA_Open, HA_Close)
    - HA_Low = min(Low, HA_Open, HA_Close)
    
    Args:
        regular_candle: Regular OHLC candle dict
        previous_ha_candle: Previous Heikin Ashi candle (for HA_Open calculation)
    
    Returns:
        Dict: Heikin Ashi candle
    """
    open_price = Decimal(str(regular_candle['open']))
    high_price = Decimal(str(regular_candle['high']))
    low_price = Decimal(str(regular_candle['low']))
    close_price = Decimal(str(regular_candle['close']))
    
    # Calculate HA_Close
    ha_close = (open_price + high_price + low_price + close_price) / Decimal('4')
    
    # Calculate HA_Open
    if previous_ha_candle:
        prev_ha_open = Decimal(str(previous_ha_candle['ha_open']))
        prev_ha_close = Decimal(str(previous_ha_candle['ha_close']))
        ha_open = (prev_ha_open + prev_ha_close) / Decimal('2')
    else:
        # First candle: HA_Open = (Regular Open + Regular Close) / 2
        ha_open = (open_price + close_price) / Decimal('2')
    
    # Calculate HA_High and HA_Low
    ha_high = max(high_price, ha_open, ha_close)
    ha_low = min(low_price, ha_open, ha_close)
    
    ha_candle = {
        'ha_open': ha_open,
        'ha_high': ha_high,
        'ha_low': ha_low,
        'ha_close': ha_close,
        'timestamp': regular_candle['timestamp'],
        'start_time': regular_candle.get('start_time'),
        'end_time': regular_candle.get('end_time'),
        'volume': regular_candle.get('volume', 0),
        # Keep original values for reference
        'original_open': open_price,
        'original_high': high_price,
        'original_low': low_price,
        'original_close': close_price,
    }
    
    return ha_candle


def convert_to_heikin_ashi(candles: List[Dict]) -> List[Dict]:
    """
    Convert list of regular candles to Heikin Ashi candles
    
    Args:
        candles: List of regular OHLC candles
    
    Returns:
        List[Dict]: List of Heikin Ashi candles
    """
    ha_candles = []
    previous_ha = None
    
    for candle in candles:
        ha_candle = calculate_heikin_ashi(candle, previous_ha)
        ha_candles.append(ha_candle)
        previous_ha = ha_candle
    
    return ha_candles


class HeikinAshiCalculator:
    """
    Heikin Ashi calculator that maintains state
    """
    
    def __init__(self):
        self.ha_candles: List[Dict] = []
    
    def add_candle(self, regular_candle: Dict) -> Dict:
        """
        Add regular candle and convert to Heikin Ashi
        
        Args:
            regular_candle: Regular OHLC candle
        
        Returns:
            Dict: Heikin Ashi candle
        """
        previous_ha = self.ha_candles[-1] if self.ha_candles else None
        ha_candle = calculate_heikin_ashi(regular_candle, previous_ha)
        
        self.ha_candles.append(ha_candle)
        
        # Keep only last 100 candles
        if len(self.ha_candles) > 100:
            self.ha_candles.pop(0)
        
        return ha_candle
    
    def get_last_candle(self) -> Optional[Dict]:
        """Get last Heikin Ashi candle"""
        return self.ha_candles[-1] if self.ha_candles else None
    
    def get_candles(self, count: int = 50) -> List[Dict]:
        """Get last N Heikin Ashi candles"""
        return self.ha_candles[-count:] if len(self.ha_candles) >= count else self.ha_candles
    
    def reset(self):
        """Reset calculator"""
        self.ha_candles = []


"""
Heikin Ashi candle calculation service
"""
import logging
from typing import List, Dict, Optional
from decimal import Decimal
from datetime import datetime, timedelta

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
    
    # Determine HA color based on HA_Close vs HA_Open (TradingView style)
    # GREEN when HA_Close > HA_Open (uptrend/bullish)
    # RED when HA_Close < HA_Open (downtrend/bearish)
    if ha_close > ha_open:
        ha_color = "GREEN"
    else:
        ha_color = "RED"
    
    ha_candle = {
        'ha_open': ha_open,
        'ha_high': ha_high,
        'ha_low': ha_low,
        'ha_close': ha_close,
        'ha_color': ha_color,  # TradingView-style HA color
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
        Detects gaps (overnight, different trading day) and resets HA calculation
        
        Args:
            regular_candle: Regular OHLC candle
        
        Returns:
            Dict: Heikin Ashi candle
        """
        # Check for gap: if there's a previous HA candle, check time difference
        previous_ha = None
        if self.ha_candles:
            last_ha = self.ha_candles[-1]
            last_ha_time = last_ha.get('end_time') or last_ha.get('timestamp')
            current_candle_time = regular_candle.get('end_time') or regular_candle.get('timestamp')
            
            if last_ha_time and current_candle_time:
                try:
                    # Ensure both are datetime objects
                    from trading.utils.time_helpers import IST
                    
                    if not isinstance(last_ha_time, datetime):
                        if isinstance(last_ha_time, str):
                            try:
                                last_ha_time = datetime.fromisoformat(last_ha_time.replace('Z', '+00:00'))
                            except:
                                from dateutil import parser
                                last_ha_time = parser.parse(last_ha_time)
                        if last_ha_time.tzinfo is None:
                            last_ha_time = IST.localize(last_ha_time)
                    
                    if not isinstance(current_candle_time, datetime):
                        if isinstance(current_candle_time, str):
                            try:
                                current_candle_time = datetime.fromisoformat(current_candle_time.replace('Z', '+00:00'))
                            except:
                                from dateutil import parser
                                current_candle_time = parser.parse(current_candle_time)
                        if current_candle_time.tzinfo is None:
                            current_candle_time = IST.localize(current_candle_time)
                    
                    # Calculate time difference
                    if isinstance(last_ha_time, datetime) and isinstance(current_candle_time, datetime):
                        time_diff = current_candle_time - last_ha_time
                        
                        # Check for different trading days (date change)
                        last_date = last_ha_time.date()
                        current_date = current_candle_time.date()
                        different_day = (last_date != current_date)
                        
                        # If gap is more than 2 hours OR different trading day, reset HA
                        if different_day or time_diff > timedelta(hours=2):
                            logger.info(
                                f"🔄 Gap detected (Date: {last_date} → {current_date}, "
                                f"Time diff: {time_diff}), resetting HA calculation for new trading session"
                            )
                            previous_ha = None  # Reset HA - will use first candle formula
                        else:
                            previous_ha = last_ha
                    else:
                        # If not datetime objects, use previous HA (fallback)
                        previous_ha = last_ha
                except Exception as e:
                    logger.warning(f"Error checking gap, using previous HA: {e}")
                    previous_ha = last_ha
            else:
                # If timestamps missing, use previous HA (fallback)
                previous_ha = last_ha
        else:
            # No previous HA candles
            previous_ha = None
        
        ha_candle = calculate_heikin_ashi(regular_candle, previous_ha)
        
        self.ha_candles.append(ha_candle)
        
        # Keep only last 200 candles for accuracy
        if len(self.ha_candles) > 200:
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


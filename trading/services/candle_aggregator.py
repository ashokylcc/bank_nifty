"""
Candle aggregation service - Converts LTP data into OHLC candles
"""
import logging
from typing import List, Dict, Optional
from decimal import Decimal
from datetime import datetime, timedelta
from trading.utils.time_helpers import get_ist_now

logger = logging.getLogger(__name__)


class CandleAggregator:
    """
    Aggregates LTP data into OHLC candles
    """
    
    def __init__(self, candle_interval_minutes: int = 15):
        """
        Initialize candle aggregator
        
        Args:
            candle_interval_minutes: Candle interval in minutes (default: 15)
        """
        self.candle_interval_minutes = candle_interval_minutes
        self.ltp_buffer: List[Dict] = []  # Store LTPs for current period
        self.current_candle_start: Optional[datetime] = None
        self.candles: List[Dict] = []  # Store completed candles
        
    def add_ltp(self, ltp: Decimal, timestamp: Optional[datetime] = None) -> Optional[Dict]:
        """
        Add LTP and check if candle should be created
        
        Args:
            ltp: Last Traded Price
            timestamp: Timestamp (default: current IST time)
        
        Returns:
            Dict: New candle if created, None otherwise
        """
        if timestamp is None:
            timestamp = get_ist_now()
        
        # Initialize first candle start time
        if self.current_candle_start is None:
            # Round down to nearest 15-minute interval
            minute = (timestamp.minute // self.candle_interval_minutes) * self.candle_interval_minutes
            self.current_candle_start = timestamp.replace(minute=minute, second=0, microsecond=0)
            # If we're past the interval start, move to next interval
            if timestamp.minute % self.candle_interval_minutes != 0 or timestamp.second > 0:
                # We're in the middle of an interval, start from the beginning of current interval
                pass  # Already set correctly above
        
        # Add LTP to buffer
        self.ltp_buffer.append({
            'ltp': ltp,
            'timestamp': timestamp
        })
        
        # Check if 15 minutes have passed
        time_diff = timestamp - self.current_candle_start
        if time_diff >= timedelta(minutes=self.candle_interval_minutes):
            # Create candle
            candle = self._create_candle()
            
            # Reset for next period
            self.current_candle_start = timestamp.replace(minute=0, second=0, microsecond=0)
            minute = (timestamp.minute // self.candle_interval_minutes) * self.candle_interval_minutes
            self.current_candle_start = timestamp.replace(minute=minute, second=0, microsecond=0)
            self.ltp_buffer = [{'ltp': ltp, 'timestamp': timestamp}]  # Keep current LTP for next candle
            
            return candle
        
        return None
    
    def _create_candle(self) -> Dict:
        """
        Create OHLC candle from LTP buffer
        
        Returns:
            Dict: OHLC candle
        """
        if not self.ltp_buffer:
            return None
        
        # Calculate OHLC
        ltps = [item['ltp'] for item in self.ltp_buffer]
        open_price = ltps[0]
        close_price = ltps[-1]
        high_price = max(ltps)
        low_price = min(ltps)
        
        # Get timestamps
        start_time = self.ltp_buffer[0]['timestamp']
        end_time = self.ltp_buffer[-1]['timestamp']
        
        candle = {
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'timestamp': end_time,
            'start_time': start_time,
            'end_time': end_time,
            'volume': len(self.ltp_buffer)  # Count of LTPs (proxy for volume)
        }
        
        # Store candle
        self.candles.append(candle)
        
        # Keep only last 100 candles
        if len(self.candles) > 100:
            self.candles.pop(0)
        
        logger.debug(f"Created candle: O={open_price}, H={high_price}, L={low_price}, C={close_price}")
        
        return candle
    
    def get_last_candle(self) -> Optional[Dict]:
        """Get the last completed candle"""
        return self.candles[-1] if self.candles else None
    
    def get_candles(self, count: int = 50) -> List[Dict]:
        """Get last N candles"""
        return self.candles[-count:] if len(self.candles) >= count else self.candles
    
    def get_current_period_ltps(self) -> List[Decimal]:
        """Get LTPs for current incomplete period"""
        return [item['ltp'] for item in self.ltp_buffer]
    
    def reset(self):
        """Reset aggregator (for new trading day)"""
        self.ltp_buffer = []
        self.current_candle_start = None
        self.candles = []


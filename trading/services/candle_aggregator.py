"""
Candle aggregation service - Converts LTP data into OHLC candles
Uses strict exchange boundaries (09:15-09:30, 09:30-09:45, etc.)
"""
import logging
from typing import List, Dict, Optional
from decimal import Decimal
from datetime import datetime, timedelta, time
from trading.utils.time_helpers import get_ist_now, IST

logger = logging.getLogger(__name__)


def get_exchange_candle_start(timestamp: datetime, interval_minutes: int = 15) -> datetime:
    """
    Get the exchange candle start time for a given timestamp
    Uses strict 15-minute boundaries: :00-:14, :15-:29, :30-:44, :45-:59
    
    Exchange candle boundaries (TradingView style):
    - 09:00:00 - 09:14:59 (first bucket)
    - 09:15:00 - 09:29:59
    - 09:30:00 - 09:44:59
    - 09:45:00 - 09:59:59
    - 10:00:00 - 10:14:59
    - etc.
    
    Args:
        timestamp: Input timestamp (must be in IST)
        interval_minutes: Candle interval in minutes (default: 15)
    
    Returns:
        datetime: Exchange candle start time (floored to bucket boundary)
    """
    # Ensure timestamp is in IST
    if timestamp.tzinfo is None:
        timestamp = IST.localize(timestamp)
    elif timestamp.tzinfo != IST:
        timestamp = timestamp.astimezone(IST)
    
    # Get hour and minute
    hour = timestamp.hour
    minute = timestamp.minute
    
    # Calculate which 15-minute bucket this timestamp falls into
    # Buckets: :00-:14, :15-:29, :30-:44, :45-:59
    if minute < 15:
        bucket_minute = 0
    elif minute < 30:
        bucket_minute = 15
    elif minute < 45:
        bucket_minute = 30
    else:
        bucket_minute = 45
    
    candle_start = timestamp.replace(minute=bucket_minute, second=0, microsecond=0)
    return candle_start


class CandleAggregator:
    """
    Aggregates LTP data into OHLC candles using strict 15-minute boundaries
    Candle boundaries: :00-:14, :15-:29, :30-:44, :45-:59 (end_time at :14:59, :29:59, :44:59, :59:59)
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
        self.is_closed: bool = False  # Track if current candle is closed
        
    def add_ltp(self, ltp: Decimal, timestamp: Optional[datetime] = None) -> Optional[Dict]:
        """
        Add LTP and check if candle should be created
        Uses strict exchange boundaries (09:15-09:30, 09:30-09:45, etc.)
        
        Args:
            ltp: Last Traded Price
            timestamp: Timestamp (default: current IST time, must be in IST)
        
        Returns:
            Dict: New candle if created, None otherwise
        """
        if timestamp is None:
            timestamp = get_ist_now()
        
        # Ensure timestamp is in IST
        if timestamp.tzinfo is None:
            timestamp = IST.localize(timestamp)
        elif timestamp.tzinfo != IST:
            timestamp = timestamp.astimezone(IST)
        
        # Initialize first candle start time using exchange boundaries
        if self.current_candle_start is None:
            self.current_candle_start = get_exchange_candle_start(timestamp, self.candle_interval_minutes)
            logger.debug(f"Initialized candle start: {self.current_candle_start.strftime('%H:%M:%S')}")
        
        # Add LTP to buffer
        self.ltp_buffer.append({
            'ltp': ltp,
            'timestamp': timestamp
        })
        
        # Calculate next candle start time
        next_candle_start = self.current_candle_start + timedelta(minutes=self.candle_interval_minutes)
        
        # Check if we've crossed into the next candle period
        # Candle closes at :14:59, :29:59, :44:59, :59:59
        if timestamp >= next_candle_start:
            # Mark previous candle as closed and create it
            candle = self._create_candle()
            if candle:
                candle['is_closed'] = True
            
            # Move to next period using exchange boundaries
            self.current_candle_start = get_exchange_candle_start(timestamp, self.candle_interval_minutes)
            self.ltp_buffer = [{'ltp': ltp, 'timestamp': timestamp}]  # Keep current LTP for next candle
            self.is_closed = False  # New candle is open
            
            logger.info(
                f"🕯️ Candle CLOSED: {candle['start_time'].strftime('%H:%M:%S')}-{candle['end_time'].strftime('%H:%M:%S')} | "
                f"Next candle starts at: {self.current_candle_start.strftime('%H:%M:%S')}"
            )
            
            return candle
        
        return None
    
    def _create_candle(self) -> Dict:
        """
        Create OHLC candle from LTP buffer
        Uses exchange boundary timestamps for start_time and end_time
        
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
        
        # Use exchange boundary timestamps
        # End time is at :14:59, :29:59, :44:59, :59:59
        start_time = self.current_candle_start
        end_time = self.current_candle_start + timedelta(minutes=self.candle_interval_minutes) - timedelta(seconds=1, microseconds=1)
        
        # Ensure timestamps are in IST
        if start_time.tzinfo is None:
            start_time = IST.localize(start_time)
        if end_time.tzinfo is None:
            end_time = IST.localize(end_time)
        
        candle = {
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'timestamp': end_time,  # Candle timestamp is end of period
            'start_time': start_time,  # Exchange boundary start (:00, :15, :30, :45)
            'end_time': end_time,  # Exchange boundary end (:14:59, :29:59, :44:59, :59:59)
            'volume': len(self.ltp_buffer),  # Count of LTPs (proxy for volume)
            'is_closed': True  # Mark as closed when finalized
        }
        
        # Store candle
        self.candles.append(candle)
        
        # Keep only last 200 candles for accuracy
        if len(self.candles) > 200:
            self.candles.pop(0)
        
        logger.debug(
            f"Created candle: {start_time.strftime('%H:%M:%S')}-{end_time.strftime('%H:%M:%S')} | "
            f"O={open_price}, H={high_price}, L={low_price}, C={close_price}"
        )
        
        return candle
    
    def get_last_candle(self) -> Optional[Dict]:
        """Get the last completed candle"""
        return self.candles[-1] if self.candles else None
    
    def get_candles(self, count: int = 50) -> List[Dict]:
        """Get last N candles"""
        return self.candles[-count:] if len(self.candles) >= count else self.candles
    
    def get_current_forming_candle(self) -> Optional[Dict]:
        """
        Get the current forming (incomplete) candle
        
        Returns:
            Dict: Current forming candle with OHLC based on current LTP buffer, or None if no data
        """
        if not self.ltp_buffer or self.current_candle_start is None:
            return None
        
        # Calculate OHLC from current buffer
        ltps = [item['ltp'] for item in self.ltp_buffer]
        open_price = ltps[0]
        close_price = ltps[-1]  # Current LTP is the close
        high_price = max(ltps)
        low_price = min(ltps)
        
        # Use current candle start time
        start_time = self.current_candle_start
        
        # Current time as end time (candle is still forming)
        end_time = get_ist_now()
        
        # Ensure timestamps are in IST
        if start_time.tzinfo is None:
            start_time = IST.localize(start_time)
        if end_time.tzinfo is None:
            end_time = IST.localize(end_time)
        
        return {
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'timestamp': end_time,
            'start_time': start_time,
            'end_time': end_time,
            'volume': len(self.ltp_buffer),
            'is_closed': False  # Mark as forming/incomplete
        }
    
    def get_current_period_ltps(self) -> List[Decimal]:
        """Get LTPs for current incomplete period"""
        return [item['ltp'] for item in self.ltp_buffer]
    
    def reset(self):
        """Reset aggregator (for new trading day)"""
        self.ltp_buffer = []
        self.current_candle_start = None
        self.candles = []


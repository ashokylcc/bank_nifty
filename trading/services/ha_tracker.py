"""
Heikin-Ashi Candle Tracker Service
Processes new 15-minute OHLC candles and stores HA calculations in database
"""
import logging
from typing import Dict, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone

from trading.models_ha import HeikinAshiCandle
from trading.services.heikin_ashi import calculate_heikin_ashi
from trading.utils.time_helpers import get_ist_now, IST

logger = logging.getLogger(__name__)


class HeikinAshiTracker:
    """
    Service to track and store Heikin-Ashi candles in database
    """
    
    def __init__(self):
        """Initialize tracker"""
        pass
    
    def get_previous_ha_candle(self, symbol: str, current_timestamp: datetime) -> Optional[Dict]:
        """
        Fetch previous Heikin-Ashi candle from database
        
        Args:
            symbol: Trading symbol
            current_timestamp: Current candle timestamp
            
        Returns:
            Dict: Previous HA candle dict or None
        """
        try:
            # Get most recent HA candle for this symbol before current timestamp
            prev_candle = HeikinAshiCandle.objects.filter(
                symbol=symbol,
                timestamp__lt=current_timestamp
            ).order_by('-timestamp').first()
            
            if prev_candle:
                return {
                    'ha_open': prev_candle.ha_open,
                    'ha_close': prev_candle.ha_close,
                    'ha_high': prev_candle.ha_high,
                    'ha_low': prev_candle.ha_low,
                    'color': prev_candle.color,
                    'timestamp': prev_candle.timestamp,
                }
        except Exception as e:
            logger.error(f"Error fetching previous HA candle for {symbol}: {e}")
        
        return None
    
    def detect_trend_reversal(self, current_color: str, previous_ha: Optional[Dict]) -> str:
        """
        Detect trend reversal based on color change
        
        Args:
            current_color: Current HA color ('green' or 'red')
            previous_ha: Previous HA candle dict or None
            
        Returns:
            str: Trend status ('uptrend_start', 'downtrend_start', 'uptrend_continue', 'downtrend_continue', 'neutral')
        """
        if not previous_ha:
            # First candle - determine initial trend
            if current_color == 'green':
                return 'uptrend_start'
            else:
                return 'downtrend_start'
        
        prev_color = previous_ha.get('color', '').lower()
        
        # Check for reversal
        if prev_color == 'red' and current_color == 'green':
            return 'uptrend_start'  # Red → Green = Uptrend reversal
        elif prev_color == 'green' and current_color == 'red':
            return 'downtrend_start'  # Green → Red = Downtrend reversal
        elif current_color == 'green':
            return 'uptrend_continue'  # Green → Green = Continue uptrend
        elif current_color == 'red':
            return 'downtrend_continue'  # Red → Red = Continue downtrend
        else:
            return 'neutral'
    
    def process_new_candle(
        self,
        symbol: str,
        open_price: Decimal,
        high_price: Decimal,
        low_price: Decimal,
        close_price: Decimal,
        timestamp: Optional[datetime] = None,
        volume: Optional[int] = None
    ) -> Tuple[str, str]:
        """
        Process new 15-minute OHLC candle and calculate Heikin-Ashi values
        
        Formula:
        - HA_Close = (O + H + L + C) / 4
        - HA_Open = (prev_HA_Open + prev_HA_Close) / 2 (first candle = (O+C)/2)
        - HA_High = max(H, HA_Open, HA_Close)
        - HA_Low = min(L, HA_Open, HA_Close)
        - Color = "green" if HA_Close > HA_Open else "red"
        
        Args:
            symbol: Trading symbol (e.g., "BANKNIFTY", "BANKNIFTY_FUTURES")
            open_price: Open price
            high_price: High price
            low_price: Low price
            close_price: Close price
            timestamp: Candle timestamp (default: current time)
            volume: Volume (optional)
            
        Returns:
            Tuple[str, str]: (color, trend) - e.g., ('green', 'uptrend_start')
        """
        # Use current time if timestamp not provided
        if timestamp is None:
            timestamp = get_ist_now()
        
        # Ensure timestamp is timezone-aware
        if timestamp.tzinfo is None:
            timestamp = IST.localize(timestamp)
        
        # Check if candle already exists
        existing = HeikinAshiCandle.objects.filter(symbol=symbol, timestamp=timestamp).first()
        if existing:
            logger.debug(f"HA candle already exists for {symbol} at {timestamp}")
            return existing.color, existing.trend
        
        # Prepare regular candle dict
        regular_candle = {
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'timestamp': timestamp,
            'volume': volume or 0,
        }
        
        # Get previous HA candle from database
        previous_ha = self.get_previous_ha_candle(symbol, timestamp)
        
        # Calculate Heikin-Ashi values using existing service
        ha_candle = calculate_heikin_ashi(regular_candle, previous_ha)
        
        # Convert HA color to lowercase for consistency
        ha_color = ha_candle['ha_color'].lower()  # 'GREEN' -> 'green', 'RED' -> 'red'
        
        # Detect trend reversal
        trend = self.detect_trend_reversal(ha_color, previous_ha)
        
        # Save to database
        ha_candle_obj = HeikinAshiCandle.objects.create(
            symbol=symbol,
            timestamp=timestamp,
            original_open=open_price,
            original_high=high_price,
            original_low=low_price,
            original_close=close_price,
            ha_open=ha_candle['ha_open'],
            ha_close=ha_candle['ha_close'],
            ha_high=ha_candle['ha_high'],
            ha_low=ha_candle['ha_low'],
            color=ha_color,
            trend=trend,
            volume=volume or 0,
        )
        
        logger.info(
            f"✅ Saved HA candle: {symbol} @ {timestamp.strftime('%Y-%m-%d %H:%M')} | "
            f"Color: {ha_color.upper()} | Trend: {trend} | "
            f"HA_O: {ha_candle['ha_open']:.2f}, HA_C: {ha_candle['ha_close']:.2f}"
        )
        
        return ha_color, trend
    
    def get_latest_candle(self, symbol: str) -> Optional[HeikinAshiCandle]:
        """
        Get latest Heikin-Ashi candle for symbol
        
        Args:
            symbol: Trading symbol
            
        Returns:
            HeikinAshiCandle or None
        """
        return HeikinAshiCandle.objects.filter(symbol=symbol).order_by('-timestamp').first()
    
    def get_candles(
        self,
        symbol: str,
        limit: int = 50,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ):
        """
        Get Heikin-Ashi candles for symbol
        
        Args:
            symbol: Trading symbol
            limit: Maximum number of candles
            start_time: Start time filter (optional)
            end_time: End time filter (optional)
            
        Returns:
            QuerySet of HeikinAshiCandle objects
        """
        queryset = HeikinAshiCandle.objects.filter(symbol=symbol)
        
        if start_time:
            queryset = queryset.filter(timestamp__gte=start_time)
        if end_time:
            queryset = queryset.filter(timestamp__lte=end_time)
        
        return queryset.order_by('-timestamp')[:limit]
    
    def get_trend_reversals(
        self,
        symbol: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ):
        """
        Get all trend reversals for symbol
        
        Args:
            symbol: Trading symbol
            start_time: Start time filter (optional)
            end_time: End time filter (optional)
            
        Returns:
            QuerySet of HeikinAshiCandle objects with trend reversals
        """
        queryset = HeikinAshiCandle.objects.filter(
            symbol=symbol,
            trend__in=['uptrend_start', 'downtrend_start']
        )
        
        if start_time:
            queryset = queryset.filter(timestamp__gte=start_time)
        if end_time:
            queryset = queryset.filter(timestamp__lte=end_time)
        
        return queryset.order_by('-timestamp')


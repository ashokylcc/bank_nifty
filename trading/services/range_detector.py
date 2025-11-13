"""
Range detection service - captures 9:15-9:30 high/low
"""
import logging
from typing import Optional, Tuple
from decimal import Decimal
from trading.services.data_ingest import CandleData

logger = logging.getLogger(__name__)


class RangeDetector:
    """
    Detects the first 15-minute range (9:15-9:30)
    """
    
    def __init__(self):
        self.first_high: Optional[Decimal] = None
        self.first_low: Optional[Decimal] = None
        self.range_value: Optional[Decimal] = None
        self.range_captured = False
    
    def capture_range(self, candle: CandleData) -> bool:
        """
        Capture range from first 15-min candle
        
        Args:
            candle: CandleData from 9:15-9:30
        
        Returns:
            bool: True if range captured successfully
        """
        if self.range_captured:
            logger.warning("Range already captured, ignoring")
            return False
        
        if candle is None:
            logger.error("Cannot capture range: candle is None")
            return False
        
        self.first_high = candle.high
        self.first_low = candle.low
        self.range_value = candle.high - candle.low
        self.range_captured = True
        
        logger.info(
            f"Range captured: High={self.first_high}, Low={self.first_low}, "
            f"Range={self.range_value}"
        )
        
        return True
    
    def detect_breakout(self, current_price: Decimal, buffer: int = 10) -> Optional[str]:
        """
        Detect breakout direction
        
        Args:
            current_price: Current spot price
            buffer: Breakout buffer points (default: 10)
        
        Returns:
            str: 'BUY' if breakout above, 'SELL' if breakout below, None if no breakout
        """
        if not self.range_captured:
            logger.warning("Range not captured yet, cannot detect breakout")
            return None
        
        buffer_decimal = Decimal(str(buffer))
        
        # BUY breakout: price > first_high + buffer
        if current_price > self.first_high + buffer_decimal:
            logger.info(
                f"BUY breakout detected: {current_price} > {self.first_high} + {buffer}"
            )
            return 'BUY'
        
        # SELL breakout: price < first_low - buffer
        if current_price < self.first_low - buffer_decimal:
            logger.info(
                f"SELL breakout detected: {current_price} < {self.first_low} - {buffer}"
            )
            return 'SELL'
        
        return None
    
    def get_range(self) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        """
        Get captured range values
        
        Returns:
            Tuple of (first_high, first_low, range_value)
        """
        return (self.first_high, self.first_low, self.range_value)
    
    def reset(self):
        """Reset range detector for new trading day"""
        self.first_high = None
        self.first_low = None
        self.range_value = None
        self.range_captured = False
        logger.info("Range detector reset")


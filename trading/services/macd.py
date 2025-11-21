"""
MACD (Moving Average Convergence Divergence) indicator calculation
"""
import logging
from typing import List, Dict, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)


def calculate_ema(values: List[Decimal], period: int) -> Optional[Decimal]:
    """
    Calculate Exponential Moving Average (EMA) - TradingView standard formula
    Formula: alpha = 2/(period+1), EMA = alpha * price + (1-alpha) * prev_EMA
    
    Args:
        values: List of price values (full history for incremental calculation)
        period: EMA period
    
    Returns:
        Decimal: EMA value or None if insufficient data
    """
    if len(values) < period:
        return None
    
    # Calculate alpha (smoothing factor): 2 / (period + 1)
    alpha = Decimal('2') / Decimal(str(period + 1))
    
    # First EMA = SMA of first period values
    sma = sum(values[:period]) / Decimal(str(period))
    ema = sma
    
    # Apply EMA formula for remaining values: EMA = alpha * price + (1-alpha) * prev_EMA
    for i in range(period, len(values)):
        price = values[i]
        ema = alpha * price + (Decimal('1') - alpha) * ema
    
    return ema


def calculate_macd(
    ha_closes: List[Decimal],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> Optional[Dict]:
    """
    Calculate MACD indicator
    
    Formula:
    - MACD Line = EMA(fast_period) - EMA(slow_period)
    - Signal Line = EMA(MACD Line, signal_period)
    - Histogram = MACD Line - Signal Line
    
    Args:
        ha_closes: List of Heikin Ashi close prices
        fast_period: Fast EMA period (default: 12)
        slow_period: Slow EMA period (default: 26)
        signal_period: Signal EMA period (default: 9)
    
    Returns:
        Dict with 'macd_line', 'signal_line', 'histogram', or None if insufficient data
    """
    # Need at least slow_period + signal_period candles
    min_candles = slow_period + signal_period
    if len(ha_closes) < min_candles:
        return None
    
    # Calculate fast and slow EMAs
    fast_ema = calculate_ema(ha_closes, fast_period)
    slow_ema = calculate_ema(ha_closes, slow_period)
    
    if fast_ema is None or slow_ema is None:
        return None
    
    # MACD Line = Fast EMA - Slow EMA
    macd_line = fast_ema - slow_ema
    
    # For signal line, we need historical MACD values
    # Calculate MACD for all available periods to build MACD line history
    macd_values = []
    # Start from slow_period (when we have both EMAs)
    for i in range(slow_period - 1, len(ha_closes)):
        # Get closes up to this point
        closes_subset = ha_closes[:i+1]
        fast_ema_val = calculate_ema(closes_subset, fast_period)
        slow_ema_val = calculate_ema(closes_subset, slow_period)
        if fast_ema_val and slow_ema_val:
            macd_val = fast_ema_val - slow_ema_val
            macd_values.append(macd_val)
    
    # Calculate signal line (EMA of MACD line)
    # Need at least signal_period MACD values
    if len(macd_values) < signal_period:
        return None
    
    signal_line = calculate_ema(macd_values, signal_period)
    if signal_line is None:
        return None
    
    # Histogram = MACD Line - Signal Line
    histogram = macd_line - signal_line
    
    return {
        'macd_line': macd_line,
        'signal_line': signal_line,
        'histogram': histogram,
        'fast_ema': fast_ema,
        'slow_ema': slow_ema
    }


class MACDCalculator:
    """
    MACD calculator that maintains state - matches TradingView exactly
    """
    
    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9):
        """
        Initialize MACD calculator
        
        Args:
            fast_period: Fast EMA period (default: 12)
            slow_period: Slow EMA period (default: 26)
            signal_period: Signal EMA period (default: 9)
        """
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.ha_closes: List[Decimal] = []
        self.macd_line_history: List[Decimal] = []  # Store MACD line values for signal calculation
        self.macd_history: List[Dict] = []
    
    def add_candle(self, ha_candle: Dict) -> Optional[Dict]:
        """
        Add Heikin Ashi candle and calculate MACD incrementally (TradingView method)
        
        Args:
            ha_candle: Heikin Ashi candle dict with 'ha_close'
        
        Returns:
            Dict: MACD values or None if insufficient data
        """
        ha_close = Decimal(str(ha_candle['ha_close']))
        self.ha_closes.append(ha_close)
        
        # Keep only last 200 closes for accuracy
        if len(self.ha_closes) > 200:
            self.ha_closes.pop(0)
        
        # Need at least slow_period candles for EMA calculation
        if len(self.ha_closes) < self.slow_period:
            return None
        
        # Calculate fast and slow EMAs
        fast_ema = calculate_ema(self.ha_closes, self.fast_period)
        slow_ema = calculate_ema(self.ha_closes, self.slow_period)
        
        if fast_ema is None or slow_ema is None:
            return None
        
        # MACD Line = Fast EMA - Slow EMA
        macd_line = fast_ema - slow_ema
        
        # Add to MACD line history
        self.macd_line_history.append(macd_line)
        
        # Keep only last 200 MACD line values
        if len(self.macd_line_history) > 200:
            self.macd_line_history.pop(0)
        
        # Calculate signal line (EMA of MACD line)
        # Need at least signal_period MACD line values
        if len(self.macd_line_history) < self.signal_period:
            return None
        
        signal_line = calculate_ema(self.macd_line_history, self.signal_period)
        if signal_line is None:
            return None
        
        # Histogram = MACD Line - Signal Line
        histogram = macd_line - signal_line
        
        macd = {
            'macd_line': macd_line,
            'signal_line': signal_line,
            'histogram': histogram,
            'fast_ema': fast_ema,
            'slow_ema': slow_ema,
            'timestamp': ha_candle.get('timestamp')
        }
        
        self.macd_history.append(macd)
        
        # Keep only last 200 MACD values
        if len(self.macd_history) > 200:
            self.macd_history.pop(0)
        
        return macd
    
    def get_last_macd(self) -> Optional[Dict]:
        """Get last MACD values"""
        return self.macd_history[-1] if self.macd_history else None
    
    def detect_crossover(self) -> Optional[str]:
        """
        Detect MACD crossover
        
        Returns:
            'BULLISH' if MACD crosses above signal, 'BEARISH' if below, None otherwise
        """
        if len(self.macd_history) < 2:
            return None
        
        current = self.macd_history[-1]
        previous = self.macd_history[-2]
        
        # Bullish crossover: MACD was below signal, now above
        if previous['macd_line'] < previous['signal_line'] and current['macd_line'] > current['signal_line']:
            return 'BULLISH'
        
        # Bearish crossover: MACD was above signal, now below
        if previous['macd_line'] > previous['signal_line'] and current['macd_line'] < current['signal_line']:
            return 'BEARISH'
        
        return None
    
    def reset(self):
        """Reset calculator"""
        self.ha_closes = []
        self.macd_history = []


"""
Momentum calculation service - EMA, RSI, volume filters
"""
import logging
from typing import List, Optional, Tuple
from decimal import Decimal
from trading.services.data_ingest import CandleData

logger = logging.getLogger(__name__)


def compute_ema(values: List[Decimal], period: int) -> Optional[Decimal]:
    """
    Compute Exponential Moving Average (EMA)
    
    Args:
        values: List of price values (closing prices)
        period: EMA period (e.g., 5, 20)
    
    Returns:
        Decimal: EMA value or None if insufficient data
    """
    if len(values) < period:
        return None
    
    # Use last 'period' values
    prices = values[-period:]
    
    # Calculate SMA for first value
    sma = sum(prices[:period]) / Decimal(str(period))
    
    # Calculate multiplier: 2 / (period + 1)
    multiplier = Decimal('2') / Decimal(str(period + 1))
    
    # Calculate EMA iteratively
    ema = sma
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    
    return ema


def compute_rsi(values: List[Decimal], period: int = 14) -> Optional[Decimal]:
    """
    Compute Relative Strength Index (RSI)
    
    Args:
        values: List of price values (closing prices)
        period: RSI period (default: 14)
    
    Returns:
        Decimal: RSI value (0-100) or None if insufficient data
    """
    if len(values) < period + 1:
        return None
    
    # Calculate price changes
    changes = []
    for i in range(1, len(values)):
        changes.append(values[i] - values[i-1])
    
    if len(changes) < period:
        return None
    
    # Get recent changes
    recent_changes = changes[-period:]
    
    # Separate gains and losses
    gains = [c if c > 0 else Decimal('0') for c in recent_changes]
    losses = [-c if c < 0 else Decimal('0') for c in recent_changes]
    
    # Calculate average gain and loss
    avg_gain = sum(gains) / Decimal(str(period))
    avg_loss = sum(losses) / Decimal(str(period))
    
    if avg_loss == 0:
        return Decimal('100')  # Perfect uptrend
    
    # Calculate RS and RSI
    rs = avg_gain / avg_loss
    rsi = Decimal('100') - (Decimal('100') / (Decimal('1') + rs))
    
    return rsi


class MomentumCalculator:
    """
    Calculates momentum indicators: EMA, RSI, volume filters
    """
    
    def __init__(self, ema_fast: int = 20, ema_slow: int = 50, rsi_period: int = 14):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.candles: List[CandleData] = []
    
    def add_candle(self, candle: CandleData):
        """Add candle for calculation"""
        self.candles.append(candle)
        # Keep only recent candles (for memory efficiency)
        if len(self.candles) > 100:
            self.candles = self.candles[-100:]
    
    def calculate_ema(self, period: int, price_list: List[Decimal]) -> Optional[Decimal]:
        """
        Calculate Exponential Moving Average
        
        Args:
            period: EMA period
            price_list: List of closing prices
        
        Returns:
            Decimal: EMA value or None if insufficient data
        """
        if len(price_list) < period:
            return None
        
        # Use closing prices
        prices = price_list[-period:]
        
        # Calculate SMA for first value
        sma = sum(prices[:period]) / Decimal(str(period))
        
        # Calculate multiplier
        multiplier = Decimal('2') / Decimal(str(period + 1))
        
        # Calculate EMA
        ema = sma
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    def get_ema_fast(self) -> Optional[Decimal]:
        """Get fast EMA (default: 20)"""
        if len(self.candles) < self.ema_fast:
            return None
        
        closes = [c.close for c in self.candles]
        return self.calculate_ema(self.ema_fast, closes)
    
    def get_ema_slow(self) -> Optional[Decimal]:
        """Get slow EMA (default: 50)"""
        if len(self.candles) < self.ema_slow:
            return None
        
        closes = [c.close for c in self.candles]
        return self.calculate_ema(self.ema_slow, closes)
    
    def calculate_rsi(self, period: int = None) -> Optional[Decimal]:
        """
        Calculate Relative Strength Index (RSI)
        
        Args:
            period: RSI period (default: self.rsi_period)
        
        Returns:
            Decimal: RSI value (0-100) or None if insufficient data
        """
        if period is None:
            period = self.rsi_period
        
        if len(self.candles) < period + 1:
            return None
        
        closes = [c.close for c in self.candles]
        
        # Calculate price changes
        changes = []
        for i in range(1, len(closes)):
            changes.append(closes[i] - closes[i-1])
        
        if len(changes) < period:
            return None
        
        # Get recent changes
        recent_changes = changes[-period:]
        
        # Separate gains and losses
        gains = [c if c > 0 else Decimal('0') for c in recent_changes]
        losses = [-c if c < 0 else Decimal('0') for c in recent_changes]
        
        # Calculate average gain and loss
        avg_gain = sum(gains) / Decimal(str(period))
        avg_loss = sum(losses) / Decimal(str(period))
        
        if avg_loss == 0:
            return Decimal('100')  # Perfect uptrend
        
        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = Decimal('100') - (Decimal('100') / (Decimal('1') + rs))
        
        return rsi
    
    def check_volume_breakout(self, current_volume: int, volume_multiplier: Decimal = Decimal('1.5')) -> bool:
        """
        Check if current volume is above average
        
        Args:
            current_volume: Current candle volume
            volume_multiplier: Multiplier for average volume (default: 1.5)
        
        Returns:
            bool: True if volume breakout
        """
        if len(self.candles) < 5:
            return False
        
        # Get last 5 candles volume
        recent_volumes = [c.volume for c in self.candles[-5:]]
        avg_volume = sum(recent_volumes) / Decimal(str(len(recent_volumes)))
        
        threshold = avg_volume * volume_multiplier
        
        return current_volume >= threshold
    
    def calculate_momentum_score(self, signal_type: str, current_candle: CandleData,
                                ema_fast: Decimal, ema_slow: Decimal, rsi: Decimal,
                                rsi_buy_min: int = 55, rsi_buy_max: int = 70,
                                rsi_sell_min: int = 30, rsi_sell_max: int = 45,
                                volume_multiplier: Decimal = Decimal('1.5')) -> Tuple[int, dict]:
        """
        Calculate momentum score (0-4)
        
        Requires ALL 4 conditions to be true for score = 4:
        1. Volume breakout (1.5x avg)
        2. EMA alignment (EMA20 > EMA50 for BUY, EMA20 < EMA50 for SELL)
        3. RSI in range (55-70 for BUY, 30-45 for SELL)
        4. Additional momentum check (can be price momentum)
        
        Args:
            signal_type: 'BUY' or 'SELL'
            current_candle: Current candle data
            ema_fast: Fast EMA value
            ema_slow: Slow EMA value
            rsi: RSI value
            rsi_buy_min: RSI minimum for BUY
            rsi_buy_max: RSI maximum for BUY
            rsi_sell_min: RSI minimum for SELL
            rsi_sell_max: RSI maximum for SELL
            volume_multiplier: Volume multiplier threshold
        
        Returns:
            Tuple of (score (0-4), details dict)
        """
        score = 0
        details = {
            'volume_breakout': False,
            'ema_alignment': False,
            'rsi_in_range': False,
            'price_momentum': False
        }
        
        # Check 1: Volume breakout
        if self.check_volume_breakout(current_candle.volume, volume_multiplier):
            score += 1
            details['volume_breakout'] = True
        
        # Check 2: EMA alignment
        if signal_type == 'BUY':
            if ema_fast and ema_slow and ema_fast > ema_slow:
                score += 1
                details['ema_alignment'] = True
        elif signal_type == 'SELL':
            if ema_fast and ema_slow and ema_fast < ema_slow:
                score += 1
                details['ema_alignment'] = True
        
        # Check 3: RSI in range
        if signal_type == 'BUY':
            if rsi and rsi_buy_min <= rsi <= rsi_buy_max:
                score += 1
                details['rsi_in_range'] = True
        elif signal_type == 'SELL':
            if rsi and rsi_sell_min <= rsi <= rsi_sell_max:
                score += 1
                details['rsi_in_range'] = True
        
        # Check 4: Price momentum (candle close > open for BUY, close < open for SELL)
        if signal_type == 'BUY':
            if current_candle.close > current_candle.open:
                score += 1
                details['price_momentum'] = True
        elif signal_type == 'SELL':
            if current_candle.close < current_candle.open:
                score += 1
                details['price_momentum'] = True
        
        return score, details


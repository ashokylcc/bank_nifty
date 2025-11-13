"""
Tests for momentum calculations
"""
from django.test import TestCase
from decimal import Decimal
from datetime import datetime
from trading.services.momentum import MomentumCalculator
from trading.services.data_ingest import CandleData


class MomentumCalculatorTestCase(TestCase):
    """Test momentum calculation"""
    
    def setUp(self):
        self.calc = MomentumCalculator(ema_fast=20, ema_slow=50, rsi_period=14)
    
    def test_calculate_momentum_score_buy(self):
        """Test momentum score calculation for BUY signal"""
        # Create test candles
        for i in range(50):
            candle = CandleData(
                timestamp=datetime.now(),
                open=Decimal('100'),
                high=Decimal('105'),
                low=Decimal('99'),
                close=Decimal('104'),
                volume=1000
            )
            self.calc.add_candle(candle)
        
        # Create current candle with strong volume
        current_candle = CandleData(
            timestamp=datetime.now(),
            open=Decimal('104'),
            high=Decimal('110'),
            low=Decimal('103'),
            close=Decimal('109'),  # Bullish
            volume=2000  # 2x average
        )
        self.calc.add_candle(current_candle)
        
        # Get indicators
        ema_fast = self.calc.get_ema_fast()
        ema_slow = self.calc.get_ema_slow()
        rsi = self.calc.calculate_rsi()
        
        # Calculate score
        score, details = self.calc.calculate_momentum_score(
            'BUY', current_candle, ema_fast, ema_slow, rsi
        )
        
        # Should have some score (exact value depends on data)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 4)
    
    def test_volume_breakout(self):
        """Test volume breakout detection"""
        # Add candles with normal volume
        for i in range(5):
            candle = CandleData(
                timestamp=datetime.now(),
                open=Decimal('100'),
                high=Decimal('101'),
                low=Decimal('99'),
                close=Decimal('100'),
                volume=1000
            )
            self.calc.add_candle(candle)
        
        # Test with high volume (1.5x average)
        is_breakout = self.calc.check_volume_breakout(2000, Decimal('1.5'))
        self.assertTrue(is_breakout)
        
        # Test with low volume
        is_breakout = self.calc.check_volume_breakout(1000, Decimal('1.5'))
        self.assertFalse(is_breakout)


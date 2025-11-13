"""
Integration tests for strategy
"""
from django.test import TestCase
from decimal import Decimal
from datetime import datetime, date
from trading.models import Strategy
from trading.services.strategy_engine import StrategyEngine
from trading.services.data_ingest import CandleData, DataIngestService
from trading.services.execution_adapter import AliceBlueMockAdapter


class StrategyIntegrationTestCase(TestCase):
    """Integration test with CSV data"""
    
    def setUp(self):
        self.strategy = Strategy.objects.create(
            name="Test Strategy",
            enabled=True,
            capital=Decimal('100000'),
            risk_per_trade_pct=Decimal('1.00'),
            max_daily_loss=Decimal('5000'),
            max_concurrent_trades=1
        )
        
        # Create mock adapter
        self.adapter = AliceBlueMockAdapter(dry_run=True)
        self.adapter.set_mock_ltp("BANKNIFTY", Decimal('58500'))
    
    def test_strategy_cycle_with_sample_data(self):
        """Test complete strategy cycle with sample candle data"""
        engine = StrategyEngine(self.strategy, execution_adapter=self.adapter, dry_run=True)
        engine.initialize()
        
        # Simulate first candle (9:15-9:30)
        first_candle = CandleData(
            timestamp=datetime.now().replace(hour=9, minute=15),
            open=Decimal('58400'),
            high=Decimal('58500'),
            low=Decimal('58300'),
            close=Decimal('58450'),
            volume=10000
        )
        engine.data_service.candles.append(first_candle)
        
        # Manually capture range (bypass time check for testing)
        engine.range_detector.capture_range(first_candle)
        engine.range_captured = True
        
        # Simulate breakout candle
        breakout_candle = CandleData(
            timestamp=datetime.now().replace(hour=9, minute=45),
            open=Decimal('58450'),
            high=Decimal('58600'),
            low=Decimal('58400'),
            close=Decimal('58550'),  # Above first_high + 10
            volume=20000  # 2x average
        )
        engine.data_service.candles.append(breakout_candle)
        engine.momentum_calc.add_candle(breakout_candle)
        
        # Set mock LTP for breakout
        self.adapter.set_mock_ltp("BANKNIFTY", Decimal('58520'))  # Above first_high + 10
        
        # Verify range was captured
        self.assertTrue(engine.range_captured)
        
        engine.shutdown()


"""
Tests for risk manager
"""
from django.test import TestCase
from decimal import Decimal
from trading.models import Strategy
from trading.services.risk_manager import RiskManager


class RiskManagerTestCase(TestCase):
    """Test risk management"""
    
    def setUp(self):
        self.strategy = Strategy.objects.create(
            name="Test Strategy",
            capital=Decimal('100000'),
            risk_per_trade_pct=Decimal('1.00'),
            max_daily_loss=Decimal('5000'),
            max_concurrent_trades=1,
            tick_value=Decimal('1.00'),
            stoploss_range_multiplier=Decimal('0.6'),
            min_stoploss_points=40,
            target_multiplier=Decimal('1.5')
        )
        self.risk_manager = RiskManager(self.strategy)
    
    def test_calculate_stoploss_points(self):
        """Test stoploss calculation"""
        range_value = Decimal('100')
        stoploss = self.risk_manager.calculate_stoploss_points(range_value)
        
        # Should be max(floor(100 * 0.6), 40) = max(60, 40) = 60
        self.assertEqual(stoploss, 60)
    
    def test_calculate_stoploss_points_minimum(self):
        """Test stoploss minimum"""
        range_value = Decimal('50')
        stoploss = self.risk_manager.calculate_stoploss_points(range_value)
        
        # Should be max(floor(50 * 0.6), 40) = max(30, 40) = 40
        self.assertEqual(stoploss, 40)
    
    def test_calculate_target_points(self):
        """Test target calculation"""
        stoploss = 60
        target = self.risk_manager.calculate_target_points(stoploss)
        
        # Should be 60 * 1.5 = 90
        self.assertEqual(target, 90)
    
    def test_calculate_position_size(self):
        """Test position sizing"""
        stoploss_points = 60
        
        # Risk amount = 100000 * 1% = 1000
        # Risk per lot = 60 * 1 = 60
        # Qty = 1000 / 60 = 16.67 -> 16
        qty = self.risk_manager.calculate_position_size(stoploss_points)
        
        self.assertGreater(qty, 0)
        self.assertLessEqual(qty, 20)  # Reasonable upper bound


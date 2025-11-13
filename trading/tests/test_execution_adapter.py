"""
Tests for execution adapter
"""
from django.test import TestCase
from decimal import Decimal
from trading.services.execution_adapter import AliceBlueMockAdapter


class ExecutionAdapterTestCase(TestCase):
    """Test execution adapter"""
    
    def setUp(self):
        self.adapter = AliceBlueMockAdapter(dry_run=True)
    
    def test_place_order_dry_run(self):
        """Test order placement in dry-run mode"""
        result = self.adapter.place_order(
            symbol="BANKNIFTY27NOV25C58400",
            side="BUY",
            qty=1,
            order_type="MARKET"
        )
        
        self.assertIn('order_id', result)
        self.assertEqual(result['status'], 'FILLED')
        self.assertIn('filled_price', result)
        self.assertTrue(result.get('dry_run', False))
    
    def test_get_order_status(self):
        """Test order status retrieval"""
        # Place order first
        order_result = self.adapter.place_order(
            symbol="BANKNIFTY27NOV25C58400",
            side="BUY",
            qty=1
        )
        
        order_id = order_result['order_id']
        status = self.adapter.get_order_status(order_id)
        
        self.assertEqual(status['status'], 'FILLED')
        self.assertEqual(status['order_id'], order_id)
    
    def test_cancel_order(self):
        """Test order cancellation"""
        # Place order first
        order_result = self.adapter.place_order(
            symbol="BANKNIFTY27NOV25C58400",
            side="BUY",
            qty=1
        )
        
        order_id = order_result['order_id']
        cancel_result = self.adapter.cancel_order(order_id)
        
        self.assertEqual(cancel_result['status'], 'CANCELLED')
    
    def test_get_ltp(self):
        """Test LTP retrieval"""
        symbol = "BANKNIFTY27NOV25C58400"
        ltp = self.adapter.get_ltp(symbol)
        
        self.assertIsNotNone(ltp)
        self.assertIsInstance(ltp, Decimal)


"""
Tests for expiry functions
"""
from django.test import TestCase
from datetime import date, timedelta
from trading.utils.expiry_functions import (
    get_nearest_thursday_expiry,
    build_option_symbol,
    round_to_nearest_strike
)


class ExpiryFunctionsTestCase(TestCase):
    """Test expiry calculation functions"""
    
    def test_get_nearest_thursday_expiry_today_is_thursday(self):
        """Test when today is Thursday"""
        thursday = date(2025, 11, 27)  # Thursday
        result = get_nearest_thursday_expiry(thursday)
        self.assertEqual(result, thursday)
    
    def test_get_nearest_thursday_expiry_wednesday(self):
        """Test when today is Wednesday (next day is Thursday)"""
        wednesday = date(2025, 11, 26)  # Wednesday
        result = get_nearest_thursday_expiry(wednesday)
        expected = date(2025, 11, 27)  # Next Thursday
        self.assertEqual(result, expected)
    
    def test_get_nearest_thursday_expiry_friday(self):
        """Test when today is Friday (next Thursday is 6 days away)"""
        friday = date(2025, 11, 28)  # Friday
        result = get_nearest_thursday_expiry(friday)
        expected = date(2025, 12, 4)  # Next Thursday
        self.assertEqual(result, expected)
    
    def test_build_option_symbol(self):
        """Test option symbol building"""
        expiry = date(2025, 11, 27)
        strike = 58400
        option_type = 'C'
        
        symbol = build_option_symbol(expiry, strike, option_type)
        expected = "BANKNIFTY27NOV25C58400"
        self.assertEqual(symbol, expected)
    
    def test_round_to_nearest_strike(self):
        """Test strike rounding"""
        # Test rounding to nearest 100
        self.assertEqual(round_to_nearest_strike(58423), 58400)
        self.assertEqual(round_to_nearest_strike(58475), 58500)
        # Note: 58450 rounds to 58400 due to Python's round() behavior (round half to even)
        self.assertEqual(round_to_nearest_strike(58450), 58400)
        self.assertEqual(round_to_nearest_strike(58451), 58500)  # Above midpoint
        
        # Test with custom step
        self.assertEqual(round_to_nearest_strike(58423, step=50), 58400)
        self.assertEqual(round_to_nearest_strike(58475, step=50), 58500)


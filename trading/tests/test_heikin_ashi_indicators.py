"""
Unit tests for Heikin-Ashi, RMA ATR, SuperTrend, and MACD indicators
Tests match TradingView formulas exactly
"""
import unittest
from decimal import Decimal
from datetime import datetime
from trading.services.heikin_ashi import HeikinAshiCalculator, calculate_heikin_ashi
from trading.services.super_trend import SuperTrendCalculator, calculate_rma, calculate_atr
from trading.services.macd import MACDCalculator, calculate_ema


class TestHeikinAshi(unittest.TestCase):
    """Test Heikin-Ashi calculation matches TradingView"""
    
    def test_ha_first_candle(self):
        """Test first HA candle calculation"""
        regular_candle = {
            'open': Decimal('100'),
            'high': Decimal('110'),
            'low': Decimal('95'),
            'close': Decimal('105'),
            'timestamp': datetime.now()
        }
        
        ha_candle = calculate_heikin_ashi(regular_candle, None)
        
        # HA_Close = (O+H+L+C)/4
        expected_ha_close = (Decimal('100') + Decimal('110') + Decimal('95') + Decimal('105')) / Decimal('4')
        self.assertEqual(ha_candle['ha_close'], expected_ha_close)
        
        # HA_Open = (Regular Open + Regular Close) / 2 (for first candle)
        expected_ha_open = (Decimal('100') + Decimal('105')) / Decimal('2')
        self.assertEqual(ha_candle['ha_open'], expected_ha_open)
        
        # HA_High = max(H, HA_Open, HA_Close)
        expected_ha_high = max(Decimal('110'), ha_candle['ha_open'], ha_candle['ha_close'])
        self.assertEqual(ha_candle['ha_high'], expected_ha_high)
        
        # HA_Low = min(L, HA_Open, HA_Close)
        expected_ha_low = min(Decimal('95'), ha_candle['ha_open'], ha_candle['ha_close'])
        self.assertEqual(ha_candle['ha_low'], expected_ha_low)
    
    def test_ha_sequential_candles(self):
        """Test HA calculation with previous HA candle"""
        calc = HeikinAshiCalculator()
        
        # First candle
        candle1 = {
            'open': Decimal('100'),
            'high': Decimal('110'),
            'low': Decimal('95'),
            'close': Decimal('105'),
            'timestamp': datetime.now()
        }
        ha1 = calc.add_candle(candle1)
        
        # Second candle
        candle2 = {
            'open': Decimal('105'),
            'high': Decimal('115'),
            'low': Decimal('100'),
            'close': Decimal('110'),
            'timestamp': datetime.now()
        }
        ha2 = calc.add_candle(candle2)
        
        # HA_Open for second candle = (prev_HA_Open + prev_HA_Close) / 2
        expected_ha_open2 = (ha1['ha_open'] + ha1['ha_close']) / Decimal('2')
        self.assertEqual(ha2['ha_open'], expected_ha_open2)
        
        # HA_Close for second candle = (O+H+L+C)/4
        expected_ha_close2 = (Decimal('105') + Decimal('115') + Decimal('100') + Decimal('110')) / Decimal('4')
        self.assertEqual(ha2['ha_close'], expected_ha_close2)


class TestRMAATR(unittest.TestCase):
    """Test RMA (Wilder's Smoothing) ATR calculation"""
    
    def test_rma_calculation(self):
        """Test RMA calculation matches TradingView"""
        # RMA formula: RMA = (prev_RMA * (period-1) + current_value) / period
        values = [Decimal('10'), Decimal('12'), Decimal('11'), Decimal('13'), Decimal('14')]
        period = 3
        
        rma = calculate_rma(values, period)
        
        # First RMA = SMA of first period values
        expected_sma = (Decimal('10') + Decimal('12') + Decimal('11')) / Decimal('3')
        
        # Then apply RMA formula for remaining values
        # RMA = (SMA * (period-1) + value[3]) / period
        expected_rma = (expected_sma * Decimal('2') + Decimal('13')) / Decimal('3')
        # RMA = (RMA * (period-1) + value[4]) / period
        expected_rma = (expected_rma * Decimal('2') + Decimal('14')) / Decimal('3')
        
        self.assertAlmostEqual(float(rma), float(expected_rma), places=2)
    
    def test_atr_with_rma(self):
        """Test ATR calculation using RMA"""
        # Create sample HA candles
        ha_candles = []
        for i in range(15):
            ha_candles.append({
                'ha_high': Decimal('100') + Decimal(str(i)),
                'ha_low': Decimal('95') - Decimal(str(i)),
                'ha_close': Decimal('98') + Decimal(str(i * 0.5))
            })
        
        atr = calculate_atr(ha_candles, period=10)
        
        # ATR should be calculated using RMA, not None
        self.assertIsNotNone(atr)
        self.assertGreater(atr, Decimal('0'))


class TestSuperTrend(unittest.TestCase):
    """Test SuperTrend calculation and flip logic"""
    
    def test_super_trend_initial(self):
        """Test initial SuperTrend calculation"""
        calc = SuperTrendCalculator(atr_period=10, multiplier=Decimal('3.0'))
        
        # Need at least 11 candles for ATR(10)
        for i in range(11):
            ha_candle = {
                'ha_high': Decimal('100') + Decimal(str(i)),
                'ha_low': Decimal('95') - Decimal(str(i)),
                'ha_close': Decimal('98') + Decimal(str(i * 0.5)),
                'timestamp': datetime.now()
            }
            st = calc.add_candle(ha_candle)
        
        # Should have SuperTrend after 11 candles
        last_st = calc.get_last_super_trend()
        self.assertIsNotNone(last_st)
        self.assertIn('value', last_st)
        self.assertIn('color', last_st)
        self.assertIn(last_st['color'], ['GREEN', 'RED'])
    
    def test_super_trend_flip_logic(self):
        """Test SuperTrend color flip when close crosses bands"""
        calc = SuperTrendCalculator(atr_period=10, multiplier=Decimal('3.0'))
        
        # Initialize with enough candles
        for i in range(11):
            ha_candle = {
                'ha_high': Decimal('100') + Decimal(str(i)),
                'ha_low': Decimal('95') - Decimal(str(i)),
                'ha_close': Decimal('98') + Decimal(str(i * 0.5)),
                'timestamp': datetime.now()
            }
            calc.add_candle(ha_candle)
        
        # Get initial ST
        initial_st = calc.get_last_super_trend()
        initial_color = initial_st['color']
        
        # Add candle that should flip color
        if initial_color == 'GREEN':
            # Add candle with close below ST to flip to RED
            ha_candle = {
                'ha_high': Decimal('90'),
                'ha_low': Decimal('85'),
                'ha_close': initial_st['value'] - Decimal('10'),  # Close below ST
                'timestamp': datetime.now()
            }
        else:
            # Add candle with close above ST to flip to GREEN
            ha_candle = {
                'ha_high': Decimal('110'),
                'ha_low': Decimal('105'),
                'ha_close': initial_st['value'] + Decimal('10'),  # Close above ST
                'timestamp': datetime.now()
            }
        
        new_st = calc.add_candle(ha_candle)
        
        # Color should flip
        self.assertNotEqual(new_st['color'], initial_color)


class TestMACD(unittest.TestCase):
    """Test MACD calculation with incremental updates"""
    
    def test_ema_calculation(self):
        """Test EMA calculation"""
        values = [Decimal('100'), Decimal('102'), Decimal('101'), Decimal('103'), Decimal('104')]
        period = 3
        
        ema = calculate_ema(values, period)
        
        # EMA should be calculated
        self.assertIsNotNone(ema)
        self.assertGreater(ema, Decimal('0'))
    
    def test_macd_incremental(self):
        """Test MACD incremental state maintenance"""
        calc = MACDCalculator(fast_period=12, slow_period=26, signal_period=9)
        
        # Need at least 26 candles for slow EMA
        for i in range(35):  # 35 candles to ensure MACD is ready
            ha_candle = {
                'ha_close': Decimal('100') + Decimal(str(i * 0.5)),
                'timestamp': datetime.now()
            }
            macd = calc.add_candle(ha_candle)
        
        # MACD should be ready after 35 candles
        last_macd = calc.get_last_macd()
        self.assertIsNotNone(last_macd)
        self.assertIn('macd_line', last_macd)
        self.assertIn('signal_line', last_macd)
        self.assertIn('histogram', last_macd)
        
        # Histogram = MACD Line - Signal Line
        expected_histogram = last_macd['macd_line'] - last_macd['signal_line']
        self.assertEqual(last_macd['histogram'], expected_histogram)
    
    def test_macd_not_ready(self):
        """Test MACD returns None when insufficient candles"""
        calc = MACDCalculator(fast_period=12, slow_period=26, signal_period=9)
        
        # Add only 10 candles (need at least 26 for slow EMA)
        for i in range(10):
            ha_candle = {
                'ha_close': Decimal('100') + Decimal(str(i)),
                'timestamp': datetime.now()
            }
            macd = calc.add_candle(ha_candle)
        
        # MACD should not be ready
        self.assertIsNone(macd)


if __name__ == '__main__':
    unittest.main()


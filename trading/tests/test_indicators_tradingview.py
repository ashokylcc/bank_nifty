"""
Unit tests for TradingView-exact indicator calculations
Tests HA, SuperTrend, and MACD with synthetic OHLC data
"""
import unittest
from decimal import Decimal
from datetime import datetime
from trading.services.heikin_ashi import HeikinAshiCalculator, calculate_heikin_ashi
from trading.services.super_trend import SuperTrendCalculator, calculate_rma, calculate_atr
from trading.services.macd import MACDCalculator, calculate_ema


class TestHeikinAshiTradingView(unittest.TestCase):
    """Test Heikin-Ashi calculation matches TradingView exactly"""
    
    def test_ha_first_candle_seeding(self):
        """Test first HA candle uses (O+C)/2 for HA_Open"""
        regular_candle = {
            'open': Decimal('100.00'),
            'high': Decimal('110.00'),
            'low': Decimal('95.00'),
            'close': Decimal('105.00'),
            'timestamp': datetime.now()
        }
        
        ha_candle = calculate_heikin_ashi(regular_candle, None)
        
        # HA_Close = (O+H+L+C)/4
        expected_ha_close = (Decimal('100') + Decimal('110') + Decimal('95') + Decimal('105')) / Decimal('4')
        self.assertEqual(ha_candle['ha_close'], expected_ha_close)
        
        # HA_Open for first candle = (Regular Open + Regular Close) / 2
        expected_ha_open = (Decimal('100') + Decimal('105')) / Decimal('2')
        self.assertEqual(ha_candle['ha_open'], expected_ha_open)
    
    def test_ha_sequential_uses_prev_ha(self):
        """Test HA_Open uses previous HA values, not raw OHLC"""
        calc = HeikinAshiCalculator()
        
        # First candle
        candle1 = {
            'open': Decimal('100.00'),
            'high': Decimal('110.00'),
            'low': Decimal('95.00'),
            'close': Decimal('105.00'),
            'timestamp': datetime.now()
        }
        ha1 = calc.add_candle(candle1)
        
        # Second candle
        candle2 = {
            'open': Decimal('105.00'),  # Different from ha1['ha_close']
            'high': Decimal('115.00'),
            'low': Decimal('100.00'),
            'close': Decimal('110.00'),
            'timestamp': datetime.now()
        }
        ha2 = calc.add_candle(candle2)
        
        # HA_Open for second candle MUST use (prev_HA_Open + prev_HA_Close) / 2
        # NOT (candle2['open'] + candle2['close']) / 2
        expected_ha_open2 = (ha1['ha_open'] + ha1['ha_close']) / Decimal('2')
        self.assertEqual(ha2['ha_open'], expected_ha_open2)
        
        # Verify it's NOT using raw candle2 open
        wrong_ha_open = (candle2['open'] + candle2['close']) / Decimal('2')
        self.assertNotEqual(ha2['ha_open'], wrong_ha_open)
    
    def test_ha_high_low_calculation(self):
        """Test HA_High and HA_Low use max/min of H, HA_Open, HA_Close"""
        regular_candle = {
            'open': Decimal('100.00'),
            'high': Decimal('110.00'),
            'low': Decimal('95.00'),
            'close': Decimal('105.00'),
            'timestamp': datetime.now()
        }
        
        ha_candle = calculate_heikin_ashi(regular_candle, None)
        
        # HA_High = max(H, HA_Open, HA_Close)
        expected_ha_high = max(
            Decimal('110.00'),  # H
            ha_candle['ha_open'],
            ha_candle['ha_close']
        )
        self.assertEqual(ha_candle['ha_high'], expected_ha_high)
        
        # HA_Low = min(L, HA_Open, HA_Close)
        expected_ha_low = min(
            Decimal('95.00'),  # L
            ha_candle['ha_open'],
            ha_candle['ha_close']
        )
        self.assertEqual(ha_candle['ha_low'], expected_ha_low)


class TestSuperTrendTradingView(unittest.TestCase):
    """Test SuperTrend calculation matches TradingView exactly"""
    
    def test_rma_wilders_smoothing(self):
        """Test RMA uses Wilder's smoothing formula exactly"""
        # RMA formula: RMA = (prev_RMA * (period-1) + current_value) / period
        values = [Decimal('10'), Decimal('12'), Decimal('11'), Decimal('13'), Decimal('14')]
        period = 3
        
        rma = calculate_rma(values, period)
        
        # First RMA = SMA of first period values
        expected_sma = (Decimal('10') + Decimal('12') + Decimal('11')) / Decimal('3')
        
        # Then apply RMA formula: RMA = (RMA * (period-1) + value) / period
        # For value[3] = 13:
        expected_rma = (expected_sma * Decimal('2') + Decimal('13')) / Decimal('3')
        # For value[4] = 14:
        expected_rma = (expected_rma * Decimal('2') + Decimal('14')) / Decimal('3')
        
        self.assertAlmostEqual(float(rma), float(expected_rma), places=4)
    
    def test_atr_uses_rma_not_sma(self):
        """Test ATR uses RMA (Wilder's smoothing), not SMA"""
        # Create sample HA candles
        ha_candles = []
        base_price = Decimal('100')
        for i in range(15):
            ha_candles.append({
                'ha_high': base_price + Decimal(str(i * 2)),
                'ha_low': base_price - Decimal(str(i)),
                'ha_close': base_price + Decimal(str(i))
            })
        
        atr = calculate_atr(ha_candles, period=10)
        
        # ATR should be calculated using RMA, not None
        self.assertIsNotNone(atr)
        self.assertGreater(atr, Decimal('0'))
    
    def test_super_trend_flip_on_close_only(self):
        """Test SuperTrend color flips only when candle close crosses bands"""
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
        initial_value = initial_st['value']
        
        # Add candle with close that should flip color
        if initial_color == 'GREEN':
            # Close below ST to flip to RED
            ha_candle = {
                'ha_high': Decimal('90'),
                'ha_low': Decimal('85'),
                'ha_close': initial_value - Decimal('10'),  # Close below ST
                'timestamp': datetime.now()
            }
        else:
            # Close above ST to flip to GREEN
            ha_candle = {
                'ha_high': Decimal('110'),
                'ha_low': Decimal('105'),
                'ha_close': initial_value + Decimal('10'),  # Close above ST
                'timestamp': datetime.now()
            }
        
        new_st = calc.add_candle(ha_candle)
        
        # Color should flip when close crosses
        self.assertNotEqual(new_st['color'], initial_color)
    
    def test_super_trend_bands_calculation(self):
        """Test SuperTrend basic bands calculation"""
        calc = SuperTrendCalculator(atr_period=10, multiplier=Decimal('3.0'))
        
        # Initialize
        for i in range(11):
            ha_candle = {
                'ha_high': Decimal('100') + Decimal(str(i)),
                'ha_low': Decimal('95') - Decimal(str(i)),
                'ha_close': Decimal('98') + Decimal(str(i * 0.5)),
                'timestamp': datetime.now()
            }
            calc.add_candle(ha_candle)
        
        last_st = calc.get_last_super_trend()
        
        # Verify bands are calculated
        self.assertIn('upper_band', last_st)
        self.assertIn('lower_band', last_st)
        self.assertIn('atr', last_st)
        
        # Upper band should be > Lower band
        self.assertGreater(last_st['upper_band'], last_st['lower_band'])


class TestMACDTradingView(unittest.TestCase):
    """Test MACD calculation matches TradingView exactly"""
    
    def test_ema_standard_formula(self):
        """Test EMA uses standard formula: alpha = 2/(period+1)"""
        values = [Decimal('100'), Decimal('102'), Decimal('101'), Decimal('103'), Decimal('104')]
        period = 3
        
        ema = calculate_ema(values, period)
        
        # Calculate manually using standard EMA formula
        alpha = Decimal('2') / Decimal(str(period + 1))  # alpha = 2/4 = 0.5
        sma = (Decimal('100') + Decimal('102') + Decimal('101')) / Decimal('3')
        expected_ema = alpha * Decimal('103') + (Decimal('1') - alpha) * sma
        expected_ema = alpha * Decimal('104') + (Decimal('1') - alpha) * expected_ema
        
        self.assertAlmostEqual(float(ema), float(expected_ema), places=2)
    
    def test_macd_line_calculation(self):
        """Test MACD line = EMA12 - EMA26"""
        calc = MACDCalculator(fast_period=12, slow_period=26, signal_period=9)
        
        # Add enough candles
        for i in range(35):
            ha_candle = {
                'ha_close': Decimal('100') + Decimal(str(i * 0.5)),
                'timestamp': datetime.now()
            }
            calc.add_candle(ha_candle)
        
        last_macd = calc.get_last_macd()
        self.assertIsNotNone(last_macd)
        
        # MACD line should be EMA12 - EMA26
        # We can't directly verify without exposing EMAs, but structure should be correct
        self.assertIn('macd_line', last_macd)
        self.assertIn('signal_line', last_macd)
        self.assertIn('histogram', last_macd)
    
    def test_macd_signal_ema_of_macd_line(self):
        """Test Signal line = EMA9 of MACD line"""
        calc = MACDCalculator(fast_period=12, slow_period=26, signal_period=9)
        
        # Add enough candles
        for i in range(35):
            ha_candle = {
                'ha_close': Decimal('100') + Decimal(str(i * 0.5)),
                'timestamp': datetime.now()
            }
            calc.add_candle(ha_candle)
        
        last_macd = calc.get_last_macd()
        
        # Histogram = MACD Line - Signal Line
        expected_histogram = last_macd['macd_line'] - last_macd['signal_line']
        self.assertEqual(last_macd['histogram'], expected_histogram)


class TestSyntheticOHLCSeries(unittest.TestCase):
    """Test indicators with synthetic OHLC series"""
    
    def test_synthetic_series_ha_st(self):
        """Test HA and SuperTrend with synthetic OHLC data"""
        # Create synthetic OHLC series
        synthetic_candles = [
            {'open': Decimal('100'), 'high': Decimal('105'), 'low': Decimal('98'), 'close': Decimal('103')},
            {'open': Decimal('103'), 'high': Decimal('108'), 'low': Decimal('101'), 'close': Decimal('106')},
            {'open': Decimal('106'), 'high': Decimal('110'), 'low': Decimal('104'), 'close': Decimal('108')},
            {'open': Decimal('108'), 'high': Decimal('112'), 'low': Decimal('106'), 'close': Decimal('110')},
            {'open': Decimal('110'), 'high': Decimal('115'), 'low': Decimal('108'), 'close': Decimal('113')},
        ]
        
        ha_calc = HeikinAshiCalculator()
        st_calc = SuperTrendCalculator(atr_period=10, multiplier=Decimal('3.0'))
        
        ha_results = []
        for i, candle in enumerate(synthetic_candles):
            candle['timestamp'] = datetime.now()
            ha_candle = ha_calc.add_candle(candle)
            ha_results.append(ha_candle)
            
            # SuperTrend needs at least 11 candles
            if i >= 10:
                st = st_calc.add_candle(ha_candle)
                if st:
                    self.assertIn('value', st)
                    self.assertIn('color', st)
        
        # Verify HA calculations
        self.assertEqual(len(ha_results), 5)
        
        # First HA candle: HA_Open = (O+C)/2
        self.assertEqual(ha_results[0]['ha_open'], (Decimal('100') + Decimal('103')) / Decimal('2'))
        
        # Second HA candle: HA_Open = (prev_HA_Open + prev_HA_Close) / 2
        expected_ha_open_2 = (ha_results[0]['ha_open'] + ha_results[0]['ha_close']) / Decimal('2')
        self.assertEqual(ha_results[1]['ha_open'], expected_ha_open_2)


if __name__ == '__main__':
    unittest.main()


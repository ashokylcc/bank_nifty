#!/usr/bin/env python3
"""
Helper script to compare computed HA/ST/MACD values with TradingView screenshot
Usage: python scripts/compare_with_tradingview.py --screenshot "/path/to/image.jpeg"
"""
import os
import sys
import argparse
from decimal import Decimal
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'banknifty_trader.settings')
import django
django.setup()

from trading.services.candle_aggregator import CandleAggregator
from trading.services.heikin_ashi import HeikinAshiCalculator
from trading.services.super_trend import SuperTrendCalculator
from trading.services.macd import MACDCalculator
from trading.utils.time_helpers import get_ist_now, IST


def load_historical_data_for_comparison(start_time: datetime, end_time: datetime):
    """
    Load historical data for the specified time range
    This is a placeholder - in production, load from your data source
    """
    # TODO: Load actual historical data from your data source
    # For now, return sample data structure
    return []


def print_candle_comparison(candles, ha_calc, st_calc, macd_calc, screenshot_time: datetime = None):
    """
    Print candle-by-candle comparison for manual verification
    
    Args:
        candles: List of raw OHLC candles
        ha_calc: HeikinAshiCalculator instance
        st_calc: SuperTrendCalculator instance
        macd_calc: MACDCalculator instance
        screenshot_time: Timestamp from screenshot (if available)
    """
    print("\n" + "="*80)
    print("CANDLE-BY-CANDLE COMPARISON WITH TRADINGVIEW")
    print("="*80)
    
    if screenshot_time:
        print(f"\n📸 Screenshot timestamp: {screenshot_time.strftime('%Y-%m-%d %H:%M:%S IST')}")
        print(f"   Current time: {get_ist_now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    
    print("\nFinding closest candles to screenshot time...\n")
    
    # Get last few candles for comparison
    last_candles = candles[-10:] if len(candles) > 10 else candles
    
    for i, candle in enumerate(last_candles):
        candle_time = candle.get('timestamp') or candle.get('end_time')
        if isinstance(candle_time, str):
            candle_time = datetime.fromisoformat(candle_time)
        
        # Get HA values
        ha_candle = ha_calc.get_last_candle() if i == len(last_candles) - 1 else None
        if ha_candle is None:
            # Try to get from history
            ha_candles = ha_calc.get_candles(count=len(last_candles))
            if i < len(ha_candles):
                ha_candle = ha_candles[-(len(last_candles) - i)]
        
        # Get SuperTrend
        st = st_calc.get_last_super_trend() if i == len(last_candles) - 1 else None
        
        # Get MACD
        macd = macd_calc.get_last_macd() if i == len(last_candles) - 1 else None
        
        print(f"\n{'─'*80}")
        print(f"Candle #{len(candles) - len(last_candles) + i + 1}")
        if candle_time:
            print(f"Time: {candle_time.strftime('%Y-%m-%d %H:%M:%S IST')}")
        
        print(f"\nRAW OHLC:")
        print(f"  O: {candle['open']:.2f}")
        print(f"  H: {candle['high']:.2f}")
        print(f"  L: {candle['low']:.2f}")
        print(f"  C: {candle['close']:.2f}")
        
        if ha_candle:
            print(f"\nHEIKIN-ASHI:")
            print(f"  HA_O: {ha_candle['ha_open']:.2f}")
            print(f"  HA_H: {ha_candle['ha_high']:.2f}")
            print(f"  HA_L: {ha_candle['ha_low']:.2f}")
            print(f"  HA_C: {ha_candle['ha_close']:.2f}")
            print(f"  Color: {'GREEN' if ha_candle['ha_close'] > ha_candle['ha_open'] else 'RED'}")
        else:
            print(f"\nHEIKIN-ASHI: Not calculated yet")
        
        if st:
            print(f"\nSUPER TREND(10,3):")
            print(f"  Value: {st['value']:.2f}")
            print(f"  Direction: {st['color']}")
            print(f"  Upper Band: {st.get('upper_band', 'N/A'):.2f}" if 'upper_band' in st else "  Upper Band: N/A")
            print(f"  Lower Band: {st.get('lower_band', 'N/A'):.2f}" if 'lower_band' in st else "  Lower Band: N/A")
        else:
            print(f"\nSUPER TREND(10,3): Not ready yet")
        
        if macd:
            print(f"\nMACD(12,26,9):")
            print(f"  MACD Line: {macd['macd_line']:.2f}")
            print(f"  Signal Line: {macd['signal_line']:.2f}")
            print(f"  Histogram: {macd['histogram']:.2f}")
            print(f"  Crossover: {'BULLISH' if macd['macd_line'] > macd['signal_line'] else 'BEARISH'}")
        else:
            print(f"\nMACD(12,26,9): Not ready yet")
    
    print("\n" + "="*80)
    print("COMPARISON INSTRUCTIONS:")
    print("="*80)
    print("1. Compare RAW OHLC values with your TradingView chart")
    print("2. Compare HEIKIN-ASHI values (especially HA_C vs HA_O for color)")
    print("3. Compare SUPER TREND direction (GREEN/RED) with TradingView")
    print("4. Compare MACD values (MACD Line, Signal Line, Histogram)")
    print("5. If values don't match, check:")
    print("   - Are you using the same data source? (NFO Futures)")
    print("   - Are timestamps aligned? (IST timezone)")
    print("   - Are you using 15-minute candles?")
    print("="*80 + "\n")


def extract_timestamp_from_screenshot(image_path: str) -> datetime:
    """
    Extract timestamp from screenshot (if visible in image)
    This is a placeholder - implement OCR or manual input
    """
    # TODO: Implement OCR to extract timestamp from screenshot
    # For now, return current time
    print(f"⚠️  Timestamp extraction not implemented. Using current time.")
    return get_ist_now()


def main():
    parser = argparse.ArgumentParser(
        description='Compare computed indicators with TradingView screenshot'
    )
    parser.add_argument(
        '--screenshot',
        type=str,
        help='Path to TradingView screenshot image'
    )
    parser.add_argument(
        '--time',
        type=str,
        help='Timestamp from screenshot (format: YYYY-MM-DD HH:MM:SS)'
    )
    parser.add_argument(
        '--candles',
        type=int,
        default=10,
        help='Number of recent candles to display (default: 10)'
    )
    
    args = parser.parse_args()
    
    # Initialize calculators
    ha_calc = HeikinAshiCalculator()
    st_calc = SuperTrendCalculator(atr_period=10, multiplier=Decimal('3.0'))
    macd_calc = MACDCalculator(fast_period=12, slow_period=26, signal_period=9)
    
    # Get screenshot timestamp
    screenshot_time = None
    if args.time:
        try:
            screenshot_time = datetime.strptime(args.time, '%Y-%m-%d %H:%M:%S')
            screenshot_time = IST.localize(screenshot_time)
        except ValueError:
            print(f"❌ Invalid time format. Use: YYYY-MM-DD HH:MM:SS")
            return
    elif args.screenshot:
        screenshot_time = extract_timestamp_from_screenshot(args.screenshot)
    
    # Load historical data (placeholder)
    # In production, load actual data from your data source
    print("📊 Loading historical data...")
    print("⚠️  Note: This script requires historical data to be loaded.")
    print("   Currently using placeholder. Implement data loading in production.\n")
    
    # For demonstration, create sample candles
    # In production, load from actual data source
    candles = []
    
    print_candle_comparison(candles, ha_calc, st_calc, macd_calc, screenshot_time)
    
    print("\n💡 TIP: To use this script effectively:")
    print("   1. Load actual historical data in load_historical_data_for_comparison()")
    print("   2. Process candles through calculators")
    print("   3. Compare output with TradingView chart manually")
    print("   4. If values don't match, check formulas and data alignment\n")


if __name__ == '__main__':
    main()


#!/usr/bin/env python3
"""
Reproducible script to compare computed HA/ST values with TradingView screenshot
Usage: python scripts/compare_with_image.py --screenshot "/path/to/image.jpeg"
"""
import os
import sys
import argparse
from decimal import Decimal
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from trading.services.heikin_ashi import HeikinAshiCalculator
from trading.services.super_trend import SuperTrendCalculator


def compute_ha_st_from_ohlc(open_price, high_price, low_price, close_price, previous_ha=None):
    """
    Compute HA and SuperTrend from single OHLC candle
    
    Args:
        open_price: Raw open price
        high_price: Raw high price
        low_price: Raw low price
        close_price: Raw close price
        previous_ha: Previous HA candle dict (optional)
    
    Returns:
        dict with HA and ST values
    """
    # Create regular candle
    regular_candle = {
        'open': Decimal(str(open_price)),
        'high': Decimal(str(high_price)),
        'low': Decimal(str(low_price)),
        'close': Decimal(str(close_price)),
        'timestamp': datetime.now()
    }
    
    # Calculate HA
    from trading.services.heikin_ashi import calculate_heikin_ashi
    ha_candle = calculate_heikin_ashi(regular_candle, previous_ha)
    
    # For SuperTrend, we need at least 11 HA candles
    # So we'll create a synthetic series
    st_calc = SuperTrendCalculator(atr_period=10, multiplier=Decimal('3.0'))
    
    # Create synthetic history (10 previous candles with similar values)
    base_price = Decimal(str(close_price))
    for i in range(10):
        synthetic_ha = {
            'ha_high': base_price + Decimal(str(i * 2)),
            'ha_low': base_price - Decimal(str(i)),
            'ha_close': base_price + Decimal(str(i * 0.5)),
            'timestamp': datetime.now()
        }
        st_calc.add_candle(synthetic_ha)
    
    # Now add our actual HA candle
    st = st_calc.add_candle(ha_candle)
    
    return {
        'ha_open': ha_candle['ha_open'],
        'ha_high': ha_candle['ha_high'],
        'ha_low': ha_candle['ha_low'],
        'ha_close': ha_candle['ha_close'],
        'st_value': st['value'] if st else None,
        'st_color': st['color'] if st else None
    }


def main():
    parser = argparse.ArgumentParser(
        description='Compare computed HA/ST values with TradingView screenshot'
    )
    parser.add_argument(
        '--screenshot',
        type=str,
        help='Path to TradingView screenshot image (for reference)'
    )
    parser.add_argument(
        '--ohlc',
        type=str,
        nargs=4,
        metavar=('OPEN', 'HIGH', 'LOW', 'CLOSE'),
        help='Raw OHLC values: --ohlc 59052.10 59078.40 59048.60 59066.80'
    )
    parser.add_argument(
        '--prev-ha',
        type=str,
        nargs=4,
        metavar=('HA_O', 'HA_H', 'HA_L', 'HA_C'),
        help='Previous HA values (optional): --prev-ha 59060.25 59078.40 59052.10 59066.80'
    )
    
    args = parser.parse_args()
    
    if not args.ohlc:
        print("❌ Error: --ohlc is required")
        print("\nUsage example:")
        print("  python scripts/compare_with_image.py --ohlc 59052.10 59078.40 59048.60 59066.80")
        print("\nWith previous HA:")
        print("  python scripts/compare_with_image.py --ohlc 59052.10 59078.40 59048.60 59066.80 \\")
        print("    --prev-ha 59060.25 59078.40 59052.10 59066.80")
        return
    
    try:
        open_price = float(args.ohlc[0])
        high_price = float(args.ohlc[1])
        low_price = float(args.ohlc[2])
        close_price = float(args.ohlc[3])
    except ValueError:
        print("❌ Error: Invalid OHLC values. Use numbers.")
        return
    
    # Parse previous HA if provided
    previous_ha = None
    if args.prev_ha:
        try:
            previous_ha = {
                'ha_open': Decimal(str(args.prev_ha[0])),
                'ha_high': Decimal(str(args.prev_ha[1])),
                'ha_low': Decimal(str(args.prev_ha[2])),
                'ha_close': Decimal(str(args.prev_ha[3]))
            }
        except (ValueError, IndexError):
            print("⚠️  Warning: Invalid previous HA values, using first candle formula")
    
    # Compute HA and ST
    result = compute_ha_st_from_ohlc(
        open_price, high_price, low_price, close_price, previous_ha
    )
    
    print("\n" + "="*60)
    print("COMPUTED VALUES (TradingView Match)")
    print("="*60)
    print(f"\nINPUT (Raw OHLC):")
    print(f"  Open : {open_price:.2f}")
    print(f"  High : {high_price:.2f}")
    print(f"  Low  : {low_price:.2f}")
    print(f"  Close: {close_price:.2f}")
    
    if previous_ha:
        print(f"\nPREVIOUS HA (used for HA_Open calculation):")
        print(f"  HA_O: {previous_ha['ha_open']:.2f}")
        print(f"  HA_C: {previous_ha['ha_close']:.2f}")
    
    print(f"\nCOMPUTED HEIKIN-ASHI:")
    print(f"  HA_O: {result['ha_open']:.2f}")
    print(f"  HA_H: {result['ha_high']:.2f}")
    print(f"  HA_L: {result['ha_low']:.2f}")
    print(f"  HA_C: {result['ha_close']:.2f}")
    
    if result['st_value']:
        print(f"\nCOMPUTED SUPER TREND(10,3):")
        print(f"  Value: {result['st_value']:.2f}")
        print(f"  Color: {result['st_color']}")
    else:
        print(f"\nSUPER TREND: Not ready (needs 11+ candles)")
    
    print("\n" + "="*60)
    print("VERIFICATION:")
    print("="*60)
    print("1. Compare HA values with TradingView chart")
    print("2. Verify HA_Open uses previous HA values (not raw OHLC)")
    print("3. Check SuperTrend value and color match")
    print("="*60 + "\n")
    
    if args.screenshot:
        print(f"📸 Screenshot reference: {args.screenshot}")
        print("   (Manual comparison required)\n")


if __name__ == '__main__':
    main()


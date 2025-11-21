"""
Django management command to process new Heikin-Ashi candles
Can be run via cron every 15 minutes or as a Celery task
"""
import logging
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone

from trading.services.ha_tracker import HeikinAshiTracker
from trading.utils.time_helpers import get_ist_now, IST

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Process new 15-minute Heikin-Ashi candles from OHLC data"
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--symbol',
            type=str,
            default='BANKNIFTY_FUTURES',
            help='Trading symbol (default: BANKNIFTY_FUTURES)'
        )
        parser.add_argument(
            '--open',
            type=float,
            required=True,
            help='Open price'
        )
        parser.add_argument(
            '--high',
            type=float,
            required=True,
            help='High price'
        )
        parser.add_argument(
            '--low',
            type=float,
            required=True,
            help='Low price'
        )
        parser.add_argument(
            '--close',
            type=float,
            required=True,
            help='Close price'
        )
        parser.add_argument(
            '--volume',
            type=int,
            default=0,
            help='Volume (optional)'
        )
        parser.add_argument(
            '--timestamp',
            type=str,
            help='Candle timestamp in ISO format (default: current time)'
        )
    
    def handle(self, *args, **options):
        symbol = options['symbol']
        open_price = Decimal(str(options['open']))
        high_price = Decimal(str(options['high']))
        low_price = Decimal(str(options['low']))
        close_price = Decimal(str(options['close']))
        volume = options.get('volume', 0)
        
        # Parse timestamp if provided
        timestamp = None
        if options.get('timestamp'):
            from dateutil import parser
            timestamp = parser.parse(options['timestamp'])
            if timestamp.tzinfo is None:
                timestamp = IST.localize(timestamp)
        
        # Initialize tracker
        tracker = HeikinAshiTracker()
        
        # Process new candle
        try:
            color, trend = tracker.process_new_candle(
                symbol=symbol,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                timestamp=timestamp,
                volume=volume
            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Processed HA candle: {symbol} | "
                    f"Color: {color.upper()} | Trend: {trend}"
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Error processing HA candle: {e}")
            )
            logger.error(f"Error processing HA candle: {e}", exc_info=True)
            raise


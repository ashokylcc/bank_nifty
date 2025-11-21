"""
Celery tasks for Heikin-Ashi candle processing
Run every 15 minutes to process new candles

To use with Celery, add to your celery.py:
    from trading.tasks_ha import process_ha_candle_task

To use with cron, create a script that calls:
    python manage.py process_ha_candles --symbol BANKNIFTY_FUTURES --open <O> --high <H> --low <L> --close <C>
"""
import logging
from decimal import Decimal
from datetime import datetime

# Try to import Celery, but don't fail if not available
try:
    from celery import shared_task
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    # Create a dummy decorator if Celery is not available
    def shared_task(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

from trading.services.ha_tracker import HeikinAshiTracker
from trading.utils.time_helpers import get_ist_now

logger = logging.getLogger(__name__)


if CELERY_AVAILABLE:
    @shared_task(name='trading.process_ha_candle')
    def process_ha_candle_task(
        symbol: str,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
        timestamp: str = None,
        volume: int = 0
    ):
        """
        Celery task to process a new Heikin-Ashi candle
        
        Args:
            symbol: Trading symbol
            open_price: Open price
            high_price: High price
            low_price: Low price
            close_price: Close price
            timestamp: ISO format timestamp (optional)
            volume: Volume (optional)
            
        Returns:
            dict: Result with color and trend
        """
        try:
            tracker = HeikinAshiTracker()
            
            # Parse timestamp if provided
            dt_timestamp = None
            if timestamp:
                from dateutil import parser
                from trading.utils.time_helpers import IST
                dt_timestamp = parser.parse(timestamp)
                if dt_timestamp.tzinfo is None:
                    dt_timestamp = IST.localize(dt_timestamp)
            
            # Process candle
            color, trend = tracker.process_new_candle(
                symbol=symbol,
                open_price=Decimal(str(open_price)),
                high_price=Decimal(str(high_price)),
                low_price=Decimal(str(low_price)),
                close_price=Decimal(str(close_price)),
                timestamp=dt_timestamp,
                volume=volume
            )
            
            logger.info(f"✅ Celery task processed HA candle: {symbol} | Color: {color} | Trend: {trend}")
            
            return {
                'status': 'success',
                'symbol': symbol,
                'color': color,
                'trend': trend
            }
            
        except Exception as e:
            logger.error(f"❌ Error in Celery task processing HA candle: {e}", exc_info=True)
            return {
                'status': 'error',
                'error': str(e)
            }
else:
    # If Celery is not available, provide a simple function
    def process_ha_candle_task(
        symbol: str,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
        timestamp: str = None,
        volume: int = 0
    ):
        """
        Process HA candle (non-Celery version)
        """
        tracker = HeikinAshiTracker()
        
        dt_timestamp = None
        if timestamp:
            from dateutil import parser
            from trading.utils.time_helpers import IST
            dt_timestamp = parser.parse(timestamp)
            if dt_timestamp.tzinfo is None:
                dt_timestamp = IST.localize(dt_timestamp)
        
        color, trend = tracker.process_new_candle(
            symbol=symbol,
            open_price=Decimal(str(open_price)),
            high_price=Decimal(str(high_price)),
            low_price=Decimal(str(low_price)),
            close_price=Decimal(str(close_price)),
            timestamp=dt_timestamp,
            volume=volume
        )
        
        return {
            'status': 'success',
            'symbol': symbol,
            'color': color,
            'trend': trend
        }


# Example cron script (save as scripts/cron_process_ha.sh):
"""
#!/bin/bash
# Run every 15 minutes: */15 * * * * /path/to/scripts/cron_process_ha.sh

# Get latest OHLC data (you'll need to implement this based on your data source)
# For example, from API or database
SYMBOL="BANKNIFTY_FUTURES"
OPEN=$(get_open_price)  # Your function to get open
HIGH=$(get_high_price)  # Your function to get high
LOW=$(get_low_price)    # Your function to get low
CLOSE=$(get_close_price) # Your function to get close

# Run Django management command
cd /var/www/html/bank_nifty
python manage.py process_ha_candles \
    --symbol "$SYMBOL" \
    --open "$OPEN" \
    --high "$HIGH" \
    --low "$LOW" \
    --close "$CLOSE"
"""


"""
Time utility functions for trading strategy
"""
from datetime import datetime, time, timedelta
import pytz


IST = pytz.timezone('Asia/Kolkata')


def get_ist_now():
    """Get current time in IST timezone"""
    return datetime.now(IST)


def is_time_between(check_time, start_time, end_time):
    """
    Check if current time is between start_time and end_time
    
    Args:
        check_time: datetime.time or datetime object
        start_time: datetime.time or string (HH:MM:SS)
        end_time: datetime.time or string (HH:MM:SS)
    
    Returns:
        bool: True if check_time is between start_time and end_time
    """
    if isinstance(check_time, datetime):
        check_time = check_time.time()
    
    # Convert string times to time objects if needed
    if isinstance(start_time, str):
        from datetime import datetime as dt
        start_time = dt.strptime(start_time, '%H:%M:%S').time()
    if isinstance(end_time, str):
        from datetime import datetime as dt
        end_time = dt.strptime(end_time, '%H:%M:%S').time()
    
    if start_time <= end_time:
        return start_time <= check_time <= end_time
    else:  # Handles overnight ranges
        return check_time >= start_time or check_time <= end_time


def is_trading_hours(strategy):
    """
    Check if current time is within trading hours
    
    Args:
        strategy: Strategy model instance
    
    Returns:
        bool: True if within trading hours
    """
    now = get_ist_now()
    return is_time_between(now, strategy.trade_start_time, strategy.trade_end_time)


def is_range_detection_time(strategy):
    """
    Check if current time is within range detection window (9:15-9:30)
    
    Args:
        strategy: Strategy model instance
    
    Returns:
        bool: True if within range detection window
    """
    now = get_ist_now()
    return is_time_between(now, strategy.range_start_time, strategy.range_end_time)


def is_square_off_time(strategy):
    """
    Check if current time is at or past square-off time
    
    Args:
        strategy: Strategy model instance
    
    Returns:
        bool: True if at or past square-off time
    """
    now = get_ist_now()
    square_off = strategy.square_off_time
    
    # Convert string time to time object if needed
    if isinstance(square_off, str):
        from datetime import datetime as dt
        square_off = dt.strptime(square_off, '%H:%M:%S').time()
    
    return now.time() >= square_off


def get_today_date():
    """Get today's date in IST"""
    return get_ist_now().date()


def format_time(dt):
    """Format datetime for logging"""
    if isinstance(dt, datetime):
        return dt.strftime('%Y-%m-%d %H:%M:%S IST')
    return str(dt)


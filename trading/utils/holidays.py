"""
Trading holidays configuration for BankNifty
"""

from datetime import date

# Add NSE trading holidays here
# Format: date(year, month, day)
TRADING_HOLIDAYS = [
    # Example holidays (update with actual NSE holidays)
    date(2025, 1, 26),  # Republic Day
    date(2025, 3, 29),  # Holi
    date(2025, 4, 14),  # Ambedkar Jayanti
    date(2025, 4, 17),  # Ram Navami
    date(2025, 5, 1),   # Labour Day
    date(2025, 6, 17),  # Id-ul-Fitr
    date(2025, 8, 15),  # Independence Day
    date(2025, 10, 2),  # Gandhi Jayanti
    date(2025, 11, 1),  # Diwali (example)
    date(2025, 12, 25), # Christmas
    # Add more holidays as needed
]


def is_trading_holiday(check_date):
    """
    Check if a date is a trading holiday
    
    Args:
        check_date: datetime.date
    
    Returns:
        bool: True if holiday
    """
    return check_date in TRADING_HOLIDAYS


def get_next_trading_day(reference_date):
    """
    Get next trading day (skip holidays and weekends)
    
    Args:
        reference_date: datetime.date
    
    Returns:
        datetime.date: Next trading day
    """
    from datetime import timedelta
    
    next_day = reference_date + timedelta(days=1)
    
    # Skip weekends and holidays
    while next_day.weekday() >= 5 or is_trading_holiday(next_day):
        next_day = next_day + timedelta(days=1)
    
    return next_day


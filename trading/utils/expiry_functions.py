"""
Functions for calculating option expiry dates (nearest Thursday)
"""
import logging
from datetime import datetime, timedelta
from trading.utils.time_helpers import get_ist_now

logger = logging.getLogger(__name__)


def get_nearest_thursday_expiry(reference_date=None):
    """
    Get the nearest Thursday expiry date for BankNifty options.
    BankNifty has weekly expiries on Thursdays.
    If today is Thursday and before 3:30 PM, use today. Otherwise, find next Thursday.
    
    Args:
        reference_date: datetime.date or None (uses today if None)
    
    Returns:
        datetime.date: Nearest Thursday expiry date
    """
    if reference_date is None:
        reference_date = get_ist_now().date()
        now = get_ist_now()
    else:
        now = get_ist_now()
    
    # Get expiry time (3:30 PM IST)
    expiry_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    # If today is Thursday
    if reference_date.weekday() == 3:  # Thursday = 3
        # If before 3:30 PM, use today; otherwise use next Thursday
        if now.time() < expiry_time.time():
            return reference_date
        else:
            # Past expiry time, use next Thursday
            return reference_date + timedelta(days=7)
    
    # Find next Thursday
    days_until_thursday = (3 - reference_date.weekday()) % 7
    if days_until_thursday == 0:
        days_until_thursday = 7  # If today is Thursday (shouldn't happen here), use next week
    
    next_thursday = reference_date + timedelta(days=days_until_thursday)
    return next_thursday


def is_holiday(date):
    """
    Check if a date is a trading holiday.
    
    This is a stub function. In production, integrate with:
    - NSE holiday calendar API
    - pandas_market_calendars
    - Custom holiday list
    
    Args:
        date: datetime.date
    
    Returns:
        bool: True if holiday, False otherwise
    """
    # Stub: Add your holiday list here
    # Example: holidays = [date(2025, 1, 26), date(2025, 3, 29), ...]
    holidays = []
    return date in holidays


def get_trading_thursday_expiry(reference_date=None):
    """
    Get the nearest Thursday that is not a holiday.
    If Thursday is a holiday, use previous business day.
    
    Args:
        reference_date: datetime.date or None
    
    Returns:
        datetime.date: Nearest trading Thursday expiry
    """
    thursday = get_nearest_thursday_expiry(reference_date)
    
    # If Thursday is a holiday, go back to previous business day
    while is_holiday(thursday):
        thursday = thursday - timedelta(days=1)
    
    return thursday


def get_available_option_expiry(reference_date=None):
    """
    Get the nearest available option expiry by querying contract master.
    Finds all available BankNifty option expiries and returns the nearest one.
    
    Args:
        reference_date: datetime.date or None (uses today if None)
    
    Returns:
        datetime.date: Nearest available option expiry date
    """
    if reference_date is None:
        reference_date = get_ist_now().date()
    
    # Try to get from Alice Blue contract master
    try:
        # Import here to avoid circular dependencies
        from alice_blue import AliceBlue
        import os
        
        # Get credentials
        username = os.getenv('ALICE_BLUE_USER_ID') or os.getenv('ALICE_BLUE_USERNAME')
        api_key = os.getenv('ALICE_BLUE_API_KEY')
        access_token = os.getenv('ALICE_BLUE_ACCESS_TOKEN')
        
        if not username:
            # Try to get from alice_client.py
            try:
                from strategy.broker.alice_client import USER_ID, API_KEY
                username = USER_ID
                api_key = API_KEY
            except:
                pass
        
        if username and (api_key or access_token):
            # Create Alice Blue client to access contract master
            if access_token:
                alice = AliceBlue(username=username, access_token=access_token, master_contracts_to_download=['NFO'])
            elif api_key:
                from strategy.broker.alice_client import get_encryption_key, get_session_id
                enc_key = get_encryption_key(username)
                session_id = get_session_id(username, api_key, enc_key)
                alice = AliceBlue(username=username, session_id=session_id, master_contracts_to_download=['NFO'])
            else:
                raise Exception("No credentials available")
            
            # Get all BankNifty option contracts using search_instruments
            all_instruments = alice.search_instruments('NFO', 'BANKNIFTY')
            banknifty_options = [
                inst for inst in all_instruments
                if inst.symbol.startswith('BANKNIFTY') and 
                (inst.symbol.endswith('CE') or inst.symbol.endswith('PE'))
            ]
            
            if banknifty_options:
                # Extract unique expiry dates from option symbols
                # Format: BANKNIFTY{DD}{MMM}{YY}{C|P}{STRIKE}
                available_expiries = set()
                month_map = {
                    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4,
                    'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8,
                    'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
                }
                
                for inst in banknifty_options:
                    try:
                        symbol = inst.symbol
                        # Find where option type (C or P) starts
                        if 'C' in symbol and symbol.index('C') > 9:  # After BANKNIFTY
                            date_end = symbol.index('C')
                        elif 'P' in symbol and symbol.index('P') > 9:
                            date_end = symbol.index('P')
                        else:
                            continue
                        
                        # Extract date part: BANKNIFTY{DDMMMYY}
                        date_part = symbol[9:date_end]  # Skip 'BANKNIFTY'
                        if len(date_part) >= 6:
                            day = int(date_part[:2])
                            month_str = date_part[2:5]
                            year_str = date_part[5:7]
                            
                            month = month_map.get(month_str.upper())
                            year = 2000 + int(year_str)
                            
                            if month:
                                expiry_date = datetime(year, month, day).date()
                                # Only include current or future expiries
                                if expiry_date >= reference_date:
                                    available_expiries.add(expiry_date)
                    except Exception as e:
                        # Skip if parsing fails
                        continue
                
                if available_expiries:
                    # Sort by expiry date and get nearest
                    sorted_expiries = sorted(available_expiries)
                    nearest_expiry = sorted_expiries[0]
                    logger.info(f"Found nearest available option expiry from contract master: {nearest_expiry}")
                    return nearest_expiry
            
    except Exception as e:
        # If contract master query fails, fall back to calculated expiry
        logger.warning(f"Could not query contract master for option expiries: {e}")
        logger.info("Falling back to calculated Thursday expiry")
    
    # Fallback: Use calculated Thursday expiry
    return get_trading_thursday_expiry(reference_date)


def build_option_symbol(expiry_date, strike, option_type, underlying="BANKNIFTY"):
    """
    Build BankNifty option symbol string.
    
    Format: BANKNIFTY{DD}{MMM}{YY}{C|P}{STRIKE}
    Example: BANKNIFTY28NOV25C58400
    
    Args:
        expiry_date: datetime.date
        strike: int (strike price, e.g., 58400)
        option_type: str ('C' for Call, 'P' for Put)
        underlying: str (default: "BANKNIFTY")
    
    Returns:
        str: Option symbol string
    """
    # Format: DDMMMYY
    day = expiry_date.strftime('%d')
    month = expiry_date.strftime('%b').upper()  # NOV, DEC, etc.
    year = expiry_date.strftime('%y')  # 25, 26, etc.
    
    date_str = f"{day}{month}{year}"
    
    # Build symbol
    symbol = f"{underlying}{date_str}{option_type}{strike}"
    
    return symbol


def build_futures_symbol(expiry_date, underlying="BANKNIFTY"):
    """
    Build BankNifty futures symbol string.
    
    Format: BANKNIFTY{DD}{MMM}{YY}F
    Example: BANKNIFTY25NOV25F
    
    Args:
        expiry_date: datetime.date
        underlying: str (default: "BANKNIFTY")
    
    Returns:
        str: Futures symbol string
    """
    # Format: DDMMMYY (day, month, year)
    day = expiry_date.strftime('%d')  # 25, 26, etc.
    month = expiry_date.strftime('%b').upper()  # NOV, DEC, etc.
    year = expiry_date.strftime('%y')  # 25, 26, etc.
    
    date_str = f"{day}{month}{year}"
    
    # Build symbol: BANKNIFTY{DD}{MMM}{YY}F
    symbol = f"{underlying}{date_str}F"
    
    return symbol


def get_banknifty_futures_symbol(reference_date=None):
    """
    Get the active BankNifty futures symbol by querying contract master.
    Finds the nearest available expiry contract for the current month.
    
    Args:
        reference_date: datetime.date or None (uses today if None)
    
    Returns:
        str: Futures symbol (e.g., 'BANKNIFTY25NOV25F')
    """
    if reference_date is None:
        reference_date = get_ist_now().date()
    
    # Try to get from Alice Blue contract master
    try:
        # Import here to avoid circular dependencies
        from alice_blue import AliceBlue
        import os
        
        # Get credentials
        username = os.getenv('ALICE_BLUE_USER_ID') or os.getenv('ALICE_BLUE_USERNAME')
        api_key = os.getenv('ALICE_BLUE_API_KEY')
        access_token = os.getenv('ALICE_BLUE_ACCESS_TOKEN')
        
        if not username:
            # Try to get from alice_client.py
            try:
                from strategy.broker.alice_client import USER_ID, API_KEY
                username = USER_ID
                api_key = API_KEY
            except:
                pass
        
        if username and (api_key or access_token):
            # Create Alice Blue client to access contract master
            if access_token:
                alice = AliceBlue(username=username, access_token=access_token, master_contracts_to_download=['NFO'])
            elif api_key:
                from strategy.broker.alice_client import get_encryption_key, get_session_id
                enc_key = get_encryption_key(username)
                session_id = get_session_id(username, api_key, enc_key)
                alice = AliceBlue(username=username, session_id=session_id, master_contracts_to_download=['NFO'])
            else:
                raise Exception("No credentials available")
            
            # Get all BankNifty futures contracts using search_instruments
            # Search for "BANKNIFTY" to get all BankNifty contracts
            all_instruments = alice.search_instruments('NFO', 'BANKNIFTY')
            banknifty_futures = [
                inst for inst in all_instruments
                if inst.symbol.startswith('BANKNIFTY') and 
                inst.symbol.endswith('F')
            ]
            
            if banknifty_futures:
                # Filter for current month and future expiries
                current_month = reference_date.month
                current_year = reference_date.year
                
                # Parse expiry dates from symbols and find nearest
                available_expiries = []
                for inst in banknifty_futures:
                    try:
                        # Extract date from symbol: BANKNIFTY{DD}{MMM}{YY}F
                        symbol = inst.symbol
                        if len(symbol) >= 12:  # Minimum length check
                            # Extract date part (after BANKNIFTY, before F)
                            date_part = symbol[9:-1]  # Skip 'BANKNIFTY' and 'F'
                            if len(date_part) >= 6:
                                # Parse DDMMMYY format
                                day = int(date_part[:2])
                                month_str = date_part[2:5]
                                year_str = date_part[5:7]
                                
                                # Convert month string to number
                                month_map = {
                                    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4,
                                    'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8,
                                    'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
                                }
                                month = month_map.get(month_str.upper())
                                year = 2000 + int(year_str)  # Convert YY to YYYY
                                
                                if month:
                                    expiry_date = datetime(year, month, day).date()
                                    # Only include current month or future expiries
                                    if expiry_date >= reference_date:
                                        available_expiries.append((expiry_date, symbol))
                    except Exception as e:
                        # Skip if parsing fails
                        continue
                
                if available_expiries:
                    # Sort by expiry date and get nearest
                    available_expiries.sort(key=lambda x: x[0])
                    nearest_expiry_date, nearest_symbol = available_expiries[0]
                    logger.info(f"Found nearest BankNifty futures from contract master: {nearest_symbol} (expiry: {nearest_expiry_date})")
                    return nearest_symbol
            
    except Exception as e:
        # If contract master query fails, fall back to calculated expiry
        logger.warning(f"Could not query contract master for BankNifty futures: {e}")
        logger.info("Falling back to calculated Thursday expiry")
    
    # Fallback: Use calculated Thursday expiry
    expiry = get_nearest_thursday_expiry(reference_date)
    return build_futures_symbol(expiry)


def round_to_nearest_strike(price, step=100):
    """
    Round price to nearest strike (default: 100)
    
    Args:
        price: float or Decimal
        step: int (strike step, default 100)
    
    Returns:
        int: Rounded strike price
    """
    return int(round(float(price) / step) * step)


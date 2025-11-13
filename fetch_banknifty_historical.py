"""
Fetch historical BankNifty futures data from Alice Blue API
"""
import os
import sys
import pandas as pd
from datetime import datetime, timedelta
from decimal import Decimal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from alice_blue import AliceBlue, HistoricalDataType
except ImportError:
    print("❌ alice-blue package not installed. Install with: pip install alice-blue")
    sys.exit(1)


def get_alice_blue_session():
    """Get Alice Blue session using existing credentials"""
    print("🔑 Logging in to Alice Blue...")
    
    # Try to get credentials from alice_client.py first
    username = None
    password = None
    twoFA = None
    api_secret = None
    access_token = None
    
    try:
        from strategy.broker.alice_client import USER_ID, API_KEY
        username = USER_ID
        api_secret = API_KEY
        print(f"✅ Found credentials in alice_client.py: USER_ID={username}")
    except (ImportError, AttributeError) as e:
        print(f"⚠️  Could not import from alice_client.py: {e}")
        # Fall back to environment variables
        username = os.getenv('ALICE_BLUE_USER_ID') or os.getenv('ALICE_BLUE_USERNAME')
        password = os.getenv('ALICE_BLUE_PASSWORD')
        twoFA = os.getenv('ALICE_BLUE_TWOFA')
        api_secret = os.getenv('ALICE_BLUE_API_KEY')
        access_token = os.getenv('ALICE_BLUE_ACCESS_TOKEN')
    
    if not username:
        print("❌ No username found. Set USER_ID in strategy/broker/alice_client.py or ALICE_BLUE_USER_ID in .env")
        sys.exit(1)
    
    # Create Alice Blue client
    # Method 1: Use access token if available
    if access_token:
        try:
            alice = AliceBlue(
                username=username,
                access_token=access_token,
                master_contracts_to_download=['NFO']
            )
            print("✅ Using access token")
            return alice
        except Exception as e:
            print(f"⚠️  Failed with access token: {e}")
    
    # Method 2: Use session_id from alice_client.py (preferred)
    if api_secret:
        try:
            from strategy.broker.alice_client import get_encryption_key, get_session_id
            print("🔐 Getting session ID...")
            enc_key = get_encryption_key(username)
            session_id = get_session_id(username, api_secret, enc_key)
            alice = AliceBlue(
                username=username,
                session_id=session_id,
                master_contracts_to_download=['NFO']
            )
            print("✅ Using session_id")
            return alice
        except Exception as e:
            print(f"⚠️  Failed with session_id: {e}")
    
    # Method 3: Try login with password/2FA (if provided)
    if password and twoFA and api_secret:
        try:
            print("🔐 Logging in with username/password/2FA...")
            result = AliceBlue.login_and_get_access_token(
                username=username,
                password=password,
                twoFA=twoFA,
                api_secret=api_secret
            )
            access_token = result.get('access_token')
            if not access_token:
                print("❌ Failed to get access token")
                sys.exit(1)
            print(f"✅ Access Token Received: {access_token[:20]}...")
            alice = AliceBlue(
                username=username,
                access_token=access_token,
                master_contracts_to_download=['NFO']
            )
            return alice
        except Exception as e:
            print(f"❌ Login failed: {e}")
    
    # If all methods failed
    print("❌ Failed to create Alice Blue client")
    print("💡 Options:")
    print("   1. Set USER_ID and API_KEY in strategy/broker/alice_client.py")
    print("   2. Set ALICE_BLUE_ACCESS_TOKEN in .env")
    print("   3. Set ALICE_BLUE_USER_ID, PASSWORD, TWOFA, API_KEY in .env")
    sys.exit(1)


def get_banknifty_futures_instrument(alice, reference_date=None):
    """Get BankNifty futures instrument for current month"""
    print("🔍 Finding BankNifty futures instrument...")
    
    try:
        # Try to get from contract master
        all_instruments = alice.search_instruments('NFO', 'BANKNIFTY')
        banknifty_futures = [
            inst for inst in all_instruments
            if inst.symbol.startswith('BANKNIFTY') and inst.symbol.endswith('F')
        ]
        
        if banknifty_futures:
            # Get nearest expiry
            if reference_date is None:
                from datetime import date
                reference_date = date.today()
            
            # Parse expiry dates and find nearest
            from datetime import datetime
            month_map = {
                'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4,
                'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8,
                'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
            }
            
            available_expiries = []
            for inst in banknifty_futures:
                try:
                    symbol = inst.symbol
                    if len(symbol) >= 12:
                        date_part = symbol[9:-1]  # Skip 'BANKNIFTY' and 'F'
                        if len(date_part) >= 6:
                            day = int(date_part[:2])
                            month_str = date_part[2:5]
                            year_str = date_part[5:7]
                            month = month_map.get(month_str.upper())
                            year = 2000 + int(year_str)
                            
                            if month:
                                expiry_date = datetime(year, month, day).date()
                                if expiry_date >= reference_date:
                                    available_expiries.append((expiry_date, inst))
                except Exception:
                    continue
            
            if available_expiries:
                available_expiries.sort(key=lambda x: x[0])
                nearest_instrument = available_expiries[0][1]
                print(f"✅ Found: {nearest_instrument.symbol}")
                return nearest_instrument
        
        # Fallback: try to build symbol and get by symbol
        print("⚠️  Trying alternative method...")
        try:
            # Try to get current month futures using calculated expiry
            from datetime import date
            from trading.utils.expiry_functions import get_nearest_thursday_expiry, build_futures_symbol
            
            if reference_date is None:
                reference_date = date.today()
            
            expiry_date = get_nearest_thursday_expiry(reference_date)
            expected_symbol = build_futures_symbol(expiry_date)
            
            # Try to get instrument by symbol
            try:
                instrument = alice.get_instrument_by_symbol('NFO', expected_symbol)
                if instrument:
                    print(f"✅ Found: {instrument.symbol}")
                    return instrument
            except Exception as e:
                print(f"⚠️  get_instrument_by_symbol failed: {e}")
            
            # Last resort: search and pick first futures
            all_instruments = alice.search_instruments('NFO', 'BANKNIFTY')
            futures = [inst for inst in all_instruments if inst.symbol.endswith('F')]
            if futures:
                print(f"✅ Found: {futures[0].symbol}")
                return futures[0]
        except Exception as e:
            print(f"⚠️  Alternative method failed: {e}")
        
        print("❌ Could not find BankNifty futures instrument")
        return None
        
    except Exception as e:
        print(f"❌ Error finding instrument: {e}")
        return None


def fetch_historical_data(alice, instrument, start_date, end_date, interval="minute"):
    """
    Fetch historical data from Alice Blue
    
    Args:
        alice: AliceBlue client
        instrument: Instrument object
        start_date: datetime or date
        end_date: datetime or date
        interval: "minute", "5minute", "day", etc.
    
    Returns:
        pandas.DataFrame with columns: timestamp, open, high, low, close, volume
    """
    print(f"📅 Fetching {interval} data from {start_date} to {end_date}")
    
    try:
        # Convert dates to datetime if needed
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
        elif hasattr(start_date, 'date'):
            start_date = datetime.combine(start_date, datetime.min.time())
        
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, "%Y-%m-%d")
            # Set to end of day
            end_date = end_date.replace(hour=23, minute=59, second=59)
        elif hasattr(end_date, 'date'):
            end_date = datetime.combine(end_date, datetime.max.time())
        
        print(f"   Instrument: {instrument.symbol} ({instrument.exchange})")
        print(f"   From: {start_date}")
        print(f"   To: {end_date}")
        
        # Fetch historical data using historical_data method
        # Method signature: historical_data(instrument, ffrom, to, type)
        # Note: type must be HistoricalDataType enum, not a string
        # Available: HistoricalDataType.Minute, HistoricalDataType.Day
        interval_map = {
            'minute': HistoricalDataType.Minute,
            '5minute': HistoricalDataType.Minute,  # 5-minute not available, use 1-minute
            'day': HistoricalDataType.Day
        }
        alice_interval = interval_map.get(interval, HistoricalDataType.Minute)
        
        if interval == '5minute':
            print("⚠️  5-minute interval not available, using 1-minute data")
        
        data = alice.historical_data(
            instrument=instrument,
            ffrom=start_date,  # Note: parameter name is 'ffrom' not 'from_datetime'
            to=end_date,       # Note: parameter name is 'to' not 'to_datetime'
            type=alice_interval  # Note: must be HistoricalDataType enum
        )
        
        if not data:
            print("⚠️  No data returned from API")
            return pd.DataFrame()
        
        # Check if data is a dictionary with 'result' key (API response format)
        if isinstance(data, dict):
            if 'stat' in data and data.get('stat') != 'Ok':
                print(f"❌ API returned error: {data.get('message', 'Unknown error')}")
                return pd.DataFrame()
            
            # Extract actual data from 'result' field
            if 'result' in data:
                actual_data = data['result']
                print(f"📊 API response: stat={data.get('stat')}, message={data.get('message', 'N/A')}")
            else:
                # If no 'result' key, try to use the dict directly
                actual_data = data
        else:
            actual_data = data
        
        # Convert to DataFrame
        df = pd.DataFrame(actual_data)
        
        if df.empty:
            print("⚠️  Empty DataFrame returned")
            return df
        
        print(f"✅ Fetched {len(df)} records")
        
        # Standardize column names
        # Alice Blue typically returns: datetime, open, high, low, close, volume
        column_mapping = {
            'datetime': 'timestamp',
            'time': 'timestamp',
            'date': 'timestamp',
        }
        
        for old_name, new_name in column_mapping.items():
            if old_name in df.columns:
                df.rename(columns={old_name: new_name}, inplace=True)
        
        # Ensure timestamp column exists
        if 'timestamp' not in df.columns:
            if 'time' in df.columns:
                df['timestamp'] = df['time']
            elif 'date' in df.columns:
                df['timestamp'] = df['date']
            else:
                print("⚠️  Could not find timestamp column in data")
                print(f"   Available columns: {df.columns.tolist()}")
                return pd.DataFrame()
        
        # Convert timestamp to datetime if needed
        if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Ensure required columns exist
        required_columns = ['open', 'high', 'low', 'close']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            print(f"⚠️  Missing columns: {missing_columns}")
            print(f"   Available columns: {df.columns.tolist()}")
            return pd.DataFrame()
        
        # Add volume if missing (set to 0)
        if 'volume' not in df.columns:
            df['volume'] = 0
        
        # Select and reorder columns
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
        
        # Sort by timestamp
        df.sort_values('timestamp', inplace=True)
        df.reset_index(drop=True, inplace=True)
        
        print(f"✅ Processed {len(df)} records")
        print(f"   Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        
        return df
        
    except Exception as e:
        print(f"❌ Error fetching historical data: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Fetch historical BankNifty futures data from Alice Blue')
    parser.add_argument('--from', dest='start_date', type=str, required=True,
                       help='Start date (YYYY-MM-DD)')
    parser.add_argument('--to', dest='end_date', type=str, required=True,
                       help='End date (YYYY-MM-DD)')
    parser.add_argument('--interval', type=str, default='minute',
                       choices=['minute', '5minute', 'day'],
                       help='Data interval (default: minute)')
    parser.add_argument('--output', type=str, default=None,
                       help='Output CSV file path (default: data/BANKNIFTY_YYYY_MM.csv)')
    parser.add_argument('--symbol', type=str, default='BANKNIFTY',
                       help='Symbol to fetch (default: BANKNIFTY)')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("📊 Fetch Historical BankNifty Data from Alice Blue")
    print("=" * 70)
    print(f"📅 Date Range: {args.start_date} to {args.end_date}")
    print(f"⏱️  Interval: {args.interval}")
    print("")
    
    # Get Alice Blue session
    alice = get_alice_blue_session()
    
    # Get BankNifty futures instrument
    start_date_obj = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    instrument = get_banknifty_futures_instrument(alice, start_date_obj)
    
    if not instrument:
        print("❌ Could not find BankNifty futures instrument")
        sys.exit(1)
    
    # Fetch historical data
    df = fetch_historical_data(alice, instrument, args.start_date, args.end_date, args.interval)
    
    if df.empty:
        print("❌ No data fetched")
        sys.exit(1)
    
    # Determine output file
    if args.output:
        output_file = args.output
    else:
        # Default: data/BANKNIFTY_YYYY_MM.csv
        from pathlib import Path
        BASE_DIR = Path(__file__).resolve().parent
        data_dir = BASE_DIR / 'data'
        data_dir.mkdir(exist_ok=True)
        
        # Extract year and month from start date
        year_month = args.start_date[:7]  # YYYY-MM
        output_file = data_dir / f"BANKNIFTY_{year_month.replace('-', '_')}.csv"
    
    # Save to CSV
    print(f"\n💾 Saving to: {output_file}")
    df.to_csv(output_file, index=False)
    
    print(f"✅ Data saved successfully!")
    print(f"   Records: {len(df)}")
    print(f"   Columns: {', '.join(df.columns.tolist())}")
    print(f"\n📊 Sample data:")
    print(df.head(10).to_string(index=False))
    print(f"\n📊 Last 5 records:")
    print(df.tail(5).to_string(index=False))
    
    print(f"\n✅ Done! Use this file for backtesting:")
    print(f"   python manage.py backtest_momentum_strategy --from {args.start_date} --to {args.end_date} --capital 100000")


if __name__ == "__main__":
    main()


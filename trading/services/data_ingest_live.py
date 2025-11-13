"""
Live data ingestion service - Alice Blue WebSocket integration
"""
import os
import logging
from typing import Optional
from decimal import Decimal
from datetime import datetime
from trading.services.data_ingest import DataIngestService, TickData, CandleData
from trading.services.websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)


class LiveDataIngestService(DataIngestService):
    """
    Live data ingestion with Alice Blue WebSocket
    
    Integrates with Alice Blue WebSocket feed for real-time market data
    Features:
    - Exponential backoff reconnection
    - Last tick persistence (resume after disconnect)
    - Network latency optimization
    """
    
    def __init__(self):
        super().__init__()
        self.ws_client = None
        self.subscribed_symbols = set()
        self.ws_manager = WebSocketManager(
            max_retries=10,
            initial_backoff=1.0,  # Start with 1 second
            max_backoff=60.0  # Max 60 seconds
        )
        self.last_tick_persistence = {}  # Store last tick per symbol
        self.alice_client = None  # Alice Blue client
        self.username = None
        self.session_id = None
        self.exchange = "NFO"  # NFO for BankNifty options/futures
    
    def connect(self):
        """Connect to Alice Blue WebSocket with exponential backoff"""
        def _connect():
            try:
                # First try to get credentials from alice_client.py (like run_strategy.py does)
                username = None
                api_key = None
                access_token = None
                
                try:
                    from strategy.broker.alice_client import USER_ID, API_KEY
                    username = USER_ID
                    api_key = API_KEY
                    logger.info(f"✅ Found credentials in alice_client.py: USER_ID={username}")
                except (ImportError, AttributeError) as e:
                    logger.debug(f"Could not import from alice_client.py: {e}")
                    # Fall back to environment variables
                    username = os.getenv('ALICE_BLUE_USER_ID') or os.getenv('ALICE_BLUE_USERNAME')
                    api_key = os.getenv('ALICE_BLUE_API_KEY')
                    access_token = os.getenv('ALICE_BLUE_ACCESS_TOKEN')
                
                if not username:
                    logger.warning("⚠️  ALICE_BLUE_USER_ID not found in alice_client.py or .env - using stub mode")
                    logger.warning("⚠️  Set USER_ID and API_KEY in strategy/broker/alice_client.py or .env for real WebSocket")
                    self._connected = True
                    return True
                
                # Try to get session_id if we have credentials
                session_id = None
                if username and api_key:
                    try:
                        from strategy.broker.alice_client import get_encryption_key, get_session_id
                        logger.info(f"🔐 Getting encryption key for USER_ID: {username}")
                        enc_key = get_encryption_key(username)
                        logger.info(f"✅ Encryption key received")
                        logger.info(f"🔐 Getting session ID...")
                        session_id = get_session_id(username, api_key, enc_key)
                        self.username = username
                        self.session_id = session_id
                        logger.info(f"✅ Alice Blue session created: {session_id[:20]}...")
                    except Exception as e:
                        logger.warning(f"⚠️  Failed to create session: {e}")
                        logger.warning("⚠️  Falling back to stub mode")
                        self._connected = True
                        return True
                
                # Initialize Alice Blue WebSocket
                if session_id or access_token:
                    try:
                        from alice_blue import AliceBlue, LiveFeedType
                        
                        if access_token:
                            # Use access token if available
                            self.alice_client = AliceBlue(
                                username=username,
                                access_token=access_token,
                                master_contracts_to_download=[self.exchange]
                            )
                        elif session_id:
                            # Use session_id
                            self.alice_client = AliceBlue(
                                username=username,
                                session_id=session_id,
                                master_contracts_to_download=[self.exchange]
                            )
                        
                        # Start WebSocket with callbacks
                        self.alice_client.start_websocket(
                            subscribe_callback=self._tick_callback,
                            socket_open_callback=self._open_callback,
                            socket_error_callback=self._error_callback,
                            socket_close_callback=self._close_callback
                        )
                        
                        logger.info("✅ Alice Blue WebSocket started")
                        self._connected = True
                        return True
                        
                    except Exception as e:
                        logger.error(f"❌ Failed to start WebSocket: {e}")
                        logger.warning("⚠️  Falling back to stub mode")
                        self._connected = True
                        return True
                else:
                    logger.warning("⚠️  No session_id or access_token - using stub mode")
                    self._connected = True
                    return True
                
            except Exception as e:
                logger.error(f"Failed to connect to WebSocket: {e}")
                logger.warning("⚠️  Falling back to stub mode")
                self._connected = True
                return True
        
        # Use manager for connection with backoff
        return self.ws_manager.connect_with_backoff(_connect)
    
    def _open_callback(self):
        """WebSocket open callback"""
        logger.info("✅ WebSocket connected to Alice Blue")
        self._connected = True
        self.ws_manager.is_connected = True
        self.ws_manager.reset_retry_count()
    
    def _tick_callback(self, tick):
        """WebSocket tick callback - receives real market data"""
        try:
            instrument = tick.get('instrument')
            if not instrument:
                return
            
            symbol = instrument.symbol
            ltp = tick.get('ltp')
            volume = tick.get('volume', 0)
            timestamp = datetime.now()  # Use current time for tick
            
            if ltp is None:
                return
            
            # Convert to Decimal
            ltp_decimal = Decimal(str(ltp))
            
            # Create tick data dict
            tick_data = {
                'ltp': ltp_decimal,
                'volume': volume,
                'timestamp': timestamp.isoformat(),
                'tick_id': f"{symbol}_{timestamp.timestamp()}"
            }
            
            # Process tick through on_tick_received
            self.on_tick_received(symbol, tick_data)
            
            # Log occasionally (every 50th tick to avoid spam)
            if len(self.ticks) % 50 == 0:
                logger.debug(f"📩 Live tick: {symbol} = ₹{ltp_decimal:,.2f}")
                
        except Exception as e:
            logger.error(f"Error in tick callback: {e}")
    
    def _error_callback(self, err):
        """WebSocket error callback"""
        logger.error(f"❌ WebSocket error: {err}")
        self._connected = False
        self.ws_manager.is_connected = False
        # Will reconnect via websocket_manager
    
    def _close_callback(self):
        """WebSocket close callback"""
        logger.warning("🔌 WebSocket closed")
        self._connected = False
        self.ws_manager.is_connected = False
    
    def set_test_ltp(self, symbol: str, ltp: Decimal):
        """
        Set test LTP for development/testing (when WebSocket is stubbed)
        
        Args:
            symbol: Instrument symbol
            ltp: LTP value to set
        """
        self.ltp_cache[symbol] = ltp
        logger.info(f"Test LTP set for {symbol}: ₹{ltp:,.2f}")
    
    def subscribe(self, symbol: str):
        """
        Subscribe to symbol for real-time ticks
        
        Args:
            symbol: Instrument symbol (e.g., 'BANKNIFTY25NOV25F' or 'BANKNIFTY')
        """
        if not self._connected:
            logger.warning("Not connected to WebSocket")
            return
        
        if symbol in self.subscribed_symbols:
            logger.debug(f"Already subscribed to {symbol}")
            return
        
        try:
            if self.alice_client:
                # Real Alice Blue WebSocket
                from alice_blue import LiveFeedType
                
                instrument = None
                
                # Try 1: Direct lookup by symbol
                try:
                    instrument = self.alice_client.get_instrument_by_symbol(self.exchange, symbol)
                    if instrument:
                        logger.debug(f"✅ Found instrument via get_instrument_by_symbol: {symbol}")
                except Exception as e:
                    logger.debug(f"⚠️  get_instrument_by_symbol failed for {symbol}: {e}")
                
                # Try 2: Search instruments if direct lookup failed
                if not instrument:
                    try:
                        logger.debug(f"🔍 Searching for instrument: {symbol}")
                        instruments = self.alice_client.search_instruments('NFO', symbol)
                        if instruments and len(instruments) > 0:
                            instrument = instruments[0]
                            logger.info(f"✅ Found instrument via search_instruments: {symbol}")
                        else:
                            logger.warning(f"⚠️  No instruments found in search for {symbol}")
                    except Exception as e:
                        logger.warning(f"⚠️  search_instruments failed for {symbol}: {e}")
                
                # Try 3: Search with partial match (if full symbol not found)
                if not instrument:
                    try:
                        # Try searching without the 'F' suffix (e.g., BANKNIFTY13NOV25)
                        if symbol.endswith('F'):
                            base_symbol = symbol[:-1]  # Remove 'F'
                            logger.debug(f"🔍 Trying partial search: {base_symbol}")
                            instruments = self.alice_client.search_instruments('NFO', base_symbol)
                            if instruments and len(instruments) > 0:
                                # Filter for futures contracts
                                for inst in instruments:
                                    if 'FUT' in str(inst) or 'F' in str(inst):
                                        instrument = inst
                                        logger.info(f"✅ Found instrument via partial search: {symbol}")
                                        break
                    except Exception as e:
                        logger.debug(f"⚠️  Partial search failed: {e}")
                
                # Subscribe if instrument found
                if instrument:
                    try:
                        self.alice_client.subscribe(instrument, LiveFeedType.TICK_DATA)
                        self.subscribed_symbols.add(symbol)
                        logger.info(f"✅ Subscribed to {symbol} (real WebSocket)")
                    except Exception as e:
                        logger.error(f"❌ Failed to subscribe to {symbol}: {e}")
                else:
                    logger.warning(f"⚠️  Instrument {symbol} not found - subscription skipped")
                    # Still mark as subscribed in stub mode to avoid repeated attempts
                    self.subscribed_symbols.add(symbol)
                    logger.info(f"⚠️  Marked {symbol} as subscribed (stub mode - no real ticks)")
            else:
                # Stub mode - just mark as subscribed
                self.subscribed_symbols.add(symbol)
                logger.info(f"Subscribed to {symbol} (stub mode - no real ticks)")
            
        except Exception as e:
            logger.error(f"Failed to subscribe to {symbol}: {e}")
    
    def on_tick_received(self, symbol: str, tick_data: dict):
        """
        Handle incoming tick from WebSocket with deduplication
        
        Args:
            symbol: Instrument symbol
            tick_data: Dict with 'ltp', 'volume', 'timestamp', 'order_id' (optional)
        """
        try:
            timestamp = datetime.fromisoformat(tick_data.get('timestamp', datetime.now().isoformat()))
            ltp = Decimal(str(tick_data.get('ltp', 0)))
            volume = int(tick_data.get('volume', 0))
            
            # Deduplication: Check if this tick was already processed
            tick_id = tick_data.get('order_id') or tick_data.get('tick_id')
            if tick_id and tick_id in self.last_tick_persistence.get(symbol, {}):
                logger.debug(f"Skipping duplicate tick {tick_id} for {symbol}")
                return
            
            tick = TickData(timestamp, ltp, volume)
            self.ticks.append(tick)
            
            # Update LTP cache
            self.ltp_cache[symbol] = ltp
            
            # Persist last tick (for resume after disconnect)
            if tick_id:
                if symbol not in self.last_tick_persistence:
                    self.last_tick_persistence[symbol] = {}
                self.last_tick_persistence[symbol][tick_id] = {
                    'timestamp': timestamp,
                    'ltp': ltp,
                    'volume': volume
                }
                # Keep only last 100 ticks per symbol (memory management)
                if len(self.last_tick_persistence[symbol]) > 100:
                    oldest = min(self.last_tick_persistence[symbol].keys())
                    del self.last_tick_persistence[symbol][oldest]
            
            # Update manager's last tick
            self.ws_manager.update_last_tick(tick_data)
            
            # Aggregate to 15-min candle
            self._update_candle(tick)
            
        except Exception as e:
            logger.error(f"Error processing tick: {e}")
    
    def get_latest_ltp(self, symbol: str) -> Optional[Decimal]:
        """Get latest LTP from WebSocket or cache"""
        # Try cache first
        if symbol in self.ltp_cache:
            return self.ltp_cache[symbol]
        
        # Try to get from WebSocket
        # TODO: Request from WebSocket if not in cache
        return None
    
    def disconnect(self):
        """Disconnect from WebSocket"""
        try:
            if self.alice_client:
                # Real Alice Blue WebSocket - stop it
                try:
                    # Alice Blue WebSocket runs in a thread, it will close automatically
                    # when the process exits or we can call stop_websocket if available
                    if hasattr(self.alice_client, 'stop_websocket'):
                        self.alice_client.stop_websocket()
                except Exception as e:
                    logger.debug(f"Error stopping WebSocket: {e}")
            
            self.subscribed_symbols.clear()
            self._connected = False
            self.ws_manager.is_connected = False
            logger.info("Disconnected from WebSocket")
            
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
    
    def reconnect(self):
        """Reconnect with exponential backoff"""
        def _reconnect():
            return self.connect()
        
        return self.ws_manager.reconnect(_reconnect)
    
    def get_last_tick_for_symbol(self, symbol: str) -> Optional[dict]:
        """
        Get last processed tick for symbol (for resume)
        
        Args:
            symbol: Instrument symbol
        
        Returns:
            Last tick data or None
        """
        if symbol in self.last_tick_persistence:
            ticks = self.last_tick_persistence[symbol]
            if ticks:
                # Return most recent tick
                latest = max(ticks.values(), key=lambda x: x['timestamp'])
                return latest
        return None


# Integration example:
"""
To integrate with Alice Blue WebSocket:

1. Import WebSocket client:
   from strategy.broker.websocket_ltp import WebSocketLTP

2. In connect():
   self.ws_client = WebSocketLTP()
   self.ws_client.connect()
   self.ws_client.set_callback(self.on_tick_received)

3. In subscribe():
   self.ws_client.subscribe(symbol)

4. Implement on_tick_received callback:
   def on_tick_received(self, symbol, ltp, volume):
       self.on_tick_received(symbol, {
           'ltp': ltp,
           'volume': volume,
           'timestamp': datetime.now().isoformat()
       })
"""


"""
Data ingestion service - WebSocket aggregator stub
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime
from decimal import Decimal

logger = logging.getLogger(__name__)


class TickData:
    """Represents a single tick"""
    def __init__(self, timestamp: datetime, ltp: Decimal, volume: int = 0):
        self.timestamp = timestamp
        self.ltp = ltp
        self.volume = volume


class CandleData:
    """Represents a 15-minute OHLCV candle"""
    def __init__(self, timestamp: datetime, open: Decimal, high: Decimal, 
                 low: Decimal, close: Decimal, volume: int):
        self.timestamp = timestamp
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
    
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp,
            'open': float(self.open),
            'high': float(self.high),
            'low': float(self.low),
            'close': float(self.close),
            'volume': self.volume
        }


class DataIngestService:
    """
    Data ingestion service - WebSocket aggregator stub
    
    In production, this would connect to:
    - Alice Blue WebSocket
    - NSE WebSocket
    - Other data providers
    
    For now, provides interface for:
    - Receiving ticks
    - Aggregating to 15-min candles
    - Providing historical data
    """
    
    def __init__(self):
        self.ticks: List[TickData] = []
        self.candles: List[CandleData] = []
        self.current_candle: Optional[CandleData] = None
        self.ltp_cache = {}  # LTP cache for symbols
        self._connected = False
    
    def connect(self):
        """Connect to data feed (stub)"""
        logger.info("DataIngestService: Connecting to data feed (stub)")
        self._connected = True
    
    def disconnect(self):
        """Disconnect from data feed"""
        logger.info("DataIngestService: Disconnecting from data feed")
        self._connected = False
    
    def is_connected(self) -> bool:
        """Check if connected"""
        return self._connected
    
    def on_tick(self, symbol: str, tick: Dict):
        """
        Handle incoming tick data
        
        Args:
            symbol: Instrument symbol
            tick: Dict with 'timestamp', 'ltp', 'volume'
        """
        if not self._connected:
            return
        
        timestamp = tick.get('timestamp', datetime.now())
        ltp = Decimal(str(tick.get('ltp', 0)))
        volume = int(tick.get('volume', 0))
        
        # Update LTP cache
        self.ltp_cache[symbol] = ltp
        
        tick_data = TickData(timestamp, ltp, volume)
        self.ticks.append(tick_data)
        
        # Aggregate to 15-min candle
        self._update_candle(tick_data)
    
    def _update_candle(self, tick: TickData):
        """Update current 15-min candle or create new one"""
        if self.current_candle is None:
            # Create new candle
            self.current_candle = CandleData(
                timestamp=tick.timestamp,
                open=tick.ltp,
                high=tick.ltp,
                low=tick.ltp,
                close=tick.ltp,
                volume=tick.volume
            )
        else:
            # Update existing candle
            self.current_candle.high = max(self.current_candle.high, tick.ltp)
            self.current_candle.low = min(self.current_candle.low, tick.ltp)
            self.current_candle.close = tick.ltp
            self.current_candle.volume += tick.volume
    
    def get_latest_ltp(self, symbol: str) -> Optional[Decimal]:
        """
        Get latest LTP for symbol
        
        Args:
            symbol: Instrument symbol
        
        Returns:
            Decimal: Latest LTP or None
        """
        if not self.ticks:
            return None
        return self.ticks[-1].ltp
    
    def get_candles(self, symbol: str, limit: int = 100) -> List[CandleData]:
        """
        Get recent candles
        
        Args:
            symbol: Instrument symbol
            limit: Maximum number of candles
        
        Returns:
            List[CandleData]: List of candles
        """
        return self.candles[-limit:]
    
    def get_first_candle_today(self) -> Optional[CandleData]:
        """Get first 15-min candle of the day (9:15-9:30)"""
        # In production, filter by time range
        if self.candles:
            return self.candles[0] if len(self.candles) > 0 else None
        return None
    
    def load_from_csv(self, csv_path: str):
        """
        Load historical data from CSV for backtesting
        
        CSV format: timestamp,open,high,low,close,volume
        """
        import csv
        from datetime import datetime
        
        logger.info(f"Loading data from CSV: {csv_path}")
        
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                timestamp = datetime.fromisoformat(row['timestamp'])
                candle = CandleData(
                    timestamp=timestamp,
                    open=Decimal(row['open']),
                    high=Decimal(row['high']),
                    low=Decimal(row['low']),
                    close=Decimal(row['close']),
                    volume=int(row['volume'])
                )
                self.candles.append(candle)
        
        logger.info(f"Loaded {len(self.candles)} candles from CSV")


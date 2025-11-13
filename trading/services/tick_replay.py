"""
Tick replay service for deterministic testing
"""
import logging
from typing import List, Dict
from decimal import Decimal
from datetime import datetime
from trading.services.data_ingest import DataIngestService, TickData, CandleData

logger = logging.getLogger(__name__)


class TickReplay:
    """
    Replay tick-level data deterministically for testing
    """
    
    def __init__(self, data_service: DataIngestService):
        self.data_service = data_service
        self.ticks: List[Dict] = []
        self.current_index = 0
    
    def load_ticks_from_csv(self, csv_path: str):
        """
        Load tick data from CSV
        
        CSV format: timestamp,ltp,volume,order_id (optional)
        """
        import csv
        
        logger.info(f"Loading ticks from CSV: {csv_path}")
        
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                tick = {
                    'timestamp': datetime.fromisoformat(row['timestamp']),
                    'ltp': Decimal(row['ltp']),
                    'volume': int(row.get('volume', 0)),
                    'order_id': row.get('order_id', None),
                    'symbol': row.get('symbol', 'BANKNIFTY')
                }
                self.ticks.append(tick)
        
        logger.info(f"Loaded {len(self.ticks)} ticks")
    
    def replay_next_tick(self) -> bool:
        """
        Replay next tick
        
        Returns:
            bool: True if tick replayed, False if no more ticks
        """
        if self.current_index >= len(self.ticks):
            return False
        
        tick = self.ticks[self.current_index]
        self.current_index += 1
        
        # Process tick through data service
        self.data_service.on_tick(
            tick['symbol'],
            {
                'timestamp': tick['timestamp'],
                'ltp': tick['ltp'],
                'volume': tick['volume'],
                'order_id': tick.get('order_id')
            }
        )
        
        return True
    
    def replay_all(self):
        """Replay all ticks"""
        logger.info(f"Replaying {len(self.ticks)} ticks...")
        
        while self.replay_next_tick():
            pass
        
        logger.info("Tick replay complete")
    
    def replay_until_time(self, target_time: datetime):
        """
        Replay ticks until target time
        
        Args:
            target_time: Target datetime
        """
        replayed = 0
        while self.current_index < len(self.ticks):
            tick = self.ticks[self.current_index]
            if tick['timestamp'] > target_time:
                break
            
            self.replay_next_tick()
            replayed += 1
        
        logger.info(f"Replayed {replayed} ticks until {target_time}")
    
    def reset(self):
        """Reset replay to beginning"""
        self.current_index = 0
        logger.info("Tick replay reset")


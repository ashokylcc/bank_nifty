"""
WebSocket connection manager with exponential backoff and reconnection
"""
import logging
import time
from typing import Optional, Callable
from datetime import datetime
from trading.utils.time_helpers import get_ist_now

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages WebSocket connections with exponential backoff and reconnection
    """
    
    def __init__(self, max_retries: int = 10, initial_backoff: float = 1.0, max_backoff: float = 60.0):
        """
        Initialize WebSocket manager
        
        Args:
            max_retries: Maximum reconnection attempts
            initial_backoff: Initial backoff time in seconds
            max_backoff: Maximum backoff time in seconds
        """
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.retry_count = 0
        self.last_connect_time = None
        self.last_tick_time = None
        self.last_tick_data = None
        self.is_connected = False
        self.ws_client = None
    
    def connect_with_backoff(self, connect_func: Callable) -> bool:
        """
        Connect with exponential backoff
        
        Args:
            connect_func: Function to call for connection
        
        Returns:
            bool: True if connected successfully
        """
        self.retry_count = 0
        
        while self.retry_count < self.max_retries:
            try:
                logger.info(f"Attempting connection (attempt {self.retry_count + 1}/{self.max_retries})")
                
                # Call connection function
                result = connect_func()
                
                if result:
                    self.is_connected = True
                    self.last_connect_time = get_ist_now()
                    self.retry_count = 0
                    logger.info("✅ WebSocket connected successfully")
                    return True
                
            except Exception as e:
                logger.warning(f"Connection attempt {self.retry_count + 1} failed: {e}")
            
            # Calculate backoff time (exponential)
            backoff_time = min(
                self.initial_backoff * (2 ** self.retry_count),
                self.max_backoff
            )
            
            self.retry_count += 1
            
            if self.retry_count < self.max_retries:
                logger.info(f"Retrying in {backoff_time:.1f} seconds...")
                time.sleep(backoff_time)
        
        logger.error(f"Failed to connect after {self.max_retries} attempts")
        self.is_connected = False
        return False
    
    def reconnect(self, connect_func: Callable) -> bool:
        """
        Reconnect with exponential backoff
        
        Args:
            connect_func: Function to call for reconnection
        
        Returns:
            bool: True if reconnected successfully
        """
        logger.warning("WebSocket disconnected, attempting reconnection...")
        self.is_connected = False
        return self.connect_with_backoff(connect_func)
    
    def update_last_tick(self, tick_data: dict):
        """
        Update last processed tick (for resume after disconnect)
        
        Args:
            tick_data: Tick data dict with timestamp
        """
        self.last_tick_time = tick_data.get('timestamp', get_ist_now())
        self.last_tick_data = tick_data
        logger.debug(f"Last tick updated: {self.last_tick_time}")
    
    def get_last_tick_time(self) -> Optional[datetime]:
        """Get last processed tick time"""
        return self.last_tick_time
    
    def should_resume_from_last_tick(self) -> bool:
        """
        Check if we should resume from last tick
        
        Returns:
            bool: True if last tick exists and is recent
        """
        if not self.last_tick_time:
            return False
        
        # Resume if last tick was within last 5 minutes
        time_diff = (get_ist_now() - self.last_tick_time).total_seconds()
        return time_diff < 300  # 5 minutes
    
    def reset_retry_count(self):
        """Reset retry count after successful connection"""
        self.retry_count = 0
    
    def get_backoff_time(self) -> float:
        """Get current backoff time"""
        return min(
            self.initial_backoff * (2 ** self.retry_count),
            self.max_backoff
        )


"""
Concurrency guard - ensures single authoritative strategy runner
"""
import os
import fcntl
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ConcurrencyGuard:
    """
    Ensures only one strategy runner process at a time
    
    Uses file locking to prevent multiple instances
    """
    
    def __init__(self, lock_file: str = "/tmp/banknifty_strategy.lock"):
        """
        Initialize concurrency guard
        
        Args:
            lock_file: Path to lock file
        """
        self.lock_file = Path(lock_file)
        self.lock_fd = None
        self.is_locked = False
    
    def acquire_lock(self) -> bool:
        """
        Acquire exclusive lock
        
        Returns:
            bool: True if lock acquired, False if already locked
        """
        try:
            # Create lock file if it doesn't exist
            self.lock_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Open file for writing
            self.lock_fd = open(self.lock_file, 'w')
            
            # Try to acquire exclusive lock (non-blocking)
            fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            # Write process ID
            self.lock_fd.write(str(os.getpid()))
            self.lock_fd.flush()
            
            self.is_locked = True
            logger.info(f"Lock acquired: {self.lock_file} (PID: {os.getpid()})")
            return True
            
        except (IOError, OSError) as e:
            if self.lock_fd:
                self.lock_fd.close()
                self.lock_fd = None
            
            logger.warning(f"Could not acquire lock: {e}")
            logger.warning("Another strategy runner may be running")
            return False
    
    def release_lock(self):
        """Release lock"""
        if self.lock_fd and self.is_locked:
            try:
                fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)
                self.lock_fd.close()
                self.lock_file.unlink(missing_ok=True)
                self.is_locked = False
                logger.info(f"Lock released: {self.lock_file}")
            except Exception as e:
                logger.error(f"Error releasing lock: {e}")
    
    def __enter__(self):
        """Context manager entry"""
        if not self.acquire_lock():
            raise RuntimeError("Could not acquire lock - another process may be running")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.release_lock()
    
    def is_another_instance_running(self) -> bool:
        """
        Check if another instance is running
        
        Returns:
            bool: True if another instance detected
        """
        if not self.lock_file.exists():
            return False
        
        try:
            # Try to read lock file
            with open(self.lock_file, 'r') as f:
                pid = int(f.read().strip())
            
            # Check if process is still running
            try:
                os.kill(pid, 0)  # Signal 0 doesn't kill, just checks
                return True  # Process is running
            except OSError:
                # Process doesn't exist, lock file is stale
                self.lock_file.unlink(missing_ok=True)
                return False
                
        except Exception as e:
            logger.error(f"Error checking lock file: {e}")
            return False


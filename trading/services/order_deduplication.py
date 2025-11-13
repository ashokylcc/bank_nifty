"""
Order deduplication service - prevents duplicate order processing
"""
import logging
from typing import Optional, Dict
from django.db import transaction
from trading.models import Order

logger = logging.getLogger(__name__)


class OrderDeduplicator:
    """
    Prevents duplicate order processing using broker order IDs
    """
    
    @staticmethod
    @transaction.atomic
    def get_or_create_order(order_id: str, symbol: str, side: str, qty: int,
                           order_type: str = "MARKET", **kwargs) -> tuple[Order, bool]:
        """
        Get existing order or create new one (idempotent)
        
        Args:
            order_id: Broker order ID (must be unique)
            symbol: Instrument symbol
            side: 'BUY' or 'SELL'
            qty: Quantity
            order_type: Order type
            **kwargs: Additional order fields
        
        Returns:
            Tuple of (Order instance, created boolean)
        """
        # Check if order already exists
        existing_order = Order.objects.filter(order_id=order_id).first()
        
        if existing_order:
            logger.info(f"Order {order_id} already exists, returning existing order")
            return existing_order, False
        
        # Create new order
        order = Order.objects.create(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=qty,
            order_type=order_type,
            **kwargs
        )
        
        logger.info(f"Created new order {order_id}")
        return order, True
    
    @staticmethod
    def is_duplicate_order(order_id: str) -> bool:
        """
        Check if order ID already exists
        
        Args:
            order_id: Broker order ID
        
        Returns:
            bool: True if duplicate
        """
        return Order.objects.filter(order_id=order_id).exists()
    
    @staticmethod
    def get_order_by_broker_id(order_id: str) -> Optional[Order]:
        """
        Get order by broker order ID
        
        Args:
            order_id: Broker order ID
        
        Returns:
            Order instance or None
        """
        return Order.objects.filter(order_id=order_id).first()


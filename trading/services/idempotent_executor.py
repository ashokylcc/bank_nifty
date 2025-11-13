"""
Idempotent order execution - prevents duplicate orders
"""
import logging
from typing import Optional, Dict
from decimal import Decimal
from django.db import transaction
from trading.models import Order
from trading.services.execution_adapter import ExecutionAdapter
from trading.services.order_deduplication import OrderDeduplicator

logger = logging.getLogger(__name__)


class IdempotentExecutor:
    """
    Idempotent order executor - checks for existing orders before placing
    """
    
    def __init__(self, execution_adapter: ExecutionAdapter):
        self.execution_adapter = execution_adapter
        self.deduplicator = OrderDeduplicator()
    
    @transaction.atomic
    def place_order_idempotent(self, symbol: str, side: str, qty: int,
                              order_type: str = "MARKET",
                              limit_price: Optional[Decimal] = None,
                              signal_id: Optional[int] = None,
                              **kwargs) -> Dict:
        """
        Place order idempotently (check for existing order first)
        
        Args:
            symbol: Instrument symbol
            side: 'BUY' or 'SELL'
            qty: Quantity
            order_type: Order type
            limit_price: Limit price (optional)
            signal_id: Signal ID (optional)
            **kwargs: Additional order fields
        
        Returns:
            Dict with order details
        """
        # Generate a unique order identifier
        # In production, this would come from the broker
        # For now, use a combination of symbol, side, qty, timestamp
        from trading.utils.time_helpers import get_ist_now
        import hashlib
        
        # Create unique identifier
        order_key = f"{symbol}_{side}_{qty}_{get_ist_now().isoformat()}"
        order_hash = hashlib.md5(order_key.encode()).hexdigest()[:12]
        temp_order_id = f"TEMP_{order_hash}"
        
        # Check if similar order exists (within last 5 seconds)
        recent_orders = Order.objects.filter(
            symbol=symbol,
            side=side,
            quantity=qty,
            created_at__gte=get_ist_now().replace(second=get_ist_now().second - 5)
        ).order_by('-created_at')
        
        if recent_orders.exists():
            existing_order = recent_orders.first()
            logger.warning(
                f"Similar order found (ID: {existing_order.order_id}), "
                f"returning existing order instead of placing new one"
            )
            return {
                'order_id': existing_order.order_id,
                'status': existing_order.status,
                'filled_price': existing_order.filled_price,
                'is_existing': True
            }
        
        # Place order via adapter
        order_result = self.execution_adapter.place_order(
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            limit_price=limit_price
        )
        
        # Return order result
        # Note: Order record creation is handled by strategy_engine
        # This function just ensures we don't place duplicate orders
        return {
            'order_id': order_result['order_id'],
            'status': order_result.get('status', 'PENDING'),
            'filled_price': order_result.get('filled_price'),
            'is_existing': False
        }
    
    def update_order_status_idempotent(self, order_id: str, status: str,
                                      filled_price: Optional[Decimal] = None) -> Optional[Order]:
        """
        Update order status idempotently
        
        Args:
            order_id: Broker order ID
            status: New status
            filled_price: Filled price (if filled)
        
        Returns:
            Order instance or None
        """
        order = self.deduplicator.get_order_by_broker_id(order_id)
        
        if not order:
            logger.warning(f"Order {order_id} not found for status update")
            return None
        
        # Only update if status changed
        if order.status != status:
            order.status = status
            if filled_price:
                order.filled_price = filled_price
            order.save()
            logger.info(f"Order {order_id} status updated: {order.status} -> {status}")
        else:
            logger.debug(f"Order {order_id} status unchanged: {status}")
        
        return order


"""
Execution adapter - abstract interface for order placement
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)


class ExecutionAdapter(ABC):
    """
    Abstract base class for execution adapters
    """
    
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.adapter_name = self.__class__.__name__
    
    @abstractmethod
    def place_order(self, symbol: str, side: str, qty: int,
                   order_type: str = "MARKET",
                   limit_price: Optional[Decimal] = None) -> Dict:
        """
        Place an order
        
        Args:
            symbol: Instrument symbol
            side: 'BUY' or 'SELL'
            qty: Quantity
            order_type: Order type (default: 'MARKET')
            limit_price: Limit price (for limit orders)
        
        Returns:
            Dict with 'order_id', 'status', 'filled_price'
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> Dict:
        """
        Cancel an order
        
        Args:
            order_id: Order ID
        
        Returns:
            Dict with 'status', 'message'
        """
        pass
    
    @abstractmethod
    def get_order_status(self, order_id: str) -> Dict:
        """
        Get order status
        
        Args:
            order_id: Order ID
        
        Returns:
            Dict with 'status', 'filled_price', 'filled_qty', etc.
        """
        pass
    
    @abstractmethod
    def get_ltp(self, symbol: str, data_service=None) -> Optional[Decimal]:
        """
        Get latest traded price
        
        Args:
            symbol: Instrument symbol
        
        Returns:
            Decimal: Latest LTP or None
        """
        pass


class AliceBlueMockAdapter(ExecutionAdapter):
    """
    Mock adapter for testing and dry-run mode with slippage simulation
    """
    
    def __init__(self, dry_run: bool = True, slippage_pct: float = 0.2, commission_per_lot: float = 0.0):
        """
        Initialize mock adapter
        
        Args:
            dry_run: Always True for mock
            slippage_pct: Slippage percentage (0.1-0.4%, default: 0.2%)
            commission_per_lot: Commission per lot (default: 0.0, set based on broker)
        """
        super().__init__(dry_run=True)  # Always dry_run for mock
        self.orders = {}  # Store mock orders
        self.order_counter = 0
        self.ltp_cache = {}  # Mock LTP cache
        self.slippage_pct = slippage_pct / 100.0  # Convert to decimal
        self.commission_per_lot = commission_per_lot
    
    def place_order(self, symbol: str, side: str, qty: int,
                   order_type: str = "MARKET",
                   limit_price: Optional[Decimal] = None) -> Dict:
        """Place mock order with slippage simulation"""
        import random
        
        self.order_counter += 1
        order_id = f"MOCK_{self.order_counter:06d}"
        
        # Get base price (use limit_price if provided, else use cached LTP)
        if limit_price:
            base_price = limit_price
        else:
            base_price = self.ltp_cache.get(symbol, Decimal('100.00'))
        
        # Simulate slippage (0.1-0.4% of price)
        # Slippage is worse for market orders
        slippage_multiplier = random.uniform(0.5, 1.5)  # Random variation
        slippage_amount = base_price * Decimal(str(self.slippage_pct * slippage_multiplier))
        
        # Apply slippage based on side
        if side == 'BUY':
            # Buy orders get filled at higher price (slippage against you)
            filled_price = base_price + slippage_amount
        else:  # SELL
            # Sell orders get filled at lower price (slippage against you)
            filled_price = base_price - slippage_amount
        
        # Round to 2 decimal places
        filled_price = Decimal(str(round(float(filled_price), 2)))
        
        order_data = {
            'order_id': order_id,
            'status': 'FILLED',
            'filled_price': filled_price,
            'filled_qty': qty,
            'symbol': symbol,
            'side': side,
            'order_type': order_type,
            'dry_run': True,
            'slippage': slippage_amount,
            'base_price': base_price
        }
        
        self.orders[order_id] = order_data
        
        logger.info(
            f"[MOCK] Order placed: {order_id} | {side} {qty} {symbol} @ {filled_price} "
            f"(base: {base_price}, slippage: {slippage_amount:.2f})"
        )
        
        return order_data
    
    def cancel_order(self, order_id: str) -> Dict:
        """Cancel mock order"""
        if order_id in self.orders:
            self.orders[order_id]['status'] = 'CANCELLED'
            logger.info(f"[MOCK] Order cancelled: {order_id}")
            return {'status': 'CANCELLED', 'message': 'Order cancelled'}
        else:
            return {'status': 'ERROR', 'message': 'Order not found'}
    
    def get_order_status(self, order_id: str) -> Dict:
        """Get mock order status"""
        if order_id in self.orders:
            return self.orders[order_id]
        else:
            return {'status': 'NOT_FOUND', 'message': 'Order not found'}
    
    def get_ltp(self, symbol: str, data_service=None) -> Optional[Decimal]:
        """
        Get mock LTP
        
        Args:
            symbol: Instrument symbol
            data_service: Optional data service to get live LTP from
        
        Returns:
            Decimal: LTP value or None
        """
        # If data_service provided and has live LTP, use that (for live data mode)
        if data_service:
            if hasattr(data_service, 'ltp_cache') and symbol in data_service.ltp_cache:
                # Update our cache with live LTP
                self.ltp_cache[symbol] = data_service.ltp_cache[symbol]
                return data_service.ltp_cache[symbol]
            elif hasattr(data_service, 'get_latest_ltp'):
                ltp = data_service.get_latest_ltp(symbol)
                if ltp:
                    self.ltp_cache[symbol] = ltp
                    return ltp
        
        # Fallback to cached LTP
        return self.ltp_cache.get(symbol, Decimal('100.00'))
    
    def set_mock_ltp(self, symbol: str, ltp: Decimal):
        """Set mock LTP for testing"""
        self.ltp_cache[symbol] = ltp


class AliceBlueAdapter(ExecutionAdapter):
    """
    Real Alice Blue adapter (placeholder - integrate with actual API)
    """
    
    def __init__(self, dry_run: bool = True, user_id: str = None, api_key: str = None):
        super().__init__(dry_run)
        self.user_id = user_id
        self.api_key = api_key
        self.session = None
        
        if not dry_run:
            logger.warning("AliceBlueAdapter initialized in LIVE mode - real orders will be placed!")
            # TODO: Initialize Alice Blue session
            # from strategy.broker.alice_client import get_session_id
            # self.session = get_session_id(user_id, api_key)
    
    def place_order(self, symbol: str, side: str, qty: int,
                   order_type: str = "MARKET",
                   limit_price: Optional[Decimal] = None) -> Dict:
        """Place real order via Alice Blue API"""
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would place order: {side} {qty} {symbol}")
            return {
                'order_id': f"DRY_RUN_{symbol}",
                'status': 'FILLED',
                'filled_price': limit_price or Decimal('100.00'),
                'dry_run': True
            }
        
        # TODO: Implement real order placement
        # from alice_blue import TransactionType, OrderType, ProductType
        # order = self.session.place_order(
        #     TransactionType.Buy if side == 'BUY' else TransactionType.Sell,
        #     symbol,
        #     qty,
        #     OrderType.Market if order_type == 'MARKET' else OrderType.Limit,
        #     limit_price
        # )
        # return {
        #     'order_id': order['order_id'],
        #     'status': order['status'],
        #     'filled_price': order.get('filled_price')
        # }
        
        raise NotImplementedError("Real Alice Blue integration not implemented yet")
    
    def cancel_order(self, order_id: str) -> Dict:
        """Cancel real order"""
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would cancel order: {order_id}")
            return {'status': 'CANCELLED', 'message': 'Dry run mode'}
        
        # TODO: Implement real order cancellation
        raise NotImplementedError("Real Alice Blue integration not implemented yet")
    
    def get_order_status(self, order_id: str) -> Dict:
        """Get real order status"""
        if self.dry_run:
            return {'status': 'FILLED', 'dry_run': True}
        
        # TODO: Implement real order status check
        raise NotImplementedError("Real Alice Blue integration not implemented yet")
    
    def get_ltp(self, symbol: str, data_service=None) -> Optional[Decimal]:
        """
        Get real LTP from Alice Blue API or data service
        
        Args:
            symbol: Instrument symbol
            data_service: Optional data service to get live LTP from
        
        Returns:
            Decimal: LTP value or None
        """
        # If data_service provided, try to get live LTP first
        if data_service:
            if hasattr(data_service, 'ltp_cache') and symbol in data_service.ltp_cache:
                return data_service.ltp_cache[symbol]
            elif hasattr(data_service, 'get_latest_ltp'):
                return data_service.get_latest_ltp(symbol)
        
        if self.dry_run:
            return Decimal('100.00')
        
        # TODO: Implement real LTP fetch
        # from strategy.broker.live_ltp import WebSocketLTP
        # ltp = WebSocketLTP.get_ltp(symbol)
        # return Decimal(str(ltp))
        
        raise NotImplementedError("Real Alice Blue integration not implemented yet")


def get_execution_adapter(dry_run: bool = True, adapter_type: str = "mock",
                         slippage_pct: float = 0.2, commission_per_lot: float = 20.0,
                         **kwargs) -> ExecutionAdapter:
    """
    Factory function to get execution adapter
    
    Args:
        dry_run: Whether to use dry-run mode
        adapter_type: 'mock' or 'aliceblue'
        slippage_pct: Slippage percentage for mock adapter (default: 0.2%)
        commission_per_lot: Commission per lot for mock adapter (default: 20.0)
        **kwargs: Additional arguments for adapter
    
    Returns:
        ExecutionAdapter instance
    """
    if adapter_type == "mock":
        return AliceBlueMockAdapter(
            dry_run=True,
            slippage_pct=slippage_pct,
            commission_per_lot=commission_per_lot
        )
    elif adapter_type == "aliceblue":
        return AliceBlueAdapter(dry_run=dry_run, **kwargs)
    else:
        raise ValueError(f"Unknown adapter type: {adapter_type}")


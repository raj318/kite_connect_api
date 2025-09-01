import logging
from typing import Dict, Any, Optional
from datetime import datetime
import traceback
from kite_utils import setup_logger

class OrderManager:
    """Class to handle order management operations"""
    
    def __init__(self, kite_api, stock_name: str, exchange: str, logger: Optional[logging.Logger] = None):
        """
        Initialize Order Manager
        
        Parameters:
        - kite_api: KiteConnectAPI instance
        - stock_name: Trading symbol of the stock
        - exchange: Exchange name
        - logger: Optional logger instance
        """
        self.kite_api = kite_api
        self.stock_name = stock_name
        self.exchange = exchange
        self.logger = logger or setup_logger(__name__, stock_name)
        self.positions = []
        
    def place_buy_order(self, current_price: float, quantity: int = 1) -> Dict[str, Any]:
        """
        Place a buy order using Kite API
        
        Parameters:
        - current_price: Current market price of the stock
        - quantity: Number of shares to buy (default: 1)
        
        Returns:
        Dictionary containing order details
        """
        try:
            if not self.kite_api:
                raise Exception("Kite API not initialized")
            
            # Place buy order
            order_params = {
                "tradingsymbol": self.stock_name,
                "exchange": self.exchange,
                "transaction_type": "BUY",
                "quantity": quantity,
                "product": "CNC",  # Cash and Carry
                "order_type": "LIMIT",  # Limit order
                "price": current_price,  # Limit price
                "validity": "DAY"  # Valid for the day
            }
            
            self.logger.info(f"Placing buy order for {self.stock_name} at limit price {current_price}")
            order_response = self.kite_api.place_order(**order_params)
            
            if not order_response or 'order_id' not in order_response:
                raise Exception("Failed to place order")
            
            # Log order details
            self.logger.info(f"Buy order placed successfully. Order ID: {order_response['order_id']}")
            
            # Add order to tracking
            order_details = {
                'order_id': order_response['order_id'],
                'status': order_response.get('status', 'UNKNOWN'),
                'trading_symbol': self.stock_name,
                'quantity': quantity,
                'price': current_price,
                'timestamp': datetime.now().isoformat()
            }
            
            self.positions.append(order_details)
            return order_details
            
        except Exception as e:
            self.logger.error(f"Error placing buy order: {e}\n{traceback.format_exc()}")
            raise
            
    def place_sell_order(self, current_price: float, quantity: int) -> Dict[str, Any]:
        """
        Place a sell order using Kite API
        
        Parameters:
        - current_price: Current market price of the stock
        - quantity: Number of shares to sell
        
        Returns:
        Dictionary containing order details
        """
        try:
            if not self.kite_api:
                raise Exception("Kite API not initialized")
            
            # Place sell order
            order_params = {
                "tradingsymbol": self.stock_name,
                "exchange": self.exchange,
                "transaction_type": "SELL",
                "quantity": quantity,
                "product": "CNC",  # Cash and Carry
                "order_type": "LIMIT",  # Limit order
                "price": current_price,  # Limit price
                "validity": "DAY"  # Valid for the day
            }
            
            self.logger.info(f"Placing sell order for {self.stock_name} at limit price {current_price}")
            order_response = self.kite_api.place_order(**order_params)
            
            if not order_response or 'order_id' not in order_response:
                raise Exception("Failed to place order")
            
            # Log order details
            self.logger.info(f"Sell order placed successfully. Order ID: {order_response['order_id']}")
            
            # Add order to tracking
            order_details = {
                'order_id': order_response['order_id'],
                'status': order_response.get('status', 'UNKNOWN'),
                'trading_symbol': self.stock_name,
                'quantity': quantity,
                'price': current_price,
                'timestamp': datetime.now().isoformat()
            }
            
            return order_details
            
        except Exception as e:
            self.logger.error(f"Error placing sell order: {e}\n{traceback.format_exc()}")
            raise
            
    def get_positions(self) -> list:
        """Get list of current positions"""
        return self.positions 
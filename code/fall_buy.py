import logging
from typing import Dict, Any, Optional
from datetime import datetime, time as dt_time
import os
import sys
import traceback
import json
import atexit
import pytz
from kite_utils import load_config, setup_logger
from kite_connect_api import KiteConnectAPI


class FallBuy:
    """Class to handle fall buy trading strategy"""
    
    @staticmethod
    def is_market_hours() -> bool:
        """Check if current time is within Indian market hours (9:15 AM to 3:30 PM IST)"""
        try:
            # Get current time in IST
            ist = pytz.timezone('Asia/Kolkata')
            current_time = datetime.now(ist).time()
            
            # Define market hours
            market_start = dt_time(9, 15)  # 9:15 AM
            market_end = dt_time(15, 30)   # 3:30 PM
            
            # Check if current time is before market end time
            return current_time <= market_end
        except Exception as e:
            logging.error(f"Error checking market hours: {e}")
            return False

    def cleanup_pending_orders(self) -> None:
        """Clean up pending orders when market hours end"""
        try:
            if not self.pending_orders:
                self.logger.info("No pending orders to clean up")
                return

            self.logger.info(f"Cleaning up {len(self.pending_orders)} pending orders...")
            
            for order in self.pending_orders[:]:  # Create a copy to safely modify during iteration
                try:
                    # Get current order status
                    status = self.get_order_status(order['order_id'])
                    
                    if status == 'COMPLETE':
                        self.logger.info(f"Order {order['order_id']} was completed. Moving to placed orders.")
                        self.move_to_placed_orders(order)
                    else:
                        # Move to failed orders with reason
                        self.logger.info(f"Moving order {order['order_id']} to failed orders due to market hours end")
                        self.update_failed_orders(
                            type=order['type'],
                            order_id=order['order_id'],
                            shares_available_to_sell=order['quantity'],
                            cur_price=order['price'],
                            error="Order cancelled due to market hours end"
                        )
                        self.pending_orders.remove(order)
                        
                except Exception as e:
                    self.logger.error(f"Error cleaning up order {order['order_id']}: {e}")
                    # Still move to failed orders even if status check fails
                    self.update_failed_orders(
                        type=order['type'],
                        order_id=order['order_id'],
                        shares_available_to_sell=order['quantity'],
                        cur_price=order['price'],
                        error=f"Error during cleanup: {str(e)}"
                    )
                    self.pending_orders.remove(order)
            
            self.logger.info("Pending orders cleanup completed")
            
        except Exception as e:
            self.logger.error(f"Error during pending orders cleanup: {e}\n{traceback.format_exc()}")

    def __init__(self, exchange: str, stock_name: str, demo_mode: bool = False):
        """
        Initialize the Fall Buy trading strategy
        
        Parameters:
        - exchange: Exchange name (e.g., "NSE")
        - stock_name: Trading symbol of the stock (e.g., "ITC")
        - demo_mode: If True, orders will be simulated without actual execution
        
        Raises:
        - ValueError: If exchange or stock_name is not provided or is empty
        """
        if not exchange or not exchange.strip():
            error_msg = "Exchange name is required and cannot be empty"
            raise ValueError(error_msg)
            
        if not stock_name or not stock_name.strip():
            error_msg = "Stock name is required and cannot be empty"
            raise ValueError(error_msg)
            
        # Initialize instance variables
        self.exchange = exchange.strip()
        self.stock_name = stock_name.strip()
        self.demo_mode = demo_mode
        self.config = load_config()
        self.kite_api = None
        self.order_history = []
        self.current_price = None
        self.last_buy_price = None
        self.last_sell_price = None
        self.total_investment = 0
        self.total_shares = 0
        self.initial_investment = 0
        self.linear_from = 0
        self.buy_threshold = 0
        self.sell_threshold = 0
        self.first_share_price = None
        self.placed_orders = []
        self.pending_orders = []
        self.failed_orders = []
        self.history = []
        self.buy_progress = 0
        self.sell_progress = 0
        self.prev_tick_price = None
        
        # Set up stock-specific logger
        self.logger = setup_logger(__name__, self.stock_name)
    
        
        # Initialize Kite API if not in demo mode
        if not self.demo_mode:
            self._init_kite_api()
        
        # Trading parameters from config
        self.trading_params = self._load_trading_params()
        
        # Track last price and positions
        self.last_price = None
        self.positions = []
        
        # Load previous trading state if exists
        self.load_stock_history()
        
        # Register cleanup handler
        atexit.register(self.save_stock_history)
        
        self.logger.info(f"Initialized FallBuy strategy for {self.stock_name} on {self.exchange}")

    def save_stock_history(self) -> None:
        """
        Save stock trading history to JSON file.
        This method is called automatically when the script exits.
        """
        try:
            # Create orders directory if it doesn't exist
            orders_dir = os.path.join('workdir', 'orders')
            os.makedirs(orders_dir, exist_ok=True)
            
            # Prepare history data
            history_data = {
                'stock_name': self.stock_name,
                'exchange': self.exchange,
                'last_updated': datetime.now().isoformat(),
                'first_share_price': self.first_share_price,
                'placed_orders': self.placed_orders,
                'pending_orders': self.pending_orders,
                'failed_orders': self.failed_orders,
                'history': self.history,
                'positions': self.positions
            }
            
            # Save to JSON file
            file_path = os.path.join(orders_dir, f'{self.stock_name}_history.json')
            with open(file_path, 'w') as f:
                json.dump(history_data, f, indent=4)
            
            self.logger.info(f"Stock history saved to {file_path}")
            
        except Exception as e:
            self.logger.error(f"Error saving stock history: {e}\n{traceback.format_exc()}")

    def load_stock_history(self) -> None:
        """
        Load stock trading history from JSON file if it exists.
        This method should be called after initialization if you want to resume previous state.
        """
        try:
            file_path = os.path.join('workdir', 'orders', f'{self.stock_name}_history.json')
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    history_data = json.load(f)
                
                # Restore state
                self.first_share_price = history_data.get('first_share_price')
                self.placed_orders = history_data.get('placed_orders', [])
                self.pending_orders = history_data.get('pending_orders', [])
                self.failed_orders = history_data.get('failed_orders', [])
                self.history = history_data.get('history', [])
                self.positions = history_data.get('positions', [])
                
                self.logger.info(f"Loaded stock history from {file_path}")
                
        except Exception as e:
            self.logger.error(f"Error loading stock history: {e}\n{traceback.format_exc()}")
            # Initialize empty state if loading fails
            self.first_share_price = None
            self.placed_orders = []
            self.pending_orders = []
            self.failed_orders = []
            self.history = []
            self.positions = []

    def load_strategy_variables(self, strategy_config: Dict[str, Any]) -> None:
        """Load strategy variables from config"""
        self.buy_perc = strategy_config['buy']
        self.sell_perc = strategy_config['sell']
        self.start_buy = strategy_config['start_buy']
        self.linear_from = strategy_config['linear_from']

    def _load_trading_params(self) -> Dict[str, Any]:
        """
        Load trading parameters from config
        
        Returns:
        Dictionary containing trading parameters
        """
        try:
            # Get trading parameters from config
            self.logger.info(self.config)
            trading_params = self.config.get('stratergy', {})
            
            # Validate required parameters
            required_params = ['sell', 'buy', 'start_buy', 'linear_from']
            missing_params = [param for param in required_params if param not in trading_params]
            
            self.buy_perc = trading_params['buy']
            self.sell_perc = trading_params['sell']
            self.start_buy = trading_params['start_buy']
            self.linear_from = trading_params['linear_from']
            if missing_params:
                error_msg = f"Missing required trading parameters: {', '.join(missing_params)}"
                self.logger.error(error_msg)
                raise ValueError(error_msg)
            
            return trading_params
            
        except Exception as e:
            self.logger.error(f"Error loading trading parameters: {e}\n{traceback.format_exc()}")
            raise
    
    def _init_kite_api(self):
        """Initialize and connect to Kite API"""
        try:
            # Initialize Kite API
            self.kite_api = KiteConnectAPI(trading_symbol=self.stock_name)
            self.kite_api.connect()
            
            self.logger.info("Successfully initialized and connected to Kite API")
            
        except Exception as e:
            self.logger.error(f"Error initializing Kite API: {e}\n{traceback.format_exc()}")
            raise
    
    def get_account_details(self) -> Dict[str, Any]:
        """
        Get account details from Kite API
        
        Returns:
        Dictionary containing account details
        """
        try:
            if not self.kite_api:
                raise Exception("Kite API not initialized")
            
            return self.kite_api.get_account_details()
            
        except Exception as e:
            self.logger.error(f"Error getting account details: {e}\n{traceback.format_exc()}")
            raise
            
    def get_tick(self, tick: Dict[str, Any]):
        """
        Handle incoming tick data from Breeze API
        
        Parameters:
        - tick_data: Dictionary containing tick data
        """
        try:
            
            current_price = tick['last']
            if current_price == self.prev_tick_price:
                return None
            print(f"current_price = {current_price}")
            if self.buy_progress == 1 or self.sell_progress == 1:
                self.logger.info(f"buy_progress = {self.buy_progress}, sell_progress = {self.sell_progress}, will not progress to decide the order")
                return None
            
            first_share_price = self.buy_first_share(current_price)
            self.verify_pending_orders_on_startup()
            self.logger.info(f"first_share_price = {first_share_price}")
            self.trade(current_price, first_share_price)
            self.prev_tick_price = current_price

        except Exception as e:
            self.logger.error(f"Error processing tick: {e}\n{traceback.format_exc()}")

    def trade(self, current_price: float, first_share_price: float) -> None:
        """Trade logic for fall buy strategy"""
        # Use small epsilon for float comparison
        EPSILON = 1e-10
        if abs(current_price - first_share_price) < EPSILON:
            return
        diff = (current_price - first_share_price)/first_share_price * 100
        self.trade_decide(diff, current_price)
        self.verify_pending_order()

    def trade_decide(self, diff: float, current_price: float) -> None:
        """Decide to buy or sell based on the difference"""
        self.logger.info(f"trade_decide: diff = {diff}, current_price = {current_price}")
        if not self.placed_orders:
            purchase_price = self.first_share_price
        else:
            purchase_price = self.placed_orders[-1]['price']
        self.logger.info(f"last purchase_price or first share price = {purchase_price}")
        if diff > self.buy_perc:
            self.buy_progress = 1
            self.logger.info(f"selling all shares @ {current_price}")
            self.sell_all_shares(current_price)
            self.buy_progress = 0
        elif ((current_price - purchase_price)/purchase_price * 100 < -self.buy_perc):
            if self.pending_orders[-1]['type'] == 'sell':
                if current_price - self.pending_orders[-1]['price'] < self.sell_perc:
                    self.logger.info(f"possible duplicate order, will not progress to decide the order")
                    return None
            self.buy_progress = 1
            self.logger.info(f"Placing order to buy a share @ {current_price}")
            self.buy_a_share(current_price, self.get_buy_orders_count()+1)
            self.buy_progress = 0

    def sell_all_shares(self, current_price: float) -> None:
        """Sell all shares"""
        shares_available_to_sell = self.get_shares_available_to_sell()
        self.logger.info(f"Selling {shares_available_to_sell} shares @ {current_price}")
        self.sell_shares(shares_available_to_sell, current_price)
    
    def get_order_status(self, order_id: str) -> str:
        """
        Get the status of an order
        
        Parameters:
        - order_id: Order identifier
        
        Returns:
        Order status as string
        """
        if self.demo_mode:
            return 'executed'
            
        try:
            # Get all orders
            orders = self.kite_api.kite.orders()
            
            # Find the specific order
            for order in orders:
                if order['order_id'] == order_id:
                    return order['status']
                    
            self.logger.warning(f"Order {order_id} not found")
            return 'UNKNOWN'
            
        except Exception as e:
            self.logger.error(f"Error getting order status: {e}")
            return 'UNKNOWN'

    def sell_shares(self, shares_available_to_sell: int, current_price: float) -> bool:
        """Sell shares
        
        Returns:
        - bool: True if order was executed successfully, False otherwise
        """
        try:
            if shares_available_to_sell <=0:
                return False
            if self.pending_orders[-1]['type'] == 'sell':
                if current_price - self.pending_orders[-1]['price'] < self.sell_perc:
                    self.logger.info(f"possible duplicate order, will not progress to decide the order")
                    return None
            if self.demo_mode:
                # Simulate order placement
                order_id = f"DEMO_SELL_{len(self.order_history) + 1}"
                self.logger.info(f"DEMO MODE: Simulating sell order for {shares_available_to_sell} shares @ {current_price}")
                self.update_placed_orders(type='sell', order_id=order_id, shares_available_to_sell=shares_available_to_sell, cur_price=current_price)
                self.history.append(self.placed_orders)
                self.placed_orders = []
                self.first_share_price = 0
                return True

            self.logger.info(f"placing sell order for self.stock_name= {self.stock_name}, self.exchange= {self.exchange}, shares_available_to_sell= {shares_available_to_sell}, current_price= {current_price}")
            order_id = self.kite_api.kite.place_order(
                tradingsymbol=self.stock_name,
                variety=self.kite_api.kite.VARIETY_REGULAR,
                exchange=self.exchange,
                transaction_type="SELL",
                quantity=shares_available_to_sell,
                price=current_price,
                product="CNC",
                order_type=self.kite_api.kite.ORDER_TYPE_LIMIT,
                validity="DAY",
            )

            self.logger.info(f"Sell order placed successfully. Order ID: {order_id}")
            if self.get_order_status(order_id) == "COMPLETE":
                self.update_placed_orders(type='sell', order_id=order_id, shares_available_to_sell=shares_available_to_sell, cur_price=current_price)
                self.history.append(self.placed_orders)
                self.placed_orders = []
                return True
            elif self.get_order_status(order_id) == 'FAILED':
                self.update_failed_orders(type='sell', order_id=order_id, shares_available_to_sell=shares_available_to_sell, cur_price=current_price)
                self.log_failed_order(order_id, shares_available_to_sell, current_price)  # Changed to log instead of mail
                return False
            else:
                self.update_pending_orders(type='sell', order_id=order_id, shares_available_to_sell=shares_available_to_sell, cur_price=current_price)
                return False

        except Exception as e:
            self.logger.error(f"Error placing sell order: {e}\n{traceback.format_exc()}")
            self.update_failed_orders(type='sell', order_id=None, shares_available_to_sell=shares_available_to_sell, cur_price=current_price, error=str(e))
            raise

    def update_failed_orders(self, type: str, order_id: str, shares_available_to_sell: int, cur_price: float, error: str = None) -> None:
        """Update failed orders"""
        self.failed_orders.append({
            'order_id': order_id,
            'quantity': shares_available_to_sell,
            'price': cur_price,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': type,
            'error': error
        })

    def update_placed_orders(self, type: str, order_id: str, shares_available_to_sell: int, cur_price: float) -> None:
        """Update placed orders"""
        self.placed_orders.append({
            'order_id': order_id,
            'quantity': shares_available_to_sell,
            'price': cur_price,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': type
        })

    def update_pending_orders(self, type: str, order_id: str, shares_available_to_sell: int, cur_price: float) -> None:
        """Update pending orders"""
        self.pending_orders.append({
            'order_id': order_id,
            'quantity': shares_available_to_sell,
            'price': cur_price,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': type
        })

    def verify_pending_order(self) -> bool:
        """Verify pending order
        
        Returns:
        - bool: True if any pending order was executed, False otherwise
        """
        executed = False
        for order in self.pending_orders[:]:  # Create a copy to safely modify during iteration
            status = self.get_order_status(order['order_id'])
            
            if order['type'] == 'sell':
                if status == 'COMPLETE':
                    self.first_share_price = 0
                    self.history.append(self.placed_orders)
                    self.placed_orders = []
                    executed = True
            if order['type'] == 'buy':
                if status == 'COMPLETE':
                    self.move_to_placed_orders(order)
                    executed = True
                elif status in ['CANCELLED', 'REJECTED']:
                    self.update_failed_orders(order['type'], order['order_id'], order['quantity'], order['price'])
                    self.pending_orders.remove(order)
                    
        return executed

    def move_to_placed_orders(self, order: Dict[str, Any]) -> None:
        """Move order to placed orders if not already present.
        
        Args:
            order: Order dictionary containing order details
        """
        # Check if order already exists in placed_orders
        for existing_order in self.placed_orders:
            if existing_order.get('order_id') == order.get('order_id'):
                self.logger.info(f"Order {order.get('order_id')} already exists in placed orders. Skipping.")
                return
                
        # If order not found in placed_orders, add it
        self.placed_orders.append(order)
        self.logger.info(f"Added order {order.get('order_id')} to placed orders")
        
        # Remove from pending orders if present
        if order in self.pending_orders:
            self.pending_orders.remove(order)
            self.logger.info(f"Removed order {order.get('order_id')} from pending orders")

    def get_shares_available_to_sell(self) -> int:
        """Get shares available to sell"""
        shares_available_to_sell = 0
        for order in self.placed_orders:
            shares_available_to_sell += order['quantity']
        return shares_available_to_sell

    def buy_first_share(self, current_price: float) -> float:
        """Buy first share if not already purchased.
        
        Args:
            current_price: Current stock price
            
        Returns:
            First share price
        """
        if not self.first_share_price:
            self.buy_a_share(current_price)
            self.first_share_price = current_price
            self.logger.info(f"First share purchased = {self.first_share_price}")
        return self.first_share_price

    def buy_a_share(self, cur_price: float, count: int = 1) -> None:
        """Execute buy order for shares.
        
        Args:
            cur_price: Current stock price
            count: Number of shares to buy
            
        Raises:
            ValueError: If price or count is invalid
            Exception: If order placement fails
        """

        if self.pending_orders[-1]['type'] == 'buy':
            if self.pending_orders[-1]['price'] - cur_price < self.buy_perc:
                self.logger.info(f"possible duplicate order, will not progress to decide the order")
                return None
        
        self.logger.info(f"Attempting to buy {count} shares @ {cur_price}")
        
        # Check if we have sufficient funds (in non-demo mode)
        if not self.demo_mode and self.kite_api:
            try:
                margin = self.kite_api.kite.margins()
                available_cash = float(margin['equity']['available']['cash'])
                required_amount = cur_price * count
                if available_cash < required_amount:
                    self.logger.error(f"Insufficient funds. Required: {required_amount}, Available: {available_cash}")
                    return False
            except Exception as e:
                self.logger.error(f"Error checking margin: {e}")
                return False
        
        # Check if market is open (in non-demo mode)
        if not self.demo_mode:
            try:
                current_time = datetime.now().time()
                market_start = datetime.strptime("09:15:00", "%H:%M:%S").time()
                market_end = datetime.strptime("15:30:00", "%H:%M:%S").time()
                if not (market_start <= current_time <= market_end):
                    self.logger.error("Market is closed. Cannot place order.")
                    return False
            except Exception as e:
                self.logger.error(f"Error checking market hours: {e}")
                return False
        
        # Place the order
        try:
            order_id = self._place_buy_order(count, cur_price)
            # self.first_share_price = cur_price

            # self.logger.info(f"self.first_share_price after buying a share= {self.first_share_price}")
            
            # Verify order execution status
            execution_status = self.get_order_status(order_id)
            self.logger.info(f"Order {order_id} execution status: {execution_status}")
            
            if execution_status == "COMPLETE":
                self.update_placed_orders(type='buy', order_id=order_id, shares_available_to_sell=count, cur_price=cur_price)
                self.logger.info(f"Buy order {order_id} executed successfully. Updating records...")
                return True
            elif execution_status == 'FAILED':
                self.update_failed_orders(type='buy', order_id=order_id, shares_available_to_sell=count, cur_price=cur_price)
                self.logger.info(f"Buy order {order_id} failed. Updating records...")
                return False
            else:
                self.update_pending_orders(type='buy', order_id=order_id, shares_available_to_sell=count, cur_price=cur_price)
                self.logger.info(f"Buy order {order_id} not yet executed. Moving to pending orders.")
                return False
            
        except Exception as e:
            self.logger.error(f"Error in buy_a_share: {e}\n{traceback.format_exc()}")
            return False

    def _place_buy_order(self, quantity: int, price: float) -> dict:
        """
        Place a buy order
        
        Parameters:
        - quantity: Number of shares to buy
        - price: Price at which to buy
        
        Returns:
        Dictionary containing order details
        
        Raises:
        - ValueError: If quantity or price is invalid
        - Exception: If order placement fails
        """
        # Validate inputs
        if not isinstance(quantity, int) or quantity <= 0:
            self.logger.error(f"Invalid quantity: {quantity}. Quantity must be positive integer.")
        if not isinstance(price, (int, float)) or price <= 0:
            self.logger.error(f"Invalid price: {price}. Price must be positive.")
        
        if self.demo_mode:
            # Simulate order placement
            order_id = f"DEMO_BUY_{len(self.order_history) + 1}"
            order_details = {
                'order_id': order_id,
                'status': 'COMPLETE',
                'tradingsymbol': self.stock_name,
                'quantity': quantity,
                'price': price,
                'timestamp': datetime.now().isoformat()
            }
            self.logger.info(f"DEMO MODE: Simulated buy order placed: {order_details}")
            return order_details
        
        if not self.kite_api:
            raise ValueError("Kite API not initialized")
        
        try:
            # # Check circuit limits
            # try:
            #     quote = self.kite_api.kite.quote(f"{self.exchange}:{self.stock_name}")
            #     if quote:
            #         instrument_data = quote[f"{self.exchange}:{self.stock_name}"]
            #         circuit_limit = instrument_data.get("circuit_limit", 0)
            #         if circuit_limit and abs((price - instrument_data.get("last_price", 0)) / instrument_data.get("last_price", 1) * 100) > circuit_limit:
            #             raise ValueError(f"Order price {price} exceeds circuit limit of {circuit_limit}%")
            # except Exception as e:
            #     self.logger.error(f"Error checking circuit limits: {e}")
            #     raise
            
            # Place market order using Kite API constants
            order_id = self.kite_api.kite.place_order(
                variety=self.kite_api.kite.VARIETY_REGULAR,
                tradingsymbol=self.stock_name,
                exchange=self.kite_api.kite.EXCHANGE_NSE if self.exchange == "NSE" else self.kite_api.kite.EXCHANGE_BSE,
                transaction_type=self.kite_api.kite.TRANSACTION_TYPE_BUY,
                quantity=quantity,
                product=self.kite_api.kite.PRODUCT_CNC,
                order_type=self.kite_api.kite.ORDER_TYPE_LIMIT,
                validity=self.kite_api.kite.VALIDITY_DAY,
                price=price
            )
            
            # Get order details
            order_details = self.get_order_status(order_id)
            self.logger.info(f"Buy order placed: {order_details}")
            return order_id
            # return order_details
            
        except Exception as e:
            self.logger.error(f"Error placing buy order: {e}\n{traceback.format_exc()}")
            raise
    
    def get_order_details(self, order_id: str) -> dict:
        self.logger.info(f"Getting order details for {order_id}")
        order_history = self.kite_api.kite.order_history(order_id)
        self.logger.info(f"Order history: {order_history}")
        return order_history

    def _place_sell_order(self, quantity: int, price: float) -> dict:
        """
        Place a sell order
        
        Parameters:
        - quantity: Number of shares to sell
        - price: Price at which to sell
        
        Returns:
        Dictionary containing order details
        """
        if self.demo_mode:
            # Simulate order placement
            order_id = f"DEMO_SELL_{len(self.order_history) + 1}"
            order_details = {
                'order_id': order_id,
                'status': 'COMPLETE',
                'tradingsymbol': self.stock_name,
                'quantity': quantity,
                'price': price,
                'timestamp': datetime.now().isoformat()
            }
            self.logger.info(f"DEMO MODE: Simulated sell order placed: {order_details}")
            return order_details
            
        if not self.kite_api:
            raise ValueError("Kite API not initialized")
            
        try:
            # Place market order
            order_id = self.kite_api.kite.place_order(
                tradingsymbol=self.stock_name,
                exchange=self.exchange,
                transaction_type="SELL",
                quantity=quantity,
                product="CNC",
                order_type=self.kite_api.kite.ORDER_TYPE_LIMIT,
                validity="DAY",
                price=price

            )
            
            # Get order details
            order_details = self.kite_api.get_order_details(order_id)
            self.logger.info(f"Sell order placed: {order_details}")
            return order_details
            
        except Exception as e:
            self.logger.error(f"Error placing sell order: {e}")
            raise

    def log_failed_order(self, order_id: str, quantity: int, price: float) -> None:
        """Log failed order details
        
        Parameters:
        - order_id: Order identifier
        - quantity: Number of shares
        - price: Order price
        """
        self.logger.error(f"Order {order_id} failed: {quantity} shares at {price}")

    def load_previous_state(self) -> None:
        """Load previous trading state from JSON file."""
        try:
            orders_dir = os.path.join('workdir', 'orders')
            os.makedirs(orders_dir, exist_ok=True)

            self.history_file = os.path.join(orders_dir, f"{self.stock_name}_history.json")
            
            self.logger.info(f"self.history_file= {self.history_file}")
            # Check if file exists
            if not os.path.exists(self.history_file):
                self.logger.info(f"No previous state file found at {self.history_file}. Initializing with default values.")
                self.order_history = []
                self.placed_orders = []
                self.pending_orders = []
                self.failed_orders = []
                self.first_share_price = None
                return
                
            # Read and parse JSON file
            with open(self.history_file, 'r') as f:
                data = json.load(f)
                
            # Validate data structure
            if not isinstance(data, dict):
                self.logger.warning(f"Invalid data format in {self.history_file}. Initializing with default values.")
                self.order_history = []
                self.placed_orders = []
                self.pending_orders = []
                self.failed_orders = []
                self.first_share_price = None
                return
                
            print(data)
            # Extract data with default values if keys don't exist
            self.order_history = data.get('order_history', [])
            self.placed_orders = data.get('placed_orders', [])
            self.pending_orders = data.get('pending_orders', [])
            self.failed_orders = data.get('failed_orders', [])
            self.first_share_price = data.get('first_share_price')
            self.logger.info(f"self.first_share_price after loading previous state= {self.first_share_price}")
            # Log state
            self.logger.info(f"Successfully loaded previous trading state from {self.history_file}")
            self.logger.info(f"First share price: {self.first_share_price}")
            self.logger.info(f"Placed orders: {len(self.placed_orders)}")
            self.logger.info(f"Pending orders: {len(self.pending_orders)}")
            self.logger.info(f"Failed orders: {len(self.failed_orders)}")
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Error parsing JSON from {self.history_file}: {e}")
            self.logger.info("Initializing with default values due to JSON parsing error.")
            self.order_history = []
            self.placed_orders = []
            self.pending_orders = []
            self.failed_orders = []
            self.first_share_price = None
            
        except Exception as e:
            self.logger.error(f"Error loading previous state: {e}\n{traceback.format_exc()}")
            self.logger.info("Initializing with default values due to error.")
            self.order_history = []
            self.placed_orders = []
            self.pending_orders = []
            self.failed_orders = []
            self.first_share_price = None

    def verify_pending_orders_on_startup(self) -> None:
        """
        Verify status of pending orders when loading previous state.
        This ensures we don't have stale pending orders.
        """
        try:
            for order in self.pending_orders[:]:  # Create a copy to safely modify during iteration
                order_status = self.get_order_status(order['order_id'])
                self.logger.info(f"order_status testtt= {order_status}")
                if order_status == "COMPLETE":
                    if order['type'] == 'buy':
                        self.logger.info(f"Pending order {order['order_id']} was executed. Moving to placed orders.")
                        self.move_to_placed_orders(order)
                    elif order['type'] == 'sell':
                        self.logger.info(f"Pending order {order['order_id']} was executed. Moving to placed orders.")
                        self.move_to_history(order)
                elif order_status == "FAILED":
                    self.logger.info(f"Pending order {order['order_id']} failed. Moving to failed orders.")
                    self.failed_orders.append(order)
                    self.pending_orders.remove(order)
                elif order_status == "CANCELLED":
                    self.logger.info(f"Pending order {order['order_id']} was cancelled. Removing from pending orders.")
                    self.pending_orders.remove(order)
                else:
                    self.logger.info(f"Pending order {order['order_id']} still pending. Status: {order_status}")
                    
        except Exception as e:
            self.logger.error(f"Error verifying pending orders: {e}\n{traceback.format_exc()}")

    def get_buy_orders_count(self) -> int:
        """Get count of buy orders from placed orders.
        
        Returns:
            int: Number of buy orders in placed_orders
        """
        try:
            if not self.placed_orders:
                return 2
            else:
                return int(self.placed_orders[0].get('quantity')) + 1
        except Exception as e:
            self.logger.error(f"Error counting buy orders: {e}\n{traceback.format_exc()}")
            return 0

    def move_to_history(self, sell_order: Dict[str, Any]) -> None:
        """Move orders to history after a sell, preserving the first share price order.
        
        Args:
            sell_order: The sell order that triggered the history move
        """
        try:
            # First, add the sell order to history
            self.history.append(sell_order)
            self.logger.info(f"Added sell order {sell_order.get('order_id')} to history")
            
            # Find the order with first_share_price
            first_share_order = None
            for order in self.placed_orders:
                if abs(order.get('price', 0) - self.first_share_price) < 1e-10:  # Using small epsilon for float comparison
                    first_share_order = order
                    break
            
            # Move all orders except first_share_order to history
            orders_to_move = []
            for order in self.placed_orders:
                if order != first_share_order:
                    orders_to_move.append(order)
                    self.history.append(order)
                    self.logger.info(f"Added buy order {order.get('order_id')} to history")
            
            # Remove moved orders from placed_orders
            for order in orders_to_move:
                self.placed_orders.remove(order)
            
            # Keep only the first_share_order in placed_orders
            if first_share_order:
                self.placed_orders = [first_share_order]
                self.logger.info(f"Kept first share order {first_share_order.get('order_id')} in placed orders")
            else:
                self.placed_orders = []
                self.logger.info("No first share order found, cleared placed orders")
            
            # Remove the sell order from pending orders if present
            if sell_order in self.pending_orders:
                self.pending_orders.remove(sell_order)
                self.logger.info(f"Removed sell order {sell_order.get('order_id')} from pending orders")
                
        except Exception as e:
            self.logger.error(f"Error moving orders to history: {e}\n{traceback.format_exc()}")
            raise
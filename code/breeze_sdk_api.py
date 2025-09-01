"""
Breeze API SDK for Trading Operations

This module provides a Python interface to the ICICI Direct Breeze API for:
- Live market data streaming
- Order placement (buy/sell)
- Historical data retrieval
- Portfolio management

The SDK handles authentication, session management, and provides high-level
abstractions for common trading operations.
"""
import breeze_connect
from breeze_connect import BreezeConnect
from datetime import datetime, timedelta, timezone
import urllib
import sys
import time
import logging
from typing import Dict, List, Optional, Any, Union, Generator
import os
import yaml
import traceback
from kite_utils import setup_logger, load_config


class BreezeApi:
    """ICICI Direct Breeze API wrapper class.
    
    This class provides a high-level interface to the Breeze API for trading operations.
    It handles authentication, session management, and provides methods for:
    - Live market data streaming
    - Order placement
    - Historical data retrieval
    - Portfolio management
    
    Attributes:
        session_token: API session token
        app_key: API application key
        secret_key: API secret key
        symbol: Default stock symbol
    """
    
    session_token: str = 'None'

    @staticmethod
    def print_config_instructions():
        """Print instructions for configuring Breeze API"""
        print("\n--- BREEZE API CONFIGURATION INSTRUCTIONS ---")
        print("1. Open your config/config.yaml file.")
        print("2. Under 'breeze_api', ensure you have the correct values for:")
        print("   - api_token: Your ICICI Direct Breeze API token")
        print("   - secret_token: Your ICICI Direct Breeze API secret")
        print("   - session_id: Your current session ID (expires daily)")
        print("3. If your session_id is missing or expired:")
        print("   a. Remove or comment out the 'session_id' line in config.yaml.")
        print("   b. Run this script again. It will print a login URL.")
        print("   c. Open the URL, log in to your ICICI Direct account.")
        print("   d. Copy the session token from the response.")
        print("   e. Update the session_id in config.yaml.")
        print("4. For more help, see: https://api.icicidirect.com/breezeapi/")
        print("--------------------------------------\n")

    def __init__(self, symbol: str):
        """
        Initialize Breeze API
        
        Parameters:
        - symbol: Trading symbol (e.g., "ITC")
        """
        self.symbol = symbol
        self.logger = setup_logger(__name__, symbol)
        self.breeze = None
        
        # Load configuration
        try:
            self.config = load_config()
            breeze_config = self.config.get('breeze_api', {})
            # Validate required Breeze configuration
            required_params = ['api_token', 'secret_token', 'session_id']
            missing_params = [param for param in required_params if param not in breeze_config]
            
            if missing_params:
                error_msg = f"Missing required Breeze API parameters: {', '.join(missing_params)}"
                self.logger.error(error_msg)
                self.print_config_instructions()
                raise ValueError(error_msg)
            
            # Store credentials
            self.app_key = breeze_config[required_params[0]]
            self.secret_key = breeze_config[required_params[1]]
            self.session_token = breeze_config[required_params[2]]
            
            # Initialize Breeze API
            # self.initiate_api()
            
        except Exception as e:
            self.logger.error(f"Error initializing Breeze API: {e}\n{traceback.format_exc()}")
            raise

    def start_api(self) -> None:
        """Initialize API connection."""
        self.initiate_api()

    def set_app_key(self, app_key: str) -> None:
        """Set API application key.
        
        Args:
            app_key: API application key
        """
        self.app_key = app_key
    
    def get_company_token(self, token: str) -> Dict[str, Any]:
        """Get company token for a stock symbol.
        
        Args:
            token: Stock symbol
            
        Returns:
            Dictionary containing company token information
        """
        return self.breeze.get_names(exchange_code='NSE', stock_code=token)

    def set_secret_key(self, secret: str) -> None:
        """Set API secret key.
        
        Args:
            secret: API secret key
        """
        self.secret_key = secret

    def get_session_token(self, token: Optional[str] = None) -> None:
        """Get new session token from API.
        
        Args:
            token: Optional existing token
        """
        try:
            if token:
                self.session_token = token
                self.initiate_api()
                return

            # Construct the exact login URL
            login_url = f"https://api.icicidirect.com/apiuser/login?api_key={urllib.parse.quote_plus(self.app_key)}"
            print("\n" + "="*80)
            print("TOKEN RENEWAL INSTRUCTIONS")
            print("="*80)
            print(f"1. Click or copy this URL: {login_url}")
            print("2. Login with your ICICI Direct credentials")
            print("3. After login, you'll be redirected to a URL that looks like:")
            print(f"   https://api.icicidirect.com/apiuser/login?api_key={self.app_key}&request_token={self.session_token}")
            print("4. Copy the request_token value from the URL")
            print("="*80 + "\n")
            
            # Get the request token from user
            request_token = input("Enter the request token from the redirect URL: ").strip()
            if not request_token:
                raise ValueError("Request token is required")
            
            # Generate new session
            self.breeze = BreezeConnect(api_key=self.app_key)
            data = self.breeze.generate_session(
                api_secret=self.secret_key,
                session_token=request_token
            )
            
            # Update session token
            self.session_token = data.get('session_token')
            if not self.session_token:
                raise ValueError("Failed to get session token from response")
            
            # Read existing config file
            with open('config/config.yaml', 'r') as f:
                existing_config = yaml.safe_load(f)
            
            # Update only the session_id in breeze_api section
            if 'breeze_api' not in existing_config:
                existing_config['breeze_api'] = {}
            existing_config['breeze_api']['session_id'] = self.session_token
            
            # Save updated config while preserving other sections
            with open('config/config.yaml', 'w') as f:
                yaml.dump(existing_config, f, default_flow_style=False)
            
            print("\nSuccessfully generated new session token and updated config!")
            print("You can now continue with your trading operations.\n")
            
        except Exception as e:
            self.logger.error(f"Error getting session token: {e}\n{traceback.format_exc()}")
            raise

    def set_session_token(self, token: Optional[str] = None) -> None:
        """Set session token.
        
        Args:
            token: Session token to set
        """
        self.session_token = token
        self.logger.info("Session token updated")
        self.breeze = None  # Reset breeze instance
        self.initiate_api()  # Reinitialize with new token

    def initiate_api(self) -> None:
        """Initialize API connection and generate session."""
        try:
            self.breeze = BreezeConnect(api_key=self.app_key)
            self.breeze.generate_session(
                api_secret=self.secret_key,
                session_token=self.session_token
            )
            self.logger.info("Successfully initialized Breeze API with credentials")
        except Exception as err:
            error_msg = str(err)
            print(f"error_msg = {error_msg}")
            if 'SESSIONKEY_INCORRECT' in error_msg or 'Could not authenticate credentials' in error_msg or 'Request token is required' in error_msg or 'Unable to retrieve customer details at the moment' in error_msg or 'Session key is expired' in error_msg:
                self.logger.warning("Session expired or invalid, attempting to regenerate token")
                login_url = f"https://api.icicidirect.com/apiuser/login?api_key={urllib.parse.quote_plus(self.app_key)}"
                self.logger.info(f"login_url = {login_url}")
                print("\n" + "="*80)
                print("TOKEN RENEWAL INSTRUCTIONS")
                print("="*80)
                print("Your session has expired. Please follow these steps:")
                print("1. Visit the login URL that will be shown below")
                print("2. Login with your ICICI Direct credentials")
                print("3. After login, you'll be redirected to a URL that looks like:")
                print(f'   login_url = f"https://api.icicidirect.com/apiuser/login?api_key={urllib.parse.quote_plus(self.app_key)}"')
                print("4. Copy the request_token value from the URL")
                print("="*80 + "\n")
                sys.exit(1)
                # self.get_session_token()
            else:
                self.logger.error(f"Error initializing API: {err}\n{traceback.format_exc()}")
                raise

    def get_customer_details(self) -> Dict[str, Any]:
        """Get customer account details.
        
        Returns:
            Dictionary containing customer details
        """
        return self.breeze.get_customer_details(api_session=self.config['breeze_api']['session_id'])
    
    def connect_socket(self) -> None:
        """Connect to WebSocket for live data streaming."""
        try:
            self.breeze.ws_connect()
            self.set_on_ticks(self.on_ticks)
            self.logger.info("Successfully connected to WebSocket")
        except Exception as e:
            self.logger.error(f"Error connecting to WebSocket: {e}\n{traceback.format_exc()}")
            raise

    def get_names(self, stock_id: str, exchange_code: str = "NSE") -> Dict[str, Any]:
        """Get stock details by symbol.
        
        Args:
            stock_id: Stock symbol
            exchange_code: Exchange code (default: NSE)
            
        Returns:
            Dictionary containing stock details
        """
        return self.breeze.get_names(exchange_code=exchange_code, stock_code=stock_id)

    def on_ticks(self, ticks: Dict[str, Any]) -> None:
        """Default tick handler for live data.
        
        Args:
            ticks: Dictionary containing tick data
        """
        try:
            self.logger.info(f"ticks = {ticks}")
            if self.on_ticks:
                for tick in ticks:
                    self.on_ticks(tick)
        except Exception as e:
            self.logger.error(f"Error processing ticks: {e}\n{traceback.format_exc()}")

    def set_on_ticks(self, function: callable) -> None:
        """Set custom tick handler function.
        
        Args:
            function: Callback function to handle ticks
        """
        self.logger.info(f"Setting on_ticks function: {function}")
        self.breeze.on_ticks = function

    def disconnect_socket(self) -> None:
        """Disconnect WebSocket connection."""
        try:
            if self.breeze:
                self.breeze.ws_disconnect()
                self.logger.info("Successfully disconnected from WebSocket")
        except Exception as e:
            self.logger.error(f"Error disconnecting from WebSocket: {e}\n{traceback.format_exc()}")
            raise

    def subscribe_to_stock_feed(self, stock_token: str) -> None:
        """Subscribe to stock feed for live data.
        
        Args:
            stock_token: Stock token to subscribe to
        """
        try:
            self.breeze.subscribe_feeds(stock_token)
            self.logger.info(f"Successfully subscribed to feed for token: {stock_token}")
        except Exception as e:
            self.logger.error(f"Error subscribing to feed: {e}\n{traceback.format_exc()}")
            raise

    def subscribe_feed_token(self, stock_token: str) -> None:
        """Subscribe to specific stock token feed.
        
        Args:
            stock_token: Stock token to subscribe to
        """
        try:
            self.breeze.subscribe_feeds(
                stock_token=stock_token, 
                exchange_code='NSE',
                product_type=''
            )
            self.logger.info(f"Successfully subscribed to OHLC feed for token: {stock_token}")
        except Exception as e:
            self.logger.error(f"Error subscribing to feed: {e}\n{traceback.format_exc()}")
            raise

    def unsubscribe_feed(self, stock_token: str) -> None:
        """Unsubscribe from stock feed.
        
        Args:
            stock_token: Stock token to unsubscribe from
        """
        try:
            self.breeze.unsubscribe_feeds(stock_token=stock_token)
            self.logger.info(f"Successfully unsubscribed from feed for token: {stock_token}")
        except Exception as e:
            self.logger.error(f"Error unsubscribing from feed: {e}\n{traceback.format_exc()}")
            raise

    def get_names(self, stock_id: str, exchange_code: str = "NSE") -> Dict[str, Any]:
        """Get stock details by symbol.
        
        Args:
            stock_id: Stock symbol
            exchange_code: Exchange code (default: NSE)
            
        Returns:
            Dictionary containing stock details
        """
        return self.breeze.get_names(exchange_code=exchange_code, stock_code=stock_id)

    def get_icici_token_name(self, stock_code: str, exchange_code: str = "NSE") -> str:
        """Get ICICI token name for stock.
        
        Args:
            stock_code: Stock symbol
            
        Returns:
            ICICI token name
        """
        try:
            # Get token from Breeze API
            token = self.breeze.get_names(stock_code=stock_code, exchange_code="NSE")
            self.logger.info(f"token = {token}")
            if token:
                token = token['isec_token_level1']
            else:
                raise ValueError(f"No token found for {stock_code} in {exchange_code}")
            self.logger.info(f"Got token name for {stock_code}: {token}")
            return token
            
        except Exception as e:
            self.logger.error(f"Error getting token name: {e}\n{traceback.format_exc()}")
            raise
    
    def get_holdings_info(self, stock_id: str) -> Optional[int]:
        """Get current holdings information.
        
        Args:
            stock_id: Stock symbol
            
        Returns:
            Number of shares held or None if not found
        """
        info = self.breeze.get_portfolio_holdings(
            exchange_code="NSE",
            stock_code="", 
            portfolio_type=""
        )
        if "Success" in info:
            for stock_info in info['Success']:
                if stock_id.upper() == stock_info['stock_code']:
                    return stock_info['quantity']
        return None

    def get_funds_available(self) -> Optional[float]:
        """Get available funds in account.
        
        Returns:
            Available funds amount or None if not available
        """
        resp = self.breeze.get_funds()
        if 'Success' in resp:
            return resp['Success']['allocated_equity']
        print(resp)
        return None

    def sell_stocks(self, stock_id: str, limit_price: float, qty: int, 
                   settlement_id: Optional[str] = None, order_segment_code: Optional[str] = None) -> Dict[str, Any]:
        """Place a sell order for stocks.
        
        Args:
            stock_id: Stock symbol to sell
            limit_price: Limit price for the sell order
            qty: Quantity of shares to sell
            settlement_id: Optional settlement ID for the order
            order_segment_code: Optional segment code for the order
            
        Returns:
            Dictionary containing order details or error information
        """
        try:
            self.logger.info(f"Placing sell order for {qty} shares of {stock_id} @ {limit_price}")
            order_details = self.breeze.place_order(
                stock_code=stock_id,
                exchange_code="NSE",
                product="cash",
                action="sell",
                order_type="limit",
                stoploss="",
                quantity=qty,
                price=limit_price,
                validity="day",
                settlement_id=settlement_id,
                order_segment_code=order_segment_code
            )
            self.logger.info(f"Sell order placed successfully: {order_details}")
            return order_details
        except Exception as e:
            self.logger.error(f"Error placing sell order: {str(e)}")
            return {'error': str(e)}

    def buy_stocks(self, stock_id: str, limit_price: float, qty: int) -> Optional[Dict[str, Any]]:
        """Place buy order.
        
        Args:
            stock_id: Stock symbol
            limit_price: Limit price for order
            qty: Quantity to buy
            
        Returns:
            Order response or None if failed
        """
        resp = self.breeze.place_order(
            stock_code=stock_id,
            exchange_code="NSE",
            product="cash",
            action="buy",
            order_type="limit",
            stoploss="",
            quantity=qty,
            price=limit_price,
            validity="day"
        )
        if resp['Status'] != 200:
            self.logger.error(f"error = {resp['Error']}")
        if resp['Status'] == 200:
            self.logger.info(f"resp = {resp['Success']}")
            return resp['Success']
        return None

    def get_order_details(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get order details.
        
        Args:
            order_id: Order ID
        """
        order_id = '20250521T300031648'
        return self.breeze.get_trade_detail(order_id=order_id, exchange_code="NSE")

    def convert_to_icic_date_format(self, date: str) -> Optional[str]:
        """Convert date to ICICI API format.
        
        Args:
            date: Date string in dd/mm/yyyy format
            
        Returns:
            Formatted date string or None if invalid
        """
        try:
            date_obj = datetime.strptime(date, "%d/%m/%Y")
            date_obj = date_obj.replace(tzinfo=timezone.utc)
            iso_date_str = date_obj.isoformat().replace("+00:00", ".000Z")
            return iso_date_str
        except ValueError:
            print(f"Invalid date format: {date}. Expected dd/mm/yyyy.")
            return None
        
    def get_date_obj(self, date: str) -> datetime:
        """Convert date string to datetime object.
        
        Args:
            date: Date string in dd/mm/yyyy format
            
        Returns:
            datetime object
        """
        return datetime.strptime(date, "%d/%m/%Y")
    
    def iterate_dates(self, start_date: datetime, end_date: datetime) -> Generator[datetime, None, None]:
        """Generate dates between start and end date.
        
        Args:
            start_date: Start date
            end_date: End date
            
        Yields:
            datetime objects for each date in range
        """
        cur_date = start_date
        while cur_date < end_date:  # api does not take same date for from date and to date
            yield cur_date
            cur_date += timedelta(days=1)

    def get_historical_one_min_data(self, start_date: str, end_date: str, 
                                  stock_code: str, 
                                  exchange_code: str = "NSE") -> List[Dict[str, Any]]:
        """Get historical one-minute data.
        
        Args:
            date1: Start date in dd/mm/yyyy format
            date2: End date in dd/mm/yyyy format
            stock_code: Stock symbol
            exchange_code: Exchange code (default: NSE)
            
        Returns:
            List of historical data points
        """
        hist_data = []
        print(f"code = {stock_code}")
        for cur_date in self.iterate_dates(self.get_date_obj(start_date), self.get_date_obj(end_date)):
            end_date = cur_date + timedelta(days=1)
            
            # print(f"cur date = {cur_date.isoformat()}")  # Uncomment for debugging
            # print(f"end date = {end_date.isoformat()}")  # Uncomment for debugging
            data = self.breeze.get_historical_data_v2(
                interval="1day",
                from_date=cur_date,
                to_date=end_date,
                stock_code=stock_code,
                exchange_code=exchange_code,
                product_type="cash"
            )
            # print(f"data = {data}")  # Uncomment for debugging
            if data['Status'] == 200:
                hist_data.extend(data['Success'])
            elif data['Status'] == 429:
                time.sleep(1)
            else:
                print(f"unexpected response, please check!")
                time.sleep(1)

        return hist_data

    def _load_config(self) -> Optional[Dict[str, Any]]:
        """Load configuration from YAML file.
        
        Returns:
            Dict containing configuration or None if loading fails
        """
        config_path = r"C:\Users\pkudithi\OneDrive - NVIDIA Corporation\Documents\GitHub\AlogTrading\real_live_invest\configs\fall_buy_global.yaml"
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.logger.error(f"Error loading config: {str(e)}")
            return None

    def get_order_list(self, 
                      exchange_code: str = "NSE",
                      from_date: str = None,
                      to_date: str = None) -> Dict[str, Any]:
        """Get list of orders for a given date range.
        
        Args:
            exchange_code: Exchange code (NSE/NFO)
            from_date: Start date in ISO format (YYYY-MM-DDTHH:MM:SS.000Z)
            to_date: End date in ISO format (YYYY-MM-DDTHH:MM:SS.000Z)
            
        Returns:
            Dict containing order list information
        """
        try:
            if not from_date:
                from_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000Z")
            if not to_date:
                to_date = from_date
                
            return self.breeze.get_order_list(
                exchange_code=exchange_code,
                from_date=from_date,
                to_date=to_date
            )
        except Exception as e:
            self.logger.error(f"Failed to get order list: {str(e)}")
            raise

    def gtt_single_leg_place_order(self,
                                 exchange_code: str = "NSE",
                                 stock_code: str = "",
                                 product: str = "Cash",
                                 quantity: str = "0",
                                 expiry_date: str = None,
                                 right: str = "call",
                                 strike_price: str = "24000",
                                 gtt_type: str = "single",
                                 index_or_stock: str = "index",
                                 trade_date: str = None,
                                 order_details: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """Place a GTT (Good Till Triggered) single leg order.
        
        Args:
            exchange_code: Exchange code (NFO/NSE)
            stock_code: Stock symbol
            product: Product type (options/futures/cash)
            quantity: Number of shares/contracts
            expiry_date: Expiry date in ISO format
            right: Option right (call/put)
            strike_price: Strike price
            gtt_type: GTT order type (single/cover_oco)
            index_or_stock: Type of instrument (index/stock)
            trade_date: Trade date in ISO format
            order_details: List of order details containing action, limit_price, and trigger_price
            
        Returns:
            Dict containing order response
        """
        try:
            if not expiry_date:
                expiry_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.00Z")
            if not trade_date:
                trade_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.00Z")
            if not order_details:
                order_details = [{
                    "action": "buy",
                    "limit_price": "0",
                    "trigger_price": "0"
                }]
                
            return self.breeze.gtt_single_leg_place_order(
                exchange_code=exchange_code,
                stock_code=stock_code,
                product=product,
                quantity=quantity,
                expiry_date=expiry_date,
                right=right,
                strike_price=strike_price,
                gtt_type=gtt_type,
                index_or_stock=index_or_stock,
                trade_date=trade_date,
                order_details=order_details
            )
        except Exception as e:
            self.logger.error(f"Failed to place GTT single leg order: {str(e)}")
            raise
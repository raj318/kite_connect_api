import logging
import sys
import time
import traceback
import json
import os
import threading
from datetime import datetime, time as dt_time
import pytz
from typing import Dict, Any, Optional, List
from kite_utils import setup_logger, load_config
from breeze_sdk_api import BreezeApi
from kite_connect_api import KiteConnectAPI
import pandas as pd


def is_market_hours() -> bool:
    """Check if current time is within Indian market hours (9:15 AM to 3:30 PM IST)"""
    try:
        # Get current time in IST
        ist = pytz.timezone('Asia/Kolkata')
        current_time = datetime.now(ist).time()
        
        # Define market hours
        market_start = dt_time(9, 15)  # 9:15 AM
        market_end = dt_time(15, 30)   # 3:30 PM
        
        return market_start <= current_time <= market_end
    except Exception as e:
        logging.error(f"Error checking market hours: {e}")
        return False


def save_gtt_history(company_name: str, gtt_orders: List[Dict[str, Any]], logger: logging.Logger) -> None:
    """
    Save GTT order history to JSON file
    
    Parameters:
    - company_name: Name of the company
    - gtt_orders: List of GTT order details
    - logger: Logger instance
    """
    try:
        # Create orders directory if it doesn't exist
        orders_dir = os.path.join('workdir', 'orders')
        os.makedirs(orders_dir, exist_ok=True)
        
        # Prepare history data
        history_data = {
            'company_name': company_name,
            'last_updated': datetime.now().isoformat(),
            'gtt_orders': gtt_orders,
            'total_orders': len(gtt_orders)
        }
        
        # Save to JSON file
        file_path = os.path.join(orders_dir, f'{company_name}_gtt_history.json')
        
        with open(file_path, 'w') as f:
            json.dump(history_data, f, indent=4)
        
        logger.info(f"GTT history saved: {len(gtt_orders)} orders")
        
    except Exception as e:
        logger.error(f"Error saving GTT history: {e}")


def load_gtt_history(company_name: str, logger: logging.Logger) -> List[Dict[str, Any]]:
    """
    Load GTT order history from JSON file
    
    Parameters:
    - company_name: Name of the company
    - logger: Logger instance
    
    Returns:
    - List of GTT order details or empty list if file doesn't exist
    """
    try:
        file_path = os.path.join('workdir', 'orders', f'{company_name}_gtt_history.json')
        if os.path.exists(file_path):
            # Check if file is empty
            if os.path.getsize(file_path) == 0:
                logger.info(f"GTT history file is empty: {file_path}")
                return []
            
            try:
                with open(file_path, 'r') as f:
                    history_data = json.load(f)
                
                # Validate that history_data is a dictionary
                if not isinstance(history_data, dict):
                    logger.warning(f"Invalid GTT history format in {file_path}")
                    return []
                
                gtt_orders = history_data.get('gtt_orders', [])
                
                # Validate that gtt_orders is a list
                if not isinstance(gtt_orders, list):
                    logger.warning(f"Invalid gtt_orders format in {file_path}")
                    return []
                
                logger.info(f"Loaded GTT history: {len(gtt_orders)} orders")
                return gtt_orders
                
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in GTT history file: {e}")
                return []
            except Exception as e:
                logger.error(f"Error reading GTT history file: {e}")
                return []
        else:
            logger.info(f"No GTT history file found. Starting fresh.")
            return []
            
    except Exception as e:
        logger.error(f"Error loading GTT history: {e}")
        return []


def cancel_all_gtt_orders(kite_api: KiteConnectAPI, company_name: str, logger: logging.Logger) -> int:
    """
    Cancel all ACTIVE GTT orders for the specified company
    
    Note: This function only cancels GTT orders that are still waiting to be triggered.
    Once a GTT order is triggered and becomes a regular order, it cannot be cancelled
    through this function.
    
    Parameters:
    - kite_api: Initialized Kite API instance
    - company_name: Company name
    - logger: Logger instance
    
    Returns:
    - int: Number of orders cancelled
    """
    try:
        logger.info("Attempting to cancel all ACTIVE GTT orders...")
        logger.info("Note: Only GTT orders waiting to be triggered will be cancelled.")
        logger.info("Triggered orders that have become regular orders will not be affected.")
        
        # Get current GTT orders
        current_gtt_orders = kite_api.get_gtt_orders()
        logger.info(f"Found {len(current_gtt_orders)} GTT orders to check")
        
        cancelled_count = 0
        skipped_count = 0
        
        for order in current_gtt_orders:
            try:
                trigger_id = order.get('id')  # Use 'id' instead of 'trigger_id'
                trading_symbol = order.get('condition', {}).get('tradingsymbol', '')
                transaction_type = order.get('orders', [{}])[0].get('transaction_type', '')
                status = order.get('status', 'UNKNOWN')
                
                # Only cancel orders for the specified company
                if trading_symbol.upper() == company_name.upper():
                    logger.info(f"Found GTT order: {trigger_id} ({transaction_type} {trading_symbol}) - Status: {status}")
                    
                    # Check if order is still active (not triggered)
                    if status.upper() in ['ACTIVE', 'PENDING', 'OPEN']:
                        logger.info(f"Cancelling ACTIVE GTT order: {trigger_id} ({transaction_type} {trading_symbol})")
                        
                        # Cancel the GTT order
                        success = kite_api.delete_gtt_order(trigger_id)
                        
                        if success:
                            cancelled_count += 1
                            logger.info(f"Successfully cancelled GTT order: {trigger_id}")
                        else:
                            logger.error(f"Failed to cancel GTT order: {trigger_id}")
                    else:
                        logger.info(f"Skipping GTT order {trigger_id} - Status: {status} (order may have been triggered)")
                        skipped_count += 1
                else:
                    logger.info(f"Skipping GTT order for different company: {trading_symbol}")
                    
            except Exception as e:
                logger.error(f"Error cancelling GTT order {order.get('id', 'unknown')}: {e}")
        
        logger.info(f"GTT Order Cancellation Summary:")
        logger.info(f"  - Total orders found: {len(current_gtt_orders)}")
        logger.info(f"  - Orders cancelled: {cancelled_count}")
        logger.info(f"  - Orders skipped (different company/status): {skipped_count}")
        logger.info(f"  - Note: Triggered orders are not affected by this cancellation")
        
        return cancelled_count
        
    except Exception as e:
        logger.error(f"Error in cancel_all_gtt_orders: {e}\n{traceback.format_exc()}")
        return 0


def get_current_price(breeze_api: BreezeApi, trading_symbol: str) -> Optional[float]:
    """
    Get current price or last traded price from Breeze API quotes
    
    Parameters:
    - breeze_api: Initialized Breeze API instance
    - trading_symbol: Trading symbol of the stock
    
    Returns:
    - float: Last traded price or None if error
    """
    try:
        # Get stock token for Breeze API
        stock_token = breeze_api.get_icici_token_name(trading_symbol)
        
        # Get ICICI stock code using breeze.get_names()
        try:
            stock_names = breeze_api.breeze.get_names(stock_code=trading_symbol, exchange_code="NSE")
            
            if stock_names:
                icici_stock_code = stock_names['isec_stock_code']
            else:
                logging.error(f"Could not get ICICI stock code for {trading_symbol}")
                return None
                
        except Exception as e:
            logging.error(f"Error getting ICICI stock code for {trading_symbol}: {e}")
            return None
        
        # Get quotes for the stock using ICICI stock code
        quotes = breeze_api.breeze.get_quotes(
            stock_code=icici_stock_code,  # Use ICICI stock code instead of regular symbol
            exchange_code="NSE",
            product_type="cash"
        )
        
        if quotes and 'Success' in quotes:
            quote_data = quotes['Success']
            
            if quote_data and len(quote_data) > 0:
                last_traded_price = quote_data[0].get('ltp')
                
                if last_traded_price:
                    logging.info(f"Current price for {trading_symbol}: {last_traded_price}")
                    return float(last_traded_price)
                else:
                    logging.error(f"Could not find last traded price in quotes for {trading_symbol}")
                    return None
            else:
                logging.error(f"Empty quote data for {trading_symbol}")
                return None
        else:
            logging.error(f"No quotes data found for {trading_symbol}")
            return None
            
    except Exception as e:
        logging.error(f"Error getting current price for {trading_symbol}: {e}\n{traceback.format_exc()}")
        return None


def place_gtt_order(kite_api: KiteConnectAPI, trading_symbol: str, exchange: str, 
                   transaction_type: str, quantity: int, price: float, 
                   trigger_price: float, current_price: float) -> Optional[str]:
    """
    Place a GTT order using Kite API
    
    Parameters:
    - kite_api: Initialized Kite API instance
    - trading_symbol: Trading symbol of the stock
    - exchange: Exchange name
    - transaction_type: "BUY" or "SELL"
    - quantity: Number of shares to trade
    - price: Order price
    - trigger_price: Price at which the order should be triggered
    - current_price: Current price of the stock
    
    Returns:
    - str: GTT order ID or None if error
    """
    try:
        gtt_order_id = kite_api.place_gtt_order(
            trading_symbol=trading_symbol,
            exchange=exchange,
            transaction_type=transaction_type,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            order_type="LIMIT",
            validity="DAY",
            current_price=current_price
        )
        
        logging.info(f"GTT order placed successfully. Order ID: {gtt_order_id}")
        logging.info(f"Details: {trading_symbol} {transaction_type} {quantity} shares @ {price} (trigger: {trigger_price})")
        
        return gtt_order_id
        
    except Exception as e:
        logging.error(f"Error placing GTT order: {e}\n{traceback.format_exc()}")
        return None


def calculate_total_shares_and_avg_price(gtt_orders: List[Dict[str, Any]]) -> tuple:
    """
    Calculate total shares and average price from executed buy orders
    
    Parameters:
    - gtt_orders: List of GTT order details
    
    Returns:
    - tuple: (total_shares, average_price)
    """
    total_shares = 0
    total_value = 0
    
    for order in gtt_orders:
        # Check for both 'COMPLETE' and 'TRIGGERED' statuses as these indicate executed orders
        if (order.get('transaction_type') == 'BUY' and 
            order.get('status') in ['COMPLETE', 'TRIGGERED', 'FILLED']):
            quantity = order.get('quantity', 0)
            price = order.get('price', 0)
            total_shares += quantity
            total_value += quantity * price
        else:
            # Skip non-executed orders silently
            pass
    
    average_price = total_value / total_shares if total_shares > 0 else 0
    return total_shares, average_price


def update_gtt_order_statuses(kite_api: KiteConnectAPI, company_name: str, stock_exchange: str, 
                             gtt_orders: List[Dict[str, Any]], logger: logging.Logger) -> tuple:
    """
    Update GTT order statuses by checking current orders from the API
    and comparing with the history file. This function prioritizes the API.
    
    Parameters:
    - kite_api: Initialized Kite API instance
    - company_name: Name of the company
    - stock_exchange: Stock exchange
    - gtt_orders: List of GTT orders from history file
    - logger: Logger instance
    
    Returns:
    - tuple: (updated_orders, triggered_orders_detected, total_shares, avg_price)
    """
    try:
        logger.info("=== Updating GTT order statuses from API ===")
        
        # Get current GTT orders from API
        try:
            current_gtt_orders = kite_api.get_gtt_orders()
            logger.info(f"Retrieved {len(current_gtt_orders)} current GTT orders from API")
        except Exception as e:
            logger.error(f"Error getting current GTT orders: {e}")
            return gtt_orders, False, 0, 0
        
        # Create a mapping of order ID to order details for quick lookup
        current_order_map = {}
        company_orders_found = 0
        
        for order in current_gtt_orders:
            trading_symbol = order.get('condition', {}).get('tradingsymbol', '')
            if trading_symbol.upper() == company_name.upper():
                order_id = order.get('id')
                if order_id:
                    current_order_map[str(order_id)] = order
                    company_orders_found += 1
                    status = order.get('status', 'UNKNOWN')
                    transaction_type = order.get('orders', [{}])[0].get('transaction_type', 'UNKNOWN')
                    logger.info(f"Found {company_name} order in API: ID={order_id}, Type={transaction_type}, Status={status}")
        
        logger.info(f"Found {company_orders_found} {company_name} orders in API")
        
        # Update history file orders based on current API status
        updated_orders = []
        triggered_orders_detected = []
        history_updated = False
        
        for order in gtt_orders:
            trigger_id = order.get('trigger_id')
            current_status = order.get('status', 'UNKNOWN')
            trading_symbol = order.get('trading_symbol', '')
            
            # Only process orders for our target company
            if trading_symbol.upper() != company_name.upper():
                updated_orders.append(order)
                continue
            
            # Convert trigger_id to string for consistent comparison
            trigger_id_str = str(trigger_id) if trigger_id else None
            
            if trigger_id_str and trigger_id_str in current_order_map:
                # Order found in current API - update status
                api_order = current_order_map[trigger_id_str]
                api_status = api_order.get('status', 'UNKNOWN')
                transaction_type = order.get('transaction_type', 'UNKNOWN')
                
                logger.info(f"Order {trigger_id} current status: {current_status} -> API status: {api_status}")
                
                # Handle different API statuses
                if api_status.upper() == 'TRIGGERED':
                    if current_status not in ['COMPLETE', 'TRIGGERED']:
                        logger.info(f"ORDER TRIGGERED: {trigger_id} ({trading_symbol} {transaction_type} {order.get('quantity')} shares @ {order.get('price')})")
                        logger.info(f"Status: {api_status} - Order was triggered and is being processed")
                        order['status'] = 'TRIGGERED'
                        order['triggered_at'] = datetime.now().isoformat()
                        triggered_orders_detected.append(order)
                        history_updated = True
                    else:
                        logger.debug(f"Order {trigger_id} already marked as triggered/completed")
                
                elif api_status.upper() in ['COMPLETE', 'FILLED']:
                    if current_status not in ['COMPLETE', 'FILLED']:
                        logger.info(f"ORDER EXECUTED: {trigger_id} ({trading_symbol} {transaction_type} {order.get('quantity')} shares @ {order.get('price')})")
                        logger.info(f"Status: {api_status} - Order was successfully filled")
                        order['status'] = 'COMPLETE'
                        order['triggered_at'] = datetime.now().isoformat()
                        triggered_orders_detected.append(order)
                        history_updated = True
                    else:
                        logger.debug(f"Order {trigger_id} already marked as completed")
                
                elif api_status.upper() in ['CANCELLED', 'REJECTED', 'FAILED']:
                    if current_status not in ['CANCELLED', 'REJECTED', 'FAILED']:
                        logger.warning(f"ORDER FAILED: {trigger_id} ({trading_symbol} {transaction_type} {order.get('quantity')} shares @ {order.get('price')})")
                        logger.warning(f"Status: {api_status} - Order was triggered but failed to execute")
                        order['status'] = 'FAILED'
                        order['failed_at'] = datetime.now().isoformat()
                        order['failure_reason'] = f"API status: {api_status}"
                        history_updated = True
                    else:
                        logger.debug(f"Order {trigger_id} already marked as failed")
                
                elif api_status.upper() in ['ACTIVE', 'PENDING', 'OPEN']:
                    if current_status != api_status.upper():
                        logger.debug(f"Order {trigger_id} status updated: {current_status} -> {api_status}")
                        order['status'] = api_status.upper()
                        history_updated = True
                    else:
                        logger.debug(f"Order {trigger_id} still active with status: {api_status}")
                
                else:
                    logger.warning(f"Order {trigger_id} has unknown API status: {api_status}")
                    if current_status != api_status.upper():
                        order['status'] = api_status.upper()
                        history_updated = True
            
            else:
                # Order not found in current API
                if current_status in ['ACTIVE', 'PENDING', 'OPEN']:
                    logger.warning(f"Order {trigger_id} was active in history but not found in current API")
                    logger.warning(f"This could mean the order was triggered and removed from active orders")
                    # Don't automatically mark as complete - let the history-based detection handle this
                elif current_status in ['COMPLETE', 'TRIGGERED', 'FILLED']:
                    logger.debug(f"Order {trigger_id} already completed (not in current API)")
                else:
                    logger.debug(f"Order {trigger_id} with status {current_status} not found in current API")
            
            updated_orders.append(order)
        
        # Calculate total shares and average price from completed buy orders
        total_shares = 0
        total_value = 0
        
        for order in updated_orders:
            if (order.get('transaction_type') == 'BUY' and 
                order.get('status') in ['COMPLETE', 'TRIGGERED', 'FILLED'] and
                order.get('trading_symbol', '').upper() == company_name.upper()):
                quantity = order.get('quantity', 0)
                price = order.get('price', 0)
                total_shares += quantity
                total_value += quantity * price
                logger.info(f"EXECUTED ORDER: {order.get('trigger_id')} - {quantity} shares @ {price:.2f}")
        
        avg_price = total_value / total_shares if total_shares > 0 else 0
        
        # Save updated history if any orders were updated
        if history_updated:
            save_gtt_history(company_name, updated_orders, logger)
            logger.info(f"STATUS UPDATED: History file updated with {len(triggered_orders_detected)} triggered/updated orders")
        
        logger.info(f"SUMMARY: {len(triggered_orders_detected)} orders triggered/updated, {total_shares} total shares, avg price: {avg_price:.2f}")
        
        return updated_orders, len(triggered_orders_detected) > 0, total_shares, avg_price
        
    except Exception as e:
        logger.error(f"Error updating GTT order statuses: {e}")
        return gtt_orders, False, 0, 0


def get_instrument_master(kite_api: KiteConnectAPI, file_path: str = "instruments.csv") -> Optional[pd.DataFrame]:
    """
    Downloads the latest instrument master file from Zerodha if it doesn't exist
    or is too old, then loads it into a Pandas DataFrame.
    
    Parameters:
    - kite_api: Initialized Kite API instance
    - file_path: Path to save/load the instrument master file
    
    Returns:
    - pd.DataFrame: Instrument master data or None if error
    """
    try:
        # Check if file exists and is recent (e.g., less than a day old)
        if os.path.exists(file_path):
            mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            if (datetime.now() - mod_time).days < 1:
                logging.info(f"Using existing instrument master file: {file_path}")
                return pd.read_csv(file_path)
        
        logging.info("Downloading latest instrument master file...")
        instruments_data = kite_api.kite.instruments()
        df = pd.DataFrame(instruments_data)
        df.to_csv(file_path, index=False)
        logging.info(f"Instrument master file downloaded and saved to {file_path}")
        return df
    except Exception as e:
        logging.error(f"Error downloading instrument master file: {e}")
        logging.error("Could not download instrument master. Please ensure your access token is valid.")
        return None


def get_tick_size_from_instruments(df_instruments: pd.DataFrame, trading_symbol: str, exchange: str) -> float:
    """
    Retrieves the tick size for a given trading symbol and exchange
    from the instrument master DataFrame.
    
    Parameters:
    - df_instruments: Instrument master DataFrame
    - trading_symbol: Trading symbol of the stock
    - exchange: Exchange name (e.g., "NSE")
    
    Returns:
    - float: Tick size for the instrument
    """
    try:
        # Ensure exchange is a string for comparison
        exchange_str = exchange.replace('KITE_EXCHANGE_', '')  # e.g., converts 'KITE_EXCHANGE_NSE' to 'NSE'
        
        instrument_info = df_instruments[
            (df_instruments['tradingsymbol'] == trading_symbol) &
            (df_instruments['exchange'] == exchange_str)
        ]
        
        if not instrument_info.empty:
            tick_size = instrument_info.iloc[0]['tick_size']
            logging.info(f"Found tick size for {trading_symbol} on {exchange_str}: {tick_size}")
            return float(tick_size)
        else:
            logging.warning(f"Tick size not found for {trading_symbol} on {exchange_str}. Falling back to default 0.01.")
            return 0.01  # Default fallback for most NSE stocks
            
    except Exception as e:
        logging.error(f"Error getting tick size for {trading_symbol}: {e}")
        return 0.01  # Default fallback


def round_to_tick(price: float, tick_size: float) -> float:
    """
    Rounds a given price to the nearest multiple of the specified tick size.
    This is the improved version from Gemini AI with better precision handling.
    
    Parameters:
    - price: Original price to round
    - tick_size: Minimum price increment
    
    Returns:
    - float: Rounded price that's valid for order placement
    """
    try:
        if tick_size <= 0:
            raise ValueError("Tick size must be greater than zero.")
        
        # Convert to integer for precision, then back
        # Example: 289.57 / 0.05 = 5791.4 -> round(5791.4) = 5791 -> 5791 * 0.05 = 289.55
        # Example: 289.67 / 0.05 = 5793.4 -> round(5793.4) = 5793 -> 5793 * 0.05 = 289.65
        rounded_price = round(price / tick_size) * tick_size
        
        # Handle floating point inaccuracies: ensure it's represented correctly
        # Determine decimal places needed based on tick_size
        decimal_places = 0
        if '.' in str(tick_size):
            decimal_places = len(str(tick_size).split('.')[-1])
        
        return round(rounded_price, decimal_places)
        
    except Exception as e:
        logging.error(f"Error rounding price {price} with tick size {tick_size}: {e}")
        # Fallback: round to 2 decimal places
        return round(price, 2)


def calculate_gtt_prices(current_price: float, drop_percentage: float, tick_size: float, 
                        order_type: str = "BUY", price_delta_ticks: int = 2) -> tuple:
    """
    Calculate GTT trigger price and limit price based on current price and drop percentage.
    This incorporates the improved logic from Gemini AI.
    
    Parameters:
    - current_price: Current last traded price
    - drop_percentage: Percentage drop from current price (e.g., 1.0 for 1%)
    - tick_size: Tick size for the instrument
    - order_type: "BUY" or "SELL"
    - price_delta_ticks: Number of ticks difference between trigger and limit price
    
    Returns:
    - tuple: (trigger_price, limit_price)
    """
    try:
        # Calculate raw target price based on drop percentage
        target_price_raw = current_price * (1 - (drop_percentage / 100))
        
        # Round trigger price to valid tick size
        trigger_price = round_to_tick(target_price_raw, tick_size)
        
        # Calculate limit price with delta
        if order_type == "BUY":
            # For BUY orders: limit price slightly above trigger price
            limit_price_raw = trigger_price + (tick_size * price_delta_ticks)
        else:
            # For SELL orders: limit price slightly below trigger price
            limit_price_raw = trigger_price - (tick_size * price_delta_ticks)
        
        # Round limit price to valid tick size
        limit_price = round_to_tick(limit_price_raw, tick_size)
        
        logging.info(f"Price calculation for {order_type} order:")
        logging.info(f"  Current price: {current_price:.2f}")
        logging.info(f"  Drop percentage: {drop_percentage}%")
        logging.info(f"  Raw target price: {target_price_raw:.4f}")
        logging.info(f"  Rounded trigger price: {trigger_price:.2f}")
        logging.info(f"  Rounded limit price: {limit_price:.2f}")
        logging.info(f"  Tick size: {tick_size}")
        
        return trigger_price, limit_price
        
    except Exception as e:
        logging.error(f"Error calculating GTT prices: {e}")
        # Fallback calculation
        fallback_trigger = round(current_price * (1 - (drop_percentage / 100)), 2)
        fallback_limit = round(fallback_trigger, 2)
        return fallback_trigger, fallback_limit


def get_tick_size_for_stock(trading_symbol: str, current_price: float = None) -> float:
    """
    Get tick size for a given stock dynamically based on LTP or from instruments.csv
    
    Parameters:
    - trading_symbol: Stock symbol
    - current_price: Current price of the stock (optional, used for dynamic calculation)
    
    Returns:
    - float: Tick size for the stock
    """
    try:
        # First, try to get tick size from instruments.csv (most accurate)
        try:
            import pandas as pd
            import os
            
            # Check if instruments.csv exists
            instruments_file = "instruments.csv"
            if os.path.exists(instruments_file):
                # Read instruments.csv
                df = pd.read_csv(instruments_file)
                
                # Filter for the specific stock and NSE equity
                stock_data = df[
                    (df['tradingsymbol'] == trading_symbol.upper()) & 
                    (df['exchange'] == 'NSE') & 
                    (df['instrument_type'] == 'EQ')
                ]
                
                if not stock_data.empty:
                    tick_size = stock_data.iloc[0]['tick_size']
                    logging.info(f"Found tick size for {trading_symbol}: {tick_size} from instruments.csv")
                    return float(tick_size)
                else:
                    logging.warning(f"No tick size found for {trading_symbol} in instruments.csv. Using dynamic calculation.")
            else:
                logging.warning(f"Instruments file {instruments_file} not found. Using dynamic calculation.")
                
        except Exception as e:
            logging.error(f"Error reading instruments.csv: {e}. Using dynamic calculation.")
        
        # Fallback: If current_price is provided, calculate tick size dynamically based on NSE rules
        if current_price is not None and current_price > 0:
            # NSE tick size rules based on price range:
            # Below ₹250: ₹0.01
            # ₹250 to ₹1,000: ₹0.05
            # > ₹1,000 to ₹5,000: ₹0.10
            # > ₹5,000 to ₹10,000: ₹0.50
            # > ₹10,000 to ₹20,000: ₹1.00
            # > ₹20,000: ₹5.00
            
            if current_price < 250:
                return 0.01
            elif current_price <= 1000:
                return 0.05
            elif current_price <= 5000:
                return 0.10
            elif current_price <= 10000:
                return 0.50
            elif current_price <= 20000:
                return 1.00
            else:
                return 5.00
        
        # Final fallback: default tick size
        logging.warning(f"Using default tick size for {trading_symbol}: 0.01")
        return 0.01
            
    except Exception as e:
        logging.error(f"Error getting tick size for {trading_symbol}: {e}")
        return 0.01  # Default fallback


def is_similar_to_existing_orders(new_price: float, new_trigger_price: float, existing_orders: List[Dict[str, Any]], 
                                similarity_threshold: float = 0.012) -> bool:
    """
    Check if a new order price is too similar to existing orders
    Now checks both order price and trigger price to ensure proper spacing
    
    Parameters:
    - new_price: Price of the new order to check
    - new_trigger_price: Trigger price of the new order to check
    - existing_orders: List of existing GTT order details
    - similarity_threshold: Percentage threshold for similarity (default: 1.5%)
    
    Returns:
    - bool: True if price is similar to existing orders, False otherwise
    """
    try:
        if not existing_orders:
            return False  # No existing orders, so not similar
        
        for order in existing_orders:
            # Only check BUY orders that are still active
            if (order.get('orders', [{}])[0].get('transaction_type') == 'BUY' and 
                order.get('status', '').upper() == 'ACTIVE'):
                
                # Get price and trigger price from the nested orders structure
                existing_price = order.get('orders', [{}])[0].get('price', 0)
                existing_trigger_price = order.get('condition', {}).get('price', 0)
                
                if existing_price > 0:
                    # Check order price similarity
                    price_diff = abs(new_price - existing_price) / existing_price
                    if price_diff <= similarity_threshold:
                        logging.info(f"New order price {new_price:.2f} is similar to existing order price {existing_price:.2f} (diff: {price_diff*100:.2f}%)")
                        return True
                    
                    # Check trigger price similarity
                    if existing_trigger_price > 0:
                        trigger_diff = abs(new_trigger_price - existing_trigger_price) / existing_trigger_price
                        if trigger_diff <= similarity_threshold:
                            logging.info(f"New trigger price {new_trigger_price:.2f} is similar to existing trigger price {existing_trigger_price:.2f} (diff: {trigger_diff*100:.2f}%)")
                            return True
        
        logging.info(f"New order (price: {new_price:.2f}, trigger: {new_trigger_price:.2f}) is not similar to any existing orders")
        return False
        
    except Exception as e:
        logging.error(f"Error checking order similarity: {e}")
        return False  # Default to False to allow order placement


def check_and_update_sell_order_for_new_purchases(kite_api: KiteConnectAPI, company_name: str, stock_exchange: str, 
                                                 gtt_orders: List[Dict[str, Any]], logger: logging.Logger) -> bool:
    """
    Check for newly executed buy orders and update sell orders accordingly.
    This function is called from tick data handler to immediately update sell orders.
    
    Returns:
    - bool: True if a new purchase was detected and sell order was updated, False otherwise
    """
    try:
        # Get current GTT orders
        current_gtt_orders = kite_api.get_gtt_orders()
        
        # Update order statuses in our history before calculating shares
        updated_gtt_orders, triggered_detected, total_shares, avg_price = update_gtt_order_statuses(
            kite_api, company_name, stock_exchange, gtt_orders, logger
        )
        
        # Calculate total shares and average price from executed buy orders
        # total_shares, avg_price = calculate_total_shares_and_avg_price(updated_gtt_orders)
        
        logger.info(f"Checking for new purchases - Total shares: {total_shares}, Average price: {avg_price:.2f}")
        
        if total_shares > 0:
            # Get tick size for the stock using improved method
            tick_size = get_tick_size_for_stock(company_name, current_price)
            
            # Calculate dynamic profit target based on share count
            if total_shares <= 3:
                # 3% profit for ≤3 shares
                raw_profit_target = avg_price * 1.03
                profit_percentage = 3
            else:
                # 2% profit for >3 shares
                raw_profit_target = avg_price * 1.02
                profit_percentage = 2
            
            profit_target = round_to_tick(raw_profit_target, tick_size)
            sell_price = profit_target  # Sell at dynamic profit target
            
            logger.info(f"New purchase detected - Total shares: {total_shares}, Avg price: {avg_price:.2f}, New sell price: {raw_profit_target:.4f} → {sell_price:.2f} ({profit_percentage}% profit)")
            
            # Find existing sell order
            existing_sell_order = None
            for sell_order in current_gtt_orders:
                if sell_order.get('orders', [{}])[0].get('transaction_type') == 'SELL':
                    existing_sell_order = sell_order
                    break
            
            # Update or place sell order
            if existing_sell_order:
                try:
                    logger.info(f"Updating sell order for new purchase - Quantity: {existing_sell_order.get('quantity')}→{total_shares}, Price: {existing_sell_order.get('price'):.2f}→{sell_price:.2f}")
                    kite_api.modify_gtt_order(
                        gtt_order_id=existing_sell_order.get('trigger_id'),
                        trading_symbol=company_name,
                        exchange=stock_exchange,
                        transaction_type="SELL",
                        quantity=total_shares,
                        price=sell_price,
                        trigger_price=calculate_gtt_prices(sell_price, 1.2, tick_size, "SELL", 1)[0]
                    )
                    logger.info("Sell order updated for new purchase")
                    return True
                except Exception as e:
                    logger.error(f"Error updating sell order for new purchase: {e}")
                    return False
            else:
                # Place new sell order
                try:
                    # Calculate trigger price using improved method
                    trigger_price, _ = calculate_gtt_prices(
                        current_price=sell_price,
                        drop_percentage=1.2,
                        tick_size=tick_size,
                        order_type="SELL",
                        price_delta_ticks=1
                    )
                    
                    logger.info(f"Placing new sell GTT order for {total_shares} shares @ {sell_price:.2f} ({profit_percentage}% profit)")
                    logger.debug(f"Trigger price: {trigger_price:.2f}")
                    sell_order_id = place_gtt_order(
                        kite_api=kite_api,
                        trading_symbol=company_name,
                        exchange=stock_exchange,
                        transaction_type="SELL",
                        quantity=total_shares,
                        price=sell_price,
                        trigger_price=trigger_price
                    )
                    
                    if sell_order_id:
                        sell_order_details = {
                            'trigger_id': sell_order_id,
                            'trading_symbol': company_name,
                            'exchange': stock_exchange,
                            'transaction_type': 'SELL',
                            'quantity': total_shares,
                            'price': sell_price,
                            'trigger_price': trigger_price,
                            'order_type': 'LIMIT',
                            'validity': 'DAY',
                            'date_placed': datetime.now().isoformat(),
                            'current_price_when_placed': current_price,
                            'status': 'ACTIVE',
                            'profit_target': profit_target,
                            'avg_purchase_price': avg_price,
                            'profit_percentage': profit_percentage,
                            'placed_for_new_purchase': True
                        }
                        updated_gtt_orders.append(sell_order_details)
                        save_gtt_history(company_name, updated_gtt_orders, logger)
                        logger.info("New sell order placed for new purchase")
                        return True
                except Exception as e:
                    logger.error(f"Error placing sell order for new purchase: {e}")
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking for new purchases: {e}")
        return False


def handle_tick_data(tick_data: Dict[str, Any], kite_api: KiteConnectAPI, breeze_api: BreezeApi, 
                    company_name: str, stock_exchange: str, gtt_orders: List[Dict[str, Any]], 
                    logger: logging.Logger) -> None:
    """
    Handle real-time tick data for immediate price monitoring and order management
    Now prioritizes history file for order detection and management
    
    Parameters:
    - tick_data: Real-time tick data from Breeze API
    - kite_api: Initialized Kite API instance
    - breeze_api: Initialized Breeze API instance
    - company_name: Company name
    - stock_exchange: Stock exchange
    - gtt_orders: List of GTT orders from history file
    - logger: Logger instance
    """
    try:
        # Extract current price from tick data
        current_price = tick_data.get('last', None)
        if not current_price:
            return
        
        logger.debug(f"Tick data received - Current price: {current_price}")
        
        # First, check for triggered orders using history file (prioritizes history)
        updated_orders, triggered_detected, total_shares, avg_price = detect_and_update_triggered_orders_from_history(
            kite_api, company_name, stock_exchange, gtt_orders, logger
        )
        
        # Update the gtt_orders list with the updated orders
        gtt_orders.clear()
        gtt_orders.extend(updated_orders)
        
        # If triggered orders were detected, manage sell orders immediately
        if triggered_detected:
            logger.info("TRIGGERED ORDERS DETECTED - managing sell orders immediately")
            sell_order_updated = manage_sell_orders_based_on_history(
                kite_api, company_name, stock_exchange, gtt_orders, current_price, logger
            )
            if sell_order_updated:
                logger.info("SUCCESS: Sell order management completed for triggered orders")
            return  # Exit early since we've handled the triggered orders
        
        # If no triggered orders, check if we need to maintain 5 active buy orders
        try:
            current_gtt_orders = kite_api.get_gtt_orders()
            
            # Filter for company-specific active buy orders
            active_buy_orders = [order for order in current_gtt_orders 
                               if (order.get('condition', {}).get('tradingsymbol', '').upper() == company_name.upper() and 
                                   order.get('orders', [{}])[0].get('transaction_type') == 'BUY' and 
                                   order.get('status', '').upper() in ['ACTIVE', 'PENDING', 'OPEN'])]
            
            logger.info(f"Tick: Active buy orders for {company_name}: {len(active_buy_orders)}")
            
            # If we have less than 5 active buy orders, the main monitoring thread will handle it
            if len(active_buy_orders) < 5:
                logger.info(f"Tick: Only {len(active_buy_orders)} active buy orders, main thread will place more")
                return
                
        except Exception as e:
            logger.debug(f"Error checking GTT orders in tick handler: {e}")
            return
        
        # If we have shares but no triggered orders in this tick, still check sell orders
        if total_shares > 0:
            logger.debug(f"Tick: Checking sell orders for {total_shares} shares (avg price: {avg_price:.2f})")
            
            # Only manage sell orders during market hours
            if is_market_hours():
                sell_order_updated = manage_sell_orders_based_on_history(
                    kite_api, company_name, stock_exchange, gtt_orders, current_price, logger
                )
                if sell_order_updated:
                    logger.debug("Tick: Sell order management completed")
            else:
                logger.debug("Tick: Outside market hours - sell order management paused")
        
    except Exception as e:
        logger.error(f"Error in tick data handler: {e}")


def monitor_and_manage_sell_orders(kite_api: KiteConnectAPI, breeze_api: BreezeApi, 
                                 company_name: str, stock_exchange: str, 
                                 gtt_orders: List[Dict[str, Any]], logger: logging.Logger,
                                 stop_monitoring: threading.Event) -> None:
    """
    Monitor GTT orders every 5 minutes and manage sell orders for profit booking
    Also maintain exactly 5 active buy orders by placing new orders when existing ones are triggered
    
    Parameters:
    - kite_api: Initialized Kite API instance
    - breeze_api: Initialized Breeze API instance
    - company_name: Company name
    - stock_exchange: Stock exchange
    - gtt_orders: List of GTT orders
    - logger: Logger instance
    - stop_monitoring: Threading event to stop monitoring
    """
    logger.info("Starting GTT order monitoring thread")
    
    # Track if sell order was placed outside market hours
    sell_order_placed_outside_market = False
    consecutive_market_closed_cycles = 0
    max_market_closed_cycles = 12  # 1 hour (12 * 5 minutes) of market closed before stopping
    
    # Track the next order number for maintaining 5 active orders
    next_order_number = 6  # Start with 6 since we already have orders 1-5
    
    while not stop_monitoring.is_set():
        try:
            logger.info("=== GTT Order Monitoring Cycle ===")
            
            # Check if it's market hours
            is_market_open = is_market_hours()
            logger.info(f"Market hours: {'OPEN' if is_market_open else 'CLOSED'}")
            
            # Track consecutive market closed cycles
            if not is_market_open:
                consecutive_market_closed_cycles += 1
                logger.info(f"Market closed cycle {consecutive_market_closed_cycles}/{max_market_closed_cycles}")
                
                # Stop monitoring if market has been closed for too long
                if consecutive_market_closed_cycles >= max_market_closed_cycles:
                    logger.info("Market has been closed for 1 hour. Stopping monitoring.")
                    break
            else:
                consecutive_market_closed_cycles = 0  # Reset counter when market opens
            
            # Get current price
            current_price = get_current_price(breeze_api, company_name)
            if not current_price:
                logger.warning("Could not get current price. Skipping this cycle.")
                time.sleep(300)  # Wait 5 minutes
                continue
            
            # First, check for newly executed buy orders and update sell order immediately
            purchase_detected = check_and_update_sell_order_for_new_purchases(kite_api, company_name, stock_exchange, gtt_orders, logger)
            if purchase_detected:
                logger.info("Monitoring: New purchase detected and sell order updated")
                # Continue with the rest of the monitoring cycle
            
            # Check for triggered orders using history file (prioritizes history)
            updated_orders, triggered_detected, total_shares, avg_price = detect_and_update_triggered_orders_from_history(
                kite_api, company_name, stock_exchange, gtt_orders, logger
            )
            
            # Update the gtt_orders list with the updated orders
            gtt_orders.clear()
            gtt_orders.extend(updated_orders)
            
            # If triggered orders were detected, manage sell orders immediately
            if triggered_detected:
                logger.info("TRIGGERED ORDERS DETECTED - managing sell orders immediately")
                sell_order_updated = manage_sell_orders_based_on_history(
                    kite_api, company_name, stock_exchange, gtt_orders, current_price, logger
                )
                if sell_order_updated:
                    logger.info("SUCCESS: Sell order management completed for triggered orders")
            
            # Get current GTT orders from Kite
            try:
                current_gtt_orders = kite_api.get_gtt_orders()
                logger.info(f"Current GTT orders in account: {len(current_gtt_orders)}")
            except Exception as e:
                logger.error(f"Error getting current GTT orders: {e}")
                # Continue with empty list instead of skipping the cycle
                current_gtt_orders = []
                logger.info("Continuing with empty GTT orders list")
            
            # Count active buy orders for the company
            active_buy_orders = []
            for order in current_gtt_orders:
                if (order.get('condition', {}).get('tradingsymbol', '').upper() == company_name.upper() and 
                    order.get('orders', [{}])[0].get('transaction_type') == 'BUY' and 
                    order.get('status', '').upper() in ['ACTIVE', 'PENDING', 'OPEN']):
                    active_buy_orders.append(order)
            
            logger.info(f"Active buy orders for {company_name}: {len(active_buy_orders)}")
            
            # Maintain exactly 5 active buy orders
            if len(active_buy_orders) < 5:
                orders_needed = 5 - len(active_buy_orders)
                logger.info(f"Need to place {orders_needed} more buy orders to maintain 5 active orders")
                logger.info(f"Current active orders: {len(active_buy_orders)}/5")
                
                # Get the lowest active buy order price to calculate next order price (last order in sequence)
                lowest_active_price = None
                if active_buy_orders:
                    # Extract prices from the nested GTT order structure
                    prices = []
                    logger.info(f"DEBUG: Found {len(active_buy_orders)} active buy orders to extract prices from")
                    
                    for i, order in enumerate(active_buy_orders):
                        try:
                            logger.info(f"DEBUG: Order {i+1} structure: {order}")
                            
                            # Try multiple ways to extract price
                            order_price = None
                            
                            # Method 1: Try nested orders structure
                            if 'orders' in order and order['orders']:
                                order_price = order['orders'][0].get('price')
                                logger.info(f"DEBUG: Method 1 - Price from orders[0].price: {order_price}")
                            
                            # Method 2: Try direct price field
                            if not order_price and 'price' in order:
                                order_price = order.get('price')
                                logger.info(f"DEBUG: Method 2 - Price from direct price field: {order_price}")
                            
                            # Method 3: Try condition structure
                            if not order_price and 'condition' in order:
                                order_price = order['condition'].get('price')
                                logger.info(f"DEBUG: Method 3 - Price from condition.price: {order_price}")
                            
                            if order_price and order_price != float('inf') and order_price > 0:
                                prices.append(order_price)
                                logger.info(f"DEBUG: Valid price found: {order_price}")
                            else:
                                logger.warning(f"DEBUG: Invalid price found: {order_price}")
                                
                        except (IndexError, TypeError) as e:
                            logger.warning(f"Could not extract price from order {i+1}: {e}")
                            continue
                    
                    if prices:
                        lowest_active_price = min(prices)  # Use lowest price (last order in sequence)
                        logger.info(f"Lowest active order price (last order): {lowest_active_price}")
                    else:
                        logger.warning("No valid prices found in existing orders, using current market price")
                        lowest_active_price = current_price
                
                if lowest_active_price:
                    # Use the lowest active price as the base for new orders
                    previous_order_price = lowest_active_price
                    logger.info(f"Starting new order placement from lowest active price: {previous_order_price}")
                    
                    # Get tick size for the stock using improved method
                    tick_size = get_tick_size_for_stock(company_name, current_price)
                    logger.info(f"Tick size for {company_name}: {tick_size}")
                    
                    for i in range(orders_needed):
                        # Calculate the correct order number and quantity based on existing orders
                        # We need to find the lowest existing order number and add 1
                        existing_order_numbers = []
                        for order in active_buy_orders:
                            try:
                                # Try to get quantity from the order to determine order number
                                quantity = order.get('orders', [{}])[0].get('quantity', 0)
                                if quantity > 0:
                                    existing_order_numbers.append(quantity)
                                    logger.debug(f"DEBUG: Found existing order with quantity: {quantity}")
                            except (IndexError, TypeError):
                                continue
                        
                        if existing_order_numbers:
                            # Find the highest existing order number
                            highest_existing = max(existing_order_numbers)
                            order_number = highest_existing + 1
                            logger.info(f"DEBUG: Highest existing order number: {highest_existing}, new order number: {order_number}")
                        else:
                            # If no existing orders found, start with 1
                            order_number = 1
                            logger.info(f"DEBUG: No existing orders found, starting with order number: {order_number}")
                        
                        quantity = order_number  # Quantity equals the order number: 1, 2, 3, 4, 5, 6, 7, etc.
                        
                        logger.info(f"DEBUG: existing_order_count={len(active_buy_orders)}, i={i}, order_number={order_number}")
                        logger.info(f"DEBUG: Attempting to place order {i+1}/{orders_needed} with order_number={order_number}")
                        
                        # Calculate order price using improved method
                        if i == 0:  # First new order in this cycle
                            # For 6th order: trigger at 1% below lowest active price, limit at 1% below trigger
                            raw_trigger_price = previous_order_price * 0.99  # 1% below lowest active price
                            trigger_price = round_to_tick(raw_trigger_price, tick_size)
                            
                            raw_order_price = trigger_price * 0.99  # 1% below trigger price
                            order_price = round_to_tick(raw_order_price, tick_size)
                            
                            logger.info(f"DEBUG: First order - trigger at 1% below lowest active price: {previous_order_price} * 0.99 = {raw_trigger_price:.4f} -> {trigger_price:.2f}")
                            logger.info(f"DEBUG: First order - limit at 1% below trigger: {trigger_price} * 0.99 = {raw_order_price:.4f} -> {order_price:.2f}")
                        else:
                            # For subsequent orders: trigger at 1% below previous order price, limit at 1% below trigger
                            raw_trigger_price = previous_order_price * 0.99  # 1% below previous order price
                            trigger_price = round_to_tick(raw_trigger_price, tick_size)
                            
                            raw_order_price = trigger_price * 0.99  # 1% below trigger price
                            order_price = round_to_tick(raw_order_price, tick_size)
                            
                            logger.info(f"DEBUG: Subsequent order - trigger at 1% below previous price: {previous_order_price} * 0.99 = {raw_trigger_price:.4f} -> {trigger_price:.2f}")
                            logger.info(f"DEBUG: Subsequent order - limit at 1% below trigger: {trigger_price} * 0.99 = {raw_order_price:.4f} -> {order_price:.2f}")
                        
                        logger.info(f"Placing GTT order {order_number}: {quantity} shares @ {order_price:.2f} (trigger: {trigger_price:.2f}) - {order_number}% drop from entry")
                        logger.info(f"DEBUG: Price validation - Order: {order_price:.2f}, Trigger: {trigger_price:.2f}, Tick size: {tick_size}")
                        
                        # Check if new price is similar to existing orders
                        logger.info(f"DEBUG: Checking if price {order_price:.2f} is similar to existing orders...")
                        if is_similar_to_existing_orders(order_price, trigger_price, active_buy_orders):
                            logger.info(f"New price {order_price:.2f} is similar to existing orders. Skipping this order.")
                            logger.info(f"DEBUG: Order {i+1} skipped due to similar price")
                            continue
                        
                        logger.info(f"DEBUG: Price check passed, proceeding with order placement...")
                        
                        # Place a GTT buy order
                        gtt_order_id = place_gtt_order(
                            kite_api=kite_api,
                            trading_symbol=company_name,
                            exchange=stock_exchange,
                            transaction_type="BUY",
                            quantity=quantity,
                            price=order_price,
                            trigger_price=trigger_price,
                            current_price=current_price
                        )
                        
                        if gtt_order_id:
                            logger.info(f"Successfully placed new GTT order {order_number}: {gtt_order_id}")
                            
                            # Add to local tracking
                            new_order_details = {
                                'trigger_id': gtt_order_id,
                                'trading_symbol': company_name,
                                'exchange': stock_exchange,
                                'transaction_type': 'BUY',
                                'quantity': quantity,
                                'price': order_price,
                                'trigger_price': trigger_price,
                                'order_type': 'LIMIT',
                                'validity': 'DAY',
                                'date_placed': datetime.now().isoformat(),
                                'current_price_when_placed': current_price,
                                'status': 'ACTIVE',
                                'percentage_drop_from_entry': order_number
                            }
                            gtt_orders.append(new_order_details)
                            
                            # Update previous order price for next iteration
                            previous_order_price = order_price
                        else:
                            logger.error(f"Failed to place new GTT order {order_number}")
                            break
                    
                    # Save updated GTT history
                    save_gtt_history(company_name, gtt_orders, logger)
                    logger.info("Updated GTT history saved")
                else:
                    logger.warning("No active buy orders found, cannot determine price for new orders")
            else:
                logger.info("Already have 5 active buy orders, no new orders needed")
                logger.info(f"Active orders count: {len(active_buy_orders)}/5")
            
            # Calculate total shares and average price from executed buy orders
            # Update order statuses before calculating shares
            updated_gtt_orders, triggered_detected, total_shares, avg_price = update_gtt_order_statuses(
                kite_api, company_name, stock_exchange, gtt_orders, logger
            )
            # total_shares, avg_price = calculate_total_shares_and_avg_price(updated_gtt_orders)
            
            if total_shares > 0:
                logger.info(f"Total shares: {total_shares}, Average price: {avg_price:.2f}")
                
                # Get tick size for the stock using improved method (ensure it's always defined)
                tick_size = get_tick_size_for_stock(company_name, current_price)
                logger.info(f"Tick size for {company_name}: {tick_size}")
                
                # Calculate dynamic profit target based on share count
                if total_shares <= 3:
                    # 3% profit for ≤3 shares
                    raw_profit_target = avg_price * 1.03
                    profit_percentage = 3
                else:
                    # 2% profit for >3 shares
                    raw_profit_target = avg_price * 1.02
                    profit_percentage = 2
                
                profit_target = round_to_tick(raw_profit_target, tick_size)
                sell_price = profit_target  # Sell at dynamic profit target
                logger.info(f"{profit_percentage}% profit target: {raw_profit_target:.4f} → {profit_target:.2f}, Sell price: {sell_price:.2f}")
                
                # Check if we already have a sell GTT order
                existing_sell_order = None
                for order in current_gtt_orders:
                    if order.get('orders', [{}])[0].get('transaction_type') == 'SELL':
                        existing_sell_order = order
                        break
                
                # Determine if we should place/update sell order
                should_place_order = False
                
                if is_market_open:
                    # During market hours: always place/update sell orders
                    should_place_order = True
                    logger.info("Market is open - proceeding with sell order placement/update")
                else:
                    # Outside market hours: only place once
                    if not sell_order_placed_outside_market:
                        should_place_order = True
                        sell_order_placed_outside_market = True
                        logger.info("Market is closed - placing sell order once for next market session")
                    else:
                        logger.info("Market is closed - sell order already placed for next session")
                
                if should_place_order:
                    if existing_sell_order:
                        # Check if update is needed (quantity or price change)
                        current_quantity = existing_sell_order.get('orders', [{}])[0].get('quantity', 0)
                        current_price = existing_sell_order.get('orders', [{}])[0].get('price', 0)
                        
                        if current_quantity != total_shares or abs(current_price - sell_price) > 0.01:
                            try:
                                logger.info(f"UPDATING SELL ORDER: Quantity: {current_quantity}->{total_shares}, Price: {current_price:.2f}->{sell_price:.2f}")
                                
                                # Calculate trigger price for sell order
                                trigger_price, _ = calculate_gtt_prices(
                                    current_price=sell_price,
                                    drop_percentage=1.2,
                                    tick_size=tick_size,
                                    order_type="SELL",
                                    price_delta_ticks=1
                                )
                                
                                kite_api.modify_gtt_order(
                                    gtt_order_id=existing_sell_order.get('id'),
                                    trading_symbol=company_name,
                                    exchange=stock_exchange,
                                    transaction_type="SELL",
                                    quantity=total_shares,
                                    price=sell_price,
                                    trigger_price=trigger_price
                                )
                                
                                # Update history file
                                if existing_sell_order:
                                    existing_sell_order['quantity'] = total_shares
                                    existing_sell_order['price'] = sell_price
                                    existing_sell_order['trigger_price'] = trigger_price
                                    existing_sell_order['updated_at'] = datetime.now().isoformat()
                                else:
                                    # Add new sell order to history
                                    sell_order_details = {
                                        'trigger_id': api_sell_order.get('id'),
                                        'trading_symbol': company_name,
                                        'exchange': stock_exchange,
                                        'transaction_type': 'SELL',
                                        'quantity': total_shares,
                                        'price': sell_price,
                                        'trigger_price': trigger_price,
                                        'order_type': 'LIMIT',
                                        'validity': 'DAY',
                                        'date_placed': datetime.now().isoformat(),
                                        'status': 'ACTIVE',
                                        'profit_target': profit_target,
                                        'avg_purchase_price': avg_price,
                                        'profit_percentage': profit_percentage
                                    }
                                    gtt_orders.append(sell_order_details)
                                
                                save_gtt_history(company_name, gtt_orders, logger)
                                logger.info("SUCCESS: Sell order updated successfully")
                                return True
                                
                            except Exception as e:
                                logger.error(f"ERROR: Error updating sell order: {e}")
                                return False
                        else:
                            logger.info(f"SUCCESS: Sell order already up to date - {total_shares} shares @ {sell_price:.2f}")
                            return True
                    else:
                        # Place new sell GTT order immediately when we have shares
                        try:
                            # Calculate trigger price using improved method
                            trigger_price, _ = calculate_gtt_prices(
                                current_price=sell_price,
                                drop_percentage=1.2,
                                tick_size=tick_size,
                                order_type="SELL",
                                price_delta_ticks=1
                            )
                            
                            logger.info(f"Placing new sell GTT order for {total_shares} shares @ {sell_price:.2f}")
                            logger.debug(f"Trigger price: {trigger_price:.2f}")
                            sell_order_id = place_gtt_order(
                                kite_api=kite_api,
                                trading_symbol=company_name,
                                exchange=stock_exchange,
                                transaction_type="SELL",
                                quantity=total_shares,
                                price=sell_price,
                                trigger_price=trigger_price,
                                current_price=current_price
                            )
                            
                            if sell_order_id:
                                # Add to history file
                                sell_order_details = {
                                    'trigger_id': sell_order_id,
                                    'trading_symbol': company_name,
                                    'exchange': stock_exchange,
                                    'transaction_type': 'SELL',
                                    'quantity': total_shares,
                                    'price': sell_price,
                                    'trigger_price': trigger_price,
                                    'order_type': 'LIMIT',
                                    'validity': 'DAY',
                                    'date_placed': datetime.now().isoformat(),
                                    'status': 'ACTIVE',
                                    'profit_target': profit_target,
                                    'avg_purchase_price': avg_price,
                                    'profit_percentage': profit_percentage
                                }
                                gtt_orders.append(sell_order_details)
                                save_gtt_history(company_name, gtt_orders, logger)
                                logger.info("SUCCESS: New sell order placed successfully")
                                return True
                            else:
                                logger.error("ERROR: Failed to place sell order")
                                return False
                                
                        except Exception as e:
                            logger.error(f"ERROR: Error placing sell order: {e}")
                            return False
            else:
                logger.info("No shares available for selling")
            
            logger.info("=== End Monitoring Cycle ===")
            
            # Reset sell order flag when market opens
            if is_market_open:
                sell_order_placed_outside_market = False
            
            # Wait 2 minutes before next cycle (reduced from 5 minutes since we have tick data)
            # This cycle now focuses on order maintenance rather than price monitoring
            time.sleep(120)
            
        except Exception as e:
            logger.error(f"Error in monitoring cycle: {e}\n{traceback.format_exc()}")
            time.sleep(300)  # Wait 5 minutes before retrying
    
    logger.info("GTT order monitoring stopped")
    # Signal main thread to stop
    stop_monitoring.set()


def main(company_name: str, stock_exchange: str = "NSE", num_orders: int = 5, cancel_orders: bool = False):
    """
    Main function to handle GTT fall buy strategy
    
    Parameters:
    - company_name: Name of the company (e.g., "HINDALCO", "ITC")
    - stock_exchange: Stock exchange (default: "NSE")
    - num_orders: Number of GTT orders to place (default: 5)
    - cancel_orders: If True, cancel all existing GTT orders (default: False)
    """
    # Set up logger
    logger = setup_logger(__name__, company_name)
    
    # Global variables for cleanup
    breeze_api = None
    stop_monitoring = None
    
    def cleanup_on_exit():
        """Cleanup function to be called on exit"""
        nonlocal breeze_api, stop_monitoring
        try:
            if stop_monitoring:
                stop_monitoring.set()
                logger.info("Stop monitoring signal set")
            
            if breeze_api:
                try:
                    if hasattr(breeze_api, 'breeze') and hasattr(breeze_api.breeze, 'sio'):
                        if breeze_api.breeze.sio.connected:
                            logger.info("Cleaning up WebSocket connection on exit...")
                            breeze_api.disconnect_socket()
                            logger.info("WebSocket connection closed on exit")
                        else:
                            logger.info("WebSocket already disconnected on exit")
                except Exception as e:
                    logger.warning(f"Error during WebSocket cleanup on exit: {e}")
        except Exception as e:
            logger.warning(f"Error during cleanup on exit: {e}")
    
    try:
        logger.info(f"Starting GTT Fall Buy strategy for {company_name} on {stock_exchange}")
        
        # Initialize Breeze API
        try:
            breeze_api = BreezeApi(symbol=company_name)
            breeze_api.start_api()
            logger.info("Successfully initialized Breeze API")
        except Exception as e:
            logger.error(f"Failed to initialize Breeze API: {e}\n{traceback.format_exc()}")
            sys.exit(1)
        
        # Initialize Kite API
        try:
            kite_api = KiteConnectAPI(trading_symbol=company_name)
            kite_api.connect()
            logger.info("Successfully initialized Kite API")
        except Exception as e:
            logger.error(f"Failed to initialize Kite API: {e}\n{traceback.format_exc()}")
            sys.exit(1)
        
        # Cancel all existing GTT orders if requested
        if cancel_orders:
            logger.info("Cancelling all existing GTT orders...")
            cancelled_count = cancel_all_gtt_orders(kite_api, company_name, logger)
            logger.info(f"Cancelled {cancelled_count} GTT orders")
            
            # Clear the history file after cancelling orders
            try:
                file_path = os.path.join('workdir', 'orders', f'{company_name}_gtt_history.json')
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Cleared GTT history file: {file_path}")
            except Exception as e:
                logger.error(f"Error clearing history file: {e}")
            
            logger.info("GTT order cancellation completed")
            return
        
        logger.info(f"Will place {num_orders} GTT orders")
        
        # Robust order-checking logic: check history file first
        try:
            existing_gtt_orders = load_gtt_history(company_name, logger)
            logger.info(f"Found {len(existing_gtt_orders)} existing GTT orders in history file")
            
            # Also check Kite API for current orders
            try:
                current_api_orders = kite_api.get_gtt_orders()
                logger.info(f"Found {len(current_api_orders)} current GTT orders in Kite API")
                
                # Log all current API orders for debugging
                for i, order in enumerate(current_api_orders):
                    trading_symbol = order.get('condition', {}).get('tradingsymbol', '')
                    order_id = order.get('id')
                    status = order.get('status', 'UNKNOWN')
                    transaction_type = order.get('orders', [{}])[0].get('transaction_type', 'UNKNOWN')
                    logger.info(f"API Order {i+1}: ID={order_id}, Symbol={trading_symbol}, Type={transaction_type}, Status={status}")
                
                # Check if we have active orders for our company
                active_api_orders = [order for order in current_api_orders 
                                   if (order.get('condition', {}).get('tradingsymbol', '').upper() == company_name.upper() and
                                       order.get('orders', [{}])[0].get('transaction_type') == 'BUY' and
                                       order.get('status', '').upper() in ['ACTIVE', 'PENDING', 'OPEN'])]
                
                logger.info(f"Found {len(active_api_orders)} active {company_name} buy orders in Kite API")
                
                # If we have active orders in API, use them
                if len(active_api_orders) >= num_orders:
                    logger.info(f"Already have {len(active_api_orders)} active buy orders in Kite API. No need to place new orders.")
                    logger.info("If you want to place new orders, first cancel existing ones using --cancel_orders flag.")
                    
                    # Convert API orders to history format for consistency
                    all_gtt_orders = []
                    for api_order in current_api_orders:
                        if api_order.get('condition', {}).get('tradingsymbol', '').upper() == company_name.upper():
                            order_details = {
                                'trigger_id': api_order.get('id'),
                                'trading_symbol': company_name,
                                'exchange': stock_exchange,
                                'transaction_type': api_order.get('orders', [{}])[0].get('transaction_type', 'BUY'),
                                'quantity': api_order.get('orders', [{}])[0].get('quantity', 0),
                                'price': api_order.get('orders', [{}])[0].get('price', 0),
                                'trigger_price': api_order.get('condition', {}).get('price', 0),
                                'order_type': 'LIMIT',
                                'validity': 'DAY',
                                'date_placed': datetime.now().isoformat(),
                                'status': api_order.get('status', 'ACTIVE')
                            }
                            all_gtt_orders.append(order_details)
                    
                    # Save to history file for consistency
                    save_gtt_history(company_name, all_gtt_orders, logger)
                    logger.info(f"Using {len(all_gtt_orders)} existing orders for monitoring")
                    
                    # Start monitoring thread with existing orders
                    stop_monitoring = threading.Event()
                    monitoring_thread = threading.Thread(
                        target=monitor_and_manage_sell_orders,
                        args=(kite_api, breeze_api, company_name, stock_exchange, all_gtt_orders, logger, stop_monitoring)
                    )
                    monitoring_thread.daemon = True
                    monitoring_thread.start()
                    
                    # Set up tick data handling for real-time monitoring
                    try:
                        logger.info("Setting up real-time tick data monitoring...")
                        if hasattr(breeze_api, 'breeze') and hasattr(breeze_api.breeze, 'sio') and breeze_api.breeze.sio.connected:
                            logger.info("WebSocket already connected, skipping connection setup")
                        else:
                            breeze_api.connect_socket()
                            logger.info("Connected to Breeze WebSocket for real-time data")
                        stock_token = breeze_api.get_icici_token_name(company_name)
                        logger.info(f"Stock token for tick data: {stock_token}")
                        def tick_handler(tick_data):
                            handle_tick_data(tick_data, kite_api, breeze_api, company_name, stock_exchange, all_gtt_orders, logger)
                        breeze_api.set_on_ticks(tick_handler)
                        logger.info("Tick handler set up successfully")
                        breeze_api.subscribe_feed_token(stock_token)
                        logger.info(f"Subscribed to real-time feed for {company_name}")
                        logger.info("Real-time tick data monitoring is now active!")
                        logger.info("The system will now respond to price changes in real-time")
                        while True:
                            time.sleep(60)
                    except Exception as e:
                        logger.error(f"Error setting up real-time monitoring: {e}")
                        sys.exit(1)
                    return
                    
            except Exception as e:
                logger.warning(f"Could not fetch orders from Kite API: {e}. Will check history file.")
            
            # Check history file for active orders
            active_existing_orders = [order for order in existing_gtt_orders 
                                     if order.get('transaction_type') == 'BUY' and 
                                        order.get('status') == 'ACTIVE']
            if len(active_existing_orders) >= num_orders:
                logger.info(f"Already have {len(active_existing_orders)} active buy orders in history file. No need to place new orders.")
                logger.info("If you want to place new orders, first cancel existing ones using --cancel_orders flag.")
                all_gtt_orders = existing_gtt_orders
                logger.info(f"Using {len(all_gtt_orders)} existing orders for monitoring")
                # Start monitoring thread with existing orders
                stop_monitoring = threading.Event()
                monitoring_thread = threading.Thread(
                    target=monitor_and_manage_sell_orders,
                    args=(kite_api, breeze_api, company_name, stock_exchange, all_gtt_orders, logger, stop_monitoring)
                )
                monitoring_thread.daemon = True
                monitoring_thread.start()
                # Set up tick data handling for real-time monitoring
                try:
                    logger.info("Setting up real-time tick data monitoring...")
                    if hasattr(breeze_api, 'breeze') and hasattr(breeze_api.breeze, 'sio') and breeze_api.breeze.sio.connected:
                        logger.info("WebSocket already connected, skipping connection setup")
                    else:
                        breeze_api.connect_socket()
                        logger.info("Connected to Breeze WebSocket for real-time data")
                    stock_token = breeze_api.get_icici_token_name(company_name)
                    logger.info(f"Stock token for tick data: {stock_token}")
                    def tick_handler(tick_data):
                        handle_tick_data(tick_data, kite_api, breeze_api, company_name, stock_exchange, all_gtt_orders, logger)
                    breeze_api.set_on_ticks(tick_handler)
                    logger.info("Tick handler set up successfully")
                    breeze_api.subscribe_feed_token(stock_token)
                    logger.info(f"Subscribed to real-time feed for {company_name}")
                    logger.info("Real-time tick data monitoring is now active!")
                    logger.info("The system will now respond to price changes in real-time")
                    while True:
                        time.sleep(60)
                except Exception as e:
                    logger.error(f"Error setting up real-time monitoring: {e}")
                    sys.exit(1)
                return
        except Exception as e:
            logger.warning(f"Could not load or parse history file: {e}. Will try to fetch from Kite API.")
            existing_gtt_orders = []
        # If we reach here, history file is missing/corrupt/empty, so try Kite API
        try:
            actual_gtt_orders = kite_api.get_gtt_orders()
            active_buy_orders = [order for order in actual_gtt_orders 
                                if order.get('transaction_type') == 'BUY' and 
                                   order.get('status') == 'ACTIVE']
            if len(active_buy_orders) >= num_orders:
                logger.info(f"Already have {len(active_buy_orders)} active buy orders from Kite API. No need to place new orders.")
                logger.info("If you want to place new orders, first cancel existing ones using --cancel_orders flag.")
                all_gtt_orders = actual_gtt_orders
                logger.info(f"Using {len(all_gtt_orders)} existing orders for monitoring")
                # Start monitoring thread with existing orders
                stop_monitoring = threading.Event()
                monitoring_thread = threading.Thread(
                    target=monitor_and_manage_sell_orders,
                    args=(kite_api, breeze_api, company_name, stock_exchange, all_gtt_orders, logger, stop_monitoring)
                )
                monitoring_thread.daemon = True
                monitoring_thread.start()
                # Set up tick data handling for real-time monitoring
                try:
                    logger.info("Setting up real-time tick data monitoring...")
                    if hasattr(breeze_api, 'breeze') and hasattr(breeze_api.breeze, 'sio') and breeze_api.breeze.sio.connected:
                        logger.info("WebSocket already connected, skipping connection setup")
                    else:
                        breeze_api.connect_socket()
                        logger.info("Connected to Breeze WebSocket for real-time data")
                    stock_token = breeze_api.get_icici_token_name(company_name)
                    logger.info(f"Stock token for tick data: {stock_token}")
                    def tick_handler(tick_data):
                        handle_tick_data(tick_data, kite_api, breeze_api, company_name, stock_exchange, all_gtt_orders, logger)
                    breeze_api.set_on_ticks(tick_handler)
                    logger.info("Tick handler set up successfully")
                    breeze_api.subscribe_feed_token(stock_token)
                    logger.info(f"Subscribed to real-time feed for {company_name}")
                    logger.info("Real-time tick data monitoring is now active!")
                    logger.info("The system will now respond to price changes in real-time")
                    while True:
                        time.sleep(60)
                except Exception as e:
                    logger.error(f"Error setting up real-time monitoring: {e}")
                    sys.exit(1)
                return
        except Exception as e:
            logger.warning(f"Could not fetch orders from Kite API: {e}. Will proceed to place new orders.")
        # If both fail or are empty, continue to place new orders as before
        
        # Get current price
        current_price = get_current_price(breeze_api, company_name)
        if not current_price:
            logger.error("Could not get current price. Exiting.")
            sys.exit(1)
        
        logger.info(f"Current price for {company_name}: {current_price}")
        
        # Initialize variables to prevent UnboundLocalError
        lowest_existing_price = None
        existing_order_count = 0
        active_buy_orders = []
        
        # Get actual active orders from the exchange
        exchange_api_working = False
        try:
            actual_gtt_orders = kite_api.get_gtt_orders()
            active_buy_orders = [order for order in actual_gtt_orders 
                                if order.get('transaction_type') == 'BUY' and 
                                order.get('status') == 'ACTIVE']
            existing_order_count = len(active_buy_orders)
            exchange_api_working = True
            logger.info(f"Found {existing_order_count} actually active buy orders on exchange")
            
            # Check if we already have enough orders to prevent duplicates
            if existing_order_count >= num_orders:
                logger.info(f"Already have {existing_order_count} active buy orders. No need to place new orders.")
                logger.info("If you want to place new orders, first cancel existing ones using --cancel_orders flag.")
                
                # Load existing orders from history for monitoring
                all_gtt_orders = existing_gtt_orders
                logger.info(f"Using {len(all_gtt_orders)} existing orders for monitoring")
                
                # Start monitoring thread with existing orders
                stop_monitoring = threading.Event()
                monitoring_thread = threading.Thread(
                    target=monitor_and_manage_sell_orders,
                    args=(kite_api, breeze_api, company_name, stock_exchange, all_gtt_orders, logger, stop_monitoring)
                )
                monitoring_thread.daemon = True
                monitoring_thread.start()
                
                # Set up tick data handling for real-time monitoring
                try:
                    logger.info("Setting up real-time tick data monitoring...")
                    
                    # Check if WebSocket is already connected
                    if hasattr(breeze_api, 'breeze') and hasattr(breeze_api.breeze, 'sio') and breeze_api.breeze.sio.connected:
                        logger.info("WebSocket already connected, skipping connection setup")
                    else:
                        # Connect to WebSocket for real-time data
                        breeze_api.connect_socket()
                        logger.info("Connected to Breeze WebSocket for real-time data")
                    
                    # Get stock token for tick data
                    stock_token = breeze_api.get_icici_token_name(company_name)
                    logger.info(f"Stock token for tick data: {stock_token}")
                    
                    # Set up tick handler
                    def tick_handler(tick_data):
                        handle_tick_data(tick_data, kite_api, breeze_api, company_name, stock_exchange, all_gtt_orders, logger)
                    
                    breeze_api.set_on_ticks(tick_handler)
                    logger.info("Tick handler set up successfully")
                    
                    # Subscribe to stock feed
                    breeze_api.subscribe_feed_token(stock_token)
                    logger.info(f"Subscribed to real-time feed for {company_name}")
                    
                    logger.info("Real-time tick data monitoring is now active!")
                    logger.info("The system will now respond to price changes in real-time")
                    
                    # Keep the script running
                    while True:
                        time.sleep(60)  # Check every minute
                        
                except Exception as e:
                    logger.error(f"Error setting up real-time monitoring: {e}")
                    sys.exit(1)
                
                return  # Exit the function without placing new orders
            
            if active_buy_orders:
                lowest_existing_price = min(order.get('price', float('inf')) for order in active_buy_orders)
                logger.info(f"Lowest active order price on exchange: {lowest_existing_price}")
        except Exception as e:
            logger.warning(f"Could not get actual GTT orders from exchange: {e}")
            logger.info("This might be because market is not open yet or API is temporarily unavailable")
            exchange_api_working = False
        
        # If exchange API failed, check history file more carefully
        if not exchange_api_working:
            logger.info("Exchange API not working - checking history file for existing orders...")
            
            # Check history file to see if we have existing orders
            if existing_gtt_orders:
                active_existing_orders = [order for order in existing_gtt_orders 
                                        if order.get('transaction_type') == 'BUY' and 
                                        order.get('status') == 'ACTIVE']
                existing_order_count = len(active_existing_orders)
                logger.info(f"Found {existing_order_count} active orders in history file")
                
                # Check if we already have enough orders to prevent duplicates
                if existing_order_count >= num_orders:
                    logger.info(f"Already have {existing_order_count} active buy orders in history. No need to place new orders.")
                    logger.info("If you want to place new orders, first cancel existing ones using --cancel_orders flag.")
                    
                    # Use existing orders for monitoring
                    all_gtt_orders = existing_gtt_orders
                    logger.info(f"Using {len(all_gtt_orders)} existing orders for monitoring")
                    
                    # Start monitoring thread with existing orders
                    stop_monitoring = threading.Event()
                    monitoring_thread = threading.Thread(
                        target=monitor_and_manage_sell_orders,
                        args=(kite_api, breeze_api, company_name, stock_exchange, all_gtt_orders, logger, stop_monitoring)
                    )
                    monitoring_thread.daemon = True
                    monitoring_thread.start()
                    
                    # Set up tick data handling for real-time monitoring
                    try:
                        logger.info("Setting up real-time tick data monitoring...")
                        
                        # Check if WebSocket is already connected
                        if hasattr(breeze_api, 'breeze') and hasattr(breeze_api.breeze, 'sio') and breeze_api.breeze.sio.connected:
                            logger.info("WebSocket already connected, skipping connection setup")
                        else:
                            # Connect to WebSocket for real-time data
                            breeze_api.connect_socket()
                            logger.info("Connected to Breeze WebSocket for real-time data")
                        
                        # Get stock token for tick data
                        stock_token = breeze_api.get_icici_token_name(company_name)
                        logger.info(f"Stock token for tick data: {stock_token}")
                        
                        # Set up tick handler
                        def tick_handler(tick_data):
                            handle_tick_data(tick_data, kite_api, breeze_api, company_name, stock_exchange, all_gtt_orders, logger)
                        
                        breeze_api.set_on_ticks(tick_handler)
                        logger.info("Tick handler set up successfully")
                        
                        # Subscribe to stock feed
                        breeze_api.subscribe_feed_token(stock_token)
                        logger.info(f"Subscribed to real-time feed for {company_name}")
                        
                        logger.info("Real-time tick data monitoring is now active!")
                        logger.info("The system will now respond to price changes in real-time")
                        
                        # Keep the script running
                        while True:
                            time.sleep(60)  # Check every minute
                            
                    except Exception as e:
                        logger.error(f"Error setting up real-time monitoring: {e}")
                        sys.exit(1)
                    
                    return  # Exit the function without placing new orders
                
                if active_existing_orders:
                    lowest_existing_price = min(order.get('price', float('inf')) for order in active_existing_orders)
                    logger.info(f"Using history file for price reference only. Lowest price from history: {lowest_existing_price}")
            else:
                # No existing orders in history either
                existing_order_count = 0
                active_buy_orders = []  # Initialize empty list
                logger.info("No existing orders found in history - starting fresh")
        
        # Additional safety check: If we're not in market hours and exchange API failed, be extra cautious
        if not exchange_api_working and not is_market_hours():
            logger.warning("WARNING: Market is not open and exchange API is not working!")
            logger.warning("This could lead to duplicate orders if orders were placed before market hours.")
            logger.warning("Consider waiting for market to open or manually checking existing orders.")
            
            # Ask user if they want to continue
            user_input = input("Do you want to continue placing orders? (y/N): ").strip().lower()
            if user_input not in ['y', 'yes']:
                logger.info("User chose not to continue. Exiting.")
                return
        
        # Determine starting price for new orders
        if lowest_existing_price:
            # Continue from the lowest existing order price
            previous_order_price = lowest_existing_price
            logger.info(f"Continuing fall buy strategy from existing order price: {previous_order_price}")
        else:
            # Start fresh with current price
            previous_order_price = current_price
            logger.info(f"Starting fresh fall buy strategy from current price: {previous_order_price}")
        
        # Place multiple GTT orders with different quantities and prices
        # First order will be 0.27% below current price (to meet Kite's 0.25% minimum requirement), then 1% below previous order price for gradual fall buy strategy
        # Quantities will be based on percentage drop from first share price: 1% drop = 1 share, 2% drop = 2 shares, etc.
        orders_placed = 0
        new_gtt_orders = []
        
        # Get tick size for the stock
        tick_size = get_tick_size_for_stock(company_name, current_price)
        
        for i in range(1, num_orders + 1):  # 1 to num_orders
            # Calculate the correct order number and quantity based on existing orders
            order_number = existing_order_count + i  # If 0 existing orders, new orders are 1, 2, 3, 4, 5
            quantity = order_number  # Quantity equals the order number: 1, 2, 3, 4, 5 shares
            
            logger.info(f"DEBUG: existing_order_count={existing_order_count}, i={i}, order_number={order_number}")
            logger.info(f"DEBUG: Attempting to place order {i}/{num_orders}")
            
            # Calculate order price using improved method
            if i == 1:  # First new order in this cycle
                drop_percentage = 0.27
                trigger_price, order_price = calculate_gtt_prices(
                    current_price=previous_order_price,
                    drop_percentage=drop_percentage,
                    tick_size=tick_size,
                    order_type="BUY",
                    price_delta_ticks=2
                )
                logger.info(f"DEBUG: First order - calculated prices using {drop_percentage}% drop from lowest active price")
            else:
                drop_percentage = 1.0
                trigger_price, order_price = calculate_gtt_prices(
                    current_price=previous_order_price,
                    drop_percentage=drop_percentage,
                    tick_size=tick_size,
                    order_type="BUY",
                    price_delta_ticks=2
                )
                logger.info(f"DEBUG: Subsequent order - calculated prices using {drop_percentage}% drop from previous price")
            
            logger.info(f"Placing GTT order {order_number}: {quantity} shares @ {order_price:.2f} (trigger: {trigger_price:.2f}) - {order_number}% drop from entry")
            logger.info(f"DEBUG: Price validation - Order: {order_price:.2f}, Trigger: {trigger_price:.2f}, Tick size: {tick_size}")
            
            # Check if new price is similar to existing orders
            logger.info(f"DEBUG: Checking if price {order_price:.2f} is similar to existing orders...")
            if is_similar_to_existing_orders(order_price, trigger_price, active_buy_orders):
                logger.info(f"New price {order_price:.2f} is similar to existing orders. Skipping this order.")
                logger.info(f"DEBUG: Order {i} skipped due to similar price")
                continue
            
            logger.info(f"DEBUG: Price check passed, proceeding with order placement...")
            
            # Place a GTT buy order
            gtt_order_id = place_gtt_order(
                kite_api=kite_api,
                trading_symbol=company_name,
                exchange=stock_exchange,
                transaction_type="BUY",
                quantity=quantity,
                price=order_price,
                trigger_price=trigger_price,
                current_price=current_price
            )
            
            if gtt_order_id:
                orders_placed += 1
                logger.info(f"Successfully placed GTT order {order_number}: {gtt_order_id}")
                logger.info(f"DEBUG: Order {i} placed successfully. Total placed: {orders_placed}")
                
                # Store order details
                order_details = {
                    'trigger_id': gtt_order_id,
                    'trading_symbol': company_name,
                    'exchange': stock_exchange,
                    'transaction_type': 'BUY',
                    'quantity': quantity,
                    'price': order_price,
                    'trigger_price': trigger_price,
                    'order_type': 'LIMIT',
                    'validity': 'DAY',
                    'date_placed': datetime.now().isoformat(),
                    'current_price_when_placed': current_price,
                    'status': 'ACTIVE',
                    'percentage_drop_from_entry': order_number
                }
                new_gtt_orders.append(order_details)
                
                # Immediately save to history file to prevent loss of orders
                try:
                    current_all_orders = existing_gtt_orders + new_gtt_orders
                    save_gtt_history(company_name, current_all_orders, logger)
                    logger.info(f"DEBUG: Immediately saved order {gtt_order_id} to history file")
                except Exception as e:
                    logger.error(f"Error immediately saving order to history: {e}")
                
                # Update previous order price for next iteration
                previous_order_price = order_price
            else:
                logger.error(f"Failed to place GTT order {order_number}")
                logger.info(f"DEBUG: Order {i} failed to place. Total placed: {orders_placed}")
        
        logger.info(f"DEBUG: Order placement loop completed. orders_placed={orders_placed}, num_orders={num_orders}")
        logger.info(f"Total GTT orders placed: {orders_placed}/{num_orders}")
        
        # Summary of what happened
        if orders_placed < num_orders:
            logger.warning(f"WARNING: Only {orders_placed} out of {num_orders} orders were placed successfully!")
            logger.warning("This could be due to:")
            logger.warning("1. Order placement failures")
            logger.warning("2. Similar price checks preventing orders")
            logger.warning("3. API errors during order placement")
        else:
            logger.info(f"SUCCESS: All {num_orders} orders were placed successfully!")
        
        # Combine existing and new orders
        all_gtt_orders = existing_gtt_orders + new_gtt_orders
        logger.info(f"DEBUG: existing_gtt_orders count: {len(existing_gtt_orders)}")
        logger.info(f"DEBUG: new_gtt_orders count: {len(new_gtt_orders)}")
        logger.info(f"DEBUG: all_gtt_orders count: {len(all_gtt_orders)}")
        
        # Final save of GTT history with all orders
        logger.info(f"DEBUG: Final save of GTT history with {len(all_gtt_orders)} orders...")
        try:
            save_gtt_history(company_name, all_gtt_orders, logger)
            logger.info(f"DEBUG: Final GTT history save completed successfully")
            
            # Verify the save by reading back the file
            try:
                verification_orders = load_gtt_history(company_name, logger)
                if len(verification_orders) == len(all_gtt_orders):
                    logger.info(f"DEBUG: History file verification successful - {len(verification_orders)} orders saved")
                else:
                    logger.warning(f"DEBUG: History file verification failed - expected {len(all_gtt_orders)}, got {len(verification_orders)}")
            except Exception as e:
                logger.warning(f"DEBUG: Could not verify history file save: {e}")
        except Exception as e:
            logger.error(f"Error in final GTT history save: {e}")
            logger.error("Orders may not be properly saved to history file!")
        
        if orders_placed > 0:
            # Get all GTT orders to verify
            try:
                gtt_orders = kite_api.get_gtt_orders()
                logger.info(f"Total GTT orders in account: {len(gtt_orders)}")
                for order in gtt_orders:
                    logger.info(f"GTT Order: {order}")
            except Exception as e:
                logger.error(f"Error getting GTT orders: {e}")
        else:
            logger.error("No GTT orders were placed successfully")
        
        # Start monitoring thread
        stop_monitoring = threading.Event()
        monitoring_thread = threading.Thread(
            target=monitor_and_manage_sell_orders,
            args=(kite_api, breeze_api, company_name, stock_exchange, all_gtt_orders, logger, stop_monitoring)
        )
        monitoring_thread.daemon = True
        monitoring_thread.start()
        
        # Set up tick data handling for real-time monitoring
        try:
            logger.info("Setting up real-time tick data monitoring...")
            
            # Check if WebSocket is already connected
            if hasattr(breeze_api, 'breeze') and hasattr(breeze_api.breeze, 'sio') and breeze_api.breeze.sio.connected:
                logger.info("WebSocket already connected, skipping connection setup")
            else:
                # Connect to WebSocket for real-time data
                breeze_api.connect_socket()
                logger.info("Connected to Breeze WebSocket for real-time data")
            
            # Get stock token for tick data
            stock_token = breeze_api.get_icici_token_name(company_name)
            logger.info(f"Stock token for tick data: {stock_token}")
            
            # Set up tick handler
            def tick_handler(tick_data):
                handle_tick_data(tick_data, kite_api, breeze_api, company_name, stock_exchange, all_gtt_orders, logger)
            
            breeze_api.set_on_ticks(tick_handler)
            logger.info("Tick handler set up successfully")
            
            # Subscribe to stock feed
            breeze_api.subscribe_feed_token(stock_token)
            logger.info(f"Subscribed to real-time feed for {company_name}")
            
            logger.info("Real-time tick data monitoring is now active!")
            logger.info("The system will now respond to price changes in real-time")
            
        except Exception as e:
            logger.warning(f"Could not set up tick data monitoring: {e}")
            logger.info("Continuing with 5-minute quote-based monitoring only")
        
        logger.info("GTT order monitoring started.")
        logger.info("Monitoring will automatically stop when market closes for 1 hour.")
        logger.info("Press Ctrl+C to stop manually.")
        
        # Keep main thread alive and check for shutdown conditions
        try:
            while not stop_monitoring.is_set():
                time.sleep(30)  # Check every 30 seconds instead of every minute
                
                # Check if monitoring thread is still alive
                if not monitoring_thread.is_alive():
                    logger.info("Monitoring thread has stopped. Exiting main thread.")
                    break
                    
        except KeyboardInterrupt:
            logger.info("Received interrupt signal. Stopping monitoring...")
            stop_monitoring.set()
            monitoring_thread.join(timeout=10)
            logger.info("Monitoring stopped by user.")
            
            # Cleanup WebSocket connection on interrupt
            try:
                if hasattr(breeze_api, 'breeze') and hasattr(breeze_api.breeze, 'sio'):
                    if breeze_api.breeze.sio.connected:
                        logger.info("Cleaning up WebSocket connection on interrupt...")
                        breeze_api.disconnect_socket()
                        logger.info("WebSocket connection closed on interrupt")
                    else:
                        logger.info("WebSocket already disconnected on interrupt")
            except Exception as e:
                logger.warning(f"Error during WebSocket cleanup on interrupt: {e}")
        
        # Wait for monitoring thread to finish
        if monitoring_thread.is_alive():
            logger.info("Waiting for monitoring thread to finish...")
            monitoring_thread.join(timeout=30)
        
        # Cleanup WebSocket connection
        try:
            logger.info("Cleaning up WebSocket connection...")
            # Check if WebSocket is connected before trying to disconnect
            if hasattr(breeze_api, 'breeze') and hasattr(breeze_api.breeze, 'sio'):
                if breeze_api.breeze.sio.connected:
                    breeze_api.disconnect_socket()
                    logger.info("WebSocket connection closed")
                else:
                    logger.info("WebSocket already disconnected, skipping cleanup")
            else:
                logger.info("WebSocket not initialized, skipping cleanup")
        except Exception as e:
            logger.warning(f"Error during WebSocket cleanup: {e}")
            # Don't let WebSocket cleanup errors affect the main program
            logger.info("Continuing with program completion despite WebSocket cleanup error")
        
        logger.info("GTT Fall Buy strategy completed.")
        
    except KeyboardInterrupt:
        logger.info("Program terminated by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}\n{traceback.format_exc()}")
        sys.exit(1)
    finally:
        cleanup_on_exit()


def detect_and_update_triggered_orders_from_history(kite_api: KiteConnectAPI, company_name: str, stock_exchange: str, 
                                                   gtt_orders: List[Dict[str, Any]], logger: logging.Logger) -> tuple:
    """
    Detect triggered orders by comparing history file with current API orders
    and update the history file accordingly. This function prioritizes the history file.
    
    Parameters:
    - kite_api: Initialized Kite API instance
    - company_name: Name of the company
    - stock_exchange: Stock exchange
    - gtt_orders: List of GTT orders from history file
    - logger: Logger instance
    
    Returns:
    - tuple: (updated_orders, triggered_orders_detected, total_shares, avg_price)
    """
    try:
        logger.info("=== Checking for triggered orders using history file ===")
        
        # Get current GTT orders from API (only for comparison)
        try:
            current_gtt_orders = kite_api.get_gtt_orders()
            logger.info(f"Retrieved {len(current_gtt_orders)} current GTT orders from API")
            
            # Debug: Log all current GTT orders for troubleshooting
            for i, order in enumerate(current_gtt_orders):
                trading_symbol = order.get('condition', {}).get('tradingsymbol', '')
                order_id = order.get('id')
                status = order.get('status', 'UNKNOWN')
                transaction_type = order.get('orders', [{}])[0].get('transaction_type', 'UNKNOWN')
                logger.info(f"API Order {i+1}: ID={order_id}, Symbol={trading_symbol}, Type={transaction_type}, Status={status}")
                
        except Exception as e:
            logger.error(f"Error getting current GTT orders: {e}")
            current_gtt_orders = []
        
        # Create a mapping of order ID to status for detailed analysis
        current_order_status_map = {}
        company_orders_found = 0
        
        for order in current_gtt_orders:
            # Only consider orders for our target company
            trading_symbol = order.get('condition', {}).get('tradingsymbol', '')
            if trading_symbol.upper() == company_name.upper():
                order_id = order.get('id')
                status = order.get('status', 'UNKNOWN')
                if order_id:
                    current_order_status_map[str(order_id)] = status
                    company_orders_found += 1
                    logger.info(f"Found {company_name} order in API: ID={order_id}, Status={status}")
        
        logger.info(f"Found {company_orders_found} {company_name} orders in API")
        logger.info(f"Order status mapping: {current_order_status_map}")
        
        # Debug: Log all history orders for troubleshooting
        logger.info("=== History File Orders ===")
        for i, order in enumerate(gtt_orders):
            trigger_id = order.get('trigger_id')
            trading_symbol = order.get('trading_symbol', '')
            status = order.get('status', 'UNKNOWN')
            transaction_type = order.get('transaction_type', 'UNKNOWN')
            logger.info(f"History Order {i+1}: ID={trigger_id}, Symbol={trading_symbol}, Type={transaction_type}, Status={status}")
        
        # Check history file orders against current API orders
        updated_orders = []
        triggered_orders_detected = []
        history_updated = False
        
        for order in gtt_orders:
            trigger_id = order.get('trigger_id')
            current_status = order.get('status', 'UNKNOWN')
            trading_symbol = order.get('trading_symbol', '')
            
            # Only process orders for our target company
            if trading_symbol.upper() != company_name.upper():
                updated_orders.append(order)
                continue
            
            # Convert trigger_id to string for consistent comparison
            trigger_id_str = str(trigger_id) if trigger_id else None
            
            # Check if this order is still active in the API
            if current_status in ['ACTIVE', 'PENDING', 'OPEN']:
                if trigger_id_str and trigger_id_str not in current_order_status_map:
                    # Order was active in history but not found in current API - it was triggered!
                    logger.info(f"TRIGGERED ORDER DETECTED: {trigger_id} ({trading_symbol} {order.get('transaction_type')} {order.get('quantity')} shares @ {order.get('price')})")
                    logger.info(f"Order not found in current API - marking as COMPLETE (assumed successfully executed)")
                    order['status'] = 'COMPLETE'
                    order['triggered_at'] = datetime.now().isoformat()
                    triggered_orders_detected.append(order)
                    history_updated = True
                elif trigger_id_str and trigger_id_str in current_order_status_map:
                    api_status = current_order_status_map[trigger_id_str]
                    logger.info(f"Order {trigger_id} found in API with status: {api_status}")
                    
                    # Check if the order was triggered and determine if it was successful
                    if api_status.upper() in ['TRIGGERED', 'COMPLETE', 'FILLED']:
                        logger.info(f"Order {trigger_id} was triggered with status: {api_status}")
                        
                        # For triggered orders, we need to check if they were actually filled
                        # A triggered order could be:
                        # - "triggered" but not yet filled (still pending)
                        # - "triggered" and successfully filled (completed)
                        # - "triggered" but failed to fill (cancelled/rejected)
                        
                        if api_status.upper() == 'TRIGGERED':
                            # Order was triggered but we need to check if it was actually filled
                            # For now, we'll assume it was filled if it's been triggered
                            # In a real implementation, you might want to check order history or positions
                            logger.info(f"Order {trigger_id} status is 'triggered' - assuming successfully executed")
                            order['status'] = 'COMPLETE'
                            order['triggered_at'] = datetime.now().isoformat()
                            triggered_orders_detected.append(order)
                            history_updated = True
                        elif api_status.upper() in ['COMPLETE', 'FILLED']:
                            # Order was successfully filled
                            logger.info(f"Order {trigger_id} was successfully executed (status: {api_status})")
                            order['status'] = 'COMPLETE'
                            order['triggered_at'] = datetime.now().isoformat()
                            triggered_orders_detected.append(order)
                            history_updated = True
                        else:
                            logger.warning(f"Order {trigger_id} has unexpected status: {api_status}")
                    elif api_status.upper() in ['CANCELLED', 'REJECTED', 'FAILED']:
                        # Order was triggered but failed to execute
                        logger.warning(f"Order {trigger_id} was triggered but failed to execute (status: {api_status})")
                        order['status'] = 'FAILED'
                        order['failed_at'] = datetime.now().isoformat()
                        order['failure_reason'] = f"API status: {api_status}"
                        history_updated = True
                    else:
                        logger.debug(f"Order {trigger_id} still active with status: {api_status}")
                else:
                    logger.warning(f"Order {trigger_id} has no trigger_id or trigger_id is None")
            elif current_status in ['TRIGGERED', 'COMPLETE', 'FILLED']:
                # Order is already marked as triggered/completed in history - include it for sell order calculation
                logger.info(f"Order {trigger_id} already triggered/completed with status: {current_status} - including for sell order calculation")
                if current_status == 'TRIGGERED':
                    # Update to COMPLETE if still marked as TRIGGERED
                    order['status'] = 'COMPLETE'
                    order['triggered_at'] = datetime.now().isoformat()
                    history_updated = True
                triggered_orders_detected.append(order)
            else:
                logger.debug(f"Order {trigger_id} has status: {current_status} (not active or triggered)")
            
            updated_orders.append(order)
        
        # Calculate total shares and average price from completed buy orders
        total_shares = 0
        total_value = 0
        
        for order in updated_orders:
            if (order.get('transaction_type') == 'BUY' and 
                order.get('status') in ['COMPLETE', 'TRIGGERED', 'FILLED'] and
                order.get('trading_symbol', '').upper() == company_name.upper()):
                quantity = order.get('quantity', 0)
                price = order.get('price', 0)
                total_shares += quantity
                total_value += quantity * price
                logger.info(f"EXECUTED ORDER: {order.get('trigger_id')} - {quantity} shares @ {price:.2f}")
        
        avg_price = total_value / total_shares if total_shares > 0 else 0
        
        # Save updated history if any orders were triggered
        if history_updated:
            save_gtt_history(company_name, updated_orders, logger)
            logger.info(f"HISTORY UPDATED: History file updated with {len(triggered_orders_detected)} triggered orders")
        
        logger.info(f"SUMMARY: {len(triggered_orders_detected)} orders triggered, {total_shares} total shares, avg price: {avg_price:.2f}")
        
        return updated_orders, len(triggered_orders_detected) > 0, total_shares, avg_price
        
    except Exception as e:
        logger.error(f"Error detecting triggered orders: {e}")
        return gtt_orders, False, 0, 0


def manage_sell_orders_based_on_history(kite_api: KiteConnectAPI, company_name: str, stock_exchange: str, 
                                       gtt_orders: List[Dict[str, Any]], current_price: float, logger: logging.Logger) -> bool:
    """
    Manage sell orders based on history file data (prioritizes history over API)
    
    Parameters:
    - kite_api: Initialized Kite API instance
    - company_name: Name of the company
    - stock_exchange: Stock exchange
    - gtt_orders: List of GTT orders from history file
    - current_price: Current stock price
    - logger: Logger instance
    
    Returns:
    - bool: True if sell order was placed/updated, False otherwise
    """
    try:
        logger.info("=== Managing sell orders based on history file ===")
        
        # Calculate total shares and average price from completed buy orders in history
        total_shares = 0
        total_value = 0
        
        for order in gtt_orders:
            if (order.get('transaction_type') == 'BUY' and 
                order.get('status') in ['COMPLETE', 'TRIGGERED', 'FILLED'] and
                order.get('trading_symbol', '').upper() == company_name.upper()):
                quantity = order.get('quantity', 0)
                price = order.get('price', 0)
                total_shares += quantity
                total_value += quantity * price
        
        avg_price = total_value / total_shares if total_shares > 0 else 0
        
        if total_shares == 0:
            logger.info("No executed buy orders found in history - no sell order needed")
            return False
        
        logger.info(f"HISTORY SHOWS: {total_shares} shares bought at avg price: {avg_price:.2f}")
        
        # Calculate profit target based on share count
        if total_shares <= 3:
            profit_percentage = 3
            raw_profit_target = avg_price * 1.03
        else:
            profit_percentage = 2
            raw_profit_target = avg_price * 1.02
        
        # Get tick size and round profit target
        tick_size = get_tick_size_for_stock(company_name, current_price)
        profit_target = round_to_tick(raw_profit_target, tick_size)
        sell_price = profit_target
        
        logger.info(f"PROFIT TARGET: {profit_percentage}% profit target: {raw_profit_target:.4f} -> {profit_target:.2f}")
        
        # Check if we already have a sell order in history
        existing_sell_order = None
        for order in gtt_orders:
            if (order.get('transaction_type') == 'SELL' and 
                order.get('trading_symbol', '').upper() == company_name.upper() and
                order.get('status') in ['ACTIVE', 'PENDING', 'OPEN']):
                existing_sell_order = order
                break
        
        # Get current sell orders from API to check if we need to place/update
        try:
            current_gtt_orders = kite_api.get_gtt_orders()
            api_sell_orders = [order for order in current_gtt_orders 
                              if (order.get('condition', {}).get('tradingsymbol', '').upper() == company_name.upper() and
                                  order.get('orders', [{}])[0].get('transaction_type') == 'SELL')]
        except Exception as e:
            logger.error(f"Error getting current GTT orders: {e}")
            api_sell_orders = []
        
        # Place or update sell order
        if api_sell_orders:
            # Update existing sell order
            api_sell_order = api_sell_orders[0]
            current_quantity = api_sell_order.get('orders', [{}])[0].get('quantity', 0)
            current_price = api_sell_order.get('orders', [{}])[0].get('price', 0)
            
            if current_quantity != total_shares or abs(current_price - sell_price) > 0.01:
                try:
                    logger.info(f"UPDATING SELL ORDER: Quantity: {current_quantity}->{total_shares}, Price: {current_price:.2f}->{sell_price:.2f}")
                    
                    # Calculate trigger price for sell order
                    trigger_price, _ = calculate_gtt_prices(
                        current_price=sell_price,
                        drop_percentage=1.2,
                        tick_size=tick_size,
                        order_type="SELL",
                        price_delta_ticks=1
                    )
                    
                    kite_api.modify_gtt_order(
                        gtt_order_id=api_sell_order.get('id'),
                        trading_symbol=company_name,
                        exchange=stock_exchange,
                        transaction_type="SELL",
                        quantity=total_shares,
                        price=sell_price,
                        trigger_price=trigger_price
                    )
                    
                    # Update history file
                    if existing_sell_order:
                        existing_sell_order['quantity'] = total_shares
                        existing_sell_order['price'] = sell_price
                        existing_sell_order['trigger_price'] = trigger_price
                        existing_sell_order['updated_at'] = datetime.now().isoformat()
                    else:
                        # Add new sell order to history
                        sell_order_details = {
                            'trigger_id': api_sell_order.get('id'),
                            'trading_symbol': company_name,
                            'exchange': stock_exchange,
                            'transaction_type': 'SELL',
                            'quantity': total_shares,
                            'price': sell_price,
                            'trigger_price': trigger_price,
                            'order_type': 'LIMIT',
                            'validity': 'DAY',
                            'date_placed': datetime.now().isoformat(),
                            'status': 'ACTIVE',
                            'profit_target': profit_target,
                            'avg_purchase_price': avg_price,
                            'profit_percentage': profit_percentage
                        }
                        gtt_orders.append(sell_order_details)
                    
                    save_gtt_history(company_name, gtt_orders, logger)
                    logger.info("SUCCESS: Sell order updated successfully")
                    return True
                    
                except Exception as e:
                    logger.error(f"ERROR: Error updating sell order: {e}")
                    return False
            else:
                logger.info(f"SUCCESS: Sell order already up to date - {total_shares} shares @ {sell_price:.2f}")
                return True
        else:
            # Place new sell order
            try:
                logger.info(f"PLACING NEW SELL ORDER: {total_shares} shares @ {sell_price:.2f}")
                
                # Calculate trigger price for sell order
                trigger_price, _ = calculate_gtt_prices(
                    current_price=sell_price,
                    drop_percentage=1.2,
                    tick_size=tick_size,
                    order_type="SELL",
                    price_delta_ticks=1
                )
                
                sell_order_id = place_gtt_order(
                    kite_api=kite_api,
                    trading_symbol=company_name,
                    exchange=stock_exchange,
                    transaction_type="SELL",
                    quantity=total_shares,
                    price=sell_price,
                    trigger_price=trigger_price,
                    current_price=current_price
                )
                
                if sell_order_id:
                    # Add to history file
                    sell_order_details = {
                        'trigger_id': sell_order_id,
                        'trading_symbol': company_name,
                        'exchange': stock_exchange,
                        'transaction_type': 'SELL',
                        'quantity': total_shares,
                        'price': sell_price,
                        'trigger_price': trigger_price,
                        'order_type': 'LIMIT',
                        'validity': 'DAY',
                        'date_placed': datetime.now().isoformat(),
                        'status': 'ACTIVE',
                        'profit_target': profit_target,
                        'avg_purchase_price': avg_price,
                        'profit_percentage': profit_percentage
                    }
                    gtt_orders.append(sell_order_details)
                    save_gtt_history(company_name, gtt_orders, logger)
                    logger.info("SUCCESS: New sell order placed successfully")
                    return True
                else:
                    logger.error("ERROR: Failed to place sell order")
                    return False
                    
            except Exception as e:
                logger.error(f"ERROR: Error placing sell order: {e}")
                return False
        
    except Exception as e:
        logger.error(f"Error managing sell orders: {e}")
        return False


if __name__ == "__main__":
    # Hardcoded values for direct execution
    # COMPANY_NAME = "HINDALCO"  # Change this to your desired company
    COMPANY_NAME = "ONGC"  # Change this to your desired company
    STOCK_EXCHANGE = "NSE"     # Change this to your desired exchange
    N = 5  # Change this to specify number of GTT orders to place (should be 5 for proper fall buy strategy)
    CANCEL_ORDERS = False  # Set to True to cancel all existing GTT orders
    
    print(f"Starting GTT Fall Buy strategy:")
    print(f"  Company: {COMPANY_NAME}")
    print(f"  Exchange: {STOCK_EXCHANGE}")
    print(f"  Number of orders: {N}")
    print(f"  Cancel existing orders: {CANCEL_ORDERS}")
    print("-" * 50)
    
    main(COMPANY_NAME, STOCK_EXCHANGE, N, CANCEL_ORDERS) 
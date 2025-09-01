import logging
import sys
import time
import traceback
from datetime import datetime, time as dt_time
import pytz
from kite_utils import signal_handler, setup_logger
from breeze_sdk_api import BreezeApi
from fall_buy import FallBuy

def is_market_hours() -> bool:
    """Check if current time is within Indian market hours (9:15 AM to 3:30 PM IST)"""
    # Get current time in IST
    ist = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(ist).time()
    
    # Define market hours
    market_start = dt_time(9, 15)  # 9:15 AM
    market_end = dt_time(15, 30)   # 3:30 PM
    
    return market_start <= current_time <= market_end

def cleanup_pending_orders(fall_buy: FallBuy, logger: logging.Logger) -> None:
    """Clean up pending orders when market hours end"""
    try:
        if not fall_buy.pending_orders:
            logger.info("No pending orders to clean up")
            return

        logger.info(f"Cleaning up {len(fall_buy.pending_orders)} pending orders...")
        
        for order in fall_buy.pending_orders[:]:  # Create a copy to safely modify during iteration
            try:
                # Get current order status
                status = fall_buy.get_order_status(order['order_id'])
                
                if status == 'COMPLETE':
                    logger.info(f"Order {order['order_id']} was completed. Moving to placed orders.")
                    fall_buy.move_to_placed_orders(order)
                else:
                    # Move to failed orders with reason
                    logger.info(f"Moving order {order['order_id']} to failed orders due to market hours end")
                    fall_buy.update_failed_orders(
                        type=order['type'],
                        order_id=order['order_id'],
                        shares_available_to_sell=order['quantity'],
                        cur_price=order['price'],
                        error="Order cancelled due to market hours end"
                    )
                    fall_buy.pending_orders.remove(order)
                    
            except Exception as e:
                logger.error(f"Error cleaning up order {order['order_id']}: {e}")
                # Still move to failed orders even if status check fails
                fall_buy.update_failed_orders(
                    type=order['type'],
                    order_id=order['order_id'],
                    shares_available_to_sell=order['quantity'],
                    cur_price=order['price'],
                    error=f"Error during cleanup: {str(e)}"
                )
                fall_buy.pending_orders.remove(order)
        
        logger.info("Pending orders cleanup completed")
        
    except Exception as e:
        logger.error(f"Error during pending orders cleanup: {e}\n{traceback.format_exc()}")

def main(trading_symbol: str = "ITC"):
    """Main function to demonstrate Kite Connect API and Breeze SDK usage for a single company"""
    # Set up logger for this module with trading symbol
    logger = setup_logger(__name__, trading_symbol)
    
    try:
        # Initialize Breeze API
        try:
            breeze_api = BreezeApi(symbol=trading_symbol)
            logger.info("Successfully initialized Breeze API")
        except ValueError as ve:
            if "Missing required Breeze API parameters" in str(ve):
                logger.error(f"Failed to initialize Breeze API: {ve}")
                BreezeApi.print_config_instructions()
            else:
                logger.error(f"Failed to initialize Breeze API: {ve}\n{traceback.format_exc()}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to initialize Breeze API: {e}\n{traceback.format_exc()}")
            sys.exit(1)

        # Initialize FallBuy strategy
        try:
            fall_buy = FallBuy(exchange="NSE", stock_name=trading_symbol, demo_mode=False)
            logger.info("Successfully initialized FallBuy strategy")
        except ValueError as ve:
            logger.error(f"Failed to initialize FallBuy strategy: {ve}\n{traceback.format_exc()}")
            sys.exit(1)

        # In demo mode, fall_buy.kite_api will be None since _init_kite_api() is not called
        # So this code block will raise an AttributeError when trying to access fall_buy.kite_api.order_history
        # We should check if we're in demo mode first
        
        if fall_buy.demo_mode:
            try:
                # Skip Kite API calls since we're in demo mode
                logger.info("Running in demo mode - skipping Kite API calls")
                
                breeze_api.start_api()
                breeze_api.connect_socket()
                logger.info("Connected to Breeze WebSocket for live data")

                # Get stock token for Breeze API
                stock_token = breeze_api.get_icici_token_name(trading_symbol)
                logger.info(f"Stock token: {stock_token}")
                
                # Set up tick handler for Breeze API
                breeze_api.set_on_ticks(fall_buy.get_tick)
                logger.info("Successfully set up tick handler")

                # Subscribe to stock feed
                logger.info(f"Subscribing to feed for token: {stock_token}")
                breeze_api.subscribe_feed_token(stock_token)
                logger.info("Successfully subscribed to stock feed")
                
                # Run until market hours end
                logger.info("Starting to receive market data...")
                while fall_buy.is_market_hours():
                    time.sleep(60)  # Check every 1 minute
                
                # Cleanup
                logger.info("Market hours ended, cleaning up...")
                fall_buy.cleanup_pending_orders()
                breeze_api.unsubscribe_feed(stock_token)
                breeze_api.disconnect_socket()
                logger.info("Successfully disconnected from Breeze WebSocket")
                
            except Exception as e:
                logger.error(f"Error in main execution: {e}\n{traceback.format_exc()}")
                sys.exit(1)
        else:
            with signal_handler(fall_buy.kite_api.order_history):
                try:
                    # Get account details from Kite
                    account_details = fall_buy.get_account_details()
                    logger.info("Kite account details retrieved successfully")
                    breeze_api.start_api()
                    logger.info(f"trading_symbol = {breeze_api.get_customer_details()}")

                    breeze_api.connect_socket()
                    logger.info("Connected to Breeze WebSocket for live data")

                    # Get stock token for Breeze API
                    stock_token = breeze_api.get_icici_token_name(trading_symbol)
                    logger.info(f"Stock token: {stock_token}")
                    
                    # Set up tick handler for Breeze API
                    breeze_api.set_on_ticks(fall_buy.get_tick)
                    logger.info("Successfully set up tick handler")

                    # Subscribe to stock feed
                    logger.info(f"Subscribing to feed for token: {stock_token}")
                    breeze_api.subscribe_feed_token(stock_token)
                    logger.info("Successfully subscribed to stock feed")
                    
                    # Run until market hours end
                    logger.info("Starting to receive market data...")
                    while fall_buy.is_market_hours():
                        time.sleep(60)  # Check every 1 minute
                    
                    # Cleanup
                    logger.info("Market hours ended, cleaning up...")
                    fall_buy.cleanup_pending_orders()
                    breeze_api.unsubscribe_feed(stock_token)
                    breeze_api.disconnect_socket()
                    logger.info("Successfully disconnected from Breeze WebSocket")
                    
                except Exception as e:
                    logger.error(f"Error in main execution: {e}\n{traceback.format_exc()}")
                    sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Program terminated by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}\n{traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main(trading_symbol="HINDALCO") 
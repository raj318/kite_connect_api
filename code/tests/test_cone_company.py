import logging
import sys
import time
import traceback
import os
import sys
import json
from datetime import datetime

# Add parent directory to path to allow imports from code/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kite_utils import signal_handler, setup_logger
from breeze_sdk_api import BreezeApi
from fall_buy import FallBuy

def load_historical_data(file_path: str) -> list:
    """
    Load historical data from JSON file
    
    Parameters:
    - file_path: Path to the JSON file
    
    Returns:
    List of historical data points
    """
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        return data['data']
    except Exception as e:
        logger.error(f"Error loading historical data: {e}")
        raise

def main():
    """Main function to test trading strategy with historical data"""
    try:
        # Set up logger
        global logger
        logger = setup_logger(__name__, "ITC")
        
        # Initialize FallBuy strategy in demo mode
        logger.info("Initializing FallBuy strategy...")
        fall_buy = FallBuy(exchange="NSE", stock_name="ITC", demo_mode=True)
        
        # Load historical data
        history_file = os.path.join('workdir', 'history', 'ITC_breeze_history_3years.json')
        logger.info(f"Loading historical data from {history_file}")
        historical_data = load_historical_data(history_file)
        
        # Process each data point
        logger.info(f"Processing {len(historical_data)} data points...")
        for data_point in historical_data:
            try:
                # Create tick data format
                tick = {
                    'last': float(data_point['close']),
                    'open': float(data_point['open']),
                    'high': float(data_point['high']),
                    'low': float(data_point['low']),
                    'volume': int(data_point['volume']),
                    'datetime': data_point['datetime']
                }
                
                # Process tick
                logger.info(f"Processing tick for {tick['datetime']} at price {tick['last']}")
                fall_buy.on_tick(tick)
                
                # Simulate 1-minute delay
                time.sleep(0.1)  # Reduced delay for testing
                
            except Exception as e:
                logger.error(f"Error processing data point: {e}")
                continue
            
        logger.info("Historical data processing completed")
        
    except Exception as e:
        logger.error(f"Error in main process: {e}")
        raise

if __name__ == "__main__":
    main() 
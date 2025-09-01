import json
import os
from datetime import datetime, timedelta
import logging
import traceback
from kite_utils import setup_logger, load_config
from breeze_sdk_api import BreezeApi

def fetch_stock_history(symbol: str, years: int = 5) -> dict:
    """
    Fetch historical stock data using Breeze API
    
    Parameters:
    - symbol: Stock symbol (e.g., "ITC" for NSE)
    - years: Number of years of historical data to fetch
    
    Returns:
    Dictionary containing historical data
    """
    try:
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years*365)
        
        logger.info(f"Fetching data for {symbol} from {start_date.date()} to {end_date.date()}")
        
        # Initialize Breeze API
        config = load_config()
        breeze = BreezeApi(symbol=symbol)
        
        # Get historical data
        hist_data = breeze.get_historical_one_min_data(
            stock_code=symbol,
            exchange_code="NSE",
            start_date=start_date.strftime("%d/%m/%Y"),
            end_date=end_date.strftime("%d/%m/%Y"),
        )
        
        if not hist_data:
            raise ValueError(f"No historical data found for {symbol}")
            
        logger.info(f"Successfully fetched {len(hist_data)} days of data")
        
        # Convert to dictionary format
        history_data = {
            'symbol': symbol,
            'exchange': 'NSE',
            'last_updated': datetime.now().isoformat(),
            'data': hist_data,
            'info': {
                'name': symbol,
                'exchange': 'NSE',
                'currency': 'INR'
            }
        }
        
        return history_data
        
    except Exception as e:
        logger.error(f"Error fetching stock history: {str(e)}\n{traceback.format_exc()}")
        raise

def save_history_to_json(data: dict, symbol: str, years: int) -> None:
    """
    Save historical data to JSON file
    
    Parameters:
    - data: Historical data dictionary
    - symbol: Stock symbol
    - years: Number of years of data
    """
    try:
        # Create history directory if it doesn't exist
        history_dir = os.path.join('workdir', 'history')
        os.makedirs(history_dir, exist_ok=True)
        
        # Save to JSON file
        file_path = os.path.join(history_dir, f'{symbol}_breeze_history_{years}years.json')
        
        # Verify data before saving
        if not data or 'data' not in data or not data['data']:
            raise ValueError("No data to save")
            
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
            
        logger.info(f"Historical data saved to {file_path}")
        logger.info(f"Total records saved: {len(data['data'])}")
        
    except Exception as e:
        logger.error(f"Error saving historical data: {str(e)}\n{traceback.format_exc()}")
        raise

def main():
    """Main function to fetch and save stock history"""
    try:
        # Set up logger
        global logger
        logger = setup_logger(__name__, "ITC")
        
        logger.info("Starting historical data fetch process...")
        
        # Fetch stock history
        logger.info("Fetching stock history...")
        history_data = fetch_stock_history("ITC", years=3)
        
        # Save to JSON file
        logger.info("Saving historical data...")
        save_history_to_json(history_data, "ITC", 3)
        
        logger.info("Process completed successfully")
        
    except Exception as e:
        logger.error(f"Error in main process: {str(e)}\n{traceback.format_exc()}")
        raise

if __name__ == "__main__":
    main() 
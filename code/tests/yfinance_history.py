import yfinance as yf
import json
import os
from datetime import datetime, timedelta
import logging
import traceback
import time
from kite_utils import setup_logger

def fetch_stock_history(symbol: str, years: int = 5, max_retries: int = 3) -> dict:
    """
    Fetch historical stock data using yfinance
    
    Parameters:
    - symbol: Stock symbol (e.g., "ITC.NS" for NSE)
    - years: Number of years of historical data to fetch
    - max_retries: Maximum number of retries for fetching data
    
    Returns:
    Dictionary containing historical data
    """
    try:
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years*365)
        
        logger.info(f"Fetching data for {symbol} from {start_date.date()} to {end_date.date()}")
        
        # Fetch data with retries
        for attempt in range(max_retries):
            try:
                # Fetch data
                stock = yf.Ticker(symbol)
                
                # Get historical data first
                hist = stock.history(start=start_date, end=end_date)
                
                # Verify if we got any data
                if hist.empty:
                    raise ValueError(f"No historical data found for {symbol}")
                
                # Try to get stock info
                try:
                    info = stock.info
                except:
                    info = {}
                
                logger.info(f"Successfully fetched {len(hist)} days of data")
                
                # Convert to dictionary format
                history_data = {
                    'symbol': symbol,
                    'last_updated': datetime.now().isoformat(),
                    'data': hist.to_dict('records'),
                    'info': {
                        'name': info.get('longName', ''),
                        'sector': info.get('sector', ''),
                        'industry': info.get('industry', ''),
                        'market_cap': info.get('marketCap', 0),
                        'currency': info.get('currency', ''),
                        'exchange': info.get('exchange', '')
                    }
                }
                
                return history_data
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Attempt {attempt + 1} failed: {str(e)}. Retrying...")
                    time.sleep(2)  # Wait before retrying
                else:
                    raise
        
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
        file_path = os.path.join(history_dir, f'{symbol.replace(".", "_")}_history_{years}years.json')
        
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
        logger = setup_logger(__name__, "SBIN")
        
        logger.info("Starting historical data fetch process...")
        
        # Fetch ITC stock history
        logger.info("Fetching ITC stock history...")
        history_data = fetch_stock_history("SBIN.NS", years=5)
        
        # Save to JSON file
        logger.info("Saving historical data...")
        save_history_to_json(history_data, "SBIN", 5)
        
        logger.info("Process completed successfully")
        
    except Exception as e:
        logger.error(f"Error in main process: {str(e)}\n{traceback.format_exc()}")
        raise

if __name__ == "__main__":
    main() 
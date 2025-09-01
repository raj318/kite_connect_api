import os
import sys
import logging
from datetime import datetime, time as dt_time
import pytz
import time
import traceback
from typing import Dict, Any
import yaml

# Add parent directory to path to allow imports from code/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kite_utils import setup_logger, load_config
from kite_connect_api import KiteConnectAPI
from kiteconnect import KiteConnect

# Import KiteConnect exceptions for better error handling
try:
    from kiteconnect.exceptions import TokenException
except ImportError:
    TokenException = Exception  # fallback if not available

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
        print(f"Error checking market hours: {e}")
        return False

def print_breeze_config_instructions():
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

def print_config_fix_instructions():
    print("\n--- KITE CONNECT CONFIGURATION INSTRUCTIONS ---")
    print("1. Open your config/config.yaml file.")
    print("2. Under 'kite_connect', ensure you have the correct values for:")
    print("   - api_key: Your Kite API key (from https://developers.kite.trade/apps)")
    print("   - api_secret: Your Kite API secret")
    print("   - access_token: Your current session access token (expires daily)")
    print("3. If your access_token is missing or expired:")
    print("   a. Remove or comment out the 'access_token' line in config.yaml.")
    print("   b. Run this script again. It will print a login URL.")
    print("   c. Open the URL, log in, and copy the 'request_token' from the redirect URL.")
    print("   d. Paste the 'request_token' into config.yaml under 'kite_connect'.")
    print("   e. Run this script again. It will generate and save a new access_token.")
    print("4. If you see 'Incorrect api_key or access_token', double-check your credentials.")
    print("5. For more help, see: https://kite.trade/docs/connect/v3/user/ ")
    print("--------------------------------------\n")

def update_config_token(token_type: str, token_value: str) -> None:
    """Update a single token in config file while preserving all other values.
    
    Args:
        token_type: Type of token to update ('access_token' or 'session_id')
        token_value: New token value to save
    """
    try:
        # Read existing config file
        with open('config/config.yaml', 'r') as f:
            existing_config = yaml.safe_load(f)
        
        # Update only the specified token in the appropriate section
        if token_type == 'access_token':
            if 'kite_connect' not in existing_config:
                existing_config['kite_connect'] = {}
            existing_config['kite_connect']['access_token'] = token_value
        elif token_type == 'session_id':
            if 'breeze_api' not in existing_config:
                existing_config['breeze_api'] = {}
            existing_config['breeze_api']['session_id'] = token_value
        else:
            raise ValueError(f"Invalid token type: {token_type}")
        
        # Save updated config while preserving other sections
        with open('config/config.yaml', 'w') as f:
            yaml.dump(existing_config, f, default_flow_style=False)
            
        print(f"\nToken renewed successfully! New {token_type} has been saved to config.yaml")
        
    except Exception as e:
        print(f"Error updating {token_type}: {e}")
        raise

def handle_token_renewal(config):
    """Handle token renewal process"""
    try:
        # Initialize KiteConnect with API key
        kite = KiteConnect(api_key=config['kite_connect']['api_key'])
        
        # Get login URL
        login_url = kite.login_url()
        print("\n=== TOKEN RENEWAL REQUIRED ===")
        print("Please follow these steps to renew your token:")
        print(f"1. Click this URL to login: {login_url}")
        print("2. After successful login, you'll be redirected to your redirect URL")
        print("3. From the redirect URL, copy the request_token parameter")
        print("4. Update the request_token in your config.yaml file")
        print("\nExample redirect URL format:")
        print("https://your-redirect-url/?request_token=YOUR_REQUEST_TOKEN&action=login&status=success")
        
        # Update config with new request token
        request_token = input("\nEnter your request_token: ").strip()
        if not request_token:
            raise ValueError("Request token is required")
            
        # Generate session
        data = kite.generate_session(request_token, api_secret=config['kite_connect']['api_secret'])
        access_token = data["access_token"]
        
        # Update only the access token
        update_config_token('access_token', access_token)
        return True
        
    except Exception as e:
        print(f"\nError renewing token: {e}\n{traceback.format_exc()}")
        return False

def main():
    """Main function to interact with Kite API and observe responses"""
    # Set up logger
    logger = setup_logger(__name__, "KITE_API")
    logger.info("Starting Kite API interaction")
    
    try:
        # Load configuration
        config = load_config()
        if not config:
            raise ValueError("Failed to load configuration")
            
        # Check Breeze API configuration
        breeze_config = config.get('breeze_api', {})
        required_breeze_params = ['api_token', 'secret_token', 'session_id']
        missing_breeze_params = [param for param in required_breeze_params if param not in breeze_config]
        if missing_breeze_params:
            logger.error(f"Missing required Breeze API parameters: {', '.join(missing_breeze_params)}")
            print_breeze_config_instructions()
            raise ValueError("Missing required Breeze API parameters")
        
        # Initialize Kite API
        kite_api = KiteConnectAPI(trading_symbol="ITC")
        logger.info("Initialized Kite API")
        
        try:
            # Connect to Kite
            kite_api.connect()
            logger.info("Connected to Kite")
        except TokenException:
            logger.warning("Token expired or invalid, attempting renewal")
            if handle_token_renewal(config):
                # Retry connection with new token
                kite_api = KiteConnectAPI(trading_symbol="ITC")
                kite_api.connect()
                logger.info("Connected to Kite with new token")
            else:
                raise Exception("Failed to renew token")
        
        # Run tests during market hours
        logger.info("Starting API tests...")
        while is_market_hours():
            try:
                # 1. Get margin details
                logger.info("\n=== Getting Margin Details ===")
                margin_details = kite_api.kite.margins()
                equity = margin_details.get('equity', {})
                
                # Print available margins
                available = equity.get('available', {})
                print("\nAvailable Margins:")
                print(f"Cash: ₹{available.get('cash', 0):,.2f}")
                print(f"Margin: ₹{available.get('margin', 0):,.2f}")
                print(f"Intraday: ₹{available.get('intraday', 0):,.2f}")
                
                # 2. Get account details
                logger.info("\n=== Getting Account Details ===")
                account_details = kite_api.get_account_details()
                print("\nAccount Details:")
                print(f"Profile: {account_details.get('profile', {})}")
                print(f"Balance: {account_details.get('balance', {})}")
                
                # 3. Get holdings
                logger.info("\n=== Getting Holdings ===")
                holdings = kite_api.kite.holdings()
                print("\nHoldings:")
                for holding in holdings:
                    print(f"\nSymbol: {holding.get('tradingsymbol')}")
                    print(f"Quantity: {holding.get('quantity')}")
                    print(f"Average Price: ₹{holding.get('average_price', 0):,.2f}")
                    print(f"LTP: ₹{holding.get('last_price', 0):,.2f}")
                    print(f"P&L: ₹{holding.get('pnl', 0):,.2f}")
                
                # 4. Get positions
                logger.info("\n=== Getting Positions ===")
                positions = kite_api.kite.positions()
                print("\nPositions:")
                for position in positions.get('net', []):
                    print(f"\nSymbol: {position.get('tradingsymbol')}")
                    print(f"Quantity: {position.get('quantity')}")
                    print(f"Average Price: ₹{position.get('average_price', 0):,.2f}")
                    print(f"LTP: ₹{position.get('last_price', 0):,.2f}")
                    print(f"P&L: ₹{position.get('pnl', 0):,.2f}")
                
                # Wait for 5 minutes before next iteration
                logger.info("\nWaiting 5 minutes before next iteration...")
                time.sleep(300)
                
            except Exception as e:
                logger.error(f"Error during API test iteration: {e}\n{traceback.format_exc()}")
                time.sleep(60)  # Wait a minute before retrying
                continue
        
        logger.info("Market hours ended, test completed")
        
    except TokenException as te:
        logger.error(f"KiteConnect TokenException: {te}\n{traceback.format_exc()}")
        print("\nERROR: Incorrect api_key or access_token for Kite Connect API.")
        print_config_fix_instructions()
    except ValueError as ve:
        if "Missing required Breeze API parameters" in str(ve):
            print("\nERROR: Missing required Breeze API parameters.")
            print_breeze_config_instructions()
        else:
            logger.error(f"ValueError: {ve}\n{traceback.format_exc()}")
            print(f"\nERROR: {ve}")
    except Exception as e:
        logger.error(f"Error: {e}\n{traceback.format_exc()}")
        print(f"\nERROR: {e}")
        print_config_fix_instructions()
    finally:
        logger.info("Kite API interaction completed")

if __name__ == "__main__":
    main() 
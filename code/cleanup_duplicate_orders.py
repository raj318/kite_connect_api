#!/usr/bin/env python3
"""
Script to clean up duplicate GTT orders
This script will identify duplicate orders and cancel them, keeping only the first set of orders.
"""

import json
import os
import sys
import traceback
from datetime import datetime
from typing import List, Dict, Any
from kite_utils import setup_logger
from kite_connect_api import KiteConnectAPI

def load_gtt_history(company_name: str, logger) -> List[Dict[str, Any]]:
    """Load GTT history from JSON file"""
    try:
        file_path = os.path.join('workdir', 'orders', f'{company_name}_gtt_history.json')
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return json.load(f)
        return []
    except Exception as e:
        logger.error(f"Error loading GTT history: {e}")
        return []

def save_gtt_history(company_name: str, gtt_orders: List[Dict[str, Any]], logger) -> None:
    """Save GTT history to JSON file"""
    try:
        # Create orders directory if it doesn't exist
        orders_dir = os.path.join('workdir', 'orders')
        os.makedirs(orders_dir, exist_ok=True)
        
        file_path = os.path.join(orders_dir, f'{company_name}_gtt_history.json')
        with open(file_path, 'w') as f:
            json.dump(gtt_orders, f, indent=4)
        
        logger.info(f"GTT history saved to {file_path}")
    except Exception as e:
        logger.error(f"Error saving GTT history: {e}")

def cleanup_duplicate_orders(company_name: str, logger) -> None:
    """Clean up duplicate GTT orders"""
    try:
        # Initialize Kite API
        kite_api = KiteConnectAPI(trading_symbol=company_name)
        kite_api.connect()
        logger.info("Successfully connected to Kite API")
        
        # Get all GTT orders from exchange
        try:
            all_gtt_orders = kite_api.get_gtt_orders()
            logger.info(f"Found {len(all_gtt_orders)} total GTT orders on exchange")
        except Exception as e:
            logger.error(f"Error getting GTT orders from exchange: {e}")
            return
        
        # Filter active buy orders
        active_buy_orders = [order for order in all_gtt_orders 
                           if order.get('transaction_type') == 'BUY' and 
                           order.get('status') == 'ACTIVE']
        
        logger.info(f"Found {len(active_buy_orders)} active buy orders")
        
        if len(active_buy_orders) <= 5:
            logger.info("No duplicate orders found. All orders are within the expected limit of 5.")
            return
        
        # Group orders by price to identify duplicates
        price_groups = {}
        for order in active_buy_orders:
            price = order.get('price', 0)
            if price not in price_groups:
                price_groups[price] = []
            price_groups[price].append(order)
        
        # Find duplicate prices
        duplicates_to_cancel = []
        orders_to_keep = []
        
        for price, orders in price_groups.items():
            if len(orders) > 1:
                logger.info(f"Found {len(orders)} orders at price {price}")
                # Keep the first order (earliest trigger_id), cancel the rest
                orders.sort(key=lambda x: x.get('trigger_id', ''))
                orders_to_keep.append(orders[0])
                duplicates_to_cancel.extend(orders[1:])
                logger.info(f"Keeping order {orders[0].get('trigger_id')}, canceling {len(orders)-1} duplicates")
            else:
                orders_to_keep.append(orders[0])
        
        logger.info(f"Will keep {len(orders_to_keep)} orders and cancel {len(duplicates_to_cancel)} duplicates")
        
        if not duplicates_to_cancel:
            logger.info("No duplicates found to cancel")
            return
        
        # Cancel duplicate orders
        cancelled_count = 0
        for order in duplicates_to_cancel:
            try:
                trigger_id = order.get('trigger_id')
                if trigger_id:
                    kite_api.kite.delete_gtt_order(trigger_id)
                    logger.info(f"Cancelled duplicate order: {trigger_id}")
                    cancelled_count += 1
                else:
                    logger.warning(f"Order has no trigger_id: {order}")
            except Exception as e:
                logger.error(f"Error cancelling order {order.get('trigger_id')}: {e}")
        
        logger.info(f"Successfully cancelled {cancelled_count} duplicate orders")
        
        # Update history file with only the kept orders
        try:
            # Load current history
            existing_history = load_gtt_history(company_name, logger)
            
            # Remove cancelled orders from history
            cancelled_trigger_ids = {order.get('trigger_id') for order in duplicates_to_cancel}
            updated_history = [order for order in existing_history 
                             if order.get('trigger_id') not in cancelled_trigger_ids]
            
            # Save updated history
            save_gtt_history(company_name, updated_history, logger)
            logger.info(f"Updated history file - removed {len(existing_history) - len(updated_history)} cancelled orders")
            
        except Exception as e:
            logger.error(f"Error updating history file: {e}")
        
        # Verify final state
        try:
            final_orders = kite_api.get_gtt_orders()
            final_active_buy = [order for order in final_orders 
                              if order.get('transaction_type') == 'BUY' and 
                              order.get('status') == 'ACTIVE']
            logger.info(f"Final state: {len(final_active_buy)} active buy orders remaining")
            
            if len(final_active_buy) <= 5:
                logger.info("✅ Cleanup successful! Duplicate orders have been removed.")
            else:
                logger.warning(f"⚠️ Still have {len(final_active_buy)} active buy orders. Manual review may be needed.")
                
        except Exception as e:
            logger.error(f"Error verifying final state: {e}")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}\n{traceback.format_exc()}")

def main():
    """Main function"""
    # You can change this to the company you want to clean up
    company_name = "ONGC"  # Change this to your company
    
    # Set up logger
    logger = setup_logger(__name__, f"{company_name}_cleanup")
    
    logger.info(f"Starting cleanup of duplicate GTT orders for {company_name}")
    
    try:
        cleanup_duplicate_orders(company_name, logger)
        logger.info("Cleanup process completed")
        
    except KeyboardInterrupt:
        logger.info("Cleanup interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error during cleanup: {e}\n{traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main() 
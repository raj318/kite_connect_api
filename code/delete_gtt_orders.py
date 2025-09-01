#!/usr/bin/env python3
"""
GTT Order Deletion Script

This script deletes all active GTT (Good Till Triggered) orders for a given company.
It connects to Kite Connect API, fetches all active GTT orders for the specified company,
and deletes them one by one.

Usage:
    python delete_gtt_orders.py <company_symbol>

Example:
    python delete_gtt_orders.py ITC
    python delete_gtt_orders.py RELIANCE
"""

import argparse
import sys
import logging
from datetime import datetime
from typing import List, Dict, Any
from kite_connect_api import KiteConnectAPI
from kite_utils import setup_logger, load_config


class GTTOrderDeleter:
    """Class to delete all active GTT orders for a given company"""
    
    def __init__(self, company_symbol: str):
        """
        Initialize the GTT Order Deleter
        
        Parameters:
        - company_symbol: Trading symbol of the company (e.g., "ITC", "RELIANCE")
        """
        self.company_symbol = company_symbol.upper()
        
        # Setup logging
        self.logger = setup_logger(__name__, f"GTT_DELETE_{self.company_symbol}")
        self.logger.info(f"Initializing GTT Order Deleter for {self.company_symbol}")
        
        # Test config loading first
        try:
            load_config()
            self.logger.info("Configuration loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            self.logger.error("Please ensure config/config.yaml exists and contains valid Kite Connect credentials")
            raise
        
        # Initialize Kite Connect API
        self.kite_api = KiteConnectAPI(self.company_symbol)
        
    def connect_to_kite(self) -> None:
        """Establish connection to Kite Connect"""
        try:
            self.kite_api.connect()
            self.logger.info("Successfully connected to Kite Connect")
        except Exception as e:
            self.logger.error(f"Failed to connect to Kite Connect: {e}")
            raise
    
    def get_active_gtt_orders(self) -> List[Dict[str, Any]]:
        """
        Get all active GTT orders for the company
        
        Returns:
        List of active GTT order details
        """
        try:
            # Get all GTT orders
            gtt_orders = self.kite_api.get_gtt_orders()
            self.logger.info(f"Retrieved {len(gtt_orders)} total GTT orders")
            
            # Debug: Log all GTT orders to understand the structure
            for i, order in enumerate(gtt_orders):
                self.logger.info(f"GTT Order {i+1}: {order}")
            
            # Filter orders for the specific company AND active status
            company_orders = []
            for order in gtt_orders:
                # Try different ways to access the trading symbol based on GTT order structure
                symbol = (
                    order.get('tradingsymbol', '') or  # Direct field
                    order.get('condition', {}).get('tradingsymbol', '')  # Nested under condition
                ).upper()
                
                status = order.get('status', '').upper()
                
                self.logger.info(f"Order: Symbol={symbol}, Status={status}, Company={self.company_symbol}")
                
                # Consider these statuses as "active" GTT orders
                active_statuses = ['ACTIVE', 'PENDING', 'OPEN']
                
                if symbol == self.company_symbol and status in active_statuses:
                    company_orders.append(order)
                    self.logger.info(f"✅ Added active order for {symbol} (Status: {status})")
                elif symbol == self.company_symbol:
                    self.logger.info(f"⚠️  Found {symbol} order but status is '{status}' (not active)")
            
            self.logger.info(f"Found {len(company_orders)} active GTT orders for {self.company_symbol}")
            return company_orders
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve GTT orders: {e}")
            raise
    
    def delete_gtt_order(self, trigger_id: str, order_details: Dict[str, Any]) -> bool:
        """
        Delete a specific GTT order
        
        Parameters:
        - trigger_id: The trigger ID of the GTT order to delete
        - order_details: Order details for logging purposes
        
        Returns:
        True if deletion was successful, False otherwise
        """
        try:
            # Safely extract values to avoid None formatting errors
            symbol = (
                order_details.get('tradingsymbol') or 
                order_details.get('condition', {}).get('tradingsymbol') or
                'Unknown'
            )
            quantity = order_details.get('quantity') or 0
            price = order_details.get('price') or 0.0
            
            self.logger.info(f"Deleting GTT order: Trigger ID {trigger_id}, "
                           f"Symbol: {symbol}, "
                           f"Quantity: {quantity}, "
                           f"Price: Rs.{price:.2f}")
            
            # Delete the GTT order
            result = self.kite_api.delete_gtt_order(trigger_id)
            
            if result:
                self.logger.info(f"Successfully deleted GTT order with trigger ID: {trigger_id}")
                return True
            else:
                self.logger.error(f"Failed to delete GTT order with trigger ID: {trigger_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error deleting GTT order {trigger_id}: {e}")
            return False
    
    def delete_all_gtt_orders(self, gtt_orders: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Delete all GTT orders for the company
        
        Parameters:
        - gtt_orders: List of GTT orders to delete
        
        Returns:
        Dictionary with deletion results summary
        """
        if not gtt_orders:
            self.logger.info(f"No GTT orders found for {self.company_symbol}")
            return {
                'total_orders': 0,
                'successful_deletions': 0,
                'failed_deletions': 0,
                'deleted_orders': [],
                'failed_orders': []
            }
        
        self.logger.info(f"Starting deletion of {len(gtt_orders)} GTT orders for {self.company_symbol}")
        
        successful_deletions = 0
        failed_deletions = 0
        deleted_orders = []
        failed_orders = []
        
        for order in gtt_orders:
            trigger_id = order.get('id')
            if not trigger_id:
                self.logger.warning(f"Skipping order without trigger ID: {order}")
                continue
            
            if self.delete_gtt_order(trigger_id, order):
                successful_deletions += 1
                # Get trading symbol from multiple possible locations
                symbol = (
                    order.get('tradingsymbol') or 
                    order.get('condition', {}).get('tradingsymbol') or
                    'Unknown'
                )
                
                deleted_orders.append({
                    'trigger_id': trigger_id,
                    'symbol': symbol,
                    'quantity': order.get('quantity') or 0,
                    'price': order.get('price') or 0.0,
                    'timestamp': datetime.now().isoformat()
                })
            else:
                failed_deletions += 1
                # Get trading symbol from multiple possible locations
                symbol = (
                    order.get('tradingsymbol') or 
                    order.get('condition', {}).get('tradingsymbol') or
                    'Unknown'
                )
                
                failed_orders.append({
                    'trigger_id': trigger_id,
                    'symbol': symbol,
                    'quantity': order.get('quantity') or 0,
                    'price': order.get('price') or 0.0,
                    'error': 'Deletion failed',
                    'timestamp': datetime.now().isoformat()
                })
        
        return {
            'total_orders': len(gtt_orders),
            'successful_deletions': successful_deletions,
            'failed_deletions': failed_deletions,
            'deleted_orders': deleted_orders,
            'failed_orders': failed_orders
        }
    
    def save_deletion_summary(self, results: Dict[str, Any]) -> None:
        """
        Save deletion summary to a JSON file
        
        Parameters:
        - results: Deletion results summary
        """
        try:
            import json
            import os
            
            # Create orders directory if it doesn't exist
            orders_dir = os.path.join('workdir', 'orders')
            os.makedirs(orders_dir, exist_ok=True)
            
            # Generate filename with timestamp and company symbol
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(orders_dir, f'{self.company_symbol}_gtt_deletion_{timestamp}.json')
            
            summary = {
                'company_symbol': self.company_symbol,
                'operation': 'GTT Order Deletion',
                'timestamp': datetime.now().isoformat(),
                'results': results
            }
            
            # Write to file
            with open(filename, 'w') as f:
                json.dump(summary, f, indent=2)
            
            self.logger.info(f"Deletion summary saved to {filename}")
            
        except Exception as e:
            self.logger.error(f"Failed to save deletion summary: {e}")
    
    def print_deletion_summary(self, results: Dict[str, Any]) -> None:
        """
        Print a summary of the deletion operation
        
        Parameters:
        - results: Deletion results summary
        """
        print("\n" + "="*80)
        print(f"GTT ORDER DELETION SUMMARY FOR {self.company_symbol}")
        print("="*80)
        
        print(f"Total Orders Found: {results['total_orders']}")
        print(f"Successfully Deleted: {results['successful_deletions']}")
        print(f"Failed Deletions: {results['failed_deletions']}")
        
        if results['deleted_orders']:
            print(f"\n✅ Successfully Deleted Orders:")
            print("-" * 80)
            for order in results['deleted_orders']:
                price = order.get('price', 0) or 0.0
                quantity = order.get('quantity', 0) or 0
                symbol = order.get('symbol', 'Unknown') or 'Unknown'
                
                print(f"  • Trigger ID: {order['trigger_id']}")
                print(f"    Symbol: {symbol}")
                print(f"    Quantity: {quantity}")
                print(f"    Price: Rs.{price:.2f}")
                print()
        
        if results['failed_orders']:
            print(f"\n❌ Failed Deletions:")
            print("-" * 80)
            for order in results['failed_orders']:
                price = order.get('price', 0) or 0.0
                quantity = order.get('quantity', 0) or 0
                symbol = order.get('symbol', 'Unknown') or 'Unknown'
                
                print(f"  • Trigger ID: {order['trigger_id']}")
                print(f"    Symbol: {symbol}")
                print(f"    Quantity: {quantity}")
                print(f"    Price: Rs.{price:.2f}")
                print(f"    Error: {order['error']}")
                print()
        
        print("="*80)
    
    def run(self) -> None:
        """Execute the complete GTT order deletion process"""
        try:
            self.logger.info("Starting GTT order deletion process")
            
            # Connect to Kite
            self.connect_to_kite()
            
            # Get active GTT orders
            gtt_orders = self.get_active_gtt_orders()
            
            if not gtt_orders:
                print(f"\nNo active GTT orders found for {self.company_symbol}")
                return
            
            # Confirm deletion with user
            print(f"\nFound {len(gtt_orders)} active GTT orders for {self.company_symbol}")
            print("\n⚠️  WARNING: This will permanently delete all GTT orders for this company!")
            
            confirm = input(f"\nDo you want to proceed with deleting all GTT orders for {self.company_symbol}? (yes/no): ").strip().lower()
            if confirm not in ['yes', 'y']:
                self.logger.info("GTT order deletion cancelled by user")
                print("GTT order deletion cancelled.")
                return
            
            # Delete all GTT orders
            self.logger.info("Starting deletion of GTT orders...")
            results = self.delete_all_gtt_orders(gtt_orders)
            
            # Save and display results
            self.save_deletion_summary(results)
            self.print_deletion_summary(results)
            
            self.logger.info("GTT order deletion process completed successfully")
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"GTT order deletion failed: {error_msg}")
            self.logger.error(f"Error type: {type(e).__name__}")
            self.logger.error(f"Full error details: {e}")
            raise


def main():
    """Main function to parse arguments and run the deleter"""
    parser = argparse.ArgumentParser(
        description="Delete all active GTT orders for a given company",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        'company_symbol',
        help='Trading symbol of the company (e.g., ITC, RELIANCE, TCS)'
    )
    
    args = parser.parse_args()
    
    try:
        # Create and run deleter
        deleter = GTTOrderDeleter(company_symbol=args.company_symbol)
        deleter.run()
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()



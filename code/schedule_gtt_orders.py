#!/usr/bin/env python3
"""
 Hybrid Order Scheduler Script
 
 This script schedules orders for a given company with decreasing prices at configurable intervals
 and progressive quantity increase. The first order is placed as a normal market order,
 while subsequent orders are placed as GTT (Good Till Triggered) orders.
 Each subsequent order is placed at a configurable percentage lower than the previous order's price,
 and each order has an increasing quantity (1, 2, 3, 4, ... shares).
 
 Configuration via config/config.yaml -> stratergy section:
- price_difference_percent (default: 0.4%)
- order_count (default: 10)
- start_quantity (default: 1)

Usage:
    python schedule_gtt_orders.py <company_symbol> [order_count] <current_price> [max_quantity] [--startq N]

Sample Commands:

Basic Usage (using config defaults):
    python schedule_gtt_orders.py ITC 450.50
    # Uses: order_count=10, max_quantity=100, start_quantity=1
    # Orders: 1,2,3,4,5,6,7,8,9,10 shares

Custom Order Count:
    python schedule_gtt_orders.py ITC 5 450.50 100
    # Places 5 orders: 1,2,3,4,5 shares

Custom Max Quantity:
    python schedule_gtt_orders.py RELIANCE 2500.0 50
    # Uses 10 orders with max 50 shares: 1,2,3,4,5,6,7,8,9,10 shares (capped at 50)

Custom Starting Quantity:
    python schedule_gtt_orders.py TCS 3500.0 --startq 10
    # Uses 10 orders starting from 10: 10,11,12,13,14,15,16,17,18,19 shares

Advanced Custom Configuration:
    python schedule_gtt_orders.py ITC 5 450.50 100 --startq 5
    # Places 5 orders starting from 5: 5,6,7,8,9 shares

Large Volume Trading:
    python schedule_gtt_orders.py HDFC 1500.0 200 --startq 20
    # Uses 10 orders starting from 20: 20,21,22,23,24,25,26,27,28,29 shares

Small Volume Testing:
    python schedule_gtt_orders.py WIPRO 3 250.0 10 --startq 1
    # Places 3 orders: 1,2,3 shares
"""

import argparse
import sys
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from kite_connect_api import KiteConnectAPI
from kite_utils import setup_logger, load_config


class HybridOrderScheduler:
    """Class to schedule orders with decreasing prices (first as market order, subsequent as GTT orders)"""
    
    def __init__(self, company_symbol: str, order_count: int, current_price: float, max_quantity: int = 100, start_quantity: int = None):
        """
        Initialize the GTT Order Scheduler
        
        Parameters:
        - company_symbol: Trading symbol of the company (e.g., "ITC", "RELIANCE")
        - order_count: Number of GTT orders to place
        - current_price: Current price of the stock (base price for the first order)
        - max_quantity: Maximum number of shares for the last order (default: 100)
        - start_quantity: Starting quantity for the first order (default: from config, fallback: 1)
        """
        self.company_symbol = company_symbol.upper()
        self.current_price = current_price
        self.max_quantity = max_quantity
        
        self.logger = setup_logger(__name__, self.company_symbol)

        # Load configuration and set parameters
        try:
            config = load_config()
            self.price_difference_percent = config.get('stratergy', {}).get('price_difference_percent', 0.4)
            
            # If order_count is 0 or None, load from config
            if not order_count:
                order_count = config.get('stratergy', {}).get('order_count', 10)
                self.logger.info(f"Using order_count from config: {order_count}")
            
            # If start_quantity is None, load from config
            if start_quantity is None:
                start_quantity = config.get('stratergy', {}).get('start_quantity', 1)
                self.logger.info(f"Using start_quantity from config: {start_quantity}")
            
            self.order_count = order_count
            self.start_quantity = start_quantity
            self.logger.info(f"Price difference configured: {self.price_difference_percent}%")
            self.logger.info(f"Start quantity configured: {self.start_quantity}")
        except Exception as e:
            self.logger.warning(f"Could not load configuration: {e}, using defaults")
            self.price_difference_percent = 0.4
            # Set fallback values if config loading failed
            self.order_count = order_count or 10
            self.start_quantity = start_quantity or 1
        
        # Validate inputs
        if self.order_count <= 0:
            raise ValueError("Order count must be positive")
        if current_price <= 0:
            raise ValueError("Current price must be positive")
        if max_quantity <= 0:
            raise ValueError("Maximum quantity must be positive")
        
                 # Setup logging
        self.logger.info(f"Initializing Hybrid Order Scheduler for {self.company_symbol}")
        self.logger.info(f"Order count: {order_count}, Current price: Rs.{current_price:.2f}, Max quantity: {max_quantity}")
        self.logger.info(f"Price difference: {self.price_difference_percent}%")
        
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
        self.gtt_orders = []
        
    def connect_to_kite(self) -> None:
        """Establish connection to Kite Connect"""
        try:
            self.kite_api.connect()
            self.logger.info("Successfully connected to Kite Connect")
            
            # Check market hours to determine order type for first order
            self._check_market_hours()
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Kite Connect: {e}")
            raise
    
    def _check_market_hours(self) -> None:
        """Check if market is open to determine order type for first order"""
        try:
            from datetime import datetime
            import pytz
            
            # Get current time in IST
            ist = pytz.timezone('Asia/Kolkata')
            current_time = datetime.now(ist)
            
            # Check if it's a weekday
            if current_time.weekday() >= 5:  # Saturday = 5, Sunday = 6
                self.market_open = False
                self.logger.info("Market is closed (weekend) - will use LIMIT order for first order")
                return
            
            # Check if it's within market hours (9:15 AM to 3:30 PM IST)
            market_start = current_time.replace(hour=9, minute=15, second=0, microsecond=0)
            market_end = current_time.replace(hour=15, minute=30, second=0, microsecond=0)
            
            if current_time < market_start or current_time > market_end:
                self.market_open = False
                self.logger.info("Market is closed (outside trading hours) - will use LIMIT order for first order")
            else:
                self.market_open = True
                self.logger.info("Market is open - will use MARKET order for first order")
                
        except ImportError:
            # If pytz is not available, assume market is closed for safety
            self.market_open = False
            self.logger.warning("pytz not available, assuming market is closed - will use LIMIT order for first order")
        except Exception as e:
            # If any error, assume market is closed for safety
            self.market_open = False
            self.logger.warning(f"Could not check market hours: {e} - will use LIMIT order for first order")
    

    
    def calculate_order_prices(self, base_price: float) -> List[Dict[str, Any]]:
        """
        Calculate prices and quantities for all orders with decreasing price intervals
        and progressive quantity increase (1, 2, 3, 4, ...)
        
        Market OPEN: First order as MARKET, subsequent as GTT (0.4%, 0.8%, 1.2% lower)
        Market CLOSED: Skip first order, start with GTT at 0.25%, 0.65%, 1.05% lower
        
        Price difference is configurable via config/config.yaml -> stratergy.price_difference_percent
        
        Parameters:
        - base_price: Base price for the first order
        
        Returns:
        List of order details with calculated prices and quantities
        """
        orders = []
        
        if hasattr(self, 'market_open') and self.market_open:
            # Market is OPEN: Place all orders starting from current price
            for i in range(self.order_count):
                if i == 0:
                    # First order: MARKET order at current price
                    order_type = 'MARKET'
                    order_type_display = 'MARKET ORDER'
                    trigger_price = None
                    price_decrease = 0  # No decrease for first order
                else:
                     # Subsequent orders: GTT orders with configurable decreasing intervals
                     order_type = 'GTT'
                     order_type_display = 'GTT ORDER'
                     price_decrease = i * (self.price_difference_percent / 100)  # 0.4%, 0.8%, 1.2%, etc.
                     trigger_price = round(base_price * (1 - price_decrease) * 0.999, 1)  # 0.1% below order price
                
                order_price = base_price * (1 - price_decrease)
                progressive_quantity = min(self.start_quantity + i, self.max_quantity)
                
                order_details = {
                    'order_number': i + 1,
                    'order_price': round(order_price, 1),
                    'trigger_price': round(trigger_price, 1),
                    'quantity': progressive_quantity,
                    'total_value': round(order_price * progressive_quantity, 1),
                    'order_type': order_type
                }
                
                if order_type == 'MARKET':
                    self.logger.info(f"Order {i+1}: Price: Rs.{order_details['order_price']:.2f}, "
                                   f"Type: {order_type_display}, "
                                   f"Quantity: {progressive_quantity}, "
                                   f"Value: Rs.{order_details['total_value']:.2f}")
                else:
                    self.logger.info(f"Order {i+1}: Price: Rs.{order_details['order_price']:.2f}, "
                                   f"Trigger: Rs.{order_details['trigger_price']:.2f}, "
                                   f"Type: {order_type_display}, "
                                   f"Quantity: {progressive_quantity}, "
                                   f"Value: Rs.{order_details['total_value']:.2f}")
                
                orders.append(order_details)
        else:
            # Market is CLOSED: Skip first order, start with GTT orders at 0.25% intervals
            self.logger.info("Market is closed - skipping first order and starting with GTT orders")
            
            for i in range(self.order_count):
                if i == 0:
                    # First order: SKIPPED when market is closed
                    order_details = {
                        'order_number': i + 1,
                        'order_price': round(base_price, 1),
                        'trigger_price': None,
                        'quantity': 1,
                        'total_value': round(base_price, 1),
                        'order_type': 'SKIPPED',
                        'skip_reason': 'Market closed - AMO not supported'
                    }
                    
                    self.logger.info(f"Order {i+1}: SKIPPED (Market closed - AMO not supported)")
                else:
                                                              # Subsequent orders: GTT orders starting from 0.25% lower
                    price_decrease = (i - 0.75) * (self.price_difference_percent / 100)  # 0.25%, 0.65%, 1.05%, etc.
                    order_price = base_price * (1 - price_decrease)
                    progressive_quantity = min(self.start_quantity + i - 1, self.max_quantity)  # Start from start_quantity for first GTT order
                    trigger_price = round(order_price * 0.999, 1)  # 0.1% below order price
                    
                    order_details = {
                        'order_number': i + 1,
                        'order_price': round(order_price, 1),
                        'trigger_price': round(trigger_price, 1),
                        'quantity': progressive_quantity,
                        'total_value': round(order_price * progressive_quantity, 1),
                        'order_type': 'GTT'
                    }
                    
                    self.logger.info(f"Order {i+1}: Price: Rs.{order_details['order_price']:.2f}, "
                                   f"Trigger: Rs.{order_details['trigger_price']:.2f}, "
                                   f"Type: GTT ORDER, "
                                   f"Quantity: {progressive_quantity}, "
                                   f"Value: Rs.{order_details['total_value']:.2f}")
                
                orders.append(order_details)
        
        return orders
    
    def place_orders(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Place all orders (first as market order, subsequent as GTT orders)
        
        Parameters:
        - orders: List of order details
        
        Returns:
        List of placed orders with order IDs or trigger IDs
        """
        placed_orders = []
        
        for order in orders:
            try:
                if order['order_type'] == 'SKIPPED':
                    # First order: Skip when market is closed (AMO not supported)
                    self.logger.info(f"Skipping order {order['order_number']} - Market closed, AMO not supported")
                    
                    # Store order details as skipped
                    placed_order = {
                        **order,
                        'order_id': None,
                        'trigger_id': None,
                        'status': 'SKIPPED',
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    placed_orders.append(placed_order)
                    self.logger.info(f"Order {order['order_number']} skipped successfully")
                    
                elif order['order_type'] == 'MARKET':
                    # First order: Place as MARKET order when market is open
                    self.logger.info(f"Placing MARKET order {order['order_number']} for {self.company_symbol}")
                    
                    # Place MARKET order
                    order_id = self.kite_api.place_order(
                        quantity=order['quantity'],
                        order_type=order['order_type'],
                        product="CNC",
                        transaction_type="BUY"
                    )
                    
                    # Store order details with order ID
                    placed_order = {
                        **order,
                        'order_id': order_id,
                        'trigger_id': None,
                        'status': 'PLACED',
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    placed_orders.append(placed_order)
                    self.logger.info(f"MARKET order {order['order_number']} placed successfully with order ID: {order_id}")
                    
                else:
                    # Subsequent orders: Place as GTT orders
                    self.logger.info(f"Placing GTT order {order['order_number']} for {self.company_symbol}")
                    
                    # Place GTT order
                    trigger_id = self.kite_api.place_gtt_order(
                        trading_symbol=self.company_symbol,
                        exchange="NSE",
                        transaction_type="BUY",
                        quantity=order['quantity'],
                        price=order['order_price'],
                        trigger_price=order['trigger_price'],
                        order_type="LIMIT",
                        validity="DAY"
                    )
                    
                    # Store order details with trigger ID
                    placed_order = {
                        **order,
                        'order_id': None,
                        'trigger_id': trigger_id,
                        'status': 'PLACED',
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    placed_orders.append(placed_order)
                    self.logger.info(f"GTT order {order['order_number']} placed successfully with trigger ID: {trigger_id}")
                
            except Exception as e:
                error_msg = str(e)
                self.logger.error(f"Failed to place order {order['order_number']} ({order['order_type']}): {error_msg}")
                self.logger.error(f"Order details: Price: Rs.{order['order_price']:.2f}, Quantity: {order['quantity']}")
                
                # Continue with other orders even if one fails
                failed_order = {
                    **order,
                    'order_id': None,
                    'trigger_id': None,
                    'status': 'FAILED',
                    'error': error_msg,
                    'error_details': f"Failed to place {order['order_type']} order with price Rs.{order['order_price']:.2f} and quantity {order['quantity']}",
                    'timestamp': datetime.now().isoformat()
                }
                placed_orders.append(failed_order)
        
        return placed_orders
    
    def save_order_summary(self, orders: List[Dict[str, Any]]) -> None:
        """
        Save order summary to a JSON file
        
        Parameters:
        - orders: List of placed orders
        """
        try:
            import json
            import os
            
            # Create orders directory if it doesn't exist
            orders_dir = os.path.join('workdir', 'orders')
            os.makedirs(orders_dir, exist_ok=True)
            
            # Generate filename with timestamp and company symbol
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(orders_dir, f'{self.company_symbol}_gtt_orders_{timestamp}.json')
            
            # Filter out skipped orders from the summary
            non_skipped_orders = [order for order in orders if order.get('status') != 'SKIPPED']
            
            # Renumber the filtered orders starting from 1
            renumbered_orders = []
            for i, order in enumerate(non_skipped_orders, 1):
                renumbered_order = order.copy()
                renumbered_order['original_order_number'] = order['order_number']
                renumbered_order['order_number'] = i
                renumbered_orders.append(renumbered_order)
            
            # Prepare summary data
            if hasattr(self, 'market_open') and self.market_open:
                order_strategy = 'First order as MARKET (market open), subsequent as GTT'
            else:
                if renumbered_orders:
                    order_strategy = 'GTT orders starting from lower price (first order skipped due to market closed)'
                else:
                    order_strategy = 'All orders skipped (market closed)'
            
            summary = {
                'company_symbol': self.company_symbol,
                'order_count': self.order_count,
                'actual_orders_placed': len(renumbered_orders),
                'quantity_strategy': f'Progressive ({self.start_quantity}, {self.start_quantity+1}, {self.start_quantity+2}, {self.start_quantity+3}, ...)',
                'price_difference_percent': self.price_difference_percent,
                'order_strategy': order_strategy,
                'market_status': 'OPEN' if hasattr(self, 'market_open') and self.market_open else 'CLOSED',
                'max_quantity': self.max_quantity,
                'base_price': renumbered_orders[0]['order_price'] if renumbered_orders else None,
                'total_quantity': sum(order.get('quantity', 0) for order in renumbered_orders),
                'total_value': sum(order.get('total_value', 0) for order in renumbered_orders if order.get('total_value')),
                'orders': renumbered_orders,
                'timestamp': datetime.now().isoformat()
            }
            
            # Write to file
            with open(filename, 'w') as f:
                json.dump(summary, f, indent=2)
            
            self.logger.info(f"Order summary saved to {filename}")
            
        except Exception as e:
            self.logger.error(f"Failed to save order summary: {e}")
    
    def print_order_summary(self, orders: List[Dict[str, Any]]) -> None:
        """
        Print a summary of all placed orders (excluding skipped orders)
        
        Parameters:
        - orders: List of placed orders
        """
        print("\n" + "="*80)
        print(f"GTT ORDER SUMMARY FOR {self.company_symbol}")
        print("="*80)
        
        # Filter out skipped orders from the summary display
        non_skipped_orders = [order for order in orders if order.get('status') != 'SKIPPED' and order.get('order_type') != 'SKIPPED']
        
        # Renumber the filtered orders starting from 1 for display
        renumbered_orders = []
        for i, order in enumerate(non_skipped_orders, 1):
            renumbered_order = order.copy()
            renumbered_order['original_order_number'] = order['order_number']
            renumbered_order['order_number'] = i
            renumbered_orders.append(renumbered_order)
        
        # Check if orders have status field (placed orders) or not (calculated orders)
        if renumbered_orders and 'status' in renumbered_orders[0]:
            successful_orders = [o for o in renumbered_orders if o.get('status') == 'PLACED']
            failed_orders = [o for o in renumbered_orders if o.get('status') == 'FAILED']
        else:
            # These are calculated orders, not placed orders yet
            successful_orders = renumbered_orders
            failed_orders = []
        
        print(f"Total Orders Processed: {len(renumbered_orders)}")
        print(f"Successful: {len(successful_orders)}")
        print(f"Failed: {len(failed_orders)}")
        
        if failed_orders:
            print(f"\n❌ ERRORS ENCOUNTERED:")
            for order in failed_orders:
                print(f"   • Order {order['order_number']}: {order.get('error', 'Unknown error')}")
        
        print(f"Quantity Strategy: Progressive ({self.start_quantity}, {self.start_quantity+1}, {self.start_quantity+2}, {self.start_quantity+3}, ...)")
        print(f"Price Difference: {self.price_difference_percent}%")
        if hasattr(self, 'market_open') and self.market_open:
            print(f"Order Strategy: First as MARKET (market open), subsequent as GTT")
        else:
            if renumbered_orders:
                print(f"Order Strategy: GTT orders starting from lower price (first order skipped)")
            else:
                print(f"Order Strategy: All orders skipped (market closed)")
        print(f"Max Quantity: {self.max_quantity}")
        
        # Calculate totals from renumbered orders only
        total_quantity = sum(order.get('quantity', 0) for order in renumbered_orders)
        print(f"Total Quantity: {total_quantity:,}")
        
        if successful_orders:
            total_value = sum(order.get('total_value', 0) for order in successful_orders)
            print(f"Total Value: Rs.{total_value:,.2f}")
        
        if renumbered_orders:
            print("\nOrder Details:")
            print("-" * 80)
            print(f"{'Order':<6} {'Type':<8} {'Price':<10} {'Trigger':<10} {'Quantity':<10} {'Value':<12} {'Status':<10}")
            print("-" * 80)
            
            for order in renumbered_orders:
                status = order.get('status', 'CALCULATED')
                order_type = order.get('order_type', 'UNKNOWN')
                trigger_price = order.get('trigger_price', 'N/A')
                
                if trigger_price is None:
                    trigger_display = 'N/A'
                else:
                    trigger_display = f"Rs.{trigger_price:.2f}"
                
                print(f"{order['order_number']:<6} "
                       f"{order_type:<8} "
                       f"Rs.{order['order_price']:<9.2f} "
                       f"{trigger_display:<10} "
                       f"{order['quantity']:<10,} "
                       f"Rs.{order['total_value']:<11.2f} "
                       f"{status:<10}")
        else:
            print("\nNo orders to display (all orders were skipped)")
            print("-" * 50)
        
        if failed_orders:
            print("\nFailed Orders:")
            print("-" * 80)
            for order in failed_orders:
                print(f"Order {order['order_number']} ({order.get('order_type', 'UNKNOWN')}):")
                print(f"  • Price: Rs.{order.get('order_price', 0):.2f}")
                print(f"  • Quantity: {order.get('quantity', 0)}")
                print(f"  • Error: {order.get('error', 'Unknown error')}")
                if order.get('error_details'):
                    print(f"  • Details: {order.get('error_details')}")
                print()
        
        print("="*80)
    
    def run(self) -> None:
        """Execute the complete GTT order scheduling process"""
        try:
            self.logger.info("Starting hybrid order scheduling process")
            
            # Connect to Kite
            self.connect_to_kite()
            
            # Use the provided current price as base
            self.logger.info(f"Using provided current price as base: Rs.{self.current_price:.2f}")
            
            # Calculate order prices
            orders = self.calculate_order_prices(self.current_price)
            
            # Confirm with user before placing orders
            self.print_order_summary(orders)
            
            print("\n⚠️  IMPORTANT NOTES:")
            if hasattr(self, 'market_open') and self.market_open:
                 print("   • First order will be placed as a MARKET order (executes immediately)")
                 print("   • Subsequent orders will be placed as GTT orders (execute when triggered)")
                 print("   • GTT orders will only execute when market price reaches trigger price")
                 print("   • Trigger prices are set 0.1% above order prices for tight control")
            else:
                 print("   • First order will be SKIPPED (Market closed - AMO not supported)")
                 print("   • GTT orders will start from 0.25% lower than current price")
                 print("   • GTT orders will only execute when market price reaches trigger price")
                 print("   • Trigger prices are set 0.1% above order prices for tight control")
            
            confirm = input("\nDo you want to proceed with placing these orders? (yes/no): ").strip().lower()
            if confirm not in ['yes', 'y']:
                self.logger.info("Order placement cancelled by user")
                print("Order placement cancelled.")
                return
            
            # Place orders (first as market order, subsequent as GTT orders)
            self.logger.info("Placing orders...")
            placed_orders = self.place_orders(orders)
            
            # Save and display results
            self.save_order_summary(placed_orders)
            self.print_order_summary(placed_orders)
            
            self.logger.info("Hybrid order scheduling process completed successfully")
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Hybrid order scheduling failed: {error_msg}")
            self.logger.error(f"Error type: {type(e).__name__}")
            self.logger.error(f"Full error details: {e}")
            raise


def main():
    """Main function to parse arguments and run the scheduler"""
    parser = argparse.ArgumentParser(
        description="Schedule orders with decreasing prices at configurable intervals (first as market order, subsequent as GTT orders)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        'company_symbol',
        help='Trading symbol of the company (e.g., ITC, RELIANCE, TCS)'
    )
    
    parser.add_argument(
        'order_count',
        nargs='?',
        type=int,
        default=None,
        help='Number of GTT orders to place (default: from config.yaml, fallback: 10)'
    )
    
    parser.add_argument(
        'current_price',
        type=float,
        help='Current price of the stock (base price for the first order)'
    )
    
    parser.add_argument(
        'max_quantity',
        nargs='?',
        type=int,
        default=100,
        help='Maximum number of shares for the last order (default: 100)'
    )
    
    parser.add_argument(
        '--startq',
        type=int,
        default=None,
        help='Starting quantity for the first order (default: from config.yaml, fallback: 1). Example: --startq 10 starts with 10,11,12... shares'
    )
    
    args = parser.parse_args()
    
    try:
        # Create and run scheduler
        scheduler = HybridOrderScheduler(
            company_symbol=args.company_symbol,
            order_count=args.order_count,
            current_price=args.current_price,
            max_quantity=args.max_quantity,
            start_quantity=args.startq
        )
        
        scheduler.run()
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

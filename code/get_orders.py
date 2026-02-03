#!/usr/bin/env python3
"""
Order Status Viewer Script

This script retrieves and displays both normal orders and GTT (Good Till Triggered) orders 
for a given company symbol from Kite Connect API.

Usage:
    python get_orders.py <company_symbol> [options]

Examples:
    python get_orders.py ITC
    python get_orders.py RELIANCE --only_normal
    python get_orders.py TCS --only_gtt
    python get_orders.py BAJFINANCE --status COMPLETE
"""

import argparse
import sys
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from kite_connect_api import KiteConnectAPI
from kite_utils import setup_logger, load_config


class OrderViewer:
    """Class to view all normal and GTT orders for a given company"""
    
    def __init__(self, company_symbol: str):
        """
        Initialize the Order Viewer
        
        Parameters:
        - company_symbol: Trading symbol of the company (e.g., "ITC", "RELIANCE")
        """
        self.company_symbol = company_symbol.upper()
        
        # Setup logging
        self.logger = setup_logger(__name__, f"ORDER_VIEW_{self.company_symbol}")
        self.logger.info(f"Initializing Order Viewer for {self.company_symbol}")
        
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
    
    def get_normal_orders(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all normal orders for the company
        
        Parameters:
        - status_filter: Optional status filter (e.g., 'COMPLETE', 'OPEN', 'PENDING')
        
        Returns:
        List of normal order details
        """
        try:
            # Get all orders
            all_orders = self.kite_api.kite.orders()
            self.logger.info(f"Retrieved {len(all_orders)} total orders")
            
            # Filter orders for the specific company
            company_orders = []
            for order in all_orders:
                symbol = order.get('tradingsymbol', '').upper()
                status = order.get('status', '').upper()
                
                # Check if order matches company
                if symbol == self.company_symbol:
                    # Apply status filter if provided
                    if status_filter and status != status_filter.upper():
                        continue
                    company_orders.append(order)
            
            filter_text = f" with status {status_filter}" if status_filter else ""
            self.logger.info(f"Found {len(company_orders)} normal orders for {self.company_symbol}{filter_text}")
            return company_orders
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve normal orders: {e}")
            return []
    
    def get_gtt_orders(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all GTT orders for the company
        
        Parameters:
        - status_filter: Optional status filter (e.g., 'ACTIVE', 'TRIGGERED', 'DISABLED')
        
        Returns:
        List of GTT order details
        """
        try:
            # Get all GTT orders
            gtt_orders = self.kite_api.get_gtt_orders()
            self.logger.info(f"Retrieved {len(gtt_orders)} total GTT orders")
            
            # Filter orders for the specific company
            company_orders = []
            for order in gtt_orders:
                # Try different ways to access the trading symbol
                symbol = (
                    order.get('tradingsymbol', '') or
                    order.get('condition', {}).get('tradingsymbol', '')
                ).upper()
                
                status = order.get('status', '').upper()
                
                # Check if order matches company
                if symbol == self.company_symbol:
                    # Apply status filter if provided
                    if status_filter and status != status_filter.upper():
                        continue
                    company_orders.append(order)
            
            filter_text = f" with status {status_filter}" if status_filter else ""
            self.logger.info(f"Found {len(company_orders)} GTT orders for {self.company_symbol}{filter_text}")
            return company_orders
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve GTT orders: {e}")
            return []
    
    def print_normal_orders(self, orders: List[Dict[str, Any]]) -> None:
        """
        Print normal orders in a formatted table
        
        Parameters:
        - orders: List of normal order details
        """
        if not orders:
            print("\nNo normal orders found.")
            return
        
        print("\n" + "="*120)
        print("NORMAL ORDERS")
        print("="*120)
        
        # Print header
        print(f"{'Order ID':<20} {'Status':<12} {'Type':<8} {'Quantity':<10} {'Price':<12} {'Filled':<10} {'Time':<20}")
        print("-"*120)
        
        # Print each order
        for order in orders:
            order_id = order.get('order_id', 'N/A')
            status = order.get('status', 'N/A')
            order_type = order.get('order_type', 'N/A')
            transaction_type = order.get('transaction_type', 'N/A')
            quantity = order.get('quantity', 0)
            price = order.get('price', 0) or order.get('average_price', 0) or 0
            filled_quantity = order.get('filled_quantity', 0)
            order_timestamp = order.get('order_timestamp', 'N/A')
            
            # Format time if available
            if order_timestamp and order_timestamp != 'N/A':
                try:
                    if isinstance(order_timestamp, datetime):
                        time_str = order_timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        time_str = str(order_timestamp)[:19]
                except:
                    time_str = str(order_timestamp)
            else:
                time_str = 'N/A'
            
            print(f"{order_id:<20} {status:<12} {transaction_type}/{order_type:<6} {quantity:<10} "
                  f"Rs.{price:<10.2f} {filled_quantity:<10} {time_str:<20}")
        
        print("-"*120)
        print(f"Total Normal Orders: {len(orders)}")
    
    def print_gtt_orders(self, orders: List[Dict[str, Any]]) -> None:
        """
        Print GTT orders in a formatted table
        
        Parameters:
        - orders: List of GTT order details
        """
        if not orders:
            print("\nNo GTT orders found.")
            return
        
        print("\n" + "="*140)
        print("GTT ORDERS (Good Till Triggered)")
        print("="*140)
        
        # Print header
        print(f"{'Trigger ID':<15} {'Status':<12} {'Type':<8} {'Qty':<8} {'Trigger':<12} {'Price':<12} {'Created':<20}")
        print("-"*140)
        
        # Print each order
        for order in orders:
            trigger_id = order.get('id', 'N/A')
            status = order.get('status', 'N/A')
            
            # Get transaction type from multiple possible locations
            transaction_type = (
                order.get('type', '') or
                order.get('condition', {}).get('transaction_type', '') or
                order.get('orders', [{}])[0].get('transaction_type', '') if order.get('orders') else ''
            ).upper() or 'N/A'
            
            # Get quantity
            quantity = (
                order.get('quantity') or
                order.get('orders', [{}])[0].get('quantity', 0) if order.get('orders') else 0
            )
            
            # Get trigger price
            trigger_price = (
                order.get('trigger_values', [0])[0] if order.get('trigger_values') else
                order.get('condition', {}).get('trigger_values', [0])[0] if order.get('condition', {}).get('trigger_values') else 0
            )
            
            # Get order price
            price = (
                order.get('price') or
                order.get('orders', [{}])[0].get('price', 0) if order.get('orders') else 0
            )
            
            # Get created time
            created_at = order.get('created_at', 'N/A')
            if created_at and created_at != 'N/A':
                try:
                    if isinstance(created_at, datetime):
                        time_str = created_at.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        time_str = str(created_at)[:19]
                except:
                    time_str = str(created_at)
            else:
                time_str = 'N/A'
            
            print(f"{str(trigger_id):<15} {status:<12} {transaction_type:<8} {quantity:<8} "
                  f"Rs.{trigger_price:<10.2f} Rs.{price:<10.2f} {time_str:<20}")
        
        print("-"*140)
        print(f"Total GTT Orders: {len(orders)}")
    
    def print_summary(self, normal_orders: List[Dict[str, Any]], gtt_orders: List[Dict[str, Any]]) -> None:
        """
        Print a summary of all orders
        
        Parameters:
        - normal_orders: List of normal orders
        - gtt_orders: List of GTT orders
        """
        print("\n" + "="*80)
        print(f"ORDER SUMMARY FOR {self.company_symbol}")
        print("="*80)
        
        print(f"Total Normal Orders: {len(normal_orders)}")
        if normal_orders:
            # Count by status
            status_counts = {}
            for order in normal_orders:
                status = order.get('status', 'UNKNOWN')
                status_counts[status] = status_counts.get(status, 0) + 1
            
            print("\nNormal Orders by Status:")
            for status, count in sorted(status_counts.items()):
                print(f"  • {status}: {count}")
            
            # Calculate executed/completed order statistics
            completed_buy_orders = [
                o for o in normal_orders 
                if o.get('status', '').upper() == 'COMPLETE' and 
                   o.get('transaction_type', '').upper() == 'BUY'
            ]
            
            completed_sell_orders = [
                o for o in normal_orders 
                if o.get('status', '').upper() == 'COMPLETE' and 
                   o.get('transaction_type', '').upper() == 'SELL'
            ]
            
            if completed_buy_orders:
                print("\n📊 Completed BUY Orders Analysis:")
                total_buy_qty = 0
                total_buy_value = 0.0
                
                for order in completed_buy_orders:
                    filled_qty = order.get('filled_quantity', 0)
                    avg_price = order.get('average_price', 0) or 0
                    
                    total_buy_qty += filled_qty
                    total_buy_value += (filled_qty * avg_price)
                
                weighted_avg_price = total_buy_value / total_buy_qty if total_buy_qty > 0 else 0
                
                print(f"  • Total BUY Quantity: {total_buy_qty:,} shares")
                print(f"  • Weighted Average BUY Price: Rs.{weighted_avg_price:.2f}")
                print(f"  • Total BUY Value: Rs.{total_buy_value:,.2f}")
                print(f"  • Number of BUY Orders: {len(completed_buy_orders)}")
            
            if completed_sell_orders:
                print("\n📊 Completed SELL Orders Analysis:")
                total_sell_qty = 0
                total_sell_value = 0.0
                
                for order in completed_sell_orders:
                    filled_qty = order.get('filled_quantity', 0)
                    avg_price = order.get('average_price', 0) or 0
                    
                    total_sell_qty += filled_qty
                    total_sell_value += (filled_qty * avg_price)
                
                weighted_avg_price = total_sell_value / total_sell_qty if total_sell_qty > 0 else 0
                
                print(f"  • Total SELL Quantity: {total_sell_qty:,} shares")
                print(f"  • Weighted Average SELL Price: Rs.{weighted_avg_price:.2f}")
                print(f"  • Total SELL Value: Rs.{total_sell_value:,.2f}")
                print(f"  • Number of SELL Orders: {len(completed_sell_orders)}")
            
            # Net position calculation
            if completed_buy_orders or completed_sell_orders:
                buy_qty = sum(o.get('filled_quantity', 0) for o in completed_buy_orders)
                sell_qty = sum(o.get('filled_quantity', 0) for o in completed_sell_orders)
                net_qty = buy_qty - sell_qty
                
                print("\n📈 Net Position:")
                print(f"  • Net Quantity: {net_qty:,} shares {'(Long)' if net_qty > 0 else '(Short)' if net_qty < 0 else '(Flat)'}")
                
                if net_qty != 0:
                    buy_value = sum(
                        o.get('filled_quantity', 0) * (o.get('average_price', 0) or 0) 
                        for o in completed_buy_orders
                    )
                    sell_value = sum(
                        o.get('filled_quantity', 0) * (o.get('average_price', 0) or 0) 
                        for o in completed_sell_orders
                    )
                    
                    if net_qty > 0:  # Long position
                        net_avg_price = (buy_value - sell_value) / net_qty if net_qty > 0 else 0
                        print(f"  • Net Average Cost: Rs.{net_avg_price:.2f}")
                    else:  # Short position
                        net_avg_price = (sell_value - buy_value) / abs(net_qty) if net_qty < 0 else 0
                        print(f"  • Net Average Sale Price: Rs.{net_avg_price:.2f}")
        
        print(f"\nTotal GTT Orders: {len(gtt_orders)}")
        if gtt_orders:
            # Count by status
            status_counts = {}
            for order in gtt_orders:
                status = order.get('status', 'UNKNOWN')
                status_counts[status] = status_counts.get(status, 0) + 1
            
            print("\nGTT Orders by Status:")
            for status, count in sorted(status_counts.items()):
                print(f"  • {status}: {count}")
        
        print("="*80)
    
    def run(self, show_normal: bool = True, show_gtt: bool = True, 
            status_filter: Optional[str] = None) -> None:
        """
        Execute the order viewing process
        
        Parameters:
        - show_normal: Whether to show normal orders (default: True)
        - show_gtt: Whether to show GTT orders (default: True)
        - status_filter: Optional status filter to apply
        """
        try:
            self.logger.info("Starting order viewing process")
            
            # Connect to Kite
            self.connect_to_kite()
            
            normal_orders = []
            gtt_orders = []
            
            # Get normal orders if requested
            if show_normal:
                self.logger.info("Fetching normal orders...")
                normal_orders = self.get_normal_orders(status_filter)
            
            # Get GTT orders if requested
            if show_gtt:
                self.logger.info("Fetching GTT orders...")
                gtt_orders = self.get_gtt_orders(status_filter)
            
            # Display results
            if not normal_orders and not gtt_orders:
                print(f"\nNo orders found for {self.company_symbol}")
                if status_filter:
                    print(f"(with status filter: {status_filter})")
                return
            
            # Print orders
            if show_normal:
                self.print_normal_orders(normal_orders)
            
            if show_gtt:
                self.print_gtt_orders(gtt_orders)
            
            # Print summary
            self.print_summary(normal_orders, gtt_orders)
            
            self.logger.info("Order viewing process completed successfully")
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Order viewing failed: {error_msg}")
            self.logger.error(f"Error type: {type(e).__name__}")
            self.logger.error(f"Full error details: {e}")
            raise


def main():
    """Main function to parse arguments and run the viewer"""
    parser = argparse.ArgumentParser(
        description="View normal and GTT orders for a given company",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        'company_symbol',
        help='Trading symbol of the company (e.g., ITC, RELIANCE, TCS)'
    )
    
    parser.add_argument(
        '--only_normal',
        action='store_true',
        help='Show only normal orders (exclude GTT orders)'
    )
    
    parser.add_argument(
        '--only_gtt',
        action='store_true',
        help='Show only GTT orders (exclude normal orders)'
    )
    
    parser.add_argument(
        '--status',
        type=str,
        default=None,
        help='Filter by order status (e.g., COMPLETE, OPEN, PENDING, ACTIVE, TRIGGERED)'
    )
    
    args = parser.parse_args()
    
    # Validate that both filters are not used together
    if args.only_normal and args.only_gtt:
        print("Error: Cannot use both --only_normal and --only_gtt flags together")
        sys.exit(1)
    
    # Determine what to show
    show_normal = not args.only_gtt
    show_gtt = not args.only_normal
    
    try:
        # Create and run viewer
        viewer = OrderViewer(company_symbol=args.company_symbol)
        viewer.run(
            show_normal=show_normal,
            show_gtt=show_gtt,
            status_filter=args.status
        )
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

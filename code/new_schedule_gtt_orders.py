#!/usr/bin/env python3
"""
Convex Accumulation Order Scheduler Script

This script schedules orders for a given company using a convex accumulation strategy.
Small falls → small adds, bigger falls → wider spacing + larger size.
Both price spacing and share size are convex (power-based).

The first order is placed as a normal market order (if market is open),
while subsequent orders are placed as GTT (Good Till Triggered) orders.

Configuration via config/config.yaml -> stratergy section:
- base_shares (default: 15)
- max_fall_pct (default: 10.0%)
- steps (default: 10)
- fall_power (default: 1.7)
- size_power (default: 1.6)
- size_multiplier (default: 1.0)

Usage:
    python schedule_gtt_orders.py <company_symbol> [steps] <current_price> [--base_shares N] [--max_fall_pct X] [--fall_power X] [--size_power X] [--size_multiplier X]

Sample Commands:

Basic Usage (using config defaults):
    python schedule_gtt_orders.py ITC 450.50
    # Uses: steps=10, base_shares=15, max_fall_pct=10.0%

Custom Steps:
    python schedule_gtt_orders.py ITC 5 450.50
    # Places 5 orders with convex accumulation

Custom Base Shares:
    python schedule_gtt_orders.py RELIANCE 2500.0 --base_shares 20
    # Uses 20 shares as base, grows convexly

Custom Max Fall:
    python schedule_gtt_orders.py TCS 3500.0 --max_fall_pct 15.0
    # Plans for up to 15% fall

Advanced Configuration:
    python schedule_gtt_orders.py ITC 8 450.50 --base_shares 10 --max_fall_pct 12.0 --fall_power 2.0 --size_power 1.8
"""

import argparse
import sys
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from kite_connect_api import KiteConnectAPI
from kite_utils import setup_logger, load_config


def convex_accumulation_plan(
    start_price: float,
    base_shares: int = 15,
    max_fall_pct: float = 10.0,
    steps: int = 10,
    fall_power: float = 1.7,
    size_power: float = 1.6,
    size_multiplier: float = 3.8
) -> List[Dict[str, Any]]:
    """
    Generates price levels and share sizes for a convex accumulation strategy.

    Parameters
    ----------
    start_price : float
        Current market price.
    base_shares : int
        Shares bought at initial entry.
    max_fall_pct : float
        Maximum cumulative fall to plan for (e.g. 10%).
    steps : int
        Number of planned buys (including first).
    fall_power : float
        Controls convexity of price spacing (>1 = convex).
    size_power : float
        Controls convexity of share sizing (>1 = convex).
    size_multiplier : float
        Scales overall aggressiveness of size growth.

    Returns
    -------
    list of dict
        Each dict contains:
        - level
        - fall_pct
        - trigger_price
        - shares_to_buy
    """
    plan = []

    for i in range(steps):
        # Normalized step (0 → 1)
        t = i / (steps - 1) if steps > 1 else 0

        # Convex cumulative % fall
        fall_pct = max_fall_pct * (t ** fall_power)

        # Price level
        trigger_price = start_price * (1 - fall_pct / 100)

        # Convex share sizing
        shares = round(
            base_shares * (1 + size_multiplier * (t ** size_power))
        )

        # Ensure at least base_shares at first buy
        shares = max(shares, base_shares)

        plan.append({
            "level": i,
            "fall_pct": round(fall_pct, 2),
            "trigger_price": round(trigger_price, 1),
            "shares_to_buy": shares
        })

    return plan


class HybridOrderScheduler:
    """Class to schedule orders with convex accumulation strategy (first as market order, subsequent as GTT orders)"""
    
    def __init__(self, company_symbol: str, steps: int, current_price: float, 
                 base_shares: int = None, max_fall_pct: float = None,
                 fall_power: float = None, size_power: float = None, 
                 size_multiplier: float = None):
        """
        Initialize the Convex Accumulation Order Scheduler
        
        Parameters:
        - company_symbol: Trading symbol of the company (e.g., "ITC", "RELIANCE")
        - steps: Number of orders to place (including first)
        - current_price: Current price of the stock (base price for the first order)
        - base_shares: Base number of shares for first order (default: from config, fallback: 15)
        - max_fall_pct: Maximum fall percentage to plan for (default: from config, fallback: 10.0)
        - fall_power: Convexity of price spacing (default: from config, fallback: 1.7)
        - size_power: Convexity of share sizing (default: from config, fallback: 1.6)
        - size_multiplier: Size growth multiplier (default: from config, fallback: 1.0)
        """
        self.company_symbol = company_symbol.upper()
        self.current_price = current_price
        
        self.logger = setup_logger(__name__, self.company_symbol)

        # Load configuration and set parameters
        try:
            config = load_config()
            strategy_config = config.get('stratergy', {})  # Note: keeping typo for compatibility
            
            # If steps is 0 or None, load from config
            if not steps:
                steps = strategy_config.get('steps', 10)
                self.logger.info(f"Using steps from config: {steps}")
            
            # Load defaults from config if not provided
            if base_shares is None:
                base_shares = strategy_config.get('base_shares', 15)
                self.logger.info(f"Using base_shares from config: {base_shares}")
            
            if max_fall_pct is None:
                max_fall_pct = strategy_config.get('max_fall_pct', 10.0)
                self.logger.info(f"Using max_fall_pct from config: {max_fall_pct}")
            
            if fall_power is None:
                fall_power = strategy_config.get('fall_power', 1.7)
                self.logger.info(f"Using fall_power from config: {fall_power}")
            
            if size_power is None:
                size_power = strategy_config.get('size_power', 1.6)
                self.logger.info(f"Using size_power from config: {size_power}")
            
            if size_multiplier is None:
                size_multiplier = strategy_config.get('size_multiplier', 3.8)
                self.logger.info(f"Using size_multiplier from config: {size_multiplier}")
            
            self.steps = steps
            self.base_shares = base_shares
            self.max_fall_pct = max_fall_pct
            self.fall_power = fall_power
            self.size_power = size_power
            self.size_multiplier = size_multiplier
            
            self.logger.info(f"Convex accumulation parameters:")
            self.logger.info(f"  Steps: {self.steps}")
            self.logger.info(f"  Base shares: {self.base_shares}")
            self.logger.info(f"  Max fall: {self.max_fall_pct}%")
            self.logger.info(f"  Fall power: {self.fall_power}")
            self.logger.info(f"  Size power: {self.size_power}")
            self.logger.info(f"  Size multiplier: {self.size_multiplier}")
            
        except Exception as e:
            self.logger.warning(f"Could not load configuration: {e}, using defaults")
            # Set fallback values if config loading failed
            self.steps = steps or 10
            self.base_shares = base_shares or 15
            self.max_fall_pct = max_fall_pct or 10.0
            self.fall_power = fall_power or 1.7
            self.size_power = size_power or 1.6
            self.size_multiplier = size_multiplier or 3.8
        
        # Validate inputs
        if self.steps <= 0:
            raise ValueError("Steps must be positive")
        if current_price <= 0:
            raise ValueError("Current price must be positive")
        if self.base_shares <= 0:
            raise ValueError("Base shares must be positive")
        if self.max_fall_pct <= 0 or self.max_fall_pct > 100:
            raise ValueError("Max fall percentage must be between 0 and 100")
        
        # Setup logging
        self.logger.info(f"Initializing Convex Accumulation Order Scheduler for {self.company_symbol}")
        self.logger.info(f"Steps: {self.steps}, Current price: Rs.{current_price:.1f}")
        
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
                self.logger.info("Market is closed (weekend) - will skip first order")
                return
            
            # Check if it's within market hours (9:15 AM to 3:30 PM IST)
            market_start = current_time.replace(hour=9, minute=15, second=0, microsecond=0)
            market_end = current_time.replace(hour=15, minute=30, second=0, microsecond=0)
            
            if current_time < market_start or current_time > market_end:
                self.market_open = False
                self.logger.info("Market is closed (outside trading hours) - will skip first order")
            else:
                self.market_open = True
                self.logger.info("Market is open - will use MARKET order for first order")
                
        except ImportError:
            # If pytz is not available, assume market is closed for safety
            self.market_open = False
            self.logger.warning("pytz not available, assuming market is closed - will skip first order")
        except Exception as e:
            # If any error, assume market is closed for safety
            self.market_open = False
            self.logger.warning(f"Could not check market hours: {e} - will skip first order")
    
    def calculate_order_prices(self, base_price: float) -> List[Dict[str, Any]]:
        """
        Calculate prices and quantities for all orders using convex accumulation strategy
        
        Market OPEN: First order as MARKET, subsequent as GTT (convex spacing)
        Market CLOSED: Skip first order, start with GTT orders (convex spacing)
        
        Parameters:
        - base_price: Base price for the first order
        
        Returns:
        List of order details with calculated prices and quantities
        """
        # Generate convex accumulation plan
        plan = convex_accumulation_plan(
            start_price=base_price,
            base_shares=self.base_shares,
            max_fall_pct=self.max_fall_pct,
            steps=self.steps,
            fall_power=self.fall_power,
            size_power=self.size_power,
            size_multiplier=self.size_multiplier
        )
        
        orders = []
        
        if hasattr(self, 'market_open') and self.market_open:
            # Market is OPEN: Place all orders starting from current price
            for i, plan_item in enumerate(plan):
                if i == 0:
                    # First order: MARKET order at current price
                    order_type = 'MARKET'
                    order_type_display = 'MARKET ORDER'
                    trigger_price = None
                    order_price = base_price  # Use current price for market order
                else:
                    # Subsequent orders: GTT orders with convex spacing
                    order_type = 'GTT'
                    order_type_display = 'GTT ORDER'
                    order_price = plan_item['trigger_price']
                    trigger_price = round(order_price * 0.999, 1)  # 0.1% below order price
                
                quantity = plan_item['shares_to_buy']
                total_value = round(order_price * quantity, 1)
                
                order_details = {
                    'order_number': i + 1,
                    'order_price': round(order_price, 1),
                    'trigger_price': round(trigger_price, 1) if trigger_price else None,
                    'quantity': quantity,
                    'total_value': total_value,
                    'order_type': order_type,
                    'fall_pct': plan_item['fall_pct'],
                    'level': plan_item['level']
                }
                
                if order_type == 'MARKET':
                    self.logger.info(f"Order {i+1}: Price: Rs.{order_details['order_price']:.1f}, "
                                   f"Type: {order_type_display}, "
                                   f"Quantity: {quantity}, "
                                   f"Value: Rs.{total_value:.1f}")
                else:
                    self.logger.info(f"Order {i+1}: Price: Rs.{order_details['order_price']:.1f}, "
                                   f"Trigger: Rs.{order_details['trigger_price']:.1f}, "
                                   f"Type: {order_type_display}, "
                                   f"Fall: {plan_item['fall_pct']:.2f}%, "
                                   f"Quantity: {quantity}, "
                                   f"Value: Rs.{total_value:.1f}")
                
                orders.append(order_details)
        else:
            # Market is CLOSED: Skip first order, start with GTT orders
            self.logger.info("Market is closed - skipping first order and starting with GTT orders")
            
            for i, plan_item in enumerate(plan):
                if i == 0:
                    # First order: SKIPPED when market is closed
                    order_details = {
                        'order_number': i + 1,
                        'order_price': round(base_price, 1),
                        'trigger_price': None,
                        'quantity': plan_item['shares_to_buy'],
                        'total_value': round(base_price * plan_item['shares_to_buy'], 1),
                        'order_type': 'SKIPPED',
                        'skip_reason': 'Market closed - AMO not supported',
                        'fall_pct': plan_item['fall_pct'],
                        'level': plan_item['level']
                    }
                    
                    self.logger.info(f"Order {i+1}: SKIPPED (Market closed - AMO not supported)")
                else:
                    # Subsequent orders: GTT orders with convex spacing
                    order_price = plan_item['trigger_price']
                    trigger_price = round(order_price * 0.999, 1)  # 0.1% below order price
                    quantity = plan_item['shares_to_buy']
                    total_value = round(order_price * quantity, 1)
                    
                    order_details = {
                        'order_number': i + 1,
                        'order_price': round(order_price, 1),
                        'trigger_price': round(trigger_price, 1),
                        'quantity': quantity,
                        'total_value': total_value,
                        'order_type': 'GTT',
                        'fall_pct': plan_item['fall_pct'],
                        'level': plan_item['level']
                    }
                    
                    self.logger.info(f"Order {i+1}: Price: Rs.{order_details['order_price']:.1f}, "
                                   f"Trigger: Rs.{order_details['trigger_price']:.1f}, "
                                   f"Type: GTT ORDER, "
                                   f"Fall: {plan_item['fall_pct']:.2f}%, "
                                   f"Quantity: {quantity}, "
                                   f"Value: Rs.{total_value:.1f}")
                
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
                self.logger.error(f"Order details: Price: Rs.{order['order_price']:.1f}, Quantity: {order['quantity']}")
                
                # Continue with other orders even if one fails
                failed_order = {
                    **order,
                    'order_id': None,
                    'trigger_id': None,
                    'status': 'FAILED',
                    'error': error_msg,
                    'error_details': f"Failed to place {order['order_type']} order with price Rs.{order['order_price']:.1f} and quantity {order['quantity']}",
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
                order_strategy = 'First order as MARKET (market open), subsequent as GTT (convex accumulation)'
            else:
                if renumbered_orders:
                    order_strategy = 'GTT orders with convex accumulation (first order skipped due to market closed)'
                else:
                    order_strategy = 'All orders skipped (market closed)'
            
            summary = {
                'company_symbol': self.company_symbol,
                'order_count': self.steps,
                'actual_orders_placed': len(renumbered_orders),
                'strategy': 'Convex Accumulation',
                'strategy_parameters': {
                    'base_shares': self.base_shares,
                    'max_fall_pct': self.max_fall_pct,
                    'fall_power': self.fall_power,
                    'size_power': self.size_power,
                    'size_multiplier': self.size_multiplier
                },
                'order_strategy': order_strategy,
                'market_status': 'OPEN' if hasattr(self, 'market_open') and self.market_open else 'CLOSED',
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
        print(f"CONVEX ACCUMULATION ORDER SUMMARY FOR {self.company_symbol}")
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
        
        print(f"\nStrategy: Convex Accumulation")
        print(f"  Base Shares: {self.base_shares}")
        print(f"  Max Fall: {self.max_fall_pct}%")
        print(f"  Fall Power: {self.fall_power} (controls price spacing convexity)")
        print(f"  Size Power: {self.size_power} (controls share size convexity)")
        print(f"  Size Multiplier: {self.size_multiplier}")
        
        if hasattr(self, 'market_open') and self.market_open:
            print(f"Order Strategy: First as MARKET (market open), subsequent as GTT")
        else:
            if renumbered_orders:
                print(f"Order Strategy: GTT orders with convex accumulation (first order skipped)")
            else:
                print(f"Order Strategy: All orders skipped (market closed)")
        
        # Calculate totals from renumbered orders only
        total_quantity = sum(order.get('quantity', 0) for order in renumbered_orders)
        print(f"\nTotal Quantity: {total_quantity:,}")
        
        if successful_orders:
            total_value = sum(order.get('total_value', 0) for order in successful_orders)
            print(f"Total Value: Rs.{total_value:,.1f}")
        
        if renumbered_orders:
            print("\nOrder Details:")
            print("-" * 100)
            print(f"{'Order':<6} {'Type':<8} {'Fall %':<8} {'Price':<10} {'Trigger':<10} {'Quantity':<10} {'Value':<12} {'Status':<10}")
            print("-" * 100)
            
            for order in renumbered_orders:
                status = order.get('status', 'CALCULATED')
                order_type = order.get('order_type', 'UNKNOWN')
                trigger_price = order.get('trigger_price', 'N/A')
                fall_pct = order.get('fall_pct', 0)
                
                if trigger_price is None:
                    trigger_display = 'N/A'
                else:
                    trigger_display = f"Rs.{trigger_price:.1f}"
                
                print(f"{order['order_number']:<6} "
                       f"{order_type:<8} "
                       f"{fall_pct:<8.2f} "
                       f"Rs.{order['order_price']:<9.1f} "
                       f"{trigger_display:<10} "
                       f"{order['quantity']:<10,} "
                       f"Rs.{order['total_value']:<11.1f} "
                       f"{status:<10}")
        else:
            print("\nNo orders to display (all orders were skipped)")
            print("-" * 50)
        
        if failed_orders:
            print("\nFailed Orders:")
            print("-" * 80)
            for order in failed_orders:
                print(f"Order {order['order_number']} ({order.get('order_type', 'UNKNOWN')}):")
                print(f"  • Price: Rs.{order.get('order_price', 0):.1f}")
                print(f"  • Quantity: {order.get('quantity', 0)}")
                print(f"  • Error: {order.get('error', 'Unknown error')}")
                if order.get('error_details'):
                    print(f"  • Details: {order.get('error_details')}")
                print()
        
        print("="*80)
    
    def run(self) -> None:
        """Execute the complete GTT order scheduling process"""
        try:
            self.logger.info("Starting convex accumulation order scheduling process")
            
            # Connect to Kite
            self.connect_to_kite()
            
            # Use the provided current price as base
            self.logger.info(f"Using provided current price as base: Rs.{self.current_price:.1f}")
            
            # Calculate order prices using convex accumulation
            orders = self.calculate_order_prices(self.current_price)
            
            # Confirm with user before placing orders
            self.print_order_summary(orders)
            
            print("\n⚠️  IMPORTANT NOTES:")
            if hasattr(self, 'market_open') and self.market_open:
                 print("   • First order will be placed as a MARKET order (executes immediately)")
                 print("   • Subsequent orders will be placed as GTT orders (execute when triggered)")
                 print("   • GTT orders use convex accumulation: small falls → small adds, bigger falls → larger adds")
                 print("   • Price spacing and share sizes increase convexly (power-based)")
                 print("   • Trigger prices are set 0.1% below order prices for tight control")
            else:
                 print("   • First order will be SKIPPED (Market closed - AMO not supported)")
                 print("   • GTT orders use convex accumulation starting from lower prices")
                 print("   • Small falls → small adds, bigger falls → larger adds")
                 print("   • Price spacing and share sizes increase convexly (power-based)")
                 print("   • Trigger prices are set 0.1% below order prices for tight control")
            
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
            
            self.logger.info("Convex accumulation order scheduling process completed successfully")
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Convex accumulation order scheduling failed: {error_msg}")
            self.logger.error(f"Error type: {type(e).__name__}")
            self.logger.error(f"Full error details: {e}")
            raise


def main():
    """Main function to parse arguments and run the scheduler"""
    parser = argparse.ArgumentParser(
        description="Schedule orders with convex accumulation strategy (first as market order, subsequent as GTT orders)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        'company_symbol',
        help='Trading symbol of the company (e.g., ITC, RELIANCE, TCS)'
    )
    
    parser.add_argument(
        'steps',
        nargs='?',
        type=int,
        default=None,
        help='Number of orders to place (default: from config.yaml, fallback: 10)'
    )
    
    parser.add_argument(
        'current_price',
        type=float,
        help='Current price of the stock (base price for the first order)'
    )
    
    parser.add_argument(
        '--base_shares',
        type=int,
        default=None,
        help='Base number of shares for first order (default: from config.yaml, fallback: 15)'
    )
    
    parser.add_argument(
        '--max_fall_pct',
        type=float,
        default=None,
        help='Maximum fall percentage to plan for (default: from config.yaml, fallback: 10.0)'
    )
    
    parser.add_argument(
        '--fall_power',
        type=float,
        default=None,
        help='Convexity of price spacing, >1 = convex (default: from config.yaml, fallback: 1.7)'
    )
    
    parser.add_argument(
        '--size_power',
        type=float,
        default=None,
        help='Convexity of share sizing, >1 = convex (default: from config.yaml, fallback: 1.6)'
    )
    
    parser.add_argument(
        '--size_multiplier',
        type=float,
        default=None,
        help='Size growth multiplier (default: from config.yaml, fallback: 3.8)'
    )
    
    args = parser.parse_args()
    
    try:
        # Create and run scheduler
        scheduler = HybridOrderScheduler(
            company_symbol=args.company_symbol,
            steps=args.steps,
            current_price=args.current_price,
            base_shares=args.base_shares,
            max_fall_pct=args.max_fall_pct,
            fall_power=args.fall_power,
            size_power=args.size_power,
            size_multiplier=args.size_multiplier
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

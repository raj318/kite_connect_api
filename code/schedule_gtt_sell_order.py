#!/usr/bin/env python3
"""
GTT Sell Order Scheduler Script

This script places a GTT sell order for a given company to achieve a target net profit percentage.
It:
1. Fetches holdings and positions from Kite
2. Calculates total quantity and average buy price
3. Calculates required sell price considering all charges to achieve target net profit
4. Shows profit amount in rupees
5. Asks for approval before placing the GTT order

Usage:
    python schedule_gtt_sell_order.py <company_symbol> <net_profit_percentage> [--quantity N] [--yes] [--charge-mode delivery|intraday]

Examples:
    python schedule_gtt_sell_order.py ITC 2.5
    # Places GTT sell order to achieve 2.5% net profit on all ITC holdings
    
    python schedule_gtt_sell_order.py RELIANCE 3.0 --quantity 10 --charge-mode intraday
    # Places GTT sell order for 10 shares of RELIANCE to achieve 3% net profit

    python schedule_gtt_sell_order.py HDFCBANK 0.6 --charge-mode intraday
    # Same-day (intraday) charges, target 0.6% net profit
    
    python schedule_gtt_sell_order.py TCS 2.0 --yes
    # Auto-confirms and places order without prompting
"""

import argparse
import sys
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from kite_connect_api import KiteConnectAPI
from kite_utils import setup_logger, load_config


def calculate_zerodha_charges(sell_value: float, quantity: int, charge_mode: str = "delivery") -> dict:
    """
    Calculate Zerodha charges for equity sell orders
    
    Parameters:
    - sell_value: Total sell value (price * quantity)
    - quantity: Number of shares being sold
    
    Returns:
    Dictionary containing all charges and total charges
    """
    mode = (charge_mode or "delivery").lower()

    # Common charges (sell-side)
    exchange_charges = sell_value * 0.0000345  # NSE Equity: 0.00345%
    sebi_fees = sell_value * 0.000001  # 0.0001%

    if mode == "intraday":
        # Intraday (same-day) sell-side charges
        # Brokerage: 0.03% or ₹20 per order, whichever is lower
        brokerage = min(sell_value * 0.0003, 20.0)
        # STT: 0.025% on sell side
        stt = sell_value * 0.00025
        # No DP charges for intraday
        dp_charges = 0.0
        # GST: 18% on (brokerage + exchange + sebi)
        gst_base = brokerage + exchange_charges + sebi_fees
        gst = gst_base * 0.18
    else:
        # Delivery (different-day) sell-side charges
        brokerage = 0.00
        # STT: 0.1% on sell side
        stt = sell_value * 0.001
        # DP charges: ₹13.5 + 18% GST = ₹15.93
        dp_charges = 15.93
        # GST: 18% on (exchange + sebi)
        gst_base = exchange_charges + sebi_fees
        gst = gst_base * 0.18
    
    # Calculate total charges
    total_charges = brokerage + stt + exchange_charges + sebi_fees + dp_charges + gst
    
    return {
        'charge_mode': mode,
        'brokerage': brokerage,
        'stt': stt,
        'exchange_charges': exchange_charges,
        'sebi_fees': sebi_fees,
        'dp_charges': dp_charges,
        'gst': gst,
        'total_charges': total_charges,
        'charges_per_share': total_charges / quantity if quantity > 0 else 0
    }


def calculate_profit_with_charges(buy_price: float, sell_price: float, quantity: int, charge_mode: str = "delivery") -> dict:
    """
    Calculate profit after considering all Zerodha charges
    
    Parameters:
    - buy_price: Average buy price per share
    - sell_price: Sell price per share
    - quantity: Number of shares
    
    Returns:
    Dictionary containing profit analysis
    """
    # Calculate basic profit
    buy_value = buy_price * quantity
    sell_value = sell_price * quantity
    gross_profit = sell_value - buy_value
    
    # Calculate charges
    charges = calculate_zerodha_charges(sell_value, quantity, charge_mode=charge_mode)
    total_charges = charges['total_charges']
    
    # Calculate net profit
    net_profit = gross_profit - total_charges
    
    # Calculate profit percentages
    gross_profit_percentage = (gross_profit / buy_value) * 100 if buy_value > 0 else 0
    net_profit_percentage = (net_profit / buy_value) * 100 if buy_value > 0 else 0
    charges_percentage = (total_charges / buy_value) * 100 if buy_value > 0 else 0
    
    return {
        'buy_value': buy_value,
        'sell_value': sell_value,
        'gross_profit': gross_profit,
        'gross_profit_percentage': gross_profit_percentage,
        'charges': charges,
        'total_charges': total_charges,
        'charges_percentage': charges_percentage,
        'net_profit': net_profit,
        'net_profit_percentage': net_profit_percentage,
        'break_even_price': buy_price + (total_charges / quantity) if quantity > 0 else buy_price
    }


def calculate_optimal_sell_price(buy_price: float, quantity: int, target_net_profit_percentage: float, charge_mode: str = "delivery") -> float:
    """
    Calculate the optimal sell price to achieve target net profit percentage after charges.
    Ensures net profit is >= target (never below).
    
    Parameters:
    - buy_price: Average buy price per share
    - quantity: Number of shares
    - target_net_profit_percentage: Target net profit percentage
    
    Returns:
    Optimal sell price per share that achieves at least the target net profit
    """
    # Start with a reasonable guess
    sell_price = buy_price * (1 + target_net_profit_percentage / 100)
    
    # Iteratively find the optimal price
    max_iterations = 100
    tolerance = 0.001  # 0.001% tolerance for convergence
    adjustment_rate = 0.0001  # Finer adjustment (0.01%)
    
    last_price = sell_price
    converged = False
    
    for iteration in range(max_iterations):
        profit_analysis = calculate_profit_with_charges(buy_price, sell_price, quantity, charge_mode=charge_mode)
        current_net_profit_percentage = profit_analysis['net_profit_percentage']
        
        # Check if we've converged (within tolerance)
        if abs(current_net_profit_percentage - target_net_profit_percentage) <= tolerance:
            converged = True
            break
        
        # Adjust sell price based on difference
        if current_net_profit_percentage < target_net_profit_percentage:
            # Need higher profit, increase sell price
            sell_price *= (1 + adjustment_rate)
        else:
            # Too much profit, decrease sell price (but keep moving down carefully)
            sell_price *= (1 - adjustment_rate)
        
        last_price = sell_price
    
    # Final check: ensure we don't round down below target
    final_analysis = calculate_profit_with_charges(buy_price, round(sell_price, 2), quantity, charge_mode=charge_mode)
    if final_analysis['net_profit_percentage'] < target_net_profit_percentage:
        # If rounding down causes us to miss target, round up to next paisa
        sell_price = round(sell_price + 0.01, 2)
    else:
        sell_price = round(sell_price, 2)
    
    return sell_price


def get_holdings_info(kite_api: KiteConnectAPI, company_symbol: str) -> Tuple[int, float]:
    """
    Get total quantity and average price from holdings and positions
    
    Parameters:
    - kite_api: KiteConnectAPI instance
    - company_symbol: Trading symbol
    
    Returns:
    Tuple of (total_quantity, average_price)
    """
    try:
        total_quantity = 0
        total_value = 0.0
        symbol_upper = company_symbol.upper()
        logging.info("Fetching holdings information...")

        # Try to get holdings and positions via helper
        try:
            account_details = kite_api.get_account_details()
            holdings = account_details.get('holdings') or []
            account_positions = account_details.get('positions') or []
            logging.info(f"account holding = {holdings}")
        except Exception:
            holdings = []
            account_positions = []

        # If holdings empty, try raw API call
        if not holdings and hasattr(kite_api, 'kite') and getattr(kite_api.kite, 'holdings', None):
            try:
                raw_holdings = kite_api.kite.holdings() or []
                holdings = raw_holdings
            except Exception as e:
                logging.warning(f"Could not fetch raw holdings: {e}")

        # Sum allocated and t1 quantities separately and add both
        company_holdings = [h for h in (holdings or []) if h.get('tradingsymbol', '').upper() == symbol_upper]
        logging.info(f"holdings = {company_holdings}")

        allocated_total = 0
        t1_total = 0
        for holding in company_holdings:
            allocated = int(holding.get('quantity') or 0)
            t1 = int(holding.get('t1_quantity') or 0)
            avg_price = float(holding.get('average_price') or 0)
            allocated_total += allocated
            t1_total += t1
            if avg_price > 0:
                # Use the average price for both allocated and t1 quantities
                total_value += (allocated + t1) * avg_price

        total_quantity += allocated_total + t1_total
        logging.info(f"holdings allocated={allocated_total}, t1={t1_total}, subtotal={total_quantity}")

        # Also include positions (day and net) to capture trades executed today
        pos_total = 0
        positions = []
        # Prefer positions returned by account_details if present
        if account_positions:
            positions = account_positions
        else:
            try:
                positions_resp = kite_api.kite.positions() or {}
                # Combine 'net' and 'day' lists to be thorough
                positions = (positions_resp.get('net') or []) + (positions_resp.get('day') or [])
            except Exception as e:
                logging.warning(f"Could not fetch positions: {e}")

        logging.info(f"positions = {positions}")
        for position in positions or []:
            if position.get('tradingsymbol', '').upper() == symbol_upper:
                # prefer net_quantity, otherwise use buy_quantity
                qty = int(position.get('net_quantity') or position.get('buy_quantity') or 0)
                avg = float(position.get('average_price') or position.get('buy_price') or 0)
                if qty > 0:
                    pos_total += qty
                    if avg > 0:
                        total_value += qty * avg

        total_quantity += pos_total
        logging.info(f"positions_total={pos_total}, total_quantity={total_quantity}")

        # If still zero, log details to help debugging
        if total_quantity == 0:
            logging.debug(f"Holdings list: {holdings}")
            try:
                if hasattr(kite_api, 'kite') and kite_api.kite:
                    logging.debug(f"Raw positions: {kite_api.kite.positions()}")
            except Exception:
                pass

        logging.info(f"total quantity = {total_quantity}")
        average_price = (total_value / total_quantity) if total_quantity > 0 else 0.0
        return total_quantity, round(average_price, 2)

    except Exception as e:
        logging.error(f"Error getting holdings info: {e}")
        raise


def print_order_summary(company_symbol: str, quantity: int, avg_price: float, 
                       sell_price: float, target_profit_pct: float, profit_analysis: dict,
                       charge_mode: str) -> None:
    """
    Print a detailed summary of the GTT sell order
    
    Parameters:
    - company_symbol: Trading symbol
    - quantity: Number of shares
    - avg_price: Average buy price
    - sell_price: Calculated sell price
    - target_profit_pct: Target profit percentage
    - profit_analysis: Profit analysis dictionary
    """
    print("\n" + "="*80)
    print(f"GTT SELL ORDER SUMMARY FOR {company_symbol}")
    print("="*80)
    
    print(f"\nHoldings Information:")
    print(f"  Company: {company_symbol}")
    print(f"  Total Quantity: {quantity:,} shares")
    print(f"  Average Buy Price: ₹{avg_price:.2f}")
    print(f"  Total Buy Value: ₹{profit_analysis['buy_value']:,.2f}")
    
    print(f"\nSell Order Details:")
    print(f"  Charge Mode: {charge_mode}")
    print(f"  Sell Price: ₹{sell_price:.2f}")
    print(f"  Quantity: {quantity:,} shares")
    print(f"  Total Sell Value: ₹{profit_analysis['sell_value']:,.2f}")
    
    print(f"\nProfit Analysis:")
    print(f"  Target Net Profit: {target_profit_pct}%")
    print(f"  Gross Profit: ₹{profit_analysis['gross_profit']:,.2f} ({profit_analysis['gross_profit_percentage']:.2f}%)")
    print(f"  Total Charges: ₹{profit_analysis['total_charges']:,.2f} ({profit_analysis['charges_percentage']:.2f}%)")
    print(f"  Net Profit: ₹{profit_analysis['net_profit']:,.2f} ({profit_analysis['net_profit_percentage']:.2f}%)")
    print(f"  Break-even Price: ₹{profit_analysis['break_even_price']:.2f}")
    
    print(f"\nCharge Breakdown:")
    charges = profit_analysis['charges']
    print(f"  Brokerage: ₹{charges['brokerage']:.2f}")
    print(f"  STT: ₹{charges['stt']:.2f}")
    print(f"  Exchange Charges: ₹{charges['exchange_charges']:.2f}")
    print(f"  SEBI Fees: ₹{charges['sebi_fees']:.2f}")
    print(f"  DP Charges: ₹{charges['dp_charges']:.2f}")
    print(f"  GST: ₹{charges['gst']:.2f}")
    print(f"  Total Charges: ₹{charges['total_charges']:.2f}")
    print(f"  Charges per Share: ₹{charges['charges_per_share']:.2f}")
    
    print("\n" + "="*80)


def save_order_details(company_symbol: str, quantity: int, avg_price: float, 
                      sell_price: float, trigger_price: float, target_profit_pct: float,
                      profit_analysis: dict, trigger_id: Optional[str] = None) -> None:
    """
    Save order details to a JSON file
    
    Parameters:
    - company_symbol: Trading symbol
    - quantity: Number of shares
    - avg_price: Average buy price
    - sell_price: Sell price
    - trigger_price: GTT trigger price
    - target_profit_pct: Target profit percentage
    - profit_analysis: Profit analysis dictionary
    - trigger_id: GTT trigger ID (if order was placed)
    """
    try:
        import json
        import os
        
        # Create orders directory if it doesn't exist
        orders_dir = os.path.join('workdir', 'orders')
        os.makedirs(orders_dir, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(orders_dir, f'{company_symbol}_gtt_sell_{timestamp}.json')
        
        order_data = {
            'company_symbol': company_symbol,
            'order_type': 'GTT_SELL',
            'quantity': quantity,
            'average_buy_price': avg_price,
            'sell_price': sell_price,
            'trigger_price': trigger_price,
            'target_net_profit_percentage': target_profit_pct,
            'profit_analysis': profit_analysis,
            'trigger_id': trigger_id,
            'status': 'PLACED' if trigger_id else 'CALCULATED',
            'timestamp': datetime.now().isoformat()
        }
        
        # Write to file
        with open(filename, 'w') as f:
            json.dump(order_data, f, indent=2)
        
        logging.info(f"Order details saved to {filename}")
        
    except Exception as e:
        logging.error(f"Failed to save order details: {e}")


class GTTSellOrderScheduler:
    """Class to schedule GTT sell orders based on target net profit"""
    
    def __init__(self, company_symbol: str, net_profit_percentage: float, quantity: Optional[int] = None,
                 charge_mode: str = "delivery"):
        """
        Initialize the GTT Sell Order Scheduler
        
        Parameters:
        - company_symbol: Trading symbol of the company (e.g., "ITC", "RELIANCE")
        - net_profit_percentage: Target net profit percentage (e.g., 2.5 for 2.5%)
        - quantity: Optional quantity to sell (default: all holdings)
        """
        self.company_symbol = company_symbol.upper()
        self.net_profit_percentage = net_profit_percentage
        self.requested_quantity = quantity
        self.charge_mode = (charge_mode or "delivery").lower()
        
        self.logger = setup_logger(__name__, self.company_symbol)
        
        # Initialize Kite Connect API
        self.kite_api = KiteConnectAPI(self.company_symbol)
        
        self.logger.info(f"Initializing GTT Sell Order Scheduler for {self.company_symbol}")
        self.logger.info(f"Target net profit: {net_profit_percentage}%")
        self.logger.info(f"Charge mode: {self.charge_mode}")
        if quantity:
            self.logger.info(f"Requested quantity: {quantity} shares")
    
    def connect_to_kite(self) -> None:
        """Establish connection to Kite Connect"""
        try:
            self.kite_api.connect()
            self.logger.info("Successfully connected to Kite Connect")
        except Exception as e:
            self.logger.error(f"Failed to connect to Kite Connect: {e}")
            raise
    
    def check_and_handle_existing_sell_orders(self, auto_confirm: bool = False) -> bool:
        """
        Check for existing GTT SELL orders for the company.
        If found, ask user to delete them or proceed.
        
        Parameters:
        - auto_confirm: If True, automatically proceed without prompting
        
        Returns:
        - bool: True if can proceed, False if user cancelled
        """
        try:
            self.logger.info(f"Checking for existing GTT SELL orders for {self.company_symbol}...")
            
            # Get all GTT orders
            gtt_orders = self.kite_api.get_gtt_orders()
            
            # Filter for SELL orders of this company
            existing_sell_orders = []
            for order in gtt_orders:
                try:
                    trading_symbol = order.get('condition', {}).get('tradingsymbol', '').upper()
                    transaction_type = order.get('orders', [{}])[0].get('transaction_type', '').upper()
                    status = order.get('status', 'UNKNOWN').upper()
                    
                    if trading_symbol == self.company_symbol and transaction_type == 'SELL' and status in ['ACTIVE', 'PENDING']:
                        existing_sell_orders.append(order)
                except Exception:
                    continue
            
            if not existing_sell_orders:
                self.logger.info(f"No existing SELL GTT orders found for {self.company_symbol}")
                print(f"\n✓ No existing SELL GTT orders found for {self.company_symbol}")
                return True
            
            # Found existing orders - ask user
            print(f"\n⚠️  Found {len(existing_sell_orders)} existing SELL GTT order(s) for {self.company_symbol}:")
            for i, order in enumerate(existing_sell_orders, 1):
                trigger_id = order.get('id')
                price = order.get('orders', [{}])[0].get('price', 'N/A')
                quantity = order.get('orders', [{}])[0].get('quantity', 'N/A')
                status = order.get('status', 'UNKNOWN')
                print(f"  {i}. Trigger ID: {trigger_id}, Price: {price}, Qty: {quantity}, Status: {status}")
            
            if auto_confirm:
                # Auto delete existing orders
                self.logger.info(f"Auto-mode: Deleting {len(existing_sell_orders)} existing SELL orders")
                print(f"\nDeleting {len(existing_sell_orders)} existing SELL order(s)...")
                for order in existing_sell_orders:
                    trigger_id = order.get('id')
                    try:
                        self.kite_api.delete_gtt_order(trigger_id)
                        self.logger.info(f"Deleted GTT order {trigger_id}")
                        print(f"  ✓ Deleted order {trigger_id}")
                    except Exception as e:
                        self.logger.error(f"Failed to delete GTT order {trigger_id}: {e}")
                        print(f"  ✗ Failed to delete order {trigger_id}: {e}")
                return True
            else:
                # Ask user to confirm deletion
                confirm = input(f"\nDelete these {len(existing_sell_orders)} existing SELL order(s) and place new one? (yes/no): ").strip().lower()
                if confirm not in ['yes', 'y']:
                    self.logger.info("User chose not to delete existing orders. Cancelling new order placement.")
                    print("Cancelled. Keeping existing orders.")
                    return False
                
                # Delete existing orders
                print(f"Deleting {len(existing_sell_orders)} existing SELL order(s)...")
                deleted_count = 0
                for order in existing_sell_orders:
                    trigger_id = order.get('id')
                    try:
                        self.kite_api.delete_gtt_order(trigger_id)
                        self.logger.info(f"Deleted GTT order {trigger_id}")
                        print(f"  ✓ Deleted order {trigger_id}")
                        deleted_count += 1
                    except Exception as e:
                        self.logger.error(f"Failed to delete GTT order {trigger_id}: {e}")
                        print(f"  ✗ Failed to delete order {trigger_id}: {e}")
                
                if deleted_count == len(existing_sell_orders):
                    self.logger.info(f"Successfully deleted all {deleted_count} existing SELL orders")
                    print(f"\n✓ Successfully deleted all {deleted_count} order(s). Proceeding with new order...")
                    return True
                else:
                    self.logger.warning(f"Could only delete {deleted_count} of {len(existing_sell_orders)} orders")
                    print(f"\n⚠️  Could only delete {deleted_count} of {len(existing_sell_orders)} orders. Please try again.")
                    return False
                
        except Exception as e:
            self.logger.error(f"Error checking/handling existing orders: {e}")
            print(f"Error checking existing orders: {e}")
            return False
    
    def get_holdings_and_calculate_price(self) -> Tuple[int, float, float, float, dict]:
        """
        Get holdings info and calculate required sell price
        
        Returns:
        Tuple of (quantity, avg_price, sell_price, trigger_price, profit_analysis)
        """
        # Get holdings information
        total_quantity, avg_price = get_holdings_info(self.kite_api, self.company_symbol)
        
        # print(f"total")
        if total_quantity <= 0:
            raise ValueError(f"No holdings found for {self.company_symbol}")
        
        # Use requested quantity or all holdings
        sell_quantity = self.requested_quantity if self.requested_quantity else total_quantity
        
        if sell_quantity > total_quantity:
            self.logger.warning(f"Requested quantity ({sell_quantity}) exceeds holdings ({total_quantity}). Using {total_quantity}.")
            sell_quantity = total_quantity
        
        if sell_quantity <= 0:
            raise ValueError(f"Invalid quantity: {sell_quantity}")
        
        # Calculate optimal sell price
        sell_price = calculate_optimal_sell_price(avg_price, sell_quantity, self.net_profit_percentage, charge_mode=self.charge_mode)
        sell_price = round(sell_price, 1)
        
        # Calculate trigger price (fixed 0.50 rupees above sell price)
        trigger_price = round(sell_price + 0.50, 2)
        
        # Calculate profit analysis
        profit_analysis = calculate_profit_with_charges(avg_price, sell_price, sell_quantity, charge_mode=self.charge_mode)
        
        return sell_quantity, avg_price, sell_price, trigger_price, profit_analysis
    
    def place_gtt_sell_order(self, quantity: int, sell_price: float, trigger_price: float) -> str:
        """
        Place GTT sell order. Retries with increased price until successful or hits safety limit (30 retries).
        Keeps increasing price by 1 rupee each retry to exceed 0.25% trigger difference requirement.
        
        Parameters:
        - quantity: Number of shares to sell
        - sell_price: Sell price per share
        - trigger_price: GTT trigger price
        
        Returns:
        GTT trigger ID
        """
        try:
            # Get current price for GTT order
            current_price = None
            try:
                live_data = self.kite_api.get_live_data()
                current_price = live_data.get('last_traded_price', 0)
            except Exception as e:
                self.logger.warning(f"Could not fetch current price: {e}")
                current_price = trigger_price - 1.0  # Fallback
            
            # Place GTT sell order with retry logic - keep trying until successful
            max_retries = 30  # Safety limit to prevent infinite loops
            retry_count = 0
            current_sell_price = sell_price
            current_trigger_price = trigger_price
            
            while True:
                try:
                    self.logger.info(f"Placing GTT order (attempt {retry_count + 1}): sell_price={current_sell_price}, trigger_price={current_trigger_price}, current_price={current_price}")
                    
                    trigger_id = self.kite_api.place_gtt_order(
                        trading_symbol=self.company_symbol,
                        exchange="NSE",
                        transaction_type="SELL",
                        quantity=quantity,
                        price=current_sell_price,
                        trigger_price=current_trigger_price,
                        order_type="LIMIT",
                        validity="DAY",
                        current_price=current_price
                    )
                    
                    # Success!
                    if retry_count > 0:
                        self.logger.info(f"GTT sell order placed successfully on attempt {retry_count + 1}. Trigger ID: {trigger_id}")
                        print(f"\n✓ GTT order placed successfully after {retry_count} retry/retries!")
                    else:
                        self.logger.info(f"GTT sell order placed successfully. Trigger ID: {trigger_id}")
                        print(f"\n✓ GTT order placed successfully!")
                    
                    return trigger_id
                    
                except Exception as e:
                    error_str = str(e).lower()
                    self.logger.error(f"Attempt {retry_count + 1} failed: {e}")
                    
                    # Check if error is about trigger price being too close
                    if "trigger price" in error_str and "too close" in error_str:
                        
                        # Check if we've hit safety limit
                        if retry_count >= max_retries:
                            self.logger.error(f"Reached maximum retry limit of {max_retries}. Giving up.")
                            print(f"\n✗ Failed after {max_retries} retry attempts. Trigger price requirement cannot be met.")
                            raise Exception(f"Failed to place GTT order after {max_retries} retries: {e}")
                        
                        # Increase price by 0.05% of current price (scales with stock price)
                        price_increase = round(current_sell_price * 0.0005, 2)  # 0.05% increase
                        current_sell_price = round(current_sell_price + price_increase, 2)
                        current_trigger_price = round(current_sell_price + 0.50, 2)  # Fixed 0.50 rupees above sell price
                        
                        retry_count += 1
                        
                        self.logger.warning(f"Trigger price too close to last price. Retrying (attempt {retry_count + 1})...")
                        self.logger.info(f"New prices - sell={current_sell_price}, trigger={current_trigger_price}, price_increase={price_increase}")
                        print(f"⚠️  Attempt {retry_count}: Trigger too close. Trying price Rs.{current_sell_price:.2f} (+{price_increase:.2f})...")
                        
                        # Continue the loop to retry
                        continue
                    else:
                        # Not a trigger price error - raise immediately
                        self.logger.error(f"Failed to place GTT sell order: {e}")
                        raise
                        
        except Exception as e:
            self.logger.error(f"Failed to place GTT sell order: {e}")
            raise
    
    def run(self, auto_confirm: bool = False) -> None:
        """Execute the complete GTT sell order scheduling process"""
        try:
            self.logger.info("Starting GTT sell order scheduling process")
            
            # Connect to Kite
            self.connect_to_kite()
            
            # Check for existing sell orders and handle deletion
            if not self.check_and_handle_existing_sell_orders(auto_confirm=auto_confirm):
                print("Order placement cancelled.")
                return
            
            # Get holdings and calculate prices
            quantity, avg_price, sell_price, trigger_price, profit_analysis = self.get_holdings_and_calculate_price()
            # Print summary
            print_order_summary(self.company_symbol, quantity, avg_price, sell_price, 
                              self.net_profit_percentage, profit_analysis, self.charge_mode)
            
            # Show profit in rupees
            net_profit_rupees = profit_analysis['net_profit']
            print(f"\n💰 NET PROFIT: ₹{net_profit_rupees:,.2f}")
            print(f"   (Target: {self.net_profit_percentage}% net profit)")
            
            # Ask for confirmation
            if not auto_confirm:
                confirm = input("\nDo you want to proceed with placing this GTT sell order? (yes/no): ").strip().lower()
                if confirm not in ['yes', 'y']:
                    self.logger.info("Order placement cancelled by user")
                    print("Order placement cancelled.")
                    # Save calculated order even if not placed
                    save_order_details(self.company_symbol, quantity, avg_price, sell_price, 
                                     trigger_price, self.net_profit_percentage, profit_analysis)
                    return
            
            # Place GTT order
            self.logger.info("Placing GTT sell order...")
            trigger_id = self.place_gtt_sell_order(quantity, sell_price, trigger_price)
            
            # Save order details
            save_order_details(self.company_symbol, quantity, avg_price, sell_price, 
                             trigger_price, self.net_profit_percentage, profit_analysis, trigger_id)
            
            print(f"\n✅ GTT sell order placed successfully!")
            print(f"   Trigger ID: {trigger_id}")
            print(f"   Order will execute when price reaches ₹{trigger_price:.2f}")
            
            self.logger.info("GTT sell order scheduling process completed successfully")
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"GTT sell order scheduling failed: {error_msg}")
            self.logger.error(f"Error type: {type(e).__name__}")
            raise


def main():
    """Main function to parse arguments and run the scheduler"""
    parser = argparse.ArgumentParser(
        description="Place GTT sell order to achieve target net profit percentage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        'company_symbol',
        help='Trading symbol of the company (e.g., ITC, RELIANCE, TCS)'
    )
    
    parser.add_argument(
        'net_profit_percentage',
        type=float,
        help='Target net profit percentage (e.g., 2.5 for 2.5%%)'
    )
    
    parser.add_argument(
        '--quantity', '-q',
        type=int,
        default=None,
        help='Quantity to sell (default: all holdings)'
    )

    parser.add_argument(
        '--charge-mode',
        choices=['delivery', 'intraday'],
        default='delivery',
        help='Charge mode: delivery (different-day) or intraday (same-day). Default: delivery'
    )
    
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='Auto-confirm and place order without prompting'
    )
    
    args = parser.parse_args()
    
    try:
        # Validate inputs
        if args.net_profit_percentage <= 0:
            print("Error: Net profit percentage must be positive")
            sys.exit(1)
        
        if args.quantity and args.quantity <= 0:
            print("Error: Quantity must be positive")
            sys.exit(1)
        
        # Create and run scheduler
        scheduler = GTTSellOrderScheduler(
            company_symbol=args.company_symbol,
            net_profit_percentage=args.net_profit_percentage,
            quantity=args.quantity,
            charge_mode=args.charge_mode
        )
        
        scheduler.run(auto_confirm=args.yes)
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()


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
    python schedule_gtt_sell_order.py <company_symbol> <net_profit_percentage> [--quantity N] [--yes]

Examples:
    python schedule_gtt_sell_order.py ITC 2.5
    # Places GTT sell order to achieve 2.5% net profit on all ITC holdings
    
    python schedule_gtt_sell_order.py RELIANCE 3.0 --quantity 10
    # Places GTT sell order for 10 shares of RELIANCE to achieve 3% net profit
    
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


def calculate_zerodha_charges(sell_value: float, quantity: int) -> dict:
    """
    Calculate all Zerodha charges for equity delivery sell orders
    
    Parameters:
    - sell_value: Total sell value (price * quantity)
    - quantity: Number of shares being sold
    
    Returns:
    Dictionary containing all charges and total charges
    """
    # Zerodha Equity Delivery Sell-Side Charges
    brokerage = 0.00  # Zero for equity delivery
    
    # STT (Securities Transaction Tax): 0.1% of Sell Value
    stt = sell_value * 0.001
    
    # Exchange Transaction Charges (NSE Equity): 0.00345% of Sell Value
    exchange_charges = sell_value * 0.0000345
    
    # SEBI Turnover Fees: 0.0001% of Sell Value
    sebi_fees = sell_value * 0.000001
    
    # DP (Depository Participant) Charges: ₹13.5 + 18% GST = ₹15.93
    dp_charges = 15.93
    
    # GST: 18% on (Exchange Transaction Charges + SEBI Turnover Fees)
    gst_base = exchange_charges + sebi_fees
    gst = gst_base * 0.18
    
    # Calculate total charges
    total_charges = brokerage + stt + exchange_charges + sebi_fees + dp_charges + gst
    
    return {
        'brokerage': brokerage,
        'stt': stt,
        'exchange_charges': exchange_charges,
        'sebi_fees': sebi_fees,
        'dp_charges': dp_charges,
        'gst': gst,
        'total_charges': total_charges,
        'charges_per_share': total_charges / quantity if quantity > 0 else 0
    }


def calculate_profit_with_charges(buy_price: float, sell_price: float, quantity: int) -> dict:
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
    charges = calculate_zerodha_charges(sell_value, quantity)
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


def calculate_optimal_sell_price(buy_price: float, quantity: int, target_net_profit_percentage: float) -> float:
    """
    Calculate the optimal sell price to achieve target net profit percentage after charges
    
    Parameters:
    - buy_price: Average buy price per share
    - quantity: Number of shares
    - target_net_profit_percentage: Target net profit percentage
    
    Returns:
    Optimal sell price per share
    """
    # Start with a reasonable guess
    sell_price = buy_price * (1 + target_net_profit_percentage / 100)
    
    # Iteratively find the optimal price
    max_iterations = 50
    tolerance = 0.01  # 0.01% tolerance
    
    for iteration in range(max_iterations):
        profit_analysis = calculate_profit_with_charges(buy_price, sell_price, quantity)
        current_net_profit_percentage = profit_analysis['net_profit_percentage']
        
        # Check if we're close enough to target
        if abs(current_net_profit_percentage - target_net_profit_percentage) <= tolerance:
            break
        
        # Adjust sell price based on difference
        if current_net_profit_percentage < target_net_profit_percentage:
            # Need higher profit, increase sell price
            sell_price *= 1.001  # Increase by 0.1%
        else:
            # Too much profit, decrease sell price
            sell_price *= 0.999  # Decrease by 0.1%
    
    return round(sell_price, 2)


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
        # First try the helper which may return filtered holdings
        try:
            account_details = kite_api.get_account_details()
            holdings = account_details.get('holdings') or []
            logging.info(f"account holding = {holdings}")
        except Exception:
            holdings = []

        # If holdings empty, try raw API call
        if not holdings and hasattr(kite_api, 'kite') and getattr(kite_api.kite, 'holdings', None):
            try:
                raw_holdings = kite_api.kite.holdings() or []
                holdings = raw_holdings
            except Exception as e:
                logging.warning(f"Could not fetch raw holdings: {e}")

        # Filter holdings case-insensitively
        company_holdings = [h for h in (holdings or []) if h.get('tradingsymbol', '').upper() == symbol_upper]
        logging.info(f"holdings = {company_holdings}")
        for holding in company_holdings:
            qty = int(holding.get('quantity', 0) or holding.get('t1_quantity', 0) or 0)
            avg_price = float(holding.get('average_price', 0) or 0)
            if qty > 0:
                total_quantity += qty
                # Use available avg_price if present; otherwise skip adding value (positions may supply price)
                if avg_price > 0:
                    total_value += qty * avg_price

        logging.info(f"init total qunatity = {total_quantity}")
        # Also include positions (day and net) to capture trades executed today
        if hasattr(kite_api, 'kite') and kite_api.kite:
            try:
                positions = kite_api.kite.positions() or {}
                logging.info(f"positions = {positions}")
                for position in positions.get('net', []) or []:
                    print(f"\n pppposition = {position}\n")
                    if position.get('tradingsymbol', '').upper() == symbol_upper:
                        logging.info(f"total quantity in positions = {position.get('buy_quantity', 0)}")
                        qty = int(position.get('buy_quantity', 0) or 0)
                        avg = float(position.get('buy_price', 0) or 0)
                        if qty > 0:
                            total_quantity += qty
                            if avg > 0:
                                total_value += qty * avg
                logging.info(f"After positions total qunatity = {total_quantity}")
            except Exception as e:
                logging.warning(f"Could not fetch positions: {e}")

        # If still zero, log details to help debugging
        if total_quantity == 0:
            logging.debug(f"Holdings list: {holdings}")
            # Try to show positions raw for debugging
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
                       sell_price: float, target_profit_pct: float, profit_analysis: dict) -> None:
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
    
    def __init__(self, company_symbol: str, net_profit_percentage: float, quantity: Optional[int] = None):
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
        
        self.logger = setup_logger(__name__, self.company_symbol)
        
        # Initialize Kite Connect API
        self.kite_api = KiteConnectAPI(self.company_symbol)
        
        self.logger.info(f"Initializing GTT Sell Order Scheduler for {self.company_symbol}")
        self.logger.info(f"Target net profit: {net_profit_percentage}%")
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
        sell_price = calculate_optimal_sell_price(avg_price, sell_quantity, self.net_profit_percentage)
        sell_price = round(sell_price, 1)
        
        # Calculate trigger price (0.1% above sell price for GTT)
        trigger_price = round(sell_price * 1.001, 1)
        
        # Calculate profit analysis
        profit_analysis = calculate_profit_with_charges(avg_price, sell_price, sell_quantity)
        
        return sell_quantity, avg_price, sell_price, trigger_price, profit_analysis
    
    def place_gtt_sell_order(self, quantity: int, sell_price: float, trigger_price: float) -> str:
        """
        Place GTT sell order
        
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
            
            # Place GTT sell order
            trigger_id = self.kite_api.place_gtt_order(
                trading_symbol=self.company_symbol,
                exchange="NSE",
                transaction_type="SELL",
                quantity=quantity,
                price=sell_price,
                trigger_price=trigger_price,
                order_type="LIMIT",
                validity="DAY",
                current_price=current_price
            )
            
            self.logger.info(f"GTT sell order placed successfully. Trigger ID: {trigger_id}")
            return trigger_id
            
        except Exception as e:
            self.logger.error(f"Failed to place GTT sell order: {e}")
            raise
    
    def run(self, auto_confirm: bool = False) -> None:
        """Execute the complete GTT sell order scheduling process"""
        try:
            self.logger.info("Starting GTT sell order scheduling process")
            
            # Connect to Kite
            self.connect_to_kite()
            
            # Get holdings and calculate prices
            quantity, avg_price, sell_price, trigger_price, profit_analysis = self.get_holdings_and_calculate_price()
            # Print summary
            print_order_summary(self.company_symbol, quantity, avg_price, sell_price, 
                              self.net_profit_percentage, profit_analysis)
            
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
            quantity=args.quantity
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


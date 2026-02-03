#!/usr/bin/env python3
"""
Sell Price Suggestion Script

This script analyzes your completed buy orders (including today's and past purchases),
calculates the weighted average cost including all charges, and suggests optimal
sell price and trigger price for GTT sell orders.

It considers:
- All completed buy orders for the stock
- Actual brokerage and trading charges
- Target profit percentage
- Break-even analysis

Usage:
    python suggest_sell_price.py <company_symbol> [options]

Examples:
    python suggest_sell_price.py ITC
    # Analyzes ITC purchases and suggests sell prices for 2% profit
    
    python suggest_sell_price.py RELIANCE --profit 3.5
    # Suggests prices for 3.5% net profit
    
    python suggest_sell_price.py TCS --profit 2.0 --charge-mode intraday
    # Uses intraday charges (if planning same-day sell)
    
    python suggest_sell_price.py BAJFINANCE --quantity 10
    # Suggests prices for selling only 10 shares
"""

import argparse
import sys
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from kite_connect_api import KiteConnectAPI
from kite_utils import setup_logger, load_config


def calculate_zerodha_buy_charges(buy_value: float, quantity: int, charge_mode: str = "delivery") -> dict:
    """
    Calculate Zerodha charges for equity buy orders
    
    Parameters:
    - buy_value: Total buy value (price * quantity)
    - quantity: Number of shares being bought
    - charge_mode: "delivery" or "intraday"
    
    Returns:
    Dictionary containing all charges and total charges
    """
    mode = (charge_mode or "delivery").lower()
    
    # Common charges (buy-side)
    exchange_charges = buy_value * 0.0000345  # NSE Equity: 0.00345%
    sebi_fees = buy_value * 0.000001  # 0.0001%
    
    if mode == "intraday":
        # Intraday buy-side charges
        brokerage = min(buy_value * 0.0003, 20.0)  # 0.03% or ₹20, whichever is lower
        stt = buy_value * 0.00025  # 0.025% on buy side
        dp_charges = 0.0  # No DP charges on buy
        gst_base = brokerage + exchange_charges + sebi_fees
        gst = gst_base * 0.18
    else:
        # Delivery buy-side charges
        brokerage = 0.00  # Zero brokerage
        stt = buy_value * 0.001  # 0.1% on buy side
        dp_charges = 0.0  # No DP charges on buy
        gst_base = exchange_charges + sebi_fees
        gst = gst_base * 0.18
    
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


def calculate_zerodha_sell_charges(sell_value: float, quantity: int, charge_mode: str = "delivery") -> dict:
    """
    Calculate Zerodha charges for equity sell orders
    
    Parameters:
    - sell_value: Total sell value (price * quantity)
    - quantity: Number of shares being sold
    - charge_mode: "delivery" or "intraday"
    
    Returns:
    Dictionary containing all charges and total charges
    """
    mode = (charge_mode or "delivery").lower()
    
    # Common charges (sell-side)
    exchange_charges = sell_value * 0.0000345  # NSE Equity: 0.00345%
    sebi_fees = sell_value * 0.000001  # 0.0001%
    
    if mode == "intraday":
        # Intraday sell-side charges
        brokerage = min(sell_value * 0.0003, 20.0)
        stt = sell_value * 0.00025  # 0.025% on sell side
        dp_charges = 0.0  # No DP charges for intraday
        gst_base = brokerage + exchange_charges + sebi_fees
        gst = gst_base * 0.18
    else:
        # Delivery sell-side charges
        brokerage = 0.00
        stt = sell_value * 0.001  # 0.1% on sell side
        dp_charges = 15.93  # ₹13.5 + 18% GST
        gst_base = exchange_charges + sebi_fees
        gst = gst_base * 0.18
    
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


class SellPriceSuggester:
    """Class to analyze purchases and suggest sell prices"""
    
    def __init__(self, company_symbol: str, target_profit_pct: float = 2.0, 
                 charge_mode: str = "delivery", quantity_to_sell: Optional[int] = None):
        """
        Initialize the Sell Price Suggester
        
        Parameters:
        - company_symbol: Trading symbol of the company (e.g., "ITC", "RELIANCE")
        - target_profit_pct: Target net profit percentage (default: 2.0%)
        - charge_mode: "delivery" or "intraday" (default: "delivery")
        - quantity_to_sell: Specific quantity to sell (None = all holdings)
        """
        self.company_symbol = company_symbol.upper()
        self.target_profit_pct = target_profit_pct
        self.charge_mode = charge_mode.lower()
        self.quantity_to_sell = quantity_to_sell
        
        # Setup logging
        self.logger = setup_logger(__name__, f"SELL_SUGGEST_{self.company_symbol}")
        self.logger.info(f"Initializing Sell Price Suggester for {self.company_symbol}")
        self.logger.info(f"Target profit: {target_profit_pct}%, Charge mode: {charge_mode}")
        
        # Test config loading first
        try:
            load_config()
            self.logger.info("Configuration loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
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
    
    def get_completed_buy_orders(self) -> List[Dict[str, Any]]:
        """
        Get all completed buy orders for the company
        
        Returns:
        List of completed buy order details
        """
        try:
            # Get all orders
            all_orders = self.kite_api.kite.orders()
            self.logger.info(f"Retrieved {len(all_orders)} total orders")
            
            # Filter for completed buy orders of this company
            completed_buys = [
                order for order in all_orders
                if order.get('tradingsymbol', '').upper() == self.company_symbol and
                   order.get('status', '').upper() == 'COMPLETE' and
                   order.get('transaction_type', '').upper() == 'BUY'
            ]
            
            self.logger.info(f"Found {len(completed_buys)} completed buy orders for {self.company_symbol}")
            return completed_buys
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve buy orders: {e}")
            return []
    
    def analyze_purchases(self, buy_orders: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze all buy orders and calculate weighted average cost with charges
        
        Parameters:
        - buy_orders: List of completed buy orders
        
        Returns:
        Dictionary with analysis results
        """
        if not buy_orders:
            return None
        
        total_quantity = 0
        total_cost = 0.0
        total_buy_charges = 0.0
        today = datetime.now().date()
        
        orders_today = []
        orders_past = []
        
        for order in buy_orders:
            filled_qty = order.get('filled_quantity', 0)
            avg_price = order.get('average_price', 0) or 0
            order_value = filled_qty * avg_price
            
            # Calculate buy charges
            buy_charges = calculate_zerodha_buy_charges(
                order_value, filled_qty, self.charge_mode
            )
            
            total_quantity += filled_qty
            total_cost += order_value
            total_buy_charges += buy_charges['total_charges']
            
            # Categorize by date
            order_time = order.get('order_timestamp')
            if order_time:
                try:
                    if isinstance(order_time, datetime):
                        order_date = order_time.date()
                    else:
                        order_date = datetime.fromisoformat(str(order_time)).date()
                    
                    if order_date == today:
                        orders_today.append(order)
                    else:
                        orders_past.append(order)
                except:
                    orders_past.append(order)
            else:
                orders_past.append(order)
        
        # Calculate weighted average buy price (without charges)
        weighted_avg_buy_price = total_cost / total_quantity if total_quantity > 0 else 0
        
        # Calculate effective cost per share (including buy charges)
        effective_cost_per_share = (total_cost + total_buy_charges) / total_quantity if total_quantity > 0 else 0
        
        return {
            'total_quantity': total_quantity,
            'weighted_avg_buy_price': weighted_avg_buy_price,
            'total_cost': total_cost,
            'total_buy_charges': total_buy_charges,
            'effective_cost_per_share': effective_cost_per_share,
            'buy_charges_per_share': total_buy_charges / total_quantity if total_quantity > 0 else 0,
            'orders_today': orders_today,
            'orders_past': orders_past,
            'total_orders': len(buy_orders)
        }
    
    def calculate_sell_price_suggestion(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate suggested sell price and trigger price
        
        Parameters:
        - analysis: Purchase analysis from analyze_purchases()
        
        Returns:
        Dictionary with sell price suggestions
        """
        quantity = self.quantity_to_sell or analysis['total_quantity']
        effective_cost = analysis['effective_cost_per_share']
        
        # Binary search to find sell price that achieves target profit
        # considering sell charges
        def calculate_net_profit_pct(sell_price: float) -> float:
            sell_value = sell_price * quantity
            sell_charges = calculate_zerodha_sell_charges(sell_value, quantity, self.charge_mode)
            
            total_buy_cost = effective_cost * quantity
            net_sale_value = sell_value - sell_charges['total_charges']
            net_profit = net_sale_value - total_buy_cost
            profit_pct = (net_profit / total_buy_cost) * 100
            
            return profit_pct
        
        # Find sell price using binary search
        low, high = effective_cost, effective_cost * 2
        target_sell_price = effective_cost
        
        for _ in range(100):  # Max iterations
            mid = (low + high) / 2
            profit_pct = calculate_net_profit_pct(mid)
            
            if abs(profit_pct - self.target_profit_pct) < 0.01:  # Within 0.01%
                target_sell_price = mid
                break
            elif profit_pct < self.target_profit_pct:
                low = mid
            else:
                high = mid
        
        # Calculate final numbers with target sell price
        sell_value = target_sell_price * quantity
        sell_charges = calculate_zerodha_sell_charges(sell_value, quantity, self.charge_mode)
        
        total_buy_cost = effective_cost * quantity
        net_sale_value = sell_value - sell_charges['total_charges']
        net_profit = net_sale_value - total_buy_cost
        actual_profit_pct = (net_profit / total_buy_cost) * 100
        
        # Calculate break-even price (where profit = 0)
        def calculate_breakeven():
            low_be, high_be = effective_cost * 0.9, effective_cost * 1.5
            for _ in range(100):
                mid = (low_be + high_be) / 2
                profit = calculate_net_profit_pct(mid)
                if abs(profit) < 0.001:
                    return mid
                elif profit < 0:
                    low_be = mid
                else:
                    high_be = mid
            return mid
        
        breakeven_price = calculate_breakeven()
        
        # Calculate trigger price (slightly below sell price)
        # Typically 0.3-0.5% below sell price for better execution
        trigger_offset_pct = 0.4  # 0.4% below sell price
        trigger_price = target_sell_price * (1 - trigger_offset_pct / 100)
        
        return {
            'quantity_to_sell': quantity,
            'effective_cost_per_share': effective_cost,
            'suggested_sell_price': round(target_sell_price, 2),
            'suggested_trigger_price': round(trigger_price, 2),
            'breakeven_price': round(breakeven_price, 2),
            'sell_charges': sell_charges,
            'total_buy_cost': total_buy_cost,
            'expected_sale_value': sell_value,
            'expected_net_value': net_sale_value,
            'expected_net_profit': net_profit,
            'expected_profit_pct': actual_profit_pct,
            'profit_per_share': net_profit / quantity if quantity > 0 else 0
        }
    
    def print_analysis(self, analysis: Dict[str, Any], suggestion: Dict[str, Any]) -> None:
        """
        Print detailed analysis and suggestions
        
        Parameters:
        - analysis: Purchase analysis
        - suggestion: Sell price suggestions
        """
        print("\n" + "="*100)
        print(f"SELL PRICE ANALYSIS FOR {self.company_symbol}")
        print("="*100)
        
        print("\n📊 PURCHASE ANALYSIS:")
        print("-"*100)
        print(f"Total Shares Purchased: {analysis['total_quantity']:,}")
        print(f"Weighted Average Buy Price: Rs.{analysis['weighted_avg_buy_price']:.2f}")
        print(f"Total Purchase Cost: Rs.{analysis['total_cost']:,.2f}")
        print(f"Total Buy Charges: Rs.{analysis['total_buy_charges']:.2f}")
        print(f"Effective Cost per Share (with charges): Rs.{analysis['effective_cost_per_share']:.2f}")
        
        if analysis['orders_today']:
            print(f"\n  • Orders Today: {len(analysis['orders_today'])} orders")
            today_qty = sum(o.get('filled_quantity', 0) for o in analysis['orders_today'])
            print(f"    Quantity: {today_qty:,} shares")
        
        if analysis['orders_past']:
            print(f"  • Past Orders: {len(analysis['orders_past'])} orders")
            past_qty = sum(o.get('filled_quantity', 0) for o in analysis['orders_past'])
            print(f"    Quantity: {past_qty:,} shares")
        
        print("\n💡 SELL PRICE SUGGESTIONS:")
        print("-"*100)
        print(f"Charge Mode: {self.charge_mode.upper()}")
        print(f"Target Profit: {self.target_profit_pct}% (net after all charges)")
        print(f"Quantity to Sell: {suggestion['quantity_to_sell']:,} shares")
        print()
        print(f"✅ SUGGESTED SELL PRICE:    Rs.{suggestion['suggested_sell_price']:.2f}")
        print(f"✅ SUGGESTED TRIGGER PRICE: Rs.{suggestion['suggested_trigger_price']:.2f}")
        print(f"   (Trigger set 0.4% below sell price for better execution)")
        print()
        print(f"Break-even Price: Rs.{suggestion['breakeven_price']:.2f}")
        print(f"   (Sell above this to avoid loss)")
        
        print("\n📈 EXPECTED OUTCOME AT SUGGESTED PRICE:")
        print("-"*100)
        print(f"Total Buy Cost: Rs.{suggestion['total_buy_cost']:,.2f}")
        print(f"Expected Sale Value: Rs.{suggestion['expected_sale_value']:,.2f}")
        print(f"Sell Charges: Rs.{suggestion['sell_charges']['total_charges']:.2f}")
        print(f"  • Brokerage: Rs.{suggestion['sell_charges']['brokerage']:.2f}")
        print(f"  • STT: Rs.{suggestion['sell_charges']['stt']:.2f}")
        print(f"  • Exchange: Rs.{suggestion['sell_charges']['exchange_charges']:.2f}")
        print(f"  • SEBI: Rs.{suggestion['sell_charges']['sebi_fees']:.2f}")
        print(f"  • DP Charges: Rs.{suggestion['sell_charges']['dp_charges']:.2f}")
        print(f"  • GST: Rs.{suggestion['sell_charges']['gst']:.2f}")
        print(f"Net Sale Value: Rs.{suggestion['expected_net_value']:,.2f}")
        print()
        print(f"💰 NET PROFIT: Rs.{suggestion['expected_net_profit']:,.2f}")
        print(f"💰 PROFIT PER SHARE: Rs.{suggestion['profit_per_share']:.2f}")
        print(f"💰 PROFIT PERCENTAGE: {suggestion['expected_profit_pct']:.2f}%")
        
        print("\n📋 COMMAND TO SCHEDULE GTT SELL ORDER:")
        print("-"*100)
        print(f"python code/schedule_gtt_sell_order.py {self.company_symbol} "
              f"{self.target_profit_pct} --quantity {suggestion['quantity_to_sell']} "
              f"--charge-mode {self.charge_mode}")
        
        print("\n" + "="*100)
    
    def run(self) -> None:
        """Execute the sell price suggestion process"""
        try:
            self.logger.info("Starting sell price analysis")
            
            # Connect to Kite
            self.connect_to_kite()
            
            # Get completed buy orders
            self.logger.info("Fetching completed buy orders...")
            buy_orders = self.get_completed_buy_orders()
            
            if not buy_orders:
                print(f"\n❌ No completed buy orders found for {self.company_symbol}")
                print("Cannot suggest sell prices without purchase history.")
                return
            
            # Analyze purchases
            self.logger.info("Analyzing purchases...")
            analysis = self.analyze_purchases(buy_orders)
            
            if not analysis:
                print(f"\n❌ Failed to analyze purchases for {self.company_symbol}")
                return
            
            # Validate quantity to sell
            if self.quantity_to_sell and self.quantity_to_sell > analysis['total_quantity']:
                print(f"\n❌ Cannot sell {self.quantity_to_sell} shares")
                print(f"You only have {analysis['total_quantity']} shares")
                return
            
            # Calculate sell price suggestions
            self.logger.info("Calculating sell price suggestions...")
            suggestion = self.calculate_sell_price_suggestion(analysis)
            
            # Display results
            self.print_analysis(analysis, suggestion)
            
            self.logger.info("Sell price analysis completed successfully")
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Sell price analysis failed: {error_msg}")
            self.logger.error(f"Error type: {type(e).__name__}")
            raise


def main():
    """Main function to parse arguments and run the suggester"""
    parser = argparse.ArgumentParser(
        description="Analyze purchases and suggest optimal sell prices with GTT trigger",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        'company_symbol',
        help='Trading symbol of the company (e.g., ITC, RELIANCE, TCS)'
    )
    
    parser.add_argument(
        '--profit',
        type=float,
        default=2.0,
        help='Target net profit percentage (default: 2.0%%)'
    )
    
    parser.add_argument(
        '--charge-mode',
        choices=['delivery', 'intraday'],
        default='delivery',
        help='Charge calculation mode: delivery (default) or intraday'
    )
    
    parser.add_argument(
        '--quantity',
        type=int,
        default=None,
        help='Specific quantity to sell (default: all holdings)'
    )
    
    args = parser.parse_args()
    
    try:
        # Create and run suggester
        suggester = SellPriceSuggester(
            company_symbol=args.company_symbol,
            target_profit_pct=args.profit,
            charge_mode=args.charge_mode,
            quantity_to_sell=args.quantity
        )
        
        suggester.run()
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

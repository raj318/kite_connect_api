#!/usr/bin/env python3

def calculate_zerodha_charges(sell_value: float, quantity: int) -> dict:
    """
    Calculate all Zerodha charges for equity delivery sell orders
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

def calculate_optimal_sell_price(buy_price: float, quantity: int, target_net_profit_percentage: float = 2.0) -> float:
    """
    Calculate the optimal sell price to achieve target net profit percentage after charges
    """
    # Start with a reasonable guess
    sell_price = buy_price * (1 + target_net_profit_percentage / 100)
    
    # Iteratively find the optimal price
    max_iterations = 10
    tolerance = 0.01  # 1 paisa tolerance
    
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
    
    return sell_price

def test_charge_calculations():
    """
    Test function to demonstrate charge calculations and optimal sell price
    """
    print("=== Zerodha Charge Calculation Test ===")
    
    # Test parameters
    buy_price = 100.0  # Buy price per share
    quantity = 5       # Number of shares
    target_net_profit = 2.0  # Target 2% net profit
    
    print(f"Test Scenario:")
    print(f"  Buy price: ₹{buy_price:.2f}")
    print(f"  Quantity: {quantity} shares")
    print(f"  Target net profit: {target_net_profit}%")
    print()
    
    # Calculate optimal sell price
    optimal_sell_price = calculate_optimal_sell_price(buy_price, quantity, target_net_profit)
    
    # Calculate profit analysis
    profit_analysis = calculate_profit_with_charges(buy_price, optimal_sell_price, quantity)
    
    print("Results:")
    print(f"  Optimal sell price: ₹{optimal_sell_price:.2f}")
    print(f"  Gross profit: ₹{profit_analysis['gross_profit']:.2f} ({profit_analysis['gross_profit_percentage']:.2f}%)")
    print(f"  Total charges: ₹{profit_analysis['total_charges']:.2f} ({profit_analysis['charges_percentage']:.2f}%)")
    print(f"  Net profit: ₹{profit_analysis['net_profit']:.2f} ({profit_analysis['net_profit_percentage']:.2f}%)")
    print(f"  Break-even price: ₹{profit_analysis['break_even_price']:.2f}")
    print()
    
    # Show charge breakdown
    charges = profit_analysis['charges']
    print("Charge Breakdown:")
    print(f"  Brokerage: ₹{charges['brokerage']:.2f}")
    print(f"  STT: ₹{charges['stt']:.2f}")
    print(f"  Exchange Charges: ₹{charges['exchange_charges']:.2f}")
    print(f"  SEBI Fees: ₹{charges['sebi_fees']:.2f}")
    print(f"  DP Charges: ₹{charges['dp_charges']:.2f}")
    print(f"  GST: ₹{charges['gst']:.2f}")
    print(f"  Total: ₹{charges['total_charges']:.2f}")
    print(f"  Per share: ₹{charges['charges_per_share']:.2f}")
    
    print("\n=== Real-world Example (NTPC at ₹300) ===")
    buy_price_npc = 300.0
    quantity_npc = 5
    target_net_profit_npc = 2.0
    
    optimal_sell_price_npc = calculate_optimal_sell_price(buy_price_npc, quantity_npc, target_net_profit_npc)
    profit_analysis_npc = calculate_profit_with_charges(buy_price_npc, optimal_sell_price_npc, quantity_npc)
    
    print(f"NTPC Example:")
    print(f"  Buy price: ₹{buy_price_npc:.2f}")
    print(f"  Quantity: {quantity_npc} shares")
    print(f"  Optimal sell price: ₹{optimal_sell_price_npc:.2f}")
    print(f"  Gross profit: ₹{profit_analysis_npc['gross_profit']:.2f} ({profit_analysis_npc['gross_profit_percentage']:.2f}%)")
    print(f"  Total charges: ₹{profit_analysis_npc['total_charges']:.2f} ({profit_analysis_npc['charges_percentage']:.2f}%)")
    print(f"  Net profit: ₹{profit_analysis_npc['net_profit']:.2f} ({profit_analysis_npc['net_profit_percentage']:.2f}%)")
    print(f"  Break-even price: ₹{profit_analysis_npc['break_even_price']:.2f}")

if __name__ == "__main__":
    test_charge_calculations() 
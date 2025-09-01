# GTT Order Management Suite

A comprehensive Python toolkit for managing GTT (Good Till Triggered) orders on Zerodha Kite. Includes automated order scheduling with configurable strategies and bulk order deletion capabilities.

## Scripts Included

### 1. `schedule_gtt_orders.py` - GTT Order Scheduler
Automatically schedules multiple buy orders with decreasing prices and progressive quantity increase for cost-averaging strategies.

### 2. `delete_gtt_orders.py` - GTT Order Deleter  
Safely deletes all active GTT orders for a specified company with user confirmation and detailed logging.

## Features

### GTT Order Scheduler (`schedule_gtt_orders.py`)
- **Automated Order Scheduling**: Places multiple GTT orders automatically
- **Configurable Price Strategy**: Customizable price decrease percentage (default: 0.3%)
- **Flexible Quantity Strategy**: Configurable starting quantity with progressive increase
- **Market-Aware Behavior**: Adapts strategy based on market open/closed status
- **Configuration-Driven**: Key parameters configurable via `config.yaml`
- **Order Management**: Tracks all placed orders with trigger IDs and status
- **Comprehensive Logging**: Detailed logging for monitoring and debugging
- **Clean Order Summary**: Filtered summaries excluding skipped orders

### GTT Order Deleter (`delete_gtt_orders.py`)
- **Safe Bulk Deletion**: Deletes all active GTT orders for a specific company
- **User Confirmation**: Requires explicit confirmation before deletion
- **Status Filtering**: Only operates on truly active orders (ACTIVE, PENDING, OPEN)
- **Detailed Reporting**: Shows success/failure summary with order details
- **Error Handling**: Graceful handling of missing or malformed order data
- **Audit Trail**: Complete logging of all deletion operations

## How It Works

### GTT Order Scheduler

#### Market Open Strategy
1. **First Order**: Placed as MARKET order (executes immediately)
2. **Subsequent Orders**: Placed as GTT orders with decreasing prices

#### Market Closed Strategy  
1. **First Order**: SKIPPED (AMO not supported)
2. **GTT Orders**: Start from 0.25% below current price

#### Price Calculation
- **Configurable Price Decrease**: Default 0.3% between orders (configurable in config.yaml)
- **Example with 0.3% decrease**:
  - Order 1: Base price
  - Order 2: Base price × 0.997 (0.3% lower)
  - Order 3: Base price × 0.994 (0.6% lower)
  - And so on...

#### Quantity Strategy
- **Configurable Starting Quantity**: Default starts from 1 share (configurable)
- **Progressive Increase**: Each order increases by 1 share
- **Example with start_quantity=1**: 1, 2, 3, 4, 5... shares
- **Example with start_quantity=10**: 10, 11, 12, 13, 14... shares
- **Capped by max_quantity**: Orders won't exceed specified maximum

#### Trigger Price Logic
- **GTT Trigger**: Set 0.1% **below** order price for better execution
- **Example**: Order price ₹100.00 → Trigger price ₹99.90
- **Purpose**: Ensures GTT triggers when market reaches desired level

### GTT Order Deleter

1. **Order Discovery**: Retrieves all GTT orders from Kite API
2. **Status Filtering**: Identifies only active orders (ACTIVE, PENDING, OPEN)
3. **Company Filtering**: Filters orders for specified company symbol
4. **User Confirmation**: Shows order count and asks for explicit confirmation
5. **Bulk Deletion**: Deletes all matching orders with detailed logging
6. **Summary Report**: Provides success/failure summary with order details

## Usage

### GTT Order Scheduler (`schedule_gtt_orders.py`)

#### Command Line Interface

```bash
python schedule_gtt_orders.py <company_symbol> [order_count] <current_price> [max_quantity] [--startq N]
```

#### Parameters:
- `company_symbol`: Trading symbol of the company (e.g., ITC, RELIANCE, TCS)
- `order_count`: Number of GTT orders to place (optional, uses config default: 10)
- `current_price`: Current price of the stock (base price for calculations)
- `max_quantity`: Maximum shares per order (optional, default: 100)
- `--startq N`: Starting quantity for first order (optional, uses config default: 1)

#### Sample Commands:

```bash
# Basic usage (using config defaults: 10 orders, start with 1 share)
python schedule_gtt_orders.py ITC 450.50
# Orders: 1,2,3,4,5,6,7,8,9,10 shares

# Custom order count
python schedule_gtt_orders.py ITC 5 450.50 100
# Places 5 orders: 1,2,3,4,5 shares

# Custom max quantity
python schedule_gtt_orders.py RELIANCE 2500.0 50
# Uses 10 orders with max 50 shares: 1,2,3,4,5,6,7,8,9,10 shares (capped at 50)

# Custom starting quantity
python schedule_gtt_orders.py TCS 3500.0 --startq 10
# Uses 10 orders starting from 10: 10,11,12,13,14,15,16,17,18,19 shares

# Advanced custom configuration
python schedule_gtt_orders.py ITC 5 450.50 100 --startq 5
# Places 5 orders starting from 5: 5,6,7,8,9 shares

# Large volume trading
python schedule_gtt_orders.py HDFC 1500.0 200 --startq 20
# Uses 10 orders starting from 20: 20,21,22,23,24,25,26,27,28,29 shares

# Small volume testing
python schedule_gtt_orders.py WIPRO 3 250.0 10 --startq 1
# Places 3 orders: 1,2,3 shares
```

### GTT Order Deleter (`delete_gtt_orders.py`)

#### Command Line Interface

```bash
python delete_gtt_orders.py <company_symbol>
```

#### Parameters:
- `company_symbol`: Trading symbol of the company whose GTT orders should be deleted

#### Examples:

```bash
# Delete all active GTT orders for ITC
python delete_gtt_orders.py ITC

# Delete all active GTT orders for RELIANCE  
python delete_gtt_orders.py RELIANCE

# Delete all active GTT orders for TCS
python delete_gtt_orders.py TCS
```

#### Safety Features:
- Shows number of active orders found
- Displays warning about permanent deletion
- Requires explicit user confirmation ("yes" or "y")
- Can be cancelled by typing "no" or any other response
- Detailed summary of successful and failed deletions

### Programmatic Usage

#### GTT Order Scheduler
```python
from schedule_gtt_orders import HybridOrderScheduler

# Create scheduler with defaults from config
scheduler = HybridOrderScheduler(
    company_symbol="ITC",
    order_count=None,  # Uses config default (10)
    current_price=450.0,
    max_quantity=100,
    start_quantity=None  # Uses config default (1)
)

# Create scheduler with custom parameters
scheduler = HybridOrderScheduler(
    company_symbol="ITC",
    order_count=5,
    current_price=450.0,
    max_quantity=100,
    start_quantity=10  # Start from 10 shares
)

# Run the scheduler
scheduler.run()
```

#### GTT Order Deleter
```python
from delete_gtt_orders import GTTOrderDeleter

# Create deleter
deleter = GTTOrderDeleter(company_symbol="ITC")

# Run the deletion process (with user confirmation)
deleter.run()
```

## Example Scenarios

### Scenario 1: Default Configuration Strategy (Market Open)
- **Company**: ITC
- **Orders**: 10 (from config)
- **Start Quantity**: 1 share (from config)
- **Price Decrease**: 0.3% (from config)
- **Base Price**: ₹450 (current market price)
- **Result (Market Open)**:
  - Order 1: 1 share @ ₹450.00 (MARKET order - executes immediately)
  - Order 2: 2 shares @ ₹448.65 (0.3% lower, GTT trigger: ₹448.20)
  - Order 3: 3 shares @ ₹447.31 (0.6% lower, GTT trigger: ₹446.86)
  - Order 4: 4 shares @ ₹445.97 (0.9% lower, GTT trigger: ₹445.52)
  - ...continuing to Order 10

### Scenario 2: Custom Starting Quantity Strategy
- **Company**: TCS
- **Orders**: 5
- **Start Quantity**: 10 shares (custom)
- **Price Decrease**: 0.3% (from config)
- **Base Price**: ₹4000
- **Result (Market Closed)**:
  - Order 1: SKIPPED (Market closed)
  - Order 2: 10 shares @ ₹3990.00 (0.25% lower, GTT trigger: ₹3986.01)
  - Order 3: 11 shares @ ₹3978.00 (0.55% lower, GTT trigger: ₹3974.02)
  - Order 4: 12 shares @ ₹3966.00 (0.85% lower, GTT trigger: ₹3962.03)
  - Order 5: 13 shares @ ₹3954.00 (1.15% lower, GTT trigger: ₹3950.04)

### Scenario 3: Large Volume Trading Strategy
- **Company**: HDFC
- **Orders**: 10 (from config)
- **Start Quantity**: 20 shares (custom)
- **Max Quantity**: 200 shares
- **Price Decrease**: 0.3% (from config)
- **Base Price**: ₹1500
- **Result**: 10 orders with quantities 20,21,22,...,29 shares and decreasing prices

### Scenario 4: GTT Order Cleanup
- **Company**: ITC
- **Action**: Delete all active GTT orders
- **Process**:
  1. Script finds 15 active GTT orders for ITC
  2. Shows warning: "⚠️ WARNING: This will permanently delete all GTT orders for this company!"
  3. User confirms with "yes"
  4. Successfully deletes 13 orders, 2 fail (already triggered)
  5. Displays detailed summary of deletions

## Output and Logging

### Console Output

#### GTT Order Scheduler
The script provides detailed console output showing:
- Configuration loaded (order count, start quantity, price difference)
- Market status detection (open/closed)
- Order calculations with prices and quantities
- Connection status and order placement progress
- **Clean summary table** (skipped orders filtered out)
- **Renumbered order display** (starts from 1 for clarity)
- Success/failure statistics

#### GTT Order Deleter
The script provides comprehensive deletion feedback:
- Number of total GTT orders found
- Number of active orders for the specified company
- Detailed warning before deletion
- Real-time deletion progress
- Complete success/failure summary with order details

### Log Files
- **Location**: `workdir/logs/` directory
- **Filename Format**: `{COMPANY_SYMBOL}_{DATE}.log` or `GTT_DELETE_{COMPANY_SYMBOL}_{DATE}.log`
- **Content**: Detailed information about all operations, API calls, and errors
- **Purpose**: Debugging, audit trail, and troubleshooting

### Order Summary Files

#### GTT Order Scheduler
- **Location**: `workdir/orders/` directory
- **Filename Format**: `{COMPANY_SYMBOL}_gtt_orders_{TIMESTAMP}.json`
- **Content**: Complete order details with filtered results (skipped orders removed)
- **Features**: 
  - Renumbered orders starting from 1
  - Original order numbers preserved for reference
  - Strategy and configuration metadata
  - Market status and execution details

#### GTT Order Deleter
- **Location**: `workdir/orders/` directory  
- **Filename Format**: `{COMPANY_SYMBOL}_gtt_deletion_{TIMESTAMP}.json`
- **Content**: Complete deletion summary with success/failure details
- **Features**:
  - List of successfully deleted orders
  - List of failed deletions with error reasons
  - Timestamps and operation metadata

## Configuration

### Prerequisites
1. **Kite Connect API**: Valid API credentials in `config/config.yaml`
2. **Python Dependencies**: All required packages from `requirements.txt`
3. **Market Hours**: Script should be run during market hours for accurate pricing

### Configuration File
The `config/config.yaml` file contains both API credentials and trading strategy parameters:

```yaml
# Kite Connect API Credentials
kite_connect:
  api_key: your_api_key
  api_secret: your_api_secret
  access_token: your_access_token
  redirect_url: your_redirect_url
  request_token: your_request_token

# Breeze API Credentials (optional)
breeze_api:
  api_token: your_api_token
  secret_token: your_secret_token
  session_id: your_session_id

# Trading Strategy Configuration
stratergy:
  buy: 0.3
  linear_from: 1
  sell: 0.5
  start_buy: 1
  price_difference_percent: 0.3  # Percentage decrease between orders (default: 0.3%)
  order_count: 10                # Default number of orders to place
  start_quantity: 1              # Default starting quantity for first order
```

#### Configuration Parameters

**API Configuration:**
- `kite_connect.*`: Required Kite Connect API credentials
- `breeze_api.*`: Optional Breeze API credentials

**Strategy Configuration:**
- `price_difference_percent`: Percentage price decrease between orders (default: 0.3%)
- `order_count`: Default number of GTT orders to place (default: 10)
- `start_quantity`: Default starting quantity for the first order (default: 1)

## Safety Features

### GTT Order Scheduler
1. **User Confirmation**: Shows order summary and asks for confirmation before placing orders
2. **Market-Aware Behavior**: Automatically adjusts strategy based on market open/closed status
3. **Error Handling**: Continues processing other orders even if some fail
4. **Input Validation**: Validates all parameters before processing
5. **Clean Summaries**: Filters out skipped orders from final reports
6. **Order Renumbering**: Renumbers active orders starting from 1 for clarity
7. **Comprehensive Logging**: Detailed logging for monitoring and debugging
8. **Configuration Fallbacks**: Uses sensible defaults if config loading fails

### GTT Order Deleter
1. **Status Filtering**: Only targets truly active orders (ACTIVE, PENDING, OPEN)
2. **User Confirmation**: Requires explicit "yes" confirmation before deletion
3. **Safe Cancellation**: Can be cancelled by typing anything other than "yes"
4. **Detailed Preview**: Shows exact number of orders that will be deleted
5. **Error Resilience**: Handles missing or malformed order data gracefully
6. **Comprehensive Reporting**: Detailed success/failure summary with reasons
7. **Audit Trail**: Complete logging of all deletion operations

## Risk Considerations

1. **Market Risk**: GTT orders will execute when triggered, regardless of market conditions
2. **Capital Requirements**: Ensure sufficient funds for all planned orders
3. **Market Timing**: Consider market volatility and timing when setting base prices
4. **Order Management**: Monitor placed orders and cancel if market conditions change

## Troubleshooting

### Common Issues

#### GTT Order Scheduler
1. **Connection Failed**: Check API credentials in `config/config.yaml` and internet connection
2. **Invalid Symbol**: Ensure company symbol is correct and traded on NSE
3. **Insufficient Funds**: Verify account balance before placing orders
4. **"Trigger already met" Error**: 
   - Fixed in current version (trigger set 0.1% below order price)
   - Ensure current price is reasonable for the stock
5. **Config Loading Failed**: Check `config/config.yaml` syntax and file permissions
6. **All Orders Skipped**: Market may be closed, GTT orders will be placed for next trading session

#### GTT Order Deleter
1. **No Active Orders Found**: 
   - Check if orders exist in Kite web interface
   - Verify company symbol spelling
   - Orders might be in TRIGGERED/COMPLETED status (not active)
2. **Permission Denied**: Check API credentials have order management permissions
3. **Deletion Failed**: Some orders might have already been triggered or cancelled
4. **Connection Timeout**: Retry after checking internet connection

### Debug Mode
- **GTT Scheduler**: Check logs in `workdir/logs/{COMPANY_SYMBOL}_{DATE}.log`
- **GTT Deleter**: Check logs in `workdir/logs/GTT_DELETE_{COMPANY_SYMBOL}_{DATE}.log`
- **Verbose Logging**: All API calls and responses are logged for debugging

### Testing Strategy
1. **Start Small**: Test with 1-2 orders first
2. **Use Test Company**: Pick a stable, liquid stock for testing
3. **Check Config**: Verify all configuration parameters are correct
4. **Monitor Orders**: Watch placed orders in Kite web interface
5. **Cleanup Test Orders**: Use delete script to clean up test orders

## Quick Start Guide

### First Time Setup
1. **Install Dependencies**: `pip install -r requirements.txt`
2. **Configure API**: Update `config/config.yaml` with your Kite Connect credentials
3. **Test Connection**: Run a small test order to verify setup
4. **Configure Strategy**: Adjust `config.yaml` strategy parameters as needed

### Typical Workflow
1. **Schedule Orders**: Use `schedule_gtt_orders.py` to place GTT orders
2. **Monitor Progress**: Check Kite web interface for order execution
3. **Adjust Strategy**: Modify orders manually or via config as needed
4. **Clean Up**: Use `delete_gtt_orders.py` to remove unwanted orders

## Support

For issues or questions:
1. **Check Log Files**: Detailed error information in `workdir/logs/` directory
2. **Verify Configuration**: Ensure `config/config.yaml` has valid credentials and parameters
3. **Test Dependencies**: Ensure all packages from `requirements.txt` are installed
4. **Market Conditions**: Verify if issues are related to market hours or volatility
5. **API Limitations**: Check if hitting rate limits or API restrictions

## Version History

### Recent Updates
- **Configurable Parameters**: Order count and start quantity now configurable
- **Enhanced Command Line**: Optional parameters with intelligent defaults
- **Improved Trigger Logic**: Fixed "Trigger already met" error
- **Clean Summaries**: Filtered output excluding skipped orders
- **Order Renumbering**: Logical numbering starting from 1
- **Delete Script**: Added comprehensive GTT order deletion tool
- **Better Error Handling**: Resilient to malformed data and API issues

## Disclaimer

**Important Notice**: This software is for educational and informational purposes only.

### Trading Risks
- **Market Risk**: GTT orders execute automatically when triggered
- **Capital Risk**: Ensure sufficient funds for all planned orders
- **Execution Risk**: Orders may not execute as expected due to market conditions
- **API Risk**: System depends on third-party API availability and reliability

### User Responsibilities
- **Knowledge Required**: Understand GTT orders and trading strategies before use
- **Active Monitoring**: Monitor orders and market conditions regularly
- **Risk Management**: Never invest more than you can afford to lose
- **Compliance**: Ensure usage complies with your broker's terms and local regulations

### No Warranty
This software is provided "as is" without warranty of any kind. Users assume all risks associated with its use.

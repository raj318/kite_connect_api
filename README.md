# KiteConnect Trading System

A Python-based trading system that implements automated trading strategies using the Kite Connect API and ICICI Direct Breeze API.

## Recent Updates

### Token Management Improvements
- Enhanced token renewal process in `kite_utils.py`
- Automated request token collection and access token updates
- Improved error handling for invalid/expired tokens
- Safe configuration file updates that preserve existing settings

### Order Management Enhancements
- Added duplicate order checking in `move_to_placed_orders()`
- Improved order history tracking and management
- Enhanced error handling for order operations
- Added support for preserving first share price orders

### Market Hours Handling
- Updated market hours check to focus on end time (3:30 PM IST)
- Improved cleanup of pending orders at market close
- Added better logging for market hours transitions

### Configuration Management
- Safe updates to `config.yaml` that preserve other sections
- Improved error handling for configuration operations
- Better validation of configuration parameters

## Features

### Trading Strategies
- Fall Buy Strategy implementation
- Support for multiple trading symbols
- Real-time market data processing
- Automated order execution

### Order Management
- Comprehensive order tracking
- Support for pending, placed, and failed orders
- Order history preservation
- Duplicate order prevention

### Market Data
- Real-time price updates
- Volume and price change tracking
- Support for multiple exchanges
- Historical data analysis

### Risk Management
- Circuit limit checks
- Market hours validation
- Order quantity validation
- Error handling and recovery

## Setup

1. Install required packages:
```bash
pip install -r requirements.txt
```

2. Configure your API credentials in `config/config.yaml`:
```yaml
kite_connect:
  api_key: your_api_key
  api_secret: your_api_secret
  request_token: your_request_token
  access_token: your_access_token

breeze_api:
  api_key: your_api_key
  api_secret: your_api_secret
  session_id: your_session_id
```

3. Run the trading system:
```bash
python code/test_one_company.py
```

## Token Renewal Process

When tokens expire or become invalid, the system will:

1. Display a login URL for Kite Connect
2. Guide you through the login process
3. Automatically collect the request token
4. Generate and save a new access token
5. Update the configuration file while preserving other settings

## Order Management

The system maintains several order lists:
- `placed_orders`: Successfully executed orders
- `pending_orders`: Orders awaiting execution
- `failed_orders`: Orders that failed to execute
- `history`: Historical order records

## Error Handling

The system includes comprehensive error handling for:
- API connection issues
- Invalid tokens
- Order execution failures
- Market data retrieval problems
- Configuration errors

## Logging

Detailed logging is implemented for:
- Order operations
- Market data updates
- Error conditions
- System state changes

Logs are stored in `workdir/logs/` with stock-specific log files.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Project Structure

```
├── code/
│   ├── fall_buy.py           # Main trading strategy implementation
│   ├── kite_connect_api.py   # Kite Connect API wrapper
│   ├── kite_utils.py         # Utility functions and configurations
│   ├── breeze_sdk_api.py     # Breeze API integration
│   ├── order_manager.py      # Order management functionality
│   └── test_one_company.py   # Test script for single stock trading
├── config/
│   └── config.yaml          # Configuration file for API keys and strategy parameters
├── workdir/
│   └── logs/                # Trading logs organized by stock symbol and date
└── README.md
```

## Strategy Overview

The Fall Buy strategy is designed to:
1. Monitor stock prices in real-time using Breeze API
2. Place initial buy order when conditions are met
3. Execute subsequent buy orders when price falls by specified percentage
4. Sell positions when price rises above threshold
5. Maintain detailed logs of all trades and orders

## Key Components

### FallBuy Class (`fall_buy.py`)
- Core trading strategy implementation
- Handles price monitoring and decision making
- Manages order execution through Kite API
- Maintains trade history and position tracking

### OrderManager Class (`order_manager.py`)
- Handles all order-related operations
- Places buy/sell orders through Kite API
- Tracks order status and execution
- Manages order history and failed orders

### KiteConnectAPI (`kite_connect_api.py`)
- Wrapper for Kite Connect API
- Handles authentication and session management
- Provides methods for order placement and status checks

### BreezeSDKAPI (`breeze_sdk_api.py`)
- Integration with Breeze API for real-time data
- Handles WebSocket connection for live market data
- Manages session tokens and authentication

## Configuration

The strategy is configured through `config.yaml`:
```yaml
stratergy:
  buy: -2.0        # Buy threshold percentage
  sell: 2.0        # Sell threshold percentage
  start_buy: 100   # Initial investment amount
  linear_from: 5   # Linear scaling factor

breeze:
  app_key: "your_app_key"
  secret_key: "your_secret_key"
  session_token: "your_session_token"

kite:
  api_key: "your_api_key"
  api_secret: "your_api_secret"
  access_token: "your_access_token"
```

## Logging

Logs are stored in `workdir/logs/` with filenames in the format:
- `{stock_symbol}_{date}.log`

Each log file contains:
- Order execution details
- Price movements and decisions
- Error messages and stack traces
- API interaction logs

## Usage

1. Configure API credentials in `config.yaml`
2. Set strategy parameters in `config.yaml`
3. Run test script:
```bash
python code/test_one_company.py
```

## Dependencies

- Python 3.8+
- Kite Connect API
- Breeze API
- PyYAML
- Logging

## Error Handling

The strategy includes comprehensive error handling for:
- API connection issues
- Order placement failures
- Session token expiration
- Market data interruptions

## Notes

- All orders are placed as LIMIT orders
- Orders are valid for the trading day only
- Failed orders are logged and tracked
- Position tracking is maintained throughout the session 
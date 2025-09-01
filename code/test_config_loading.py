#!/usr/bin/env python3
"""
Test script to verify config loading works correctly
"""

import os
import sys

# Add the current directory to Python path so we can import kite_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kite_utils import load_config

def test_config_loading():
    """Test config loading from different scenarios"""
    print("Testing config loading...")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Script location: {os.path.abspath(__file__)}")
    
    try:
        config = load_config()
        print("✅ Config loaded successfully!")
        print(f"Config keys: {list(config.keys())}")
        
        if 'kite_connect' in config:
            kite_config = config['kite_connect']
            print(f"Kite Connect config keys: {list(kite_config.keys())}")
            # Don't print sensitive values, just confirm they exist
            if 'api_key' in kite_config:
                print("✅ API key found")
            if 'api_secret' in kite_config:
                print("✅ API secret found")
            if 'access_token' in kite_config:
                print("✅ Access token found")
        
        if 'breeze_api' in config:
            breeze_config = config['breeze_api']
            print(f"Breeze API config keys: {list(breeze_config.keys())}")
        
        return True
        
    except Exception as e:
        print(f"❌ Config loading failed: {e}")
        return False

if __name__ == "__main__":
    success = test_config_loading()
    if success:
        print("\n🎉 Config loading test passed!")
    else:
        print("\n💥 Config loading test failed!")
        sys.exit(1)


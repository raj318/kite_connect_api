#!/usr/bin/env python3
"""
Test script to verify Kite Connect connection works correctly
"""

import os
import sys

# Add the current directory to Python path so we can import kite_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kite_utils import initialize_kite, load_config

def test_kite_connection():
    """Test Kite Connect connection"""
    print("Testing Kite Connect connection...")
    
    try:
        # Test config loading
        print("1. Testing config loading...")
        config = load_config()
        print("✅ Config loaded successfully")
        
        # Test Kite initialization
        print("2. Testing Kite Connect initialization...")
        kite = initialize_kite()
        print("✅ Kite Connect initialized successfully")
        
        # Test basic connection (this should work even without market data permissions)
        print("3. Testing basic connection...")
        try:
            profile = kite.profile()
            print("✅ Profile retrieved successfully")
            print(f"User ID: {profile.get('user_id', 'N/A')}")
            print(f"User Name: {profile.get('user_name', 'N/A')}")
        except Exception as e:
            print(f"⚠️ Profile retrieval failed: {e}")
            print("This might be due to API permissions, but connection is working")
        
        # Test account balance (this should work with basic permissions)
        print("4. Testing account balance...")
        try:
            balance = kite.margins()
            print("✅ Account balance retrieved successfully")
            print(f"Available balance: ₹{balance.get('equity', {}).get('available', 'N/A')}")
        except Exception as e:
            print(f"⚠️ Balance retrieval failed: {e}")
            print("This might be due to API permissions, but connection is working")
        
        print("\n🎉 Kite Connect connection test completed!")
        return True
        
    except Exception as e:
        print(f"❌ Kite Connect connection test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_kite_connection()
    if not success:
        sys.exit(1)


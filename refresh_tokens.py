#!/usr/bin/env python3
"""
Simple script to manually refresh Tesla tokens
"""

import sys
from utils.token_manager import TeslaTokenManager

def main():
    print("🔄 Tesla Token Refresh")
    print("=" * 30)
    
    token_manager = TeslaTokenManager()
    
    if token_manager.is_token_expired():
        print("⏰ Token is expired or expiring soon")
        if token_manager.refresh_token():
            print("✅ Token refreshed successfully!")
        else:
            print("❌ Token refresh failed")
            sys.exit(1)
    else:
        print("✅ Token is still valid")

if __name__ == "__main__":
    main()

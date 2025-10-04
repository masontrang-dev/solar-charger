#!/usr/bin/env python3
"""
Simple Tesla OAuth 2.0 setup - manual process
"""

import requests
import yaml
import json
import urllib.parse

def tesla_oauth_simple():
    """Simple Tesla OAuth 2.0 flow with manual steps"""
    
    print("🔐 Tesla OAuth 2.0 Token Setup (Manual Process)")
    print("=" * 50)
    
    # Load current config
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        tesla_config = config.get('tesla', {}).get('api', {})
        client_id = tesla_config.get('client_id')
        client_secret = tesla_config.get('client_secret')
        
        if not client_id or not client_secret:
            print("❌ Missing client_id or client_secret in config.yaml")
            return
            
        print(f"✅ Found Client ID: {client_id}")
        print(f"✅ Found Client Secret: {client_secret[:10]}...")
        
    except FileNotFoundError:
        print("❌ config.yaml not found")
        return
    
    # Your redirect URI from Tesla Developer Console
    redirect_uri = "http://localhost:8080/callback"
    
    # Build authorization URL
    auth_params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'openid offline_access vehicle_device_data vehicle_cmds'
    }
    
    auth_url = "https://auth.tesla.com/oauth2/v3/authorize?" + urllib.parse.urlencode(auth_params)
    
    print(f"\n🔗 Step 1: Authorization URL")
    print("Copy this URL and paste it in your browser:")
    print()
    print(auth_url)
    print()
    
    print("📋 Step 2: Manual Process")
    print("1. Open the URL above in your browser")
    print("2. Log in with your Tesla account")
    print("3. Authorize the application")
    print("4. You'll be redirected to: http://localhost:8080/callback?code=...")
    print("5. The page will show an error (that's expected - port 8080 is busy)")
    print("6. Copy the 'code' parameter from the URL")
    print()
    
    # Get authorization code from user
    auth_code = input("Enter the authorization code from the redirect URL: ").strip()
    
    if not auth_code:
        print("❌ Authorization code is required")
        return
    
    print(f"✅ Authorization code received: {auth_code[:20]}...")
    
    # Exchange code for tokens
    print("\n🔄 Step 3: Exchanging code for tokens...")
    
    token_url = "https://auth.tesla.com/oauth2/v3/token"
    token_data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": auth_code,
        "redirect_uri": redirect_uri
    }
    
    try:
        response = requests.post(token_url, json=token_data, timeout=30)
        
        if response.status_code == 200:
            tokens = response.json()
            
            access_token = tokens.get('access_token')
            refresh_token = tokens.get('refresh_token')
            expires_in = tokens.get('expires_in', 28800)
            
            print("✅ Tokens received successfully!")
            print(f"Access Token: {access_token[:30]}...")
            print(f"Refresh Token: {refresh_token[:30]}...")
            print(f"Expires in: {expires_in} seconds ({expires_in/3600:.1f} hours)")
            
            # Update config file
            config['tesla']['api']['access_token'] = access_token
            config['tesla']['api']['refresh_token'] = refresh_token
            
            with open('config.yaml', 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
            
            print("\n✅ config.yaml updated with new tokens!")
            print("\n🚀 Your Tesla API is now ready! You can run:")
            print("   .venv/bin/python run.py")
            print("\n💡 Tokens will expire in ~8 hours. Use refresh_tesla_token.py to refresh them.")
            
        else:
            print(f"❌ Token exchange failed: {response.status_code}")
            print(f"Response: {response.text}")
            
            if response.status_code == 400:
                error_data = response.json()
                if "invalid_grant" in error_data.get("error", ""):
                    print("\n💡 The authorization code may have expired or been used already.")
                    print("Please try the process again with a fresh authorization code.")
            
    except Exception as e:
        print(f"❌ Token exchange error: {e}")

if __name__ == "__main__":
    tesla_oauth_simple()

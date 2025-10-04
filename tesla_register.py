#!/usr/bin/env python3
"""
Tesla Fleet API Registration Script
This script registers your Tesla app with the Fleet API so you can make vehicle data calls.
"""

import requests
import yaml
import json
import time


def get_partner_token(client_id, client_secret):
    """Get a partner authentication token for Fleet API registration"""
    print("Step 1: Getting partner authentication token...")
    
    token_data = {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret,
        'scope': 'openid vehicle_device_data vehicle_cmds vehicle_charging_cmds',
        'audience': 'https://fleet-api.prd.na.vn.cloud.tesla.com'
    }
    
    response = requests.post(
        'https://auth.tesla.com/oauth2/v3/token',
        data=token_data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        timeout=10
    )
    
    if response.status_code == 200:
        token_info = response.json()
        partner_token = token_info['access_token']
        print(f"✅ Partner token received (expires in {token_info.get('expires_in', 'unknown')} seconds)")
        return partner_token
    else:
        print(f"❌ Failed to get partner token: {response.status_code}")
        print(f"Response: {response.text}")
        return None


def register_partner_account(partner_token, domain="thriving-wisp-a199e4.netlify.app"):
    """Register the partner account with Tesla Fleet API"""
    print(f"Step 2: Registering partner account with domain '{domain}'...")
    
    headers = {
        'Authorization': f'Bearer {partner_token}',
        'Content-Type': 'application/json'
    }
    
    registration_data = {
        'domain': domain
    }
    
    response = requests.post(
        'https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/partner_accounts',
        headers=headers,
        json=registration_data,
        timeout=10
    )
    
    print(f"Registration response status: {response.status_code}")
    
    if response.status_code in [200, 201]:
        print("✅ Partner account registered successfully!")
        try:
            result = response.json()
            print("Registration details:")
            print(json.dumps(result, indent=2))
        except:
            print("Registration successful (no JSON response)")
        return True
    elif response.status_code == 409:
        print("✅ Partner account already registered!")
        return True
    else:
        print(f"❌ Registration failed: {response.status_code}")
        print(f"Response: {response.text}")
        return False


def test_fleet_api_access(access_token):
    """Test if Fleet API access is working"""
    print("Step 3: Testing Fleet API access...")
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    response = requests.get(
        'https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles',
        headers=headers,
        timeout=10
    )
    
    print(f"Test API call status: {response.status_code}")
    
    if response.status_code == 200:
        vehicles = response.json()
        print("✅ Fleet API access is working!")
        print(f"Found {len(vehicles.get('response', []))} vehicle(s)")
        return True
    else:
        print(f"❌ Fleet API access still failing: {response.status_code}")
        print(f"Response: {response.text}")
        return False


def main():
    print("Tesla Fleet API Registration")
    print("=" * 40)
    
    # Load config
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("❌ config.yaml not found!")
        return
    
    tesla_config = config.get('tesla', {}).get('api', {})
    client_id = tesla_config.get('client_id')
    client_secret = tesla_config.get('client_secret')
    access_token = tesla_config.get('access_token')
    
    if not client_id or not client_secret:
        print("❌ Missing client_id or client_secret in config.yaml")
        return
    
    if not access_token:
        print("❌ Missing access_token in config.yaml")
        print("Run tesla_oauth.py first to get your access token")
        return
    
    print(f"Client ID: {client_id}")
    print(f"Has access token: {bool(access_token)}")
    print()
    
    # Step 1: Get partner token
    partner_token = get_partner_token(client_id, client_secret)
    if not partner_token:
        return
    
    print()
    
    # Step 2: Register partner account
    success = register_partner_account(partner_token)
    if not success:
        return
    
    print()
    
    # Step 3: Test Fleet API access
    print("Waiting 5 seconds for registration to propagate...")
    time.sleep(5)
    
    test_success = test_fleet_api_access(access_token)
    
    print()
    print("=" * 40)
    if test_success:
        print("🎉 SUCCESS! Your Tesla Fleet API is now registered and working!")
        print("You can now run your solar charger with real Tesla data.")
        print()
        print("Try testing your Tesla connection:")
        print("  .venv/bin/python - <<'PY'")
        print("  from clients.tesla import TeslaClient")
        print("  import yaml")
        print("  with open('config.yaml') as f:")
        print("      config = yaml.safe_load(f)")
        print("  config['dry_run'] = False")
        print("  client = TeslaClient(config)")
        print("  print(client.get_state())")
        print("  PY")
    else:
        print("❌ Registration completed but API access still not working.")
        print("This might take a few more minutes to propagate.")
        print("Try running the test again in 5-10 minutes.")


if __name__ == "__main__":
    main()

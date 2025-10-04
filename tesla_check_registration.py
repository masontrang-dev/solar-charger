#!/usr/bin/env python3
"""
Check Tesla Fleet API registration status
"""

import requests
import yaml
import json


def check_registration_status():
    """Check if the account is already registered"""
    
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    tesla_config = config.get('tesla', {}).get('api', {})
    client_id = tesla_config.get('client_id')
    client_secret = tesla_config.get('client_secret')
    
    # Get partner token
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
    
    if response.status_code != 200:
        print(f"❌ Failed to get partner token: {response.text}")
        return
    
    partner_token = response.json()['access_token']
    print("✅ Got partner token")
    
    headers = {
        'Authorization': f'Bearer {partner_token}',
        'Content-Type': 'application/json'
    }
    
    # Check if public key is registered
    print("\n🔍 Checking public key registration...")
    try:
        pub_key_response = requests.get(
            'https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/partner_accounts/public_key?domain=thriving-wisp-a199e4.netlify.app',
            headers=headers,
            timeout=10
        )
        
        print(f"Public key check status: {pub_key_response.status_code}")
        if pub_key_response.status_code == 200:
            print("✅ Public key is registered!")
            print(json.dumps(pub_key_response.json(), indent=2))
        else:
            print(f"❌ Public key not found: {pub_key_response.text}")
    except Exception as e:
        print(f"❌ Error checking public key: {e}")
    
    # Try different registration approaches
    domains_to_try = [
        "thriving-wisp-a199e4.netlify.app",
        "netlify.app", 
        "github.io",
        "example.com"
    ]
    
    for domain in domains_to_try:
        print(f"\n🔍 Trying registration with domain: {domain}")
        
        registration_data = {'domain': domain}
        
        reg_response = requests.post(
            'https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/partner_accounts',
            headers=headers,
            json=registration_data,
            timeout=10
        )
        
        print(f"Status: {reg_response.status_code}")
        
        if reg_response.status_code in [200, 201]:
            print(f"✅ SUCCESS! Registered with domain: {domain}")
            return domain
        elif reg_response.status_code == 409:
            print(f"✅ Already registered with domain: {domain}")
            return domain
        else:
            print(f"❌ Failed: {reg_response.text}")
    
    return None


if __name__ == "__main__":
    print("Tesla Fleet API Registration Check")
    print("=" * 50)
    result = check_registration_status()
    if result:
        print(f"\n🎉 Registration working with domain: {result}")
    else:
        print("\n❌ No successful registration found")

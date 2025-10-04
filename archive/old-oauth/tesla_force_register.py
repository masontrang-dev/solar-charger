#!/usr/bin/env python3
"""
Force Tesla Fleet API registration with different approaches
"""

import requests
import yaml
import json
import time


def force_registration():
    """Try multiple registration approaches"""
    
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
        return False
    
    partner_token = response.json()['access_token']
    print("✅ Got partner token")
    
    headers = {
        'Authorization': f'Bearer {partner_token}',
        'Content-Type': 'application/json'
    }
    
    # Try registration with different payload formats
    registration_attempts = [
        # Standard format
        {"domain": "thriving-wisp-a199e4.netlify.app"},
        
        # With protocol (sometimes needed)
        {"domain": "https://thriving-wisp-a199e4.netlify.app"},
        
        # Root domain only
        {"domain": "netlify.app"},
        
        # Alternative payload structure
        {"root_domain": "thriving-wisp-a199e4.netlify.app"},
        
        # With additional fields
        {
            "domain": "thriving-wisp-a199e4.netlify.app",
            "public_key_url": "https://thriving-wisp-a199e4.netlify.app/.well-known/appspecific/com.tesla.3p.public-key.pem"
        }
    ]
    
    for i, payload in enumerate(registration_attempts, 1):
        print(f"\n🔍 Attempt {i}: {json.dumps(payload)}")
        
        try:
            reg_response = requests.post(
                'https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/partner_accounts',
                headers=headers,
                json=payload,
                timeout=10
            )
            
            print(f"Status: {reg_response.status_code}")
            
            if reg_response.status_code in [200, 201]:
                print(f"✅ SUCCESS! Registration worked with payload: {payload}")
                
                # Test API access immediately
                print("\n🔍 Testing API access...")
                test_api_access()
                return True
                
            elif reg_response.status_code == 409:
                print(f"✅ Already registered! Testing API access...")
                test_api_access()
                return True
                
            else:
                print(f"❌ Failed: {reg_response.text}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
        
        # Small delay between attempts
        time.sleep(1)
    
    return False


def test_api_access():
    """Test if Tesla API access works after registration"""
    
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    access_token = config.get('tesla', {}).get('api', {}).get('access_token')
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(
            "https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles",
            headers=headers,
            timeout=10
        )
        
        print(f"API Test Status: {response.status_code}")
        
        if response.status_code == 200:
            print("🎉 SUCCESS! Tesla API is working!")
            vehicles = response.json()
            print(f"Found {len(vehicles.get('response', []))} vehicle(s)")
            return True
        else:
            print(f"❌ API still not working: {response.text}")
            
    except Exception as e:
        print(f"❌ API test error: {e}")
    
    return False


if __name__ == "__main__":
    print("Tesla Fleet API Force Registration")
    print("=" * 50)
    
    if force_registration():
        print("\n🎉 Registration successful! Tesla API should now work.")
    else:
        print("\n❌ All registration attempts failed.")
        print("Next step: Contact Tesla Developer Support")

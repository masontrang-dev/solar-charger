#!/usr/bin/env python3
"""
Test Tesla Vehicle Command Protocol with signed commands
"""

import requests
import yaml
import json
import time
from tesla_command_signer import TeslaCommandSigner


def test_signed_commands():
    """Test signed Tesla charging commands"""
    
    print("🔐 Testing Tesla Signed Commands")
    print("=" * 50)
    
    # Load config
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    tesla_config = config.get('tesla', {}).get('api', {})
    access_token = tesla_config.get('access_token')
    vin = config.get('tesla', {}).get('vehicle_vin')
    
    # Get vehicle ID
    print("1. Getting vehicle ID...")
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        vehicles_response = requests.get(
            "https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles",
            headers=headers,
            timeout=10
        )
        
        if vehicles_response.status_code == 200:
            vehicles = vehicles_response.json()
            vehicle_id = None
            for vehicle in vehicles.get('response', []):
                if vehicle.get('vin') == vin:
                    vehicle_id = vehicle.get('id')
                    print(f"✅ Vehicle ID: {vehicle_id}")
                    break
        else:
            print(f"❌ Failed to get vehicles: {vehicles_response.text}")
            return
            
    except Exception as e:
        print(f"❌ Error getting vehicle ID: {e}")
        return
    
    # Initialize command signer
    print("\n2. Initializing command signer...")
    try:
        signer = TeslaCommandSigner()
        print("✅ Command signer ready")
    except Exception as e:
        print(f"❌ Failed to initialize signer: {e}")
        print("Make sure you've run: .venv/bin/python generate_command_keys.py")
        return
    
    # Test signed charge_start command
    print(f"\n3. Testing signed charge_start command...")
    try:
        # Create signed headers
        signed_headers = signer.create_signed_request_headers(
            method="POST",
            vehicle_id=vehicle_id,
            command="charge_start"
        )
        
        # Add authorization header
        signed_headers["Authorization"] = f"Bearer {access_token}"
        
        print("Headers being sent:")
        for key, value in signed_headers.items():
            if key == 'Tesla-Command-Signature':
                print(f"  {key}: {value[:30]}...")
            else:
                print(f"  {key}: {value}")
        
        # Send signed request
        url = f"https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles/{vehicle_id}/command/charge_start"
        print(f"\nURL: {url}")
        
        response = requests.post(
            url,
            headers=signed_headers,
            json={},
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get('response', {}).get('result'):
                print("🎉 SUCCESS! Signed charge_start worked!")
                
                # Test signed charge_stop after 5 seconds
                print("\n⏳ Waiting 5 seconds, then testing signed charge_stop...")
                time.sleep(5)
                
                stop_headers = signer.create_signed_request_headers(
                    method="POST",
                    vehicle_id=vehicle_id,
                    command="charge_stop"
                )
                stop_headers["Authorization"] = f"Bearer {access_token}"
                
                stop_url = f"https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles/{vehicle_id}/command/charge_stop"
                stop_response = requests.post(
                    stop_url,
                    headers=stop_headers,
                    json={},
                    timeout=10
                )
                
                print(f"Stop Status: {stop_response.status_code}")
                print(f"Stop Response: {stop_response.text}")
                
                if stop_response.status_code == 200:
                    stop_result = stop_response.json()
                    if stop_result.get('response', {}).get('result'):
                        print("🎉 SUCCESS! Both signed commands work!")
                        return True
                    else:
                        print(f"❌ Stop command failed: {stop_result}")
                else:
                    print(f"❌ Stop command HTTP error: {stop_response.status_code}")
                    
            else:
                print(f"❌ Start command failed: {result}")
                
        elif response.status_code == 403:
            if "public key" in response.text.lower():
                print("❌ Public key not uploaded or not active yet")
                print("   → Make sure you uploaded the public key to Tesla developer portal")
                print("   → Wait a few minutes for it to become active")
            elif "signature" in response.text.lower():
                print("❌ Signature verification failed")
                print("   → Check that the public key matches the private key")
            else:
                print("❌ Other 403 error - check Tesla developer portal settings")
        elif response.status_code == 401:
            print("❌ Unauthorized - check your access token")
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error testing signed commands: {e}")
        import traceback
        traceback.print_exc()
    
    return False


if __name__ == "__main__":
    print("Tesla Vehicle Command Protocol Test")
    print("=" * 50)
    print("Prerequisites:")
    print("1. Run: .venv/bin/python generate_command_keys.py")
    print("2. Upload public key to Tesla developer portal")
    print("3. Wait a few minutes for key to become active")
    print()
    
    if test_signed_commands():
        print("\n🎉 Signed commands working! Ready to integrate with solar charger.")
    else:
        print("\n❌ Signed commands not working yet. Check prerequisites above.")

#!/usr/bin/env python3
"""
Test Tesla commands through the Tesla HTTP proxy
"""

import requests
import yaml
import json
import urllib3

# Disable SSL warnings for self-signed certificate
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def test_proxy_commands():
    """Test Tesla charging commands through the HTTP proxy"""
    
    print("🔐 Testing Tesla Commands Through HTTP Proxy")
    print("=" * 60)
    
    # Load config for access token
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    tesla_config = config.get('tesla', {}).get('api', {})
    access_token = tesla_config.get('access_token')
    vin = config.get('tesla', {}).get('vehicle_vin')
    
    # Proxy is running on localhost:8080 with self-signed cert
    proxy_base = "https://localhost:8080"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    print("1. Getting vehicle list through proxy...")
    try:
        vehicles_response = requests.get(
            f"{proxy_base}/api/1/vehicles",
            headers=headers,
            verify=False,  # Skip SSL verification for self-signed cert
            timeout=10
        )
        
        print(f"Status: {vehicles_response.status_code}")
        
        if vehicles_response.status_code == 200:
            vehicles = vehicles_response.json()
            vehicle_id = None
            for vehicle in vehicles.get('response', []):
                if vehicle.get('vin') == vin:
                    vehicle_id = vehicle.get('id')
                    print(f"✅ Found vehicle ID: {vehicle_id}")
                    break
        else:
            print(f"❌ Failed to get vehicles: {vehicles_response.text}")
            return
            
    except Exception as e:
        print(f"❌ Error getting vehicles: {e}")
        return
    
    print(f"\n2. Testing charge_start through proxy...")
    try:
        charge_url = f"{proxy_base}/api/1/vehicles/{vin}/command/charge_start"
        print(f"URL: {charge_url}")
        
        charge_response = requests.post(
            charge_url,
            headers=headers,
            json={},
            verify=False,
            timeout=10
        )
        
        print(f"Status: {charge_response.status_code}")
        print(f"Response: {charge_response.text}")
        
        if charge_response.status_code == 200:
            result = charge_response.json()
            if result.get('response', {}).get('result'):
                print("🎉 SUCCESS! Charging started through proxy!")
                
                # Test stop after 5 seconds
                print("\n⏳ Waiting 5 seconds, then testing charge_stop...")
                import time
                time.sleep(5)
                
                stop_url = f"{proxy_base}/api/1/vehicles/{vin}/command/charge_stop"
                stop_response = requests.post(
                    stop_url,
                    headers=headers,
                    json={},
                    verify=False,
                    timeout=10
                )
                
                print(f"Stop Status: {stop_response.status_code}")
                print(f"Stop Response: {stop_response.text}")
                
                if stop_response.status_code == 200:
                    stop_result = stop_response.json()
                    if stop_result.get('response', {}).get('result'):
                        print("🎉 SUCCESS! Both start and stop work through proxy!")
                        return True
                    else:
                        print(f"❌ Stop command failed: {stop_result}")
                else:
                    print(f"❌ Stop command HTTP error: {stop_response.status_code}")
                    
            else:
                print(f"❌ Start command failed: {result}")
                
        else:
            print(f"❌ HTTP Error: {charge_response.status_code}")
            if "not found" in charge_response.text.lower():
                print("   → Vehicle might not be paired with virtual key")
            elif "unauthorized" in charge_response.text.lower():
                print("   → Access token issue")
            elif "timeout" in charge_response.text.lower():
                print("   → Vehicle might be asleep")
                
    except Exception as e:
        print(f"❌ Error testing charge commands: {e}")
    
    return False


if __name__ == "__main__":
    print("Tesla HTTP Proxy Command Test")
    print("=" * 60)
    print("Prerequisites:")
    print("1. Tesla HTTP proxy running on localhost:8080")
    print("2. Virtual key paired with vehicle")
    print("3. Vehicle online and plugged in")
    print()
    
    if test_proxy_commands():
        print("\n🎉 Proxy commands working! Ready to integrate with solar charger.")
    else:
        print("\n❌ Proxy commands not working yet. Check virtual key pairing.")

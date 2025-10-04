#!/usr/bin/env python3
"""
Tesla API Debug Script - Check what Tesla is actually returning
"""

import requests
import yaml
import json


def test_tesla_endpoints():
    """Test different Tesla API endpoints to see what's happening"""
    
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    tesla_config = config.get('tesla', {}).get('api', {})
    access_token = tesla_config.get('access_token')
    vin = config.get('tesla', {}).get('vehicle_vin')
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    print("Tesla API Debug")
    print("=" * 50)
    print(f"VIN: {vin}")
    print(f"Access Token: {access_token[:20]}...")
    print()
    
    # Test different endpoints
    endpoints = [
        ("Vehicles List", "https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles"),
        ("Vehicle Data (VIN)", f"https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles/{vin}/vehicle_data"),
        ("Vehicle Data (ID)", f"https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles/VEHICLE_ID/vehicle_data"),
        ("Wake Up", f"https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles/{vin}/wake_up"),
    ]
    
    for name, url in endpoints:
        print(f"\n🔍 Testing: {name}")
        print(f"URL: {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("✅ SUCCESS!")
                print(json.dumps(data, indent=2))
                
                # If this is vehicles list, extract vehicle ID for next test
                if name == "Vehicles List" and "response" in data:
                    vehicles = data["response"]
                    if vehicles:
                        vehicle_id = vehicles[0].get("id")
                        print(f"\n📝 Found Vehicle ID: {vehicle_id}")
                        
                        # Test with vehicle ID instead of VIN
                        print(f"\n🔍 Testing: Vehicle Data with ID {vehicle_id}")
                        id_url = f"https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles/{vehicle_id}/vehicle_data"
                        id_response = requests.get(id_url, headers=headers, timeout=10)
                        print(f"Status: {id_response.status_code}")
                        
                        if id_response.status_code == 200:
                            print("✅ SUCCESS with Vehicle ID!")
                            id_data = id_response.json()
                            charge_state = id_data.get("response", {}).get("charge_state", {})
                            print(f"🔋 Battery: {charge_state.get('battery_level')}%")
                            print(f"🔌 Charging: {charge_state.get('charging_state')}")
                        else:
                            print(f"❌ Failed: {id_response.text}")
                
                break  # If we get success, we can stop here
                
            else:
                print(f"❌ Failed: {response.text}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print("\n" + "=" * 50)
    print("Debug complete!")


if __name__ == "__main__":
    test_tesla_endpoints()

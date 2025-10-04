#!/usr/bin/env python3
"""
Test different wake command paths to see which one works
"""

import requests
import yaml
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def test_wake_commands():
    """Test different wake command paths"""
    
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    tesla_config = config.get('tesla', {}).get('api', {})
    access_token = tesla_config.get('access_token')
    vin = config.get('tesla', {}).get('vehicle_vin')
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    print("🔍 Testing Different Wake Command Paths")
    print("=" * 50)
    print(f"VIN: {vin}")
    print()
    
    # Test different wake paths
    wake_tests = [
        ("Tesla HTTP Proxy - /command/wake_up", f"https://localhost:8080/api/1/vehicles/{vin}/command/wake_up"),
        ("Tesla HTTP Proxy - /wake_up", f"https://localhost:8080/api/1/vehicles/{vin}/wake_up"),
        ("Direct Fleet API - /wake_up", f"https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles/{vin}/wake_up"),
    ]
    
    for name, url in wake_tests:
        print(f"🧪 Testing: {name}")
        print(f"URL: {url}")
        
        try:
            # For proxy calls, skip SSL verification
            verify_ssl = not url.startswith("https://localhost")
            
            response = requests.post(
                url, 
                headers=headers, 
                json={}, 
                timeout=15,
                verify=verify_ssl
            )
            
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                print("✅ SUCCESS! This wake path works")
                try:
                    data = response.json()
                    if data.get('response', {}).get('result'):
                        print("✅ Wake command accepted by vehicle")
                    else:
                        print("⚠️ Wake command sent but result was false")
                except:
                    print("✅ Wake command sent (no JSON response)")
            else:
                print(f"❌ Failed: {response.text}")
                
        except Exception as e:
            print(f"❌ Exception: {e}")
        
        print("-" * 30)
    
    print("\n💡 Recommendations:")
    print("- If proxy /command/wake_up works: Use Tesla HTTP proxy")
    print("- If direct Fleet API works: Use direct API calls")  
    print("- If none work: Vehicle might be in deep sleep")
    print("- Try waking manually in Tesla app first")

if __name__ == "__main__":
    test_wake_commands()

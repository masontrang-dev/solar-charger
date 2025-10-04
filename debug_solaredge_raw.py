#!/usr/bin/env python3
"""
Debug SolarEdge API raw responses
"""

import requests
import yaml
import json


def debug_raw_solaredge():
    """Check raw SolarEdge API responses"""
    
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    se_config = config.get("solaredge", {}).get("cloud", {})
    api_key = se_config.get("api_key")
    site_id = se_config.get("site_id")
    
    print("🌞 SolarEdge Raw API Debug")
    print("=" * 50)
    print(f"Site ID: {site_id}")
    print(f"API Key: {api_key[:10]}...")
    print()
    
    # Test both endpoints
    endpoints = [
        ("Current Power Flow", f"https://monitoringapi.solaredge.com/site/{site_id}/currentPowerFlow.json"),
        ("Overview", f"https://monitoringapi.solaredge.com/site/{site_id}/overview.json"),
        ("Power Details", f"https://monitoringapi.solaredge.com/site/{site_id}/powerDetails.json"),
    ]
    
    for name, url in endpoints:
        print(f"\n🔍 Testing: {name}")
        print(f"URL: {url}")
        
        try:
            params = {"api_key": api_key}
            response = requests.get(url, params=params, timeout=10)
            
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("Raw Response:")
                print(json.dumps(data, indent=2))
                
                # Extract power values
                if name == "Current Power Flow":
                    site_flow = data.get("siteCurrentPowerFlow", {})
                    pv_data = site_flow.get("PV", {})
                    print(f"\n📊 PV Data: {pv_data}")
                    print(f"Current Power: {pv_data.get('currentPower')}")
                    
                elif name == "Overview":
                    overview = data.get("overview", {})
                    current_power = overview.get("currentPower", {})
                    print(f"\n📊 Current Power Data: {current_power}")
                    print(f"Power: {current_power.get('power')}")
                    
            else:
                print(f"❌ Error: {response.text}")
                
        except Exception as e:
            print(f"❌ Exception: {e}")
        
        print("-" * 50)


if __name__ == "__main__":
    debug_raw_solaredge()

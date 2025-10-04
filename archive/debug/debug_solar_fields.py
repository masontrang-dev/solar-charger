#!/usr/bin/env python3
"""
Debug SolarEdge API fields to understand grid export
"""

import yaml
import json
from clients.solaredge_cloud import SolarEdgeCloudClient

def debug_solar_fields():
    """Debug what fields SolarEdge API returns"""
    
    print("🌞 SolarEdge API Fields Debug")
    print("=" * 40)
    
    # Load config
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Create SolarEdge client
    solar_client = SolarEdgeCloudClient(config)
    
    try:
        # Get solar data
        solar_data = solar_client.get_power()
        
        print("📊 Solar Data Fields:")
        for field, value in solar_data.items():
            print(f"  {field}: {value}")
        
        print(f"\n🔍 Field Explanations:")
        print(f"  pv_production_w: Solar panels producing {solar_data.get('pv_production_w', 0)}W")
        
        export_w = solar_data.get('site_export_w')
        if export_w is not None:
            if export_w > 0:
                print(f"  site_export_w: Exporting {export_w}W to grid (surplus solar)")
            else:
                print(f"  site_export_w: Not exporting (consuming all solar + grid power)")
        else:
            print(f"  site_export_w: No export data available (meter not configured)")
        
        # Try to get more detailed data
        print(f"\n🔍 Trying to get detailed power flow...")
        
        # Access the internal API call to see raw data
        site_id = config.get('solaredge', {}).get('cloud', {}).get('site_id')
        if site_id:
            try:
                raw_data = solar_client._get(f"/site/{site_id}/currentPowerFlow.json", {})
                print(f"\n📋 Raw Power Flow Data:")
                print(json.dumps(raw_data, indent=2))
            except Exception as e:
                print(f"❌ Could not get detailed power flow: {e}")
                
                # Try overview instead
                try:
                    overview_data = solar_client._get(f"/site/{site_id}/overview.json", {})
                    print(f"\n📋 Raw Overview Data:")
                    print(json.dumps(overview_data, indent=2))
                except Exception as e2:
                    print(f"❌ Could not get overview either: {e2}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_solar_fields()

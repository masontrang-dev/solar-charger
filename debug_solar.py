#!/usr/bin/env python3
"""
Debug SolarEdge API to see what data we're getting
"""

import yaml
import json
from clients.solaredge_cloud import SolarEdgeCloudClient


def debug_solar_data():
    """Check what SolarEdge API is returning"""
    
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    client = SolarEdgeCloudClient(config)
    
    print("🌞 SolarEdge API Debug")
    print("=" * 50)
    
    try:
        # Get raw solar data
        solar_data = client.get_power()
        
        print("Raw API Response:")
        print(json.dumps(solar_data, indent=2))
        
        print("\nParsed Values:")
        pv_production_w = solar_data.get("pv_production_w", 0)
        site_export_w = solar_data.get("site_export_w")
        
        print(f"PV Production (W): {pv_production_w}")
        print(f"Site Export (W): {site_export_w}")
        print(f"PV Production (kW): {pv_production_w / 1000.0:.3f}")
        
        if site_export_w is not None:
            print(f"Site Export (kW): {site_export_w / 1000.0:.3f}")
        else:
            print("Site Export (kW): No meter data")
            
        print(f"\nExpected from phone: 490W = 0.490kW")
        print(f"Actual from API: {pv_production_w}W = {pv_production_w / 1000.0:.3f}kW")
        
        if pv_production_w == 0:
            print("\n⚠️  API returning 0W - possible issues:")
            print("1. Nighttime (no production)")
            print("2. API delay/caching")
            print("3. Different data source than phone app")
            print("4. API endpoint issue")
            
    except Exception as e:
        print(f"❌ Error getting solar data: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    debug_solar_data()

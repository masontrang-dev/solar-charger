#!/usr/bin/env python3
"""
Debug Tesla vehicle state to see what data we're getting
"""

import yaml
import json
from clients.tesla import TeslaClient


def debug_tesla_state():
    """Check what Tesla API is returning for vehicle state"""
    
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Disable dry run to get real data
    config['dry_run'] = False
    
    client = TeslaClient(config)
    
    print("🚗 Tesla Vehicle State Debug")
    print("=" * 50)
    
    try:
        # Get raw Tesla data
        tesla_data = client.get_state()
        
        print("Full Tesla API Response:")
        print(json.dumps(tesla_data, indent=2))
        
        print("\nKey Vehicle State Fields:")
        print(f"SOC: {tesla_data.get('soc')}%")
        print(f"Plugged In: {tesla_data.get('plugged_in')}")
        print(f"Charging State: {tesla_data.get('charging_state')}")
        print(f"Shift State: {tesla_data.get('shift_state')}")
        print(f"Speed: {tesla_data.get('speed')}")
        print(f"Location: {tesla_data.get('location')}")
        
        # Check if we have the raw vehicle data
        print(f"\nVehicle State Field: {tesla_data.get('vehicle_state')}")
        
        # Determine what our display logic would show
        shift_state = tesla_data.get('shift_state')
        speed = tesla_data.get('speed', 0)
        
        if speed and speed > 0:
            display_state = f"Driving {speed}mph"
        elif shift_state == "P":
            display_state = "Parked"
        elif shift_state == "D":
            display_state = "Drive"
        elif shift_state == "R":
            display_state = "Reverse"
        elif shift_state == "N":
            display_state = "Neutral"
        elif shift_state is None:
            display_state = "Parked (no shift data)"
        else:
            display_state = shift_state or "Unknown"
            
        print(f"\nDisplay would show: '{display_state}'")
        
        if shift_state is None:
            print("\n⚠️  No shift_state data - Tesla might be asleep or API doesn't provide this field")
            
    except Exception as e:
        print(f"❌ Error getting Tesla state: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    debug_tesla_state()

#!/usr/bin/env python3
"""
Test the complete wake + charge sequence
"""

from clients.tesla import TeslaClient
import yaml
import time

def test_wake_and_charge():
    """Test wake vehicle then charge sequence"""
    
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Temporarily disable dry run for this test
    config['dry_run'] = False
    
    client = TeslaClient(config)
    
    print("🔋 Testing Wake + Charge Sequence")
    print("=" * 50)
    
    print("1. Getting initial vehicle state...")
    initial_state = client.get_state()
    print(f"   Plugged in: {initial_state.get('plugged_in')}")
    print(f"   SOC: {initial_state.get('soc')}%")
    print(f"   Charging: {initial_state.get('charging_state')}")
    
    print("\n2. Attempting to start charging (will wake if needed)...")
    success = client.start_charging()
    
    if success:
        print("✅ Charging started successfully!")
        
        print("\n3. Waiting 10 seconds then stopping...")
        time.sleep(10)
        
        stop_success = client.stop_charging()
        if stop_success:
            print("✅ Charging stopped successfully!")
        else:
            print("❌ Failed to stop charging")
    else:
        print("❌ Failed to start charging")
    
    print("\n4. Final vehicle state...")
    final_state = client.get_state()
    print(f"   Plugged in: {final_state.get('plugged_in')}")
    print(f"   SOC: {final_state.get('soc')}%")
    print(f"   Charging: {final_state.get('charging_state')}")

if __name__ == "__main__":
    test_wake_and_charge()

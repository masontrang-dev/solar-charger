#!/usr/bin/env python3
"""
Debug Tesla API fields to see what's actually available
"""

import yaml
import json
from clients.tesla import TeslaClient

def debug_tesla_fields():
    """Debug what fields Tesla API actually returns"""
    
    print("🔍 Tesla API Fields Debug")
    print("=" * 40)
    
    # Load config
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Create Tesla client
    tesla_client = TeslaClient(config)
    
    try:
        # Get raw vehicle data
        vin = config.get('tesla', {}).get('vehicle_vin')
        print(f"Getting data for VIN: {vin}")
        
        raw_data = tesla_client._get(f"/api/1/vehicles/{vin}/vehicle_data")
        vehicle_data = raw_data.get("response", {})
        
        print("\n📊 Available Data Sections:")
        for section in vehicle_data.keys():
            print(f"  - {section}")
        
        # Focus on charge_state
        charge_state = vehicle_data.get("charge_state", {})
        print(f"\n🔋 Charge State Fields ({len(charge_state)} total):")
        
        # Group fields by category
        power_fields = []
        current_fields = []
        voltage_fields = []
        other_fields = []
        
        for field, value in charge_state.items():
            if 'power' in field.lower():
                power_fields.append((field, value))
            elif 'current' in field.lower() or 'amp' in field.lower():
                current_fields.append((field, value))
            elif 'voltage' in field.lower() or 'volt' in field.lower():
                voltage_fields.append((field, value))
            else:
                other_fields.append((field, value))
        
        print("\n⚡ Power-related fields:")
        for field, value in power_fields:
            print(f"  {field}: {value}")
        
        print("\n🔌 Current/Amp fields:")
        for field, value in current_fields:
            print(f"  {field}: {value}")
        
        print("\n⚡ Voltage fields:")
        for field, value in voltage_fields:
            print(f"  {field}: {value}")
        
        print("\n📋 Other charging fields:")
        for field, value in other_fields:  # Show ALL fields
            print(f"  {field}: {value}")
        
        # Calculate power if not provided
        actual_current = charge_state.get("charger_actual_current", 0)
        voltage = charge_state.get("charger_voltage", 0)
        calculated_power = (actual_current * voltage / 1000.0) if actual_current and voltage else 0
        
        print(f"\n🧮 Power Calculation:")
        print(f"  Actual Current: {actual_current}A")
        print(f"  Voltage: {voltage}V")
        print(f"  Calculated Power: {calculated_power:.2f}kW")
        
        # Check if charging
        charging_state = charge_state.get("charging_state", "Unknown")
        print(f"\n🔋 Current Status:")
        print(f"  Charging State: {charging_state}")
        print(f"  Battery Level: {charge_state.get('battery_level', 0)}%")
        
        # Option to dump ALL charge_state fields as JSON
        print(f"\n📄 Complete charge_state dump (JSON format):")
        print("=" * 50)
        print(json.dumps(charge_state, indent=2, sort_keys=True))
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_tesla_fields()

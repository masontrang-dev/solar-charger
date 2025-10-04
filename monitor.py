#!/usr/bin/env python3
"""
Solar Charger Monitor - Clean output for monitoring
"""

import time
import yaml
from datetime import datetime
from clients.solaredge_cloud import SolarEdgeCloudClient
from clients.tesla import TeslaClient


def monitor_system():
    """Monitor solar and Tesla with clean output"""
    
    # Load config
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Initialize clients
    solar_client = SolarEdgeCloudClient(config)
    tesla_client = TeslaClient(config)
    
    print("🌞⚡ Solar Charger Monitor")
    print("=" * 60)
    print("Time                Solar (kW)  Tesla (%)  Status      Action")
    print("-" * 60)
    
    try:
        while True:
            # Get current time
            now = datetime.now().strftime("%H:%M:%S")
            
            # Get solar data
            try:
                solar_data = solar_client.get_power()
                solar_kw = solar_data.get("pv_production_w", 0) / 1000.0  # Convert to kW
                export_kw = solar_data.get("site_export_w", 0)
                if export_kw:
                    export_kw = export_kw / 1000.0
            except Exception as e:
                solar_kw = 0.0
                export_kw = None
            
            # Get Tesla data
            try:
                tesla_data = tesla_client.get_state()
                tesla_soc = tesla_data.get("soc", 0)
                plugged_in = tesla_data.get("plugged_in", False)
                charging_state = tesla_data.get("charging_state", "Unknown")
            except Exception as e:
                tesla_soc = 0
                plugged_in = False
                charging_state = "Error"
            
            # Determine status
            if not plugged_in:
                status = "Unplugged"
                action = "Waiting"
            elif charging_state == "Charging":
                status = "Charging"
                action = "Active"
            elif charging_state in ["Stopped", "Complete"]:
                if solar_kw * 1000 >= config.get("control", {}).get("start_export_watts", 100):
                    status = "Ready"
                    action = "Should Start"
                else:
                    status = "Plugged"
                    action = f"Low Solar ({solar_kw:.3f}kW < {config.get('control', {}).get('start_export_watts', 100)/1000:.1f}kW)"
            else:
                status = charging_state
                action = "Monitoring"
            
            # Format export info
            export_str = f"(+{export_kw:.3f}kW)" if export_kw else ""
            
            # Print status line
            print(f"{now}        {solar_kw:>7.3f}kW {export_str:<12} {tesla_soc:>3d}%     {status:<10} {action}")
            
            # Wait 30 seconds (to stay under SolarEdge API limits)
            time.sleep(30)
            
    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("🛑 Monitoring stopped")


if __name__ == "__main__":
    monitor_system()

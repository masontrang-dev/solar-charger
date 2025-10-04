#!/usr/bin/env python3
"""
View solar charging logs and statistics
"""

import argparse
from datetime import datetime, timedelta
from utils.solar_logger import SolarChargingLogger

def format_duration(hours):
    """Format duration in hours to human readable"""
    if hours < 1:
        minutes = int(hours * 60)
        return f"{minutes}m"
    else:
        h = int(hours)
        m = int((hours - h) * 60)
        return f"{h}h {m}m"

def main():
    parser = argparse.ArgumentParser(description="View Solar Charging Logs")
    parser.add_argument("--totals", action="store_true", help="Show total statistics")
    parser.add_argument("--recent", type=int, default=5, help="Show recent N sessions")
    parser.add_argument("--today", action="store_true", help="Show today's summary")
    parser.add_argument("--date", type=str, help="Show summary for specific date (YYYY-MM-DD)")
    parser.add_argument("--session", type=str, help="Show details for specific session ID")
    args = parser.parse_args()
    
    logger = SolarChargingLogger()
    
    print("🌞⚡ Solar Charging Log Viewer")
    print("=" * 50)
    
    if args.totals:
        print("\n📊 Total Statistics")
        print("-" * 30)
        totals = logger.get_totals()
        
        print(f"Total Solar Energy Captured: {totals['total_solar_energy_kwh']:.2f} kWh")
        print(f"Total Charging Sessions: {totals['total_charging_sessions']}")
        print(f"Total Charging Time: {format_duration(totals['total_charging_time_hours'])}")
        print(f"Average Solar Power: {totals['average_solar_power_kw']:.2f} kW")
        
        if totals['total_solar_energy_kwh'] > 0:
            # Estimate cost savings (assuming $0.30/kWh grid rate)
            cost_savings = totals['total_solar_energy_kwh'] * 0.30
            print(f"Estimated Cost Savings: ${cost_savings:.2f}")
    
    if args.today or args.date:
        date_str = args.date if args.date else None
        print(f"\n📅 Daily Summary: {date_str or 'Today'}")
        print("-" * 30)
        
        summary = logger.get_daily_summary(date_str)
        
        if summary['sessions'] == 0:
            print("No charging sessions found for this date")
        else:
            print(f"Charging Sessions: {summary['sessions']}")
            print(f"Total Solar Energy: {summary['total_solar_kwh']:.2f} kWh")
            print(f"Total Duration: {format_duration(summary['total_duration_hours'])}")
            print(f"Total SOC Gained: {summary['total_soc_gained']}%")
            print(f"Average Power: {summary['average_power_kw']:.2f} kW")
    
    if args.recent > 0:
        print(f"\n📋 Recent {args.recent} Sessions")
        print("-" * 30)
        
        sessions = logger.get_recent_sessions(args.recent)
        
        if not sessions:
            print("No charging sessions found")
        else:
            for session in sessions:
                start_time = datetime.fromisoformat(session['start_time'])
                duration = format_duration(session.get('duration_hours', 0))
                tesla_kwh = session.get('total_tesla_energy_wh', 0) / 1000.0
                solar_to_tesla_kwh = session.get('total_solar_to_tesla_wh', 0) / 1000.0
                grid_kwh = session.get('total_grid_energy_wh', 0) / 1000.0
                soc_gained = session.get('soc_gained', 0)
                avg_power = session.get('average_solar_power_w', 0) / 1000.0
                
                # Calculate solar percentage
                solar_percentage = (solar_to_tesla_kwh / tesla_kwh * 100) if tesla_kwh > 0 else 0
                
                print(f"\n🔋 Session: {session['session_id']}")
                print(f"   Date: {start_time.strftime('%Y-%m-%d %H:%M')}")
                print(f"   Duration: {duration}")
                print(f"   Tesla Used: {tesla_kwh:.2f} kWh")
                print(f"   Solar: {solar_to_tesla_kwh:.2f} kWh ({solar_percentage:.1f}%)")
                print(f"   Grid: {grid_kwh:.2f} kWh ({100-solar_percentage:.1f}%)")
                print(f"   SOC Gained: {soc_gained}%")
    
    if args.session:
        print(f"\n🔍 Session Details: {args.session}")
        print("-" * 30)
        
        # Load all sessions and find the specific one
        import json
        from pathlib import Path
        
        log_file = Path("solar_charging_log.json")
        if log_file.exists():
            with open(log_file, 'r') as f:
                log_data = json.load(f)
            
            session = None
            for s in log_data['sessions']:
                if s['session_id'] == args.session:
                    session = s
                    break
            
            if session:
                start_time = datetime.fromisoformat(session['start_time'])
                end_time = datetime.fromisoformat(session['end_time'])
                duration = format_duration(session.get('duration_hours', 0))
                solar_kwh = session.get('total_solar_energy_wh', 0) / 1000.0
                
                print(f"Session ID: {session['session_id']}")
                print(f"Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"End Time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"Duration: {duration}")
                print(f"Start SOC: {session['start_soc']}%")
                print(f"End SOC: {session['end_soc']}%")
                print(f"SOC Gained: {session['soc_gained']}%")
                print(f"Solar Energy: {solar_kwh:.2f} kWh")
                print(f"Average Solar Power: {session['average_solar_power_w']/1000:.2f} kW")
                print(f"Samples Collected: {len(session.get('energy_samples', []))}")
            else:
                print(f"Session {args.session} not found")
        else:
            print("No log file found")

if __name__ == "__main__":
    main()

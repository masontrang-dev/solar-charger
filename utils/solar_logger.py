#!/usr/bin/env python3
"""
Solar charging logger - tracks energy captured from solar to Tesla
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

class SolarChargingLogger:
    """Logs solar charging sessions and calculates total energy captured"""
    
    def __init__(self, log_file: str = "solar_charging_log.json"):
        self.log_file = Path(log_file)
        self.logger = logging.getLogger("solar_logger")
        self.current_session: Optional[Dict] = None
        
        # Ensure log file exists
        if not self.log_file.exists():
            self._initialize_log_file()
    
    def _initialize_log_file(self):
        """Initialize the log file with empty structure"""
        initial_data = {
            "sessions": [],
            "totals": {
                "total_solar_energy_kwh": 0.0,
                "total_charging_sessions": 0,
                "total_charging_time_hours": 0.0,
                "average_solar_power_kw": 0.0
            },
            "created": datetime.now().isoformat()
        }
        
        with open(self.log_file, 'w') as f:
            json.dump(initial_data, f, indent=2)
        
        self.logger.info(f"Initialized solar charging log: {self.log_file}")
    
    def _load_log_data(self) -> Dict:
        """Load existing log data"""
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading log data: {e}")
            self._initialize_log_file()
            return self._load_log_data()
    
    def _save_log_data(self, data: Dict):
        """Save log data to file"""
        try:
            with open(self.log_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving log data: {e}")
    
    def start_charging_session(self, solar_power_w: float, tesla_soc: int, tesla_power_w: float = 0):
        """Start a new charging session"""
        if self.current_session:
            self.logger.warning("Starting new session while one is active - ending previous session")
            self.end_charging_session(solar_power_w, tesla_soc, tesla_power_w)
        
        self.current_session = {
            "session_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "start_time": datetime.now().isoformat(),
            "start_soc": tesla_soc,
            "start_solar_power_w": solar_power_w,
            "start_tesla_power_w": tesla_power_w,
            "energy_samples": [],
            "total_solar_energy_wh": 0.0,
            "total_tesla_energy_wh": 0.0,
            "average_solar_power_w": 0.0,
            "average_tesla_power_w": 0.0,
            "duration_seconds": 0
        }
        
        self.logger.info(f"Started charging session {self.current_session['session_id']} - SOC: {tesla_soc}%, Solar: {solar_power_w/1000:.2f}kW")
    
    def log_charging_sample(self, solar_power_w: float, tesla_soc: int, tesla_power_w: float = 0, interval_seconds: int = 10):
        """Log a sample during charging (called every 10 seconds or so)"""
        if not self.current_session:
            self.logger.warning("No active charging session - starting new one")
            self.start_charging_session(solar_power_w, tesla_soc, tesla_power_w)
            return
        
        # Calculate energy for this interval (Wh = W * hours)
        interval_hours = interval_seconds / 3600.0
        solar_energy_wh = solar_power_w * interval_hours
        tesla_energy_wh = tesla_power_w * interval_hours
        
        # Calculate actual solar contribution to Tesla (limited by Tesla consumption)
        solar_to_tesla_wh = min(solar_energy_wh, tesla_energy_wh)
        grid_energy_wh = max(0, tesla_energy_wh - solar_energy_wh)
        excess_solar_wh = max(0, solar_energy_wh - tesla_energy_wh)
        
        # Add sample
        sample = {
            "timestamp": datetime.now().isoformat(),
            "solar_power_w": solar_power_w,
            "tesla_power_w": tesla_power_w,
            "tesla_soc": tesla_soc,
            "solar_energy_wh": solar_energy_wh,
            "tesla_energy_wh": tesla_energy_wh,
            "solar_to_tesla_wh": solar_to_tesla_wh,  # Actual solar used by Tesla
            "grid_energy_wh": grid_energy_wh,        # Grid energy used by Tesla
            "excess_solar_wh": excess_solar_wh,      # Unused solar (exported to grid)
            "interval_seconds": interval_seconds
        }
        
        self.current_session["energy_samples"].append(sample)
        self.current_session["total_solar_energy_wh"] += solar_energy_wh
        self.current_session["total_tesla_energy_wh"] += tesla_energy_wh
        
        # Track actual solar contribution and grid usage
        if "total_solar_to_tesla_wh" not in self.current_session:
            self.current_session["total_solar_to_tesla_wh"] = 0
            self.current_session["total_grid_energy_wh"] = 0
            self.current_session["total_excess_solar_wh"] = 0
        
        self.current_session["total_solar_to_tesla_wh"] += solar_to_tesla_wh
        self.current_session["total_grid_energy_wh"] += grid_energy_wh
        self.current_session["total_excess_solar_wh"] += excess_solar_wh
        self.current_session["duration_seconds"] += interval_seconds
        
        # Update averages
        num_samples = len(self.current_session["energy_samples"])
        total_solar = sum(s["solar_power_w"] for s in self.current_session["energy_samples"])
        total_tesla = sum(s["tesla_power_w"] for s in self.current_session["energy_samples"])
        
        self.current_session["average_solar_power_w"] = total_solar / num_samples
        self.current_session["average_tesla_power_w"] = total_tesla / num_samples
        
        self.logger.debug(f"Logged sample - Solar: {solar_power_w/1000:.2f}kW, Tesla: {tesla_power_w/1000:.2f}kW, SOC: {tesla_soc}%")
    
    def end_charging_session(self, solar_power_w: float, tesla_soc: int, tesla_power_w: float = 0):
        """End the current charging session"""
        if not self.current_session:
            self.logger.warning("No active charging session to end")
            return
        
        # Finalize session
        self.current_session["end_time"] = datetime.now().isoformat()
        self.current_session["end_soc"] = tesla_soc
        self.current_session["end_solar_power_w"] = solar_power_w
        self.current_session["end_tesla_power_w"] = tesla_power_w
        self.current_session["soc_gained"] = tesla_soc - self.current_session["start_soc"]
        self.current_session["duration_hours"] = self.current_session["duration_seconds"] / 3600.0
        
        # Load existing data and add this session
        log_data = self._load_log_data()
        log_data["sessions"].append(self.current_session)
        
        # Update totals
        log_data["totals"]["total_solar_energy_kwh"] += self.current_session["total_solar_energy_wh"] / 1000.0
        log_data["totals"]["total_charging_sessions"] += 1
        log_data["totals"]["total_charging_time_hours"] += self.current_session["duration_hours"]
        
        # Calculate overall average
        if log_data["totals"]["total_charging_time_hours"] > 0:
            log_data["totals"]["average_solar_power_kw"] = (
                log_data["totals"]["total_solar_energy_kwh"] / 
                log_data["totals"]["total_charging_time_hours"]
            )
        
        # Save updated data
        self._save_log_data(log_data)
        
        # Log summary with breakdown
        solar_kwh = self.current_session["total_solar_energy_wh"] / 1000.0
        tesla_kwh = self.current_session["total_tesla_energy_wh"] / 1000.0
        solar_to_tesla_kwh = self.current_session.get("total_solar_to_tesla_wh", 0) / 1000.0
        grid_kwh = self.current_session.get("total_grid_energy_wh", 0) / 1000.0
        excess_solar_kwh = self.current_session.get("total_excess_solar_wh", 0) / 1000.0
        duration_hours = self.current_session["duration_hours"]
        soc_gained = self.current_session["soc_gained"]
        
        # Calculate solar percentage
        solar_percentage = (solar_to_tesla_kwh / tesla_kwh * 100) if tesla_kwh > 0 else 0
        
        self.logger.info(f"Ended charging session {self.current_session['session_id']}")
        self.logger.info(f"  Duration: {duration_hours:.2f} hours")
        self.logger.info(f"  Tesla consumed: {tesla_kwh:.2f} kWh")
        self.logger.info(f"  Solar contributed: {solar_to_tesla_kwh:.2f} kWh ({solar_percentage:.1f}%)")
        self.logger.info(f"  Grid contributed: {grid_kwh:.2f} kWh ({100-solar_percentage:.1f}%)")
        if excess_solar_kwh > 0:
            self.logger.info(f"  Excess solar (exported): {excess_solar_kwh:.2f} kWh")
        self.logger.info(f"  SOC gained: {soc_gained}%")
        self.logger.info(f"  Average solar power: {self.current_session['average_solar_power_w']/1000:.2f} kW")
        
        # Clear current session
        self.current_session = None
    
    def get_totals(self) -> Dict:
        """Get total statistics"""
        log_data = self._load_log_data()
        return log_data["totals"]
    
    def get_recent_sessions(self, count: int = 10) -> list:
        """Get recent charging sessions"""
        log_data = self._load_log_data()
        return log_data["sessions"][-count:]
    
    def get_daily_summary(self, date_str: str = None) -> Dict:
        """Get summary for a specific day (YYYY-MM-DD format)"""
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        
        log_data = self._load_log_data()
        daily_sessions = []
        
        for session in log_data["sessions"]:
            session_date = session["start_time"][:10]  # Extract YYYY-MM-DD
            if session_date == date_str:
                daily_sessions.append(session)
        
        if not daily_sessions:
            return {
                "date": date_str,
                "sessions": 0,
                "total_solar_kwh": 0.0,
                "total_duration_hours": 0.0,
                "total_soc_gained": 0
            }
        
        total_solar_kwh = sum(s["total_solar_energy_wh"] / 1000.0 for s in daily_sessions)
        total_duration = sum(s["duration_hours"] for s in daily_sessions)
        total_soc_gained = sum(s["soc_gained"] for s in daily_sessions)
        
        return {
            "date": date_str,
            "sessions": len(daily_sessions),
            "total_solar_kwh": total_solar_kwh,
            "total_duration_hours": total_duration,
            "total_soc_gained": total_soc_gained,
            "average_power_kw": total_solar_kwh / total_duration if total_duration > 0 else 0
        }

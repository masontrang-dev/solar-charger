import argparse
import logging
import signal
import sys
import threading
import time
import yaml
import requests
import urllib3

from scheduler import Scheduler
from utils.logging_config import configure_logging
from utils.token_manager import TeslaTokenManager

# Disable SSL warnings for Tesla HTTP proxy
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def load_config(path: str) -> dict:
    with open(path, 'r') as f:
        return yaml.safe_load(f)


def should_wake_tesla(config: dict, logger: logging.Logger, force_wake: bool = False) -> bool:
    """Determine if we should wake Tesla based on solar conditions"""
    
    if force_wake:
        logger.info("🔧 Force wake enabled - will wake Tesla regardless of solar conditions")
        return True
    
    try:
        # Get current solar production to decide if we should wake the vehicle
        from clients.solaredge_cloud import SolarEdgeCloudClient
        
        solar_client = SolarEdgeCloudClient(config)
        solar_data = solar_client.get_production()
        
        current_production_w = solar_data.get('pv_production_w', 0)
        current_production_kw = current_production_w / 1000
        
        # Get charging thresholds from config
        start_threshold_kw = config.get('charging', {}).get('start_threshold_kw', 1.8)
        
        logger.info(f"Current solar production: {current_production_kw:.2f}kW")
        logger.info(f"Start charging threshold: {start_threshold_kw}kW")
        
        # Only wake if we have enough solar to potentially start charging
        # Add a small buffer (0.1kW) to account for fluctuations
        wake_threshold = start_threshold_kw - 0.1
        
        if current_production_kw >= wake_threshold:
            logger.info(f"☀️ Solar production ({current_production_kw:.2f}kW) is near charging threshold - will wake Tesla")
            return True
        else:
            logger.info(f"🌤️ Solar production ({current_production_kw:.2f}kW) is too low - keeping Tesla asleep to save energy")
            return False
            
    except Exception as e:
        logger.warning(f"Could not check solar production: {e}")
        logger.info("Defaulting to wake Tesla for safety")
        return True


def wake_tesla_if_needed(config: dict, logger: logging.Logger, force_wake: bool = False) -> bool:
    """Wake up Tesla vehicle if it's sleeping and conditions warrant it"""
    
    try:
        tesla_config = config.get('tesla', {}).get('api', {})
        access_token = tesla_config.get('access_token')
        vin = config.get('tesla', {}).get('vehicle_vin')
        
        if not access_token or not vin:
            logger.warning("Tesla configuration incomplete - skipping wake check")
            return True
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Get vehicle list to check state
        logger.info("Checking Tesla vehicle state...")
        vehicles_url = "https://localhost:8080/api/1/vehicles"
        
        response = requests.get(vehicles_url, headers=headers, verify=False, timeout=10)
        
        if response.status_code != 200:
            logger.warning(f"Failed to get vehicle list: {response.status_code}")
            return True  # Continue anyway
        
        data = response.json()
        vehicles = data.get('response', [])
        
        # Find our vehicle
        vehicle_id = None
        current_state = None
        
        for vehicle in vehicles:
            if vehicle.get('vin') == vin:
                vehicle_id = vehicle.get('id')
                current_state = vehicle.get('state')
                logger.info(f"Found Tesla vehicle - State: {current_state}")
                break
        
        if not vehicle_id:
            logger.warning(f"Vehicle with VIN {vin} not found")
            return True  # Continue anyway
        
        # Wake up if sleeping AND solar conditions warrant it
        if current_state in ['asleep', 'offline']:
            # Check if we should wake based on solar production
            if not should_wake_tesla(config, logger, force_wake):
                logger.info(f"Vehicle is {current_state} but solar is too low - leaving asleep")
                return True
            
            logger.info(f"Vehicle is {current_state} - sending wake up command...")
            
            wake_url = f"https://localhost:8080/api/1/vehicles/{vehicle_id}/wake_up"
            
            response = requests.post(wake_url, headers=headers, verify=False, timeout=30)
            
            if response.status_code == 200:
                logger.info("Wake up command sent successfully")
                
                # Wait for vehicle to wake up (max 2 minutes)
                logger.info("Waiting for vehicle to wake up...")
                
                for attempt in range(12):  # 12 attempts * 10 seconds = 2 minutes
                    time.sleep(10)
                    
                    # Check state again
                    response = requests.get(vehicles_url, headers=headers, verify=False, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        vehicles = data.get('response', [])
                        
                        for vehicle in vehicles:
                            if vehicle.get('id') == vehicle_id:
                                state = vehicle.get('state')
                                logger.info(f"Wake attempt {attempt + 1}/12 - State: {state}")
                                
                                if state == 'online':
                                    logger.info("✅ Tesla vehicle is now ONLINE and ready!")
                                    return True
                                break
                
                logger.warning("Vehicle is taking longer than expected to wake up")
                logger.info("Continuing with solar charger - vehicle may wake up during operation")
                
            else:
                logger.warning(f"Wake up command failed: {response.status_code}")
                
        else:
            logger.info(f"✅ Tesla vehicle is already {current_state}")
        
        return True
        
    except Exception as e:
        logger.warning(f"Tesla wake check failed: {e}")
        logger.info("Continuing with solar charger anyway")
        return True


def main():
    parser = argparse.ArgumentParser(description="Solar Charger Controller")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Override config to dry-run")
    parser.add_argument("--verbose", action="store_true", help="Set log level to DEBUG")
    parser.add_argument("--force-wake", action="store_true", help="Force wake Tesla regardless of solar conditions")
    args = parser.parse_args()

    config = load_config(args.config)

    # CLI overrides
    if args.dry_run:
        config["dry_run"] = True
    if args.verbose:
        config["logging"] = config.get("logging", {})
        config["logging"]["level"] = "DEBUG"

    configure_logging(config)
    logger = logging.getLogger("run")

    # Ensure Tesla tokens are valid before starting
    logger.info("🔑 Checking Tesla token validity...")
    token_manager = TeslaTokenManager(args.config)
    if not token_manager.ensure_valid_token():
        logger.error("Failed to ensure valid Tesla tokens")
        sys.exit(1)

    # Wake up Tesla if needed before starting
    logger.info("🚗 Checking Tesla vehicle status...")
    wake_tesla_if_needed(config, logger, args.force_wake)

    stop_event = threading.Event()

    def handle_sig(sig, frame):
        logger.info("Shutdown signal received. Stopping...")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    scheduler = Scheduler(config)

    try:
        scheduler.run(stop_event)
    except Exception:
        logger.exception("Fatal error in scheduler")
        sys.exit(1)


if __name__ == "__main__":
    main()

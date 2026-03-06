#!/usr/bin/env python3
"""
Simple web dashboard for Solar Charger system
"""

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import yaml
import threading
import time
from datetime import datetime
from clients.tesla import TeslaClient
from clients.solaredge_cloud import SolarEdgeCloudClient
from clients.tesla_hpwc import TeslaHPWCClient
from utils.solar_logger import SolarChargingLogger
app = Flask(__name__)
app.config['SECRET_KEY'] = 'solar-charger-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

system_data = {
    'solar': {'pv_production_w': 0},
    'tesla': {'soc': 0, 'charge_state': 'Unknown', 'plugged_in': False},
    'system': {'status': 'Starting', 'last_action': 'None', 'dry_run': True, 'start_threshold_w': 1800, 'stop_threshold_w': 1500},
    'hpwc': {'enabled': False},
    'logs': []
}

startup_poll_done = False
last_tesla_poll = 0
last_tesla_data = {}
last_charging_power = 0
battery_capacity_kwh = 75
daily_call_count = 0
last_call_reset = time.time()

# Max calls will be loaded from config
max_daily_calls = 50  # Default, will be updated from config

config = {}
clients = {}
solar_logger = None

def load_config():
    """Load configuration from file"""
    global config, clients, solar_logger, max_daily_calls
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        # Load max daily calls from config
        max_daily_calls = config.get('polling', {}).get('tesla_max_calls_per_day', 50)
        
        clients['tesla'] = TeslaClient(config)
        clients['solar'] = SolarEdgeCloudClient(config)
        clients['hpwc'] = TeslaHPWCClient(config)
        solar_logger = SolarChargingLogger()
        
        return True
    except Exception as e:
        add_log(f"Error loading config: {e}", "error")
        return False

def can_poll_tesla() -> bool:
    """Smart Tesla polling with adaptive intervals based on charging state"""
    global startup_poll_done, last_tesla_poll, daily_call_count, last_call_reset
    
    now = time.time()
    time_since_last_poll = now - last_tesla_poll
    
    if not startup_poll_done:
        add_log("Web dashboard startup Tesla poll - initializing system data", "info")
        return True
    
    if now - last_call_reset > 86400:
        daily_call_count = 0
        last_call_reset = now
        add_log("Daily Tesla API call counter reset", "info")
    
    if daily_call_count >= max_daily_calls:
        add_log(f"Daily Tesla API limit reached ({daily_call_count}/{max_daily_calls})", "warning")
        return False
    
    # Get adaptive intervals from config
    polling_config = config.get('polling', {})
    charging_interval = polling_config.get('tesla_charging_interval', 60)
    idle_interval = polling_config.get('tesla_idle_interval', 300)
    
    # Determine appropriate interval based on charging state
    is_charging = last_charging_power > 0
    min_interval = charging_interval if is_charging else idle_interval
    
    if time_since_last_poll < min_interval:
        state = "charging" if is_charging else "idle"
        add_log(f"Tesla poll skipped - too soon ({time_since_last_poll:.0f}s < {min_interval}s for {state})", "debug")
        return False
    
    # If we've waited long enough, allow polling
    return True

def add_log(message, level="info"):
    """Add log entry"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = {
        'timestamp': timestamp,
        'message': message,
        'level': level
    }
    system_data['logs'].insert(0, log_entry)
    if len(system_data['logs']) > 50:  # Keep last 50 logs
        system_data['logs'] = system_data['logs'][:50]

def update_system_data():
    """Update system data from clients"""
    global startup_poll_done, last_tesla_poll, last_tesla_data, last_charging_power, daily_call_count
    try:
        system_data['system']['status'] = 'Running'
        system_data['system']['dry_run'] = config.get('dry_run', True)
        
        # Get control thresholds from config
        ctrl = config.get('control', {})
        system_data['system']['start_threshold_w'] = ctrl.get('start_export_watts', 1800)
        system_data['system']['stop_threshold_w'] = ctrl.get('stop_export_watts', 1500)
        
        if 'solar' in clients:
            try:
                solar_data = clients['solar'].get_power()
                
                # Add freshness metadata
                solar_data['last_updated'] = time.time()
                solar_data['cached'] = hasattr(clients['solar'], '_cache') and bool(clients['solar']._cache)
                
                if solar_data.get('pv_production_w', 0) > 0 or solar_data.get('site_export_w') is not None:
                    solar_data['connection_status'] = 'connected'
                    add_log(f"Solar data: {solar_data.get('pv_production_w', 0)/1000:.2f}kW production", "debug")
                else:
                    if hasattr(clients['solar'], 'last_error_message') and clients['solar'].last_error_message:
                        solar_data['connection_status'] = 'error'
                        solar_data['error_message'] = clients['solar'].last_error_message
                        add_log(f"SolarEdge error: {clients['solar'].last_error_message}", "warning")
                    else:
                        solar_data['connection_status'] = 'connected'
                        add_log("Solar data: 0.00kW production (nighttime or no generation)", "debug")
                
                system_data['solar'] = solar_data
                
            except Exception as e:
                add_log(f"Solar client error: {e}", "error")
                system_data['solar'] = {
                    'pv_production_w': 0,
                    'connection_status': 'error',
                    'error_message': str(e)
                }
        
        if 'tesla' in clients:
            try:
                dev_mode = config.get('dev_mode', False)
                solar_kw = system_data['solar'].get('pv_production_w', 0) / 1000.0
                start_threshold_kw = system_data['system'].get('start_threshold_w', 1800) / 1000.0
                wake_threshold_percent = config.get("tesla", {}).get("wake_threshold_percent", 0.95)
                wake_threshold_kw = start_threshold_kw * wake_threshold_percent
                
                last_charging_state = system_data['tesla'].get('charging_state', 'Unknown')
                might_be_charging = last_charging_state in ['Charging', 'Starting']
                
                should_poll_tesla_solar = (
                    dev_mode or
                    solar_kw >= wake_threshold_kw or
                    might_be_charging
                )
                
                should_poll_tesla = (should_poll_tesla_solar and can_poll_tesla()) or not startup_poll_done
                
                if should_poll_tesla:
                    if not startup_poll_done:
                        reason = "startup initialization"
                    elif dev_mode:
                        reason = "dev mode enabled"
                    elif might_be_charging:
                        reason = "might be charging"
                    else:
                        reason = "solar sufficient"
                    
                    add_log(f"🚗 Polling Tesla API ({reason}) - Call #{daily_call_count + 1}/{max_daily_calls} - This may take ~2 minutes...", "info")
                    
                    try:
                        tesla_data = clients['tesla'].get_state(wake_if_needed=True)
                        system_data['tesla'] = tesla_data
                        add_log(f"✅ Tesla data received: SOC {tesla_data.get('soc', 0)}%, State: {tesla_data.get('charging_state', 'Unknown')}, Plugged: {tesla_data.get('plugged_in', False)}", "info")
                        
                        last_tesla_poll = time.time()
                        last_tesla_data = tesla_data
                        last_charging_power = tesla_data.get('charger_power', 0) * 1000
                        daily_call_count += 1
                        startup_poll_done = True
                        
                    except Exception as e:
                        add_log(f"❌ Tesla polling failed: {e}", "error")
                        startup_poll_done = True
                        # Use cached data if available
                        if last_tesla_data:
                            system_data['tesla'] = last_tesla_data
                            add_log("Using cached Tesla data after error", "debug")
                        
                elif last_tesla_data:
                    # Use cached Tesla data - don't poll yet
                    system_data['tesla'] = last_tesla_data.copy()
                    system_data['tesla']['last_updated'] = last_tesla_poll
                    system_data['tesla']['cached'] = True
                    system_data['tesla']['age_seconds'] = int(time.time() - last_tesla_poll)
                    add_log(f"📋 Using cached Tesla data (last poll: {int(time.time() - last_tesla_poll)}s ago)", "debug")
                else:
                    # No cached data and can't poll
                    if should_poll_tesla_solar:
                        add_log("⏳ Waiting to poll Tesla (rate limited)", "debug")
                        system_data['tesla'] = {'soc': 0, 'charging_state': 'Unknown', 'plugged_in': False}
                    else:
                        add_log(f"😴 Solar too low ({solar_kw:.2f}kW < {wake_threshold_kw:.2f}kW) - Tesla likely sleeping", "debug")
                        system_data['tesla'] = {'soc': 0, 'charging_state': 'Sleeping', 'plugged_in': False}
                    
            except Exception as e:
                add_log(f"Tesla client error: {e}", "error")
                system_data['tesla'] = {'soc': 0, 'charging_state': 'Error', 'plugged_in': False}
        
        # Get HPWC data if available
        if 'hpwc' in clients:
            try:
                # Fetch fresh data from HPWC
                clients['hpwc'].get_vitals()
                # Get status summary (uses cached data from get_vitals)
                hpwc_status = clients['hpwc'].get_status_summary()
                system_data['hpwc'] = hpwc_status
                if hpwc_status.get('available'):
                    add_log(f"HPWC: connected={hpwc_status.get('vehicle_connected')}, current={hpwc_status.get('vehicle_current_a')}A", "debug")
            except Exception as e:
                add_log(f"HPWC client error: {e}", "error")
                system_data['hpwc'] = {"enabled": False, "error": str(e)}
        
    except Exception as e:
        add_log(f"Error updating data: {e}", "error")
        system_data['system']['status'] = 'Error'

def data_update_thread():
    """Background thread to update data"""
    # Get dashboard update interval from config
    poll_interval = config.get('polling', {}).get('dashboard_interval', 10)
    add_log(f"Dashboard update interval: {poll_interval}s", "info")
    
    # Track previous values to detect changes
    last_charge_amps = None
    last_charging_state = None
    last_charger_power = None
    
    while True:
        if clients:
            add_log(f"🔄 Update cycle starting (interval: {poll_interval}s)", "debug")
            update_system_data()
            # Include poll interval in system data for frontend countdown
            system_data['system']['poll_interval'] = poll_interval
            
            # Check for important changes that warrant immediate update
            current_charge_amps = system_data.get('tesla', {}).get('charge_current_request')
            current_charging_state = system_data.get('tesla', {}).get('charging_state')
            current_charger_power = system_data.get('tesla', {}).get('charger_power')
            
            # Detect if amperage changed (controller adjusted it)
            amps_changed = (last_charge_amps is not None and 
                          current_charge_amps is not None and 
                          last_charge_amps != current_charge_amps)
            
            # Detect if charging state changed
            state_changed = (last_charging_state is not None and 
                           current_charging_state is not None and 
                           last_charging_state != current_charging_state)
            
            # Detect significant power change (>0.5kW)
            power_changed = (last_charger_power is not None and 
                           current_charger_power is not None and 
                           abs(last_charger_power - current_charger_power) > 0.5)
            
            if amps_changed:
                add_log(f"⚡ Amperage changed: {last_charge_amps}A → {current_charge_amps}A - pushing update", "info")
            if state_changed:
                add_log(f"🔄 Charging state changed: {last_charging_state} → {current_charging_state} - pushing update", "info")
            
            # Always emit update
            solar_w = system_data.get('solar', {}).get('pv_production_w', 0)
            timestamp = datetime.now().strftime("%H:%M:%S")
            add_log(f"📤 [{timestamp}] Pushing update to frontend: {solar_w}W ({solar_w/1000:.2f}kW), {current_charge_amps}A", "info")
            socketio.emit('data_update', system_data)
            
            # Update tracked values
            last_charge_amps = current_charge_amps
            last_charging_state = current_charging_state
            last_charger_power = current_charger_power
        else:
            add_log("⚠️ No clients initialized - skipping update", "warning")
            
        time.sleep(poll_interval)

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/data')
def get_data():
    return jsonify(system_data)

@app.route('/api/tesla/refresh', methods=['POST'])
def refresh_tesla_data():
    """Force a refresh of Tesla data"""
    try:
        global last_tesla_poll, daily_call_count
        
        # Check if we can make an API call
        if daily_call_count >= max_daily_calls:
            add_log("Cannot refresh Tesla data: Daily API call limit reached", "warning")
            return jsonify({
                'success': False,
                'message': 'Daily API call limit reached'
            })
            
        # Force a Tesla data refresh
        add_log("Manually refreshing Tesla data...", "info")
        tesla_data = clients['tesla'].get_state(wake_if_needed=True)
        system_data['tesla'] = tesla_data
        last_tesla_poll = time.time()
        daily_call_count += 1
        
        # Update all connected clients
        socketio.emit('data_update', system_data)
        
        return jsonify({
            'success': True,
            'message': 'Tesla data refreshed successfully',
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        error_msg = f"Error refreshing Tesla data: {str(e)}"
        add_log(error_msg, "error")
        return jsonify({
            'success': False,
            'message': error_msg
        }), 500

@app.route('/api/control/<action>')
def control_action(action):
    """Manual control actions"""
    try:
        if action == 'start_charging':
            # Check current state first
            current_state = system_data['tesla'].get('charging_state', 'Unknown')
            if current_state in ['Charging', 'Starting']:
                message = f"Already charging (state: {current_state})"
                level = "info"
                success = True
            else:
                success = clients['tesla'].start_charging()
                message = "Charging started" if success else "Failed to start charging"
                level = "success" if success else "error"
                
                # Immediately refresh Tesla data after command
                if success:
                    try:
                        # Wait a moment for vehicle to process command
                        time.sleep(3)
                        add_log("Refreshing Tesla data after start command...", "debug")
                        tesla_data = clients['tesla'].get_state(wake_if_needed=True)
                        system_data['tesla'] = tesla_data
                        add_log(f"Updated Tesla state: {tesla_data.get('charging_state', 'Unknown')}, SOC: {tesla_data.get('soc', 0)}%", "info")
                        
                        # Start solar logging session
                        if solar_logger and tesla_data.get('charging_state') in ['Charging', 'Starting']:
                            solar_power_w = system_data['solar'].get('pv_production_w', 0)
                            tesla_soc = tesla_data.get('soc', 0)
                            tesla_power_w = tesla_data.get('charger_power', 0) * 1000  # Convert kW to W
                            solar_logger.start_charging_session(solar_power_w, tesla_soc, tesla_power_w)
                            add_log(f"Started solar logging session: {solar_power_w/1000:.2f}kW solar, {tesla_soc}% SOC", "info")
                        
                        # Push updated data to all connected clients immediately
                        socketio.emit('data_update', system_data)
                    except Exception as e:
                        add_log(f"Failed to refresh Tesla data: {e}", "error")
            
        elif action == 'stop_charging':
            # Check current state first
            current_state = system_data['tesla'].get('charging_state', 'Unknown')
            if current_state in ['Stopped', 'Complete', 'Disconnected']:
                message = f"Already stopped (state: {current_state})"
                level = "info"
                success = True
            else:
                success = clients['tesla'].stop_charging()
                message = "Charging stopped" if success else "Failed to stop charging"
                level = "success" if success else "error"
                
                # Immediately refresh Tesla data after command
                if success:
                    try:
                        # Wait a moment for vehicle to process command
                        time.sleep(3)
                        add_log("Refreshing Tesla data after stop command...", "debug")
                        tesla_data = clients['tesla'].get_state(wake_if_needed=True)
                        system_data['tesla'] = tesla_data
                        add_log(f"Updated Tesla state: {tesla_data.get('charging_state', 'Unknown')}, SOC: {tesla_data.get('soc', 0)}%", "info")
                        
                        # End solar logging session
                        if solar_logger:
                            solar_power_w = system_data['solar'].get('pv_production_w', 0)
                            tesla_soc = tesla_data.get('soc', 0)
                            tesla_power_w = tesla_data.get('charger_power', 0) * 1000  # Convert kW to W
                            solar_logger.end_charging_session(solar_power_w, tesla_soc, tesla_power_w)
                            add_log(f"Ended solar logging session: {tesla_soc}% SOC", "info")
                        
                        # Push updated data to all connected clients immediately
                        socketio.emit('data_update', system_data)
                    except Exception as e:
                        add_log(f"Failed to refresh Tesla data: {e}", "error")
            
        elif action == 'set_amps':
            amps = request.args.get('amps', type=int)
            if not amps or amps < 5 or amps > 48:
                message = "Invalid amperage (must be 5-48A)"
                level = "error"
                success = False
            else:
                # Check if amperage is already at target to avoid unnecessary calls
                current_amps = system_data['tesla'].get('charge_current_request', 0)
                if current_amps == amps:
                    message = f"Already charging at {amps}A"
                    level = "info"
                    success = True
                    add_log(f"Skipped amperage change - already at {amps}A", "debug")
                else:
                    success = clients['tesla'].set_charging_amps(amps)
                    message = f"Set charging to {amps}A" if success else f"Failed to set charging to {amps}A"
                    level = "success" if success else "error"
                
                # Immediately refresh Tesla data after command
                if success:
                    try:
                        # Wait a moment for vehicle to process command
                        time.sleep(2)
                        add_log(f"Refreshing Tesla data after setting {amps}A...", "debug")
                        tesla_data = clients['tesla'].get_state(wake_if_needed=True)
                        system_data['tesla'] = tesla_data
                        add_log(f"Updated Tesla charging current: {tesla_data.get('charge_current_request', 0)}A", "info")
                        # Push updated data to all connected clients immediately
                        socketio.emit('data_update', system_data)
                    except Exception as e:
                        add_log(f"Failed to refresh Tesla data: {e}", "error")
        
        elif action == 'refresh_data':
            update_system_data()
            message = "Data refreshed"
            level = "info"
            success = True
        else:
            message = f"Unknown action: {action}"
            level = "error"
            success = False
        
        add_log(message, level)
        system_data['system']['last_action'] = message
        return jsonify({"success": success, "message": message})
        
    except Exception as e:
        add_log(f"Control action error: {e}", "error")
        return jsonify({"success": False, "message": str(e)})
        
@app.route('/api/stop_charging', methods=['POST'])
def stop_charging():
    """Stop Tesla charging"""
    try:
        if 'tesla' in clients:
            success = clients['tesla'].stop_charging()
            if success:
                add_log("Manual stop charging command sent", "info")
                return jsonify({"success": True, "message": "Stop charging command sent"})
            else:
                add_log("Failed to send stop charging command", "error")
                return jsonify({"success": False, "message": "Failed to send stop charging command"})
        else:
            return jsonify({"success": False, "message": "Tesla client not available"})
    except Exception as e:
        add_log(f"Error stopping charging: {e}", "error")
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/wake_vehicle', methods=['POST'])
def wake_vehicle():
    """Wake up Tesla vehicle"""
    try:
        if 'tesla' in clients:
            success = clients['tesla'].wake_vehicle()
            if success:
                add_log("Vehicle wake command sent successfully", "info")
                
                # Immediately refresh Tesla data after wake command
                try:
                    add_log("Refreshing Tesla data after wake command...", "debug")
                    tesla_data = clients['tesla'].get_state(wake_if_needed=False)  # Don't wake again, just get state
                    system_data['tesla'] = tesla_data
                    add_log(f"Updated Tesla state: {tesla_data.get('charging_state', 'Unknown')}, SOC: {tesla_data.get('soc', 0)}%", "info")
                    # Push updated data to all connected clients immediately
                    socketio.emit('data_update', system_data)
                except Exception as e:
                    add_log(f"Failed to refresh Tesla data after wake: {e}", "error")
                
                return jsonify({"success": True, "message": "Vehicle wake command sent"})
            else:
                add_log("Failed to wake vehicle", "error")
                return jsonify({"success": False, "message": "Failed to wake vehicle"})
        else:
            return jsonify({"success": False, "message": "Tesla client not available"})
    except Exception as e:
        add_log(f"Error waking vehicle: {e}", "error")
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/config')
def get_config():
    """Get current configuration"""
    safe_config = config.copy()
    if 'tesla' in safe_config and 'api' in safe_config['tesla']:
        safe_config['tesla']['api']['access_token'] = "***"
        safe_config['tesla']['api']['client_secret'] = "***"
    if 'solaredge' in safe_config and 'cloud' in safe_config['solaredge']:
        safe_config['solaredge']['cloud']['api_key'] = "***"
    
    return jsonify(safe_config)

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    add_log("Dashboard connected", "info")
    emit('data_update', system_data)

if __name__ == '__main__':
    print("🌞⚡ Solar Charger Web Dashboard")
    print("=" * 40)
    
    # Load configuration
    if load_config():
        add_log("System initialized successfully", "success")
        
        # Start background data update thread
        update_thread = threading.Thread(target=data_update_thread, daemon=True)
        update_thread.start()
        
        print("Dashboard starting at http://localhost:8091")
        socketio.run(app, host='0.0.0.0', port=8091, debug=False)
    else:
        print("❌ Failed to load configuration. Check config.yaml")

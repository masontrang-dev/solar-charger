#!/usr/bin/env python3
"""
Simple web dashboard for Solar Charger system
"""

from flask import Flask, render_template, jsonify, request, redirect, url_for
from flask_socketio import SocketIO, emit
import yaml
import json
import threading
import time
from datetime import datetime
from clients.tesla import TeslaClient
from clients.solaredge_cloud import SolarEdgeCloudClient
from utils.solar_logger import SolarChargingLogger
app = Flask(__name__)
app.config['SECRET_KEY'] = 'solar-charger-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global system data
system_data = {
    'solar': {'pv_production_w': 0},
    'tesla': {'soc': 0, 'charge_state': 'Unknown', 'plugged_in': False},
    'system': {'status': 'Starting', 'last_action': 'None', 'dry_run': True, 'start_threshold_w': 1800, 'stop_threshold_w': 1500},
    'logs': []
}

# Track startup state and API usage
startup_poll_done = False
last_tesla_poll = 0
last_tesla_data = {}
min_tesla_poll_interval = 300  # 5 minutes minimum between polls
last_charging_power = 0
battery_capacity_kwh = 75
max_daily_calls = 50  # Same conservative limit as backend
daily_call_count = 0
last_call_reset = time.time()

config = {}
clients = {}
solar_logger = None

def load_config():
    """Load configuration from file"""
    global config, clients, solar_logger
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        # Initialize clients
        clients['tesla'] = TeslaClient(config)
        clients['solar'] = SolarEdgeCloudClient(config)
        
        # Initialize solar logger
        solar_logger = SolarChargingLogger()
        
        return True
    except Exception as e:
        add_log(f"Error loading config: {e}", "error")
        return False

def can_poll_tesla(force_poll=False) -> bool:
    """Smart Tesla polling to reduce API costs (same logic as backend)"""
    global startup_poll_done, last_tesla_poll, daily_call_count, last_call_reset
    
    now = time.time()
    time_since_last_poll = now - last_tesla_poll
    
    # Always poll on startup to initialize system
    if not startup_poll_done:
        add_log("Web dashboard startup Tesla poll - initializing system data", "info")
        return True
    
    # Reset daily call counter at midnight
    if now - last_call_reset > 86400:  # 24 hours
        daily_call_count = 0
        last_call_reset = now
        add_log("Daily Tesla API call counter reset", "info")
    
    # Check daily call limit
    if daily_call_count >= max_daily_calls:
        add_log(f"Daily Tesla API limit reached ({daily_call_count}/{max_daily_calls})", "warning")
        return False
    
    # Don't poll too frequently (minimum 5 minutes)
    if time_since_last_poll < min_tesla_poll_interval:
        add_log(f"Tesla poll skipped - too soon ({time_since_last_poll:.0f}s < {min_tesla_poll_interval}s)", "debug")
        return False
        
    # If not charging, poll very rarely (every 3 hours)
    if last_charging_power == 0:
        should_poll = time_since_last_poll > 10800  # 3 hours when not charging
        if not should_poll:
            add_log(f"Tesla poll skipped - not charging ({time_since_last_poll:.0f}s < 10800s)", "debug")
        return should_poll
        
    # If charging, calculate expected SOC change
    power_kw = last_charging_power / 1000.0
    time_hours = time_since_last_poll / 3600.0
    expected_soc_change = (power_kw * time_hours) / battery_capacity_kwh * 100
    
    # Poll if we expect SOC to have changed by 2% or more
    should_poll = expected_soc_change >= 2.0
    if not should_poll:
        add_log(f"Tesla poll skipped - SOC change too small ({expected_soc_change:.2f}% < 2%)", "debug")
    return should_poll

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
        # Update system status and thresholds FIRST (use test mode values if enabled)
        system_data['system']['status'] = 'Running'
        system_data['system']['dry_run'] = config.get('dry_run', True)
        
        # Use test mode thresholds if test mode is enabled
        if config.get('test_mode', False):
            test_ctrl = config.get('test_control', {})
            system_data['system']['start_threshold_w'] = test_ctrl.get('start_export_watts', 200)
            system_data['system']['stop_threshold_w'] = test_ctrl.get('stop_export_watts', 150)
        else:
            ctrl = config.get('control', {})
            system_data['system']['start_threshold_w'] = ctrl.get('start_export_watts', 1800)
            system_data['system']['stop_threshold_w'] = ctrl.get('stop_export_watts', 1500)
        
        # Get solar data (use correct method name)
        if 'solar' in clients:
            try:
                # First check if we can connect to SolarEdge
                if not hasattr(clients['solar'], 'last_connection_success') or clients['solar'].last_connection_success is None:
                    # Test connection if we haven't already
                    clients['solar'].test_connection()
                
                if hasattr(clients['solar'], 'last_connection_success') and not clients['solar'].last_connection_success:
                    # Connection failed
                    system_data['solar'] = {
                        'pv_production_w': 0,
                        'connection_status': 'error',
                        'error_message': 'Unable to connect to SolarEdge API'
                    }
                    add_log("SolarEdge connection failed - showing error state in UI", "warning")
                else:
                    # Connection is good, get power data
                    solar_data = clients['solar'].get_power()
                    solar_data['connection_status'] = 'connected'
                    system_data['solar'] = solar_data
            except Exception as e:
                add_log(f"Solar client error: {e}", "error")
                system_data['solar'] = {
                    'pv_production_w': 0,
                    'connection_status': 'error',
                    'error_message': str(e)
                }
        
        # Get Tesla data - poll if solar is high enough OR if Tesla might be charging
        if 'tesla' in clients:
            try:
                # Check if solar is high enough to bother polling Tesla
                solar_kw = system_data['solar'].get('pv_production_w', 0) / 1000.0
                start_threshold_kw = system_data['system'].get('start_threshold_w', 1800) / 1000.0
                wake_threshold_percent = config.get("tesla", {}).get("wake_threshold_percent", 0.95)  # Default 95%
                wake_threshold_kw = start_threshold_kw * wake_threshold_percent
                
                # Check if Tesla might be charging (based on last known state)
                last_charging_state = system_data['tesla'].get('charging_state', 'Unknown')
                might_be_charging = last_charging_state in ['Charging', 'Starting']
                
                # Check if we should poll based on solar conditions
                should_poll_tesla_solar = (
                    solar_kw >= wake_threshold_kw or  # Solar is high enough
                    might_be_charging  # Or Tesla might be charging
                )
                
                # Apply smart polling logic to reduce API costs
                should_poll_tesla = (should_poll_tesla_solar and can_poll_tesla()) or not startup_poll_done
                
                if should_poll_tesla:
                    # Poll Tesla (solar sufficient or might be charging or startup)
                    if not startup_poll_done:
                        reason = "startup initialization"
                    elif might_be_charging:
                        reason = "might be charging"
                    else:
                        reason = "solar sufficient"
                    
                    add_log(f"Polling Tesla ({reason}) - Call #{daily_call_count + 1}/{max_daily_calls}", "debug")
                    
                    try:
                        tesla_data = clients['tesla'].get_state(wake_if_needed=True)
                        system_data['tesla'] = tesla_data
                        add_log(f"Tesla data: SOC {tesla_data.get('soc', 0)}%, State: {tesla_data.get('charging_state', 'Unknown')}", "info")
                        
                        # Update cache and call counter
                        last_tesla_poll = time.time()
                        last_tesla_data = tesla_data
                        last_charging_power = tesla_data.get('charger_power', 0) * 1000  # Convert kW to W
                        daily_call_count += 1
                        startup_poll_done = True  # Mark startup poll as complete
                        
                    except Exception as e:
                        add_log(f"Tesla polling failed: {e}", "error")
                        # Keep default Tesla data on failure
                        startup_poll_done = True  # Still mark as done to avoid infinite retries
                        
                elif should_poll_tesla_solar and last_tesla_data:
                    # Use cached data to avoid API call
                    add_log("Using cached Tesla data to reduce API costs", "debug")
                    system_data['tesla'] = last_tesla_data
                else:
                    # Solar too low and not charging - don't poll Tesla at all (let it sleep)
                    add_log(f"Solar too low ({solar_kw:.2f}kW < {wake_threshold_kw:.2f}kW) and not charging - not polling Tesla", "info")
                    system_data['tesla'] = {'soc': 0, 'charging_state': 'Sleeping', 'plugged_in': False}
                    
            except Exception as e:
                add_log(f"Tesla client error: {e}", "error")
                system_data['tesla'] = {'soc': 0, 'charging_state': 'Error', 'plugged_in': False}
        
    except Exception as e:
        add_log(f"Error updating data: {e}", "error")
        system_data['system']['status'] = 'Error'
        
        # Use test mode thresholds if test mode is enabled
        if config.get('test_mode', False):
            test_ctrl = config.get('test_control', {})
            system_data['system']['start_threshold_w'] = test_ctrl.get('start_export_watts', 200)
            system_data['system']['stop_threshold_w'] = test_ctrl.get('stop_export_watts', 150)
        else:
            ctrl = config.get('control', {})
            system_data['system']['start_threshold_w'] = ctrl.get('start_export_watts', 1800)
            system_data['system']['stop_threshold_w'] = ctrl.get('stop_export_watts', 1500)
        
    except Exception as e:
        add_log(f"Error updating data: {e}", "error")
        system_data['system']['status'] = 'Error'

def data_update_thread():
    """Background thread to update data"""
    while True:
        if clients:
            update_system_data()
            socketio.emit('data_update', system_data)
        time.sleep(10)  # Update every 10 seconds

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/data')
def get_data():
    """API endpoint for current data"""
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

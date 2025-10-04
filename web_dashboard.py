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

# Global state
system_data = {
    'solar': {'pv_production_w': 0},
    'tesla': {'soc': 0, 'charging_state': 'Unknown', 'plugged_in': False},
    'system': {'status': 'Starting', 'last_action': 'None', 'dry_run': True, 'start_threshold_w': 1800, 'stop_threshold_w': 1500},
    'logs': []
}

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
                solar_data = clients['solar'].get_power()
                system_data['solar'] = solar_data
            except Exception as e:
                add_log(f"Solar client error: {e}", "error")
                system_data['solar'] = {'pv_production_w': 0}
        
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
                
                should_poll_tesla = (
                    solar_kw >= wake_threshold_kw or  # Solar is high enough
                    might_be_charging  # Or Tesla might be charging
                )
                
                if should_poll_tesla:
                    # Poll Tesla (solar sufficient or might be charging)
                    reason = "might be charging" if might_be_charging else "solar sufficient"
                    add_log(f"Polling Tesla ({reason}): solar={solar_kw:.2f}kW, threshold={wake_threshold_kw:.2f}kW", "debug")
                    tesla_data = clients['tesla'].get_state(wake_if_needed=True)
                    system_data['tesla'] = tesla_data
                    add_log(f"Tesla data: SOC {tesla_data.get('soc', 0)}%, State: {tesla_data.get('charging_state', 'Unknown')}", "info")
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

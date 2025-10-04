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
from controller import Controller

app = Flask(__name__)
app.config['SECRET_KEY'] = 'solar-charger-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state
system_data = {
    'solar': {'pv_production_w': 0, 'site_export_w': 0},
    'tesla': {'soc': 0, 'charging_state': 'Unknown', 'plugged_in': False},
    'system': {'status': 'Starting', 'last_action': 'None', 'dry_run': True},
    'logs': []
}

config = {}
clients = {}

def load_config():
    """Load configuration from file"""
    global config, clients
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        # Initialize clients
        clients['tesla'] = TeslaClient(config)
        clients['solar'] = SolarEdgeCloudClient(config)
        clients['controller'] = Controller(config)
        
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
        # Get solar data
        solar_data = clients['solar'].get_production()
        system_data['solar'] = solar_data
        
        # Get Tesla data
        tesla_data = clients['tesla'].get_state()
        system_data['tesla'] = tesla_data
        
        # Update system status
        system_data['system']['status'] = 'Running'
        system_data['system']['dry_run'] = config.get('dry_run', True)
        
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
            success = clients['tesla'].start_charging()
            message = "Charging started" if success else "Failed to start charging"
            level = "success" if success else "error"
            
        elif action == 'stop_charging':
            success = clients['tesla'].stop_charging()
            message = "Charging stopped" if success else "Failed to stop charging"
            level = "success" if success else "error"
            
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
        
        return jsonify({'success': success, 'message': message})
        
    except Exception as e:
        error_msg = f"Control action failed: {e}"
        add_log(error_msg, "error")
        return jsonify({'success': False, 'message': error_msg})

@app.route('/api/config')
def get_config():
    """Get current configuration"""
    safe_config = config.copy()
    # Remove sensitive data
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
        
        print("Dashboard starting at http://localhost:8090")
        socketio.run(app, host='0.0.0.0', port=8090, debug=False)
    else:
        print("❌ Failed to load configuration. Check config.yaml")

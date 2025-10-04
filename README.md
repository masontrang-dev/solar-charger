# 🌞⚡ Solar Charger - Automated Tesla Charging System

A sophisticated Tesla charging automation system that intelligently controls your Tesla's charging based on real-time solar production data. Maximize your solar investment by charging your Tesla only when you have excess solar power!

## ✨ Features

### 🔋 **Smart Charging Control**
- **Dynamic amperage control** - Automatically adjusts charging current based on available solar
- **Stepped amperage levels** - Uses 8A, 10A, 12A steps to reduce API calls
- **Threshold-based control** - Traditional start/stop charging at configurable thresholds
- **Real-time Tesla control** via Tesla Fleet API with Vehicle Command Protocol
- **Tesla-style amperage interface** - Manual +/- amperage controls with proper charger limits
- **Anti-flicker protection** with configurable minimum on/off durations
- **SOC limits** to prevent overcharging
- **Ultra-low API usage** - Optimized for 5000 calls/month budget

### 📊 **Real-Time Monitoring**
- **Live solar production** monitoring via SolarEdge API
- **Tesla battery level** and charging state tracking
- **Beautiful console display** with 10-second updates
- **Web dashboard** with real-time updates and manual controls
- **Optional vehicle state** display (driving/parked when available)
- **Export power calculation** for accurate solar surplus detection

### ⚙️ **Advanced Configuration**
- **Flexible thresholds** (start/stop watts configurable)
- **Configurable wake threshold** (control when Tesla wakes from sleep)
- **Multiple polling rates** (fast/medium/slow based on conditions)
- **Daytime/nighttime** scheduling with sun time calculations
- **Dry-run mode** for testing without actual Tesla control
- **Comprehensive logging** with configurable levels

### 🌐 **Web Dashboard**
- **Real-time monitoring** with live updates via WebSocket
- **Manual charging control** (start/stop charging buttons)
- **Tesla-style amperage control** with +/- buttons and charger limit detection
- **Tesla wake management** with smart sleep detection
- **Solar energy logging** with detailed session tracking
- **Ultra-efficient API usage** - Same smart polling as backend system
- **Responsive design** works on desktop and mobile

### 🔐 **Enterprise-Grade Security**
- **Tesla Fleet API** integration with OAuth 2.0
- **Signed vehicle commands** using Tesla Vehicle Command Protocol
- **Virtual key pairing** for secure vehicle access
- **Domain verification** via public key hosting

### 💰 **Ultra-Efficient API Usage**
- **Smart polling algorithms** - Only calls Tesla API when necessary
- **Stepped amperage control** - Reduces command API calls by 75%
- **Intelligent caching** - Reuses data when appropriate
- **Daily call limits** - Built-in protection against overuse
- **Startup optimization** - Single initialization call per app
- **~1,200 calls/month** - 76% under Tesla's 5000/month limit
- **Cost-effective operation** - Minimal Tesla API charges

## 🚀 Beginner's Setup Guide

### What You'll Need
- Tesla vehicle (2018+ recommended)
- SolarEdge solar system with monitoring API
- A domain/website (free Netlify account works)
- 30-60 minutes for setup

### Simple 6-Step Setup

#### Step 1: Get Your API Keys 🔑
**SolarEdge API Key:**
1. Go to your SolarEdge monitoring portal
2. Navigate: Admin → Site Access → API Access
3. Click "Generate API Key" and save it

**Tesla Developer Account:**
1. Go to [developer.tesla.com](https://developer.tesla.com)
2. Create account → Create new application
3. **Application Settings:**
   ```
   Application Name: Solar Charger (or your preferred name)
   Description: Home solar charging automation system
   Redirect URI: https://localhost:8080/callback
   Scopes: 
   ✅ vehicle_device_data
   ✅ vehicle_cmds  
   ✅ vehicle_charging_cmds
   ```
4. Save your `client_id` and `client_secret`

#### Step 2: Install & Configure 💻
```bash
# Clone and setup Python environment
git clone <your-repo-url>
cd solar-charger
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Edit configuration file
cp config.yaml.example config.yaml
nano config.yaml  # Add your API keys, Tesla VIN, SolarEdge site ID
```

#### Step 3: Generate Tesla Keys 🔐
```bash
# Install Go and Tesla tools
brew install go
git clone https://github.com/teslamotors/vehicle-command.git
cd vehicle-command
go build ./cmd/tesla-keygen
go build ./cmd/tesla-http-proxy
cd ..

# Generate Tesla OAuth tokens
.venv/bin/python generate_tesla_keys.py
# Follow prompts to complete OAuth flow

# Generate command signing keys
cd vehicle-command
export TESLA_KEY_NAME=solarcharger
./tesla-keygen create > ../tesla_public_key.pem
cd ..
```

#### Step 4: Host Your Public Key 🌐
```bash
# The tesla-fleet-api/ folder is already set up for you
# Just drag and drop this folder to Netlify:
ls tesla-fleet-api/
# Should show: index.html, _redirects, netlify.toml, public-key.pem

# After deploying to Netlify, verify your key is accessible:
curl https://yoursite.netlify.app/.well-known/appspecific/com.tesla.3p.public-key.pem
```

#### Step 5: Register with Tesla ✅
```bash
# Register your domain with Tesla Fleet API
.venv/bin/python tesla_register.py

# Verify registration worked
.venv/bin/python tesla_check_registration.py
```

#### Step 6: Approve in Tesla App 📱
```bash
# Generate your virtual key pairing URL
echo "Open this link on your phone:"
echo "https://tesla.com/_ak/yoursite.netlify.app?vin=YOUR_VIN"

# Test that commands work
.venv/bin/python test_proxy_commands.py
```
1. Open the generated link on your phone
2. Approve the virtual key in your Tesla mobile app
3. Run the test script to verify commands work

### Run Your Solar Charger 🌞
```bash
# Terminal 1: Start Tesla proxy
cd vehicle-command
export TESLA_KEY_NAME=solarcharger
./tesla-http-proxy -tls-key config/tls-key.pem -cert config/tls-cert.pem -port 8080

# Terminal 2: Start solar charger (console mode)
.venv/bin/python run.py

# OR Terminal 2: Start web dashboard
.venv/bin/python web_dashboard.py
# Then visit http://localhost:8091
```

**That's it!** Your Tesla will now automatically charge when you have excess solar power.

---

## 🚀 Detailed Setup Guide

### Prerequisites
- Tesla vehicle (2018+ recommended)
- SolarEdge solar system with monitoring API
- macOS or Linux system
- Python 3.9+
- Go 1.19+ (for Tesla HTTP proxy)

### Installation

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd solar-charger
   ```

2. **Set up Python environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Install Go and build Tesla tools**
   ```bash
   brew install go
   git clone https://github.com/teslamotors/vehicle-command.git
   cd vehicle-command
   go build ./cmd/tesla-http-proxy
   go build ./cmd/tesla-keygen
   cd ..
   ```
   
   **Note:** The `vehicle-command/` folder is excluded from git as it's an external dependency.

## 🔧 Setup Guide

### Step 1: Tesla Fleet API Setup

1. **Create Tesla Developer Account**
   - Go to [developer.tesla.com](https://developer.tesla.com)
   - Create account and new application with these settings:
   ```
   Application Name: Solar Charger
   Description: Home solar charging automation system
   Redirect URI: https://localhost:8080/callback
   Scopes: vehicle_device_data, vehicle_cmds, vehicle_charging_cmds
   ```
   - Note your `client_id` and `client_secret`

2. **Generate OAuth Tokens**
   ```bash
   .venv/bin/python generate_tesla_keys.py
   ```
   Follow the prompts to complete OAuth flow.

### Step 2: Tesla Vehicle Command Protocol Setup

1. **Generate Command Signing Keys**
   ```bash
   cd vehicle-command
   export TESLA_KEY_NAME=solarcharger
   ./tesla-keygen create > ../tesla_public_key.pem
   cd ..
   ```

2. **Host Public Key on Domain**
   - Create a website (e.g., Netlify) at your domain
   - Upload `tesla_public_key.pem` to `/.well-known/appspecific/com.tesla.3p.public-key.pem`
   - Ensure it's accessible at: `https://yourdomain.com/.well-known/appspecific/com.tesla.3p.public-key.pem`

3. **Register with Tesla Fleet API**
   ```bash
   .venv/bin/python tesla_register.py
   ```

4. **Pair Virtual Key with Vehicle**
   - Open this link on your phone: `https://tesla.com/_ak/yourdomain.com?vin=YOUR_VIN`
   - Approve the pairing request in Tesla mobile app

### Step 3: SolarEdge API Setup

1. **Get SolarEdge API Key**
   - Log into SolarEdge monitoring portal
   - Go to Admin → Site Access → API Access
   - Generate API key and note your Site ID

2. **Configure SolarEdge Settings**
   ```yaml
   solaredge:
     source: "cloud"
     cloud:
       api_key: "YOUR_API_KEY"
       site_id: "YOUR_SITE_ID"
   ```

### Step 4: Configuration

1. **Copy and edit configuration**
   ```bash
   cp config.yaml.example config.yaml
   ```

2. **Update config.yaml with your settings**
   ```yaml
   tesla:
     api:
       type: "fleet"
       client_id: "your-client-id"
       client_secret: "your-client-secret"
       access_token: "your-access-token"
     vehicle_vin: "YOUR_VIN"

   solaredge:
     source: "cloud"
     cloud:
       api_key: "YOUR_SOLAREDGE_API_KEY"
       site_id: "YOUR_SITE_ID"

   control:
    mode: "threshold"         # "threshold" or "dynamic"
    start_export_watts: 1800  # Start charging at 1.8kW surplus
    stop_export_watts: 1500   # Stop charging at 1.5kW surplus
    min_on_seconds: 600       # Minimum 10 minutes charging
    min_off_seconds: 600      # Minimum 10 minutes off
    max_soc: 80              # Stop at 80% battery
    
    # Dynamic charging configuration
    dynamic_charging:
      enabled: true           # Enable dynamic amperage control
      min_watts: 600          # Minimum Tesla power (5A × 120V)
      min_amps: 5             # Tesla minimum amperage
      max_amps: 12            # Your charger maximum (12A for 120V mobile connector)
      min_start_amps: 8       # Don't start charging below 8A (reduces API calls)
      amp_steps: [8, 10, 12]  # Only use these amperage levels (reduces API calls)

  tesla:
    wake_threshold_percent: 0.95  # Wake Tesla at 95% of charging threshold
    charging_voltage: 120     # Your charging voltage (120V or 240V)

  dry_run: false  # Set to true for testing
   ```

## 🎯 Usage

### Start the System

1. **Start Tesla HTTP Proxy** (in separate terminal)
   ```bash
   cd vehicle-command
   export TESLA_KEY_NAME=solarcharger
   ./tesla-http-proxy -tls-key config/tls-key.pem -cert config/tls-cert.pem -port 8080 -verbose
   ```

2. **Run Solar Charger**
   ```bash
   # Console mode (automatic control)
   .venv/bin/python run.py
   
   # OR Web dashboard mode (manual + automatic control)
   .venv/bin/python web_dashboard.py
   # Then visit http://localhost:8091
   ```

### Monitor-Only Mode
For monitoring without control:
```bash
.venv/bin/python monitor.py
```

### Testing
Test individual components:
```bash
# Test Tesla connection
.venv/bin/python test_proxy_commands.py

# Test SolarEdge connection
.venv/bin/python debug_solar.py

# Test complete system in dry-run mode
# (Set dry_run: true in config.yaml first)
.venv/bin/python run.py
```

## 📋 Display Output

```
🌞⚡ Solar Charger System - Live Control
===============================================================================================
Time        Solar (kW)  Tesla (%)  Vehicle     Status      Action                    Control
-----------------------------------------------------------------------------------------------
17:35:15      2.180kW               47%                   Plugged     Should Start              🟢 START
17:35:25      2.180kW               47% Parked           Charging    Active                    ⚪ No Action
17:35:35      1.450kW               47%                   Charging    Low Solar                 🔴 STOP
```

### Status Indicators
- **🟢 START** - Charging command sent
- **🔴 STOP** - Stop charging command sent  
- **⚪ No Action** - No command needed
- **⚙️ Set XA** - Amperage adjustment

### Vehicle States (when available)
- **Parked** - Vehicle in Park
- **Driving XXmph** - Vehicle moving
- **Drive/Reverse/Neutral** - Gear positions

## ⚙️ Configuration Options

### Charging Modes

The system supports two charging modes:

#### **Threshold Mode** (Traditional)
- **Start/stop charging** based on fixed solar production thresholds
- **Simple operation** - charges at full power when solar > threshold
- **Good for**: Stable solar conditions, simple setup

#### **Dynamic Mode** (Advanced)
- **Automatically adjusts amperage** based on available solar power
- **Maximizes solar utilization** - starts charging at lower solar levels
- **Smooth operation** - gradually reduces power as sun sets instead of abrupt stops
- **Good for**: Variable solar conditions, maximum efficiency

**Example: Dynamic vs Threshold**
```
Solar Production: 1600W (below 1800W threshold)

Threshold Mode: No charging (waiting for 1800W)
Dynamic Mode: 10A charging (1600W - 360W house = 1240W ÷ 120V = 10A step)

Stepped Amperage Levels: 8A → 10A → 12A (reduces API calls)
```

### Charging Control
```yaml
control:
  mode: "threshold"           # "threshold" or "dynamic"
  start_export_watts: 1800    # Start charging threshold
  stop_export_watts: 1500     # Stop charging threshold  
  min_on_seconds: 600         # Minimum charging duration
  min_off_seconds: 600        # Minimum off duration
  max_soc: 80                # Maximum battery level
  
  # Dynamic charging (when mode: "dynamic")
  dynamic_charging:
    enabled: true             # Enable dynamic amperage control
    min_watts: 600            # Minimum Tesla power for charging
    min_amps: 5               # Tesla minimum amperage
    max_amps: 12              # Charger maximum amperage

tesla:
  wake_threshold_percent: 0.95  # Wake Tesla at 95% of charging threshold
  charging_voltage: 120       # Your charging voltage (120V or 240V)
```

### Polling Rates
```yaml
polling:
  test_poll: false           # Fast polling for testing
  fast_seconds: 30           # High activity polling
  medium_seconds: 60         # Normal polling
  slow_seconds: 120          # Low activity polling
  night_sleep: true          # Skip polling at night
```

### Time Windows
```yaml
control:
  daytime:
    use_sun_times: true
    timezone: "America/Los_Angeles"
    sunrise_offset_min: -30   # Start 30min before sunrise
    sunset_offset_min: 30     # End 30min after sunset
```

## 🔧 Troubleshooting

### Common Issues

**Tesla Commands Not Working**
- Ensure Tesla HTTP proxy is running
- Check virtual key pairing in Tesla app
- Verify public key is accessible at your domain

**SolarEdge Data Issues**
- Verify API key and site ID
- Check API rate limits (300 requests/day)
- Ensure site has production data

**Connection Errors**
- Check internet connectivity
- Verify all API credentials
- Review logs for specific error messages

### Debug Commands
```bash
# Check Tesla registration
.venv/bin/python tesla_check_registration.py

# Test SolarEdge API
.venv/bin/python debug_solar.py

# Verify Tesla commands
.venv/bin/python test_proxy_commands.py
```

## 🔑 Token Management

### Automatic Token Refresh
The system now includes **automatic token refresh**! Your Tesla tokens are checked and refreshed automatically when you run the solar charger.

### Manual Token Refresh
If you need to manually refresh tokens:
```bash
.venv/bin/python refresh_tokens.py
```

### When Tokens Expire
**Tomorrow when your tokens expire, you don't need to do anything!** The system will automatically:
1. Check token expiration when starting
2. Refresh tokens using your refresh_token
3. Continue normal operation

### Token Expiration Schedule
- **Access tokens**: Expire every 8 hours
- **Refresh tokens**: Last much longer (weeks/months)
- **Auto-refresh**: Happens 30 minutes before expiration

## 🛠️ Utility Scripts

### 🚀 **Daily Use Scripts**
- **`run.py`** - Main solar charger system (console mode)
  ```bash
  .venv/bin/python run.py
  ```
  **Console mode** with automatic charging control and smart Tesla wake-up.

- **`web_dashboard.py`** - Web dashboard with manual controls
  ```bash
  .venv/bin/python web_dashboard.py
  # Visit http://localhost:8091
  ```
  **Web dashboard** with real-time monitoring, manual charging controls, and solar logging.

- **`refresh_tokens.py`** - Manual token refresh (rarely needed)
  ```bash
  .venv/bin/python refresh_tokens.py
  ```
  Only use if you want to manually refresh tokens.

### 🔧 **Setup Scripts (Run Once)**
- **`tesla_oauth_simple.py`** - Get initial Tesla OAuth tokens
  ```bash
  .venv/bin/python tesla_oauth_simple.py
  ```
  Run once during initial setup to get your access/refresh tokens.

- **`tesla_register.py`** - Register your domain with Tesla Fleet API
  ```bash
  .venv/bin/python tesla_register.py
  ```
  Run once after hosting your public key to register with Tesla's servers.

### 🐛 **Debug Scripts (As Needed)**
- **`test_proxy_commands.py`** - Test Tesla commands through HTTP proxy
  ```bash
  .venv/bin/python test_proxy_commands.py
  ```
  Use if Tesla commands aren't working.

- **`debug_solar.py`** - Test SolarEdge API connection
  ```bash
  .venv/bin/python debug_solar.py
  ```
  Use if SolarEdge data issues occur.

- **`tesla_check_registration.py`** - Verify Tesla Fleet API registration
  ```bash
  .venv/bin/python tesla_check_registration.py
  ```
  Use if Tesla commands suddenly stop working.

### 📁 **Archived Scripts**
Old scripts have been organized into the `archive/` folder for reference:
- `archive/debug/` - Development debugging scripts
- `archive/tests/` - Old test scripts (replaced by better alternatives)
- `archive/old-oauth/` - Deprecated OAuth implementations
- `archive/utilities/` - Duplicate utility scripts

See `archive/README.md` for details on what each archived script does.

### 📅 **What to Run When**

**Initial Setup (Once)**
1. `tesla_oauth_simple.py` - Get OAuth tokens
2. `tesla_register.py` - Register domain with Tesla

**Daily Operation**
- `run.py` - **Console mode** with automatic charging control
- `web_dashboard.py` - **Web dashboard** with manual controls and monitoring

**Troubleshooting (Rarely)**
- `test_proxy_commands.py` - If Tesla commands fail
- `debug_solar.py` - If SolarEdge data issues
- `refresh_tokens.py` - If you want to manually refresh tokens

## 📁 Project Structure

```
solar-charger/
├── clients/                  # API client modules
│   ├── solaredge_cloud.py    # SolarEdge API client
│   ├── solaredge_modbus.py   # SolarEdge Modbus client  
│   └── tesla.py              # Tesla Fleet API client
├── utils/                    # Utility modules
│   ├── time_windows.py       # Daytime calculations
│   ├── solar_logger.py       # Solar energy session logging
│   ├── logging_config.py     # Logging configuration
│   └── token_manager.py      # Tesla token management
├── templates/                # Web dashboard templates
│   └── dashboard.html        # Web dashboard template
├── archive/                  # Old scripts (organized for reference)
│   ├── debug/               # Development debugging scripts
│   ├── tests/               # Old test scripts
│   ├── old-oauth/           # Deprecated OAuth implementations
│   ├── utilities/           # Duplicate utility scripts
│   └── README.md            # Archive documentation
├── vehicle-command/          # Tesla HTTP proxy tools (external)
├── tesla-fleet-api/          # Public key hosting (deploy to Netlify)
├── config.yaml              # Main configuration
├── controller.py            # Charging logic
├── scheduler.py             # Main automation loop
├── monitor.py              # Monitor-only mode
├── run.py                  # Console mode entry point
├── web_dashboard.py         # Web dashboard entry point
├── view_solar_logs.py       # View solar charging session logs
├── generate_tesla_keys.py   # Setup: OAuth token generation
├── tesla_register.py        # Setup: Domain registration
├── tesla_oauth_simple.py    # Setup: OAuth token generation
├── test_proxy_commands.py   # Debug: Test Tesla commands
├── test_wake_commands.py    # Debug: Test wake commands
├── tesla_check_registration.py # Debug: Check Tesla registration
├── tesla_command_signer.py  # Utility: Command signing
├── refresh_tokens.py        # Utility: Token refresh
└── debug_solar.py          # Debug: Test SolarEdge API
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ⚠️ Disclaimer

This software controls your Tesla vehicle. Use at your own risk. Always monitor the system and ensure your Tesla is safely connected to a proper charging station. The authors are not responsible for any damage to your vehicle or property.

## 🙏 Acknowledgments

- Tesla for the Fleet API and Vehicle Command Protocol
- SolarEdge for the monitoring API
- The open-source community for various Python packages used

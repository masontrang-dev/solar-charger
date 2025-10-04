# Changelog

All notable changes to this project will be documented in this file.

## [2.0.0] - 2025-10-04

### 🌐 Added - Web Dashboard
- **Real-time web dashboard** with live updates via WebSocket
- **Manual charging controls** (start/stop charging buttons)
- **Tesla wake management** with manual wake button
- **Responsive design** that works on desktop and mobile
- **Live solar and Tesla data** with 10-second updates
- **System logs display** in the web interface

### 😴 Added - Smart Tesla Sleep Management
- **Intelligent Tesla polling** - only wake when solar is sufficient
- **Configurable wake threshold** via `tesla.wake_threshold_percent` config
- **Sleep state detection** with clean UI indicators
- **Battery preservation** by avoiding unnecessary wake-ups
- **Automatic wake** when charging is active (even with low solar)

### 📊 Added - Solar Energy Logging
- **Detailed session tracking** with energy breakdown
- **Solar vs grid contribution** calculation
- **Charging session logs** with start/end times and energy captured
- **View logs utility** (`view_solar_logs.py`) with filtering options
- **Energy efficiency metrics** and statistics

### ⚡ Enhanced - Tesla Integration
- **Immediate data refresh** after manual charging commands
- **Real-time charging metrics** (power, current, voltage)
- **Enhanced error handling** for Tesla API deprecation
- **Charging state indicators** with visual feedback
- **Proper Tesla power calculation** (V × A instead of misleading API values)

### 🎨 Improved - User Experience
- **Clean sleeping state display** with dashes instead of stale data
- **Professional status indicators** with consistent styling
- **Better error messages** and user feedback
- **Instant UI updates** after user actions
- **Clear wake threshold logging** for transparency

### 🔧 Technical Improvements
- **Configurable wake thresholds** (default 95% of charging threshold)
- **Enhanced logging system** with multiple output destinations
- **Improved polling logic** with charging state awareness
- **Better error handling** and recovery
- **Code organization** with proper separation of concerns

### 📝 Configuration Changes
- **New config option**: `tesla.wake_threshold_percent` (default: 0.95)
- **Enhanced Tesla client** with smart wake detection
- **Improved scheduler** with configurable thresholds

### 🐛 Bug Fixes
- **Fixed charging button functionality** (was calling non-existent function)
- **Corrected Tesla field mappings** (charging_state vs charge_state)
- **Fixed scheduler crashes** with missing variables
- **Resolved CSS syntax errors** in dashboard
- **Fixed duplicate code** and inconsistencies

### 📚 Documentation
- **Updated README** with web dashboard instructions
- **Added configuration examples** for wake thresholds
- **Enhanced setup guide** with both console and web modes
- **Improved project structure** documentation

## [1.0.0] - Previous Release

### Initial Features
- Tesla Fleet API integration with Vehicle Command Protocol
- SolarEdge API integration for solar production monitoring
- Automatic charging control based on solar thresholds
- Console-based monitoring and control
- Comprehensive configuration system
- Token management and refresh

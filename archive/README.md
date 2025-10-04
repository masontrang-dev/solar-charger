# Archive - Old Scripts and Utilities

This folder contains scripts that are no longer needed for daily operation but are kept for reference and historical purposes.

## 📁 Folder Structure

### `debug/` - Old Debug Scripts
Scripts used during development for debugging specific components:

- **`debug_solar_fields.py`** - Debug SolarEdge API field mappings
- **`debug_solaredge_raw.py`** - Raw SolarEdge API response analysis
- **`debug_tesla_fields.py`** - Debug Tesla API field mappings  
- **`debug_tesla_state.py`** - Tesla vehicle state debugging
- **`tesla_debug.py`** - General Tesla API debugging

### `tests/` - Old Test Scripts
Specialized test scripts replaced by better alternatives:

- **`test_signed_commands.py`** - Old Tesla command signing tests (use `test_proxy_commands.py` instead)
- **`test_wake_and_charge.py`** - Wake and charge testing (functionality now in `run.py`)

### `old-oauth/` - Deprecated OAuth Scripts
OAuth scripts replaced by simpler alternatives:

- **`tesla_oauth.py`** - Complex OAuth implementation (use `tesla_oauth_simple.py` instead)
- **`tesla_force_register.py`** - Force registration script (use `tesla_register.py` instead)

### `utilities/` - Duplicate Utilities
Utility scripts with duplicate functionality:

- **`generate_command_keys.py`** - Duplicate of key generation (use `generate_tesla_keys.py` instead)

## 🚫 Why These Were Archived

1. **Debug scripts** - One-time use during development, no longer needed for operation
2. **Test scripts** - Functionality integrated into main system or better alternatives exist
3. **OAuth scripts** - Replaced by simpler, more reliable implementations
4. **Utilities** - Duplicate functionality available in active scripts

## 🔄 If You Need Them

These scripts are preserved in case you need to:
- Debug specific API issues
- Reference old implementation approaches
- Understand the development history
- Restore functionality if needed

## ✅ Current Active Scripts

For daily use, stick to the scripts in the main directory:
- `run.py` - Console mode
- `web_dashboard.py` - Web dashboard
- `test_proxy_commands.py` - Tesla command testing
- `debug_solar.py` - SolarEdge debugging
- `tesla_oauth_simple.py` - OAuth setup

#!/usr/bin/env python3
"""
Tesla token management utilities
"""

import requests
import yaml
import logging
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class TeslaTokenManager:
    """Manages Tesla OAuth token refresh"""
    
    def __init__(self, config_path: str = 'config.yaml'):
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> dict:
        """Load configuration from file"""
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def _save_config(self, config: dict):
        """Save configuration to file"""
        with open(self.config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
    
    def is_token_expired(self) -> bool:
        """Check if access token is expired or will expire soon"""
        try:
            tesla_config = self.config.get('tesla', {}).get('api', {})
            access_token = tesla_config.get('access_token')
            
            if not access_token:
                logger.warning("No access token found")
                return True
            
            # Decode JWT to check expiration (simple check)
            import base64
            import json
            
            # Split JWT and decode payload
            parts = access_token.split('.')
            if len(parts) != 3:
                logger.warning("Invalid access token format")
                return True
            
            # Add padding if needed
            payload = parts[1]
            payload += '=' * (4 - len(payload) % 4)
            
            try:
                decoded = base64.b64decode(payload)
                token_data = json.loads(decoded)
                
                exp_timestamp = token_data.get('exp')
                if not exp_timestamp:
                    logger.warning("No expiration found in token")
                    return True
                
                exp_time = datetime.fromtimestamp(exp_timestamp)
                current_time = datetime.now()
                
                # Consider expired if less than 30 minutes remaining
                buffer_time = timedelta(minutes=30)
                
                if current_time + buffer_time >= exp_time:
                    logger.info(f"Token expires at {exp_time}, refreshing now")
                    return True
                else:
                    time_remaining = exp_time - current_time
                    logger.debug(f"Token valid for {time_remaining}")
                    return False
                    
            except Exception as e:
                logger.warning(f"Could not decode token: {e}")
                return True
                
        except Exception as e:
            logger.error(f"Error checking token expiration: {e}")
            return True
    
    def refresh_token(self) -> bool:
        """Refresh the access token using refresh token"""
        try:
            tesla_config = self.config.get('tesla', {}).get('api', {})
            client_id = tesla_config.get('client_id')
            client_secret = tesla_config.get('client_secret')
            refresh_token = tesla_config.get('refresh_token')
            
            if not all([client_id, client_secret, refresh_token]):
                logger.error("Missing required credentials for token refresh")
                return False
            
            logger.info("Refreshing Tesla access token...")
            
            token_url = "https://auth.tesla.com/oauth2/v3/token"
            data = {
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token
            }
            
            response = requests.post(token_url, data=data, timeout=30)
            
            if response.status_code == 200:
                token_data = response.json()
                
                new_access_token = token_data.get('access_token')
                new_refresh_token = token_data.get('refresh_token', refresh_token)
                
                if new_access_token:
                    # Update config
                    self.config['tesla']['api']['access_token'] = new_access_token
                    self.config['tesla']['api']['refresh_token'] = new_refresh_token
                    
                    self._save_config(self.config)
                    
                    logger.info("✅ Tesla token refreshed successfully")
                    return True
                else:
                    logger.error("No access token in refresh response")
                    return False
            else:
                logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return False
    
    def ensure_valid_token(self) -> bool:
        """Ensure we have a valid access token, refresh if needed"""
        if self.is_token_expired():
            return self.refresh_token()
        return True

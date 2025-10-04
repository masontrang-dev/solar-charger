#!/usr/bin/env python3
"""
Tesla Fleet API OAuth Flow
Run this script to get access and refresh tokens for your Tesla account.
"""

import base64
import hashlib
import secrets
import urllib.parse
import webbrowser
import yaml
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import json


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Parse the callback URL
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        
        if 'code' in params:
            # Store the authorization code
            self.server.auth_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'''
            <html><body>
            <h1>Authorization Successful!</h1>
            <p>You can close this window and return to the terminal.</p>
            </body></html>
            ''')
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<html><body><h1>Error: No authorization code received</h1></body></html>')
    
    def log_message(self, format, *args):
        # Suppress server logs
        pass


def generate_pkce():
    """Generate PKCE code verifier and challenge"""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).decode('utf-8').rstrip('=')
    return code_verifier, code_challenge


def main():
    # Load config
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    tesla_config = config.get('tesla', {}).get('api', {})
    client_id = tesla_config.get('client_id')
    client_secret = tesla_config.get('client_secret')
    
    if not client_id or not client_secret:
        print("Error: client_id and client_secret must be set in config.yaml")
        return
    
    # Generate PKCE parameters
    code_verifier, code_challenge = generate_pkce()
    
    # OAuth parameters
    redirect_uri = "http://localhost:8080/callback"
    scope = "vehicle_device_data vehicle_cmds vehicle_charging_cmds"
    state = secrets.token_urlsafe(32)
    
    # Build authorization URL
    auth_params = {
        'response_type': 'code',
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'scope': scope,
        'state': state,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256'
    }
    
    auth_url = "https://auth.tesla.com/oauth2/v3/authorize?" + urllib.parse.urlencode(auth_params)
    
    print("Tesla OAuth Flow")
    print("================")
    print(f"1. Opening browser to: {auth_url}")
    print("2. Log into your Tesla account (including 2FA if enabled)")
    print("3. Grant permission to your app")
    print("4. Wait for redirect back to localhost...")
    print()
    
    # Start local server to catch callback
    server = HTTPServer(('localhost', 8080), CallbackHandler)
    server.auth_code = None
    
    # Open browser
    webbrowser.open(auth_url)
    
    # Wait for callback
    print("Waiting for authorization callback...")
    server.handle_request()
    
    if not server.auth_code:
        print("Error: No authorization code received")
        return
    
    print("Authorization code received! Exchanging for tokens...")
    
    # Exchange authorization code for tokens
    token_data = {
        'grant_type': 'authorization_code',
        'client_id': client_id,
        'client_secret': client_secret,
        'code': server.auth_code,
        'redirect_uri': redirect_uri,
        'code_verifier': code_verifier
    }
    
    try:
        response = requests.post(
            'https://auth.tesla.com/oauth2/v3/token',
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        response.raise_for_status()
        tokens = response.json()
        
        print("\n✅ Success! Tokens received:")
        print(f"Access Token: {tokens['access_token'][:20]}...")
        if 'refresh_token' in tokens:
            print(f"Refresh Token: {tokens['refresh_token'][:20]}...")
        else:
            print("Refresh Token: Not provided (access token only)")
        print(f"Expires in: {tokens.get('expires_in', 'unknown')} seconds")
        
        print(f"\n📋 Full token response:")
        print(json.dumps(tokens, indent=2))
        
        print(f"\n📝 Update your config.yaml with these tokens:")
        print(f"access_token: \"{tokens['access_token']}\"")
        if 'refresh_token' in tokens:
            print(f"refresh_token: \"{tokens['refresh_token']}\"")
        else:
            print("refresh_token: \"\" # Not provided - access token only")
        
        # Optionally auto-update config
        update_config = input("\nAuto-update config.yaml? (y/n): ").lower().strip()
        if update_config == 'y':
            config['tesla']['api']['access_token'] = tokens['access_token']
            if 'refresh_token' in tokens:
                config['tesla']['api']['refresh_token'] = tokens['refresh_token']
            else:
                config['tesla']['api']['refresh_token'] = ""
            
            with open('config.yaml', 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            
            print("✅ config.yaml updated!")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error exchanging tokens: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"Response: {e.response.text}")


if __name__ == "__main__":
    main()

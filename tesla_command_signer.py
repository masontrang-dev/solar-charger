#!/usr/bin/env python3
"""
Tesla Vehicle Command Protocol - Command Signing Implementation
"""

import json
import time
import hashlib
import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature


class TeslaCommandSigner:
    def __init__(self, private_key_path="command-private-key.pem"):
        """Initialize the command signer with private key"""
        self.private_key_path = private_key_path
        self.private_key = self._load_private_key()
    
    def _load_private_key(self):
        """Load the private key from file"""
        try:
            with open(self.private_key_path, 'rb') as f:
                private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=None
                )
            return private_key
        except Exception as e:
            raise Exception(f"Failed to load private key: {e}")
    
    def _create_signature_payload(self, method, path, body, timestamp):
        """Create the payload that needs to be signed"""
        # Tesla's signature format: METHOD|PATH|BODY|TIMESTAMP
        if body:
            body_str = json.dumps(body, separators=(',', ':'))
        else:
            body_str = ""
        
        payload = f"{method}|{path}|{body_str}|{timestamp}"
        return payload
    
    def sign_command(self, method, path, body=None):
        """Sign a Tesla command and return headers"""
        # Generate timestamp (Unix timestamp in seconds)
        timestamp = str(int(time.time()))
        
        # Create signature payload
        payload = self._create_signature_payload(method, path, body, timestamp)
        
        # Create SHA256 hash of payload
        payload_hash = hashlib.sha256(payload.encode('utf-8')).digest()
        
        # Sign the hash with private key
        try:
            signature = self.private_key.sign(
                payload_hash,
                ec.ECDSA(hashes.SHA256())
            )
            
            # Encode signature as base64
            signature_b64 = base64.b64encode(signature).decode('utf-8')
            
            # Return the required headers
            return {
                'Tesla-Command-Signature': signature_b64,
                'Tesla-Command-Timestamp': timestamp,
            }
            
        except Exception as e:
            raise Exception(f"Failed to sign command: {e}")
    
    def create_signed_request_headers(self, method, vehicle_id, command, body=None):
        """Create complete headers for a signed Tesla command"""
        # Construct the API path
        path = f"/api/1/vehicles/{vehicle_id}/command/{command}"
        
        # Get signature headers
        signature_headers = self.sign_command(method, path, body)
        
        # Combine with standard headers
        headers = {
            'Content-Type': 'application/json',
            'Tesla-Command-Signature': signature_headers['Tesla-Command-Signature'],
            'Tesla-Command-Timestamp': signature_headers['Tesla-Command-Timestamp'],
        }
        
        return headers


def test_signer():
    """Test the command signer"""
    print("🔐 Testing Tesla Command Signer")
    print("=" * 50)
    
    try:
        signer = TeslaCommandSigner()
        print("✅ Command signer initialized")
        
        # Test signing a charge_start command
        headers = signer.create_signed_request_headers(
            method="POST",
            vehicle_id="1492931983458533",
            command="charge_start"
        )
        
        print("✅ Successfully created signed headers:")
        for key, value in headers.items():
            if key == 'Tesla-Command-Signature':
                print(f"  {key}: {value[:20]}... (truncated)")
            else:
                print(f"  {key}: {value}")
                
        return True
        
    except Exception as e:
        print(f"❌ Signer test failed: {e}")
        return False


if __name__ == "__main__":
    test_signer()

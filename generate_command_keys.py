#!/usr/bin/env python3
"""
Generate keypair for Tesla Vehicle Command Protocol
"""

import subprocess
import os
import sys


def generate_command_keys():
    """Generate private/public key pair for Tesla command signing"""
    
    print("🔐 Generating Tesla Vehicle Command Protocol Keys")
    print("=" * 60)
    
    # Generate private key for command signing (different from Fleet API key)
    print("1. Generating command signing private key...")
    private_key_cmd = [
        'openssl', 'ecparam', '-genkey', '-name', 'prime256v1', '-noout', '-out', 'command-private-key.pem'
    ]
    
    try:
        subprocess.run(private_key_cmd, check=True)
        print("✅ Command private key generated: command-private-key.pem")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to generate private key: {e}")
        return False
    except FileNotFoundError:
        print("❌ OpenSSL not found. Install it with: brew install openssl")
        return False
    
    # Generate public key
    print("2. Generating command signing public key...")
    public_key_cmd = [
        'openssl', 'ec', '-in', 'command-private-key.pem', '-pubout', '-out', 'command-public-key.pem'
    ]
    
    try:
        subprocess.run(public_key_cmd, check=True)
        print("✅ Command public key generated: command-public-key.pem")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to generate public key: {e}")
        return False
    
    # Display the public key content
    print("\n" + "="*60)
    print("PUBLIC KEY FOR TESLA DEVELOPER PORTAL:")
    print("="*60)
    
    try:
        with open('command-public-key.pem', 'r') as f:
            public_key_content = f.read()
            print(public_key_content)
    except Exception as e:
        print(f"❌ Error reading public key: {e}")
        return False
    
    print("="*60)
    print("NEXT STEPS:")
    print("="*60)
    print("1. Copy the PUBLIC KEY above")
    print("2. Go to https://developer.tesla.com")
    print("3. Go to your app settings")
    print("4. Find 'Vehicle Command Public Key' or similar section")
    print("5. Paste the public key content")
    print("6. Save the settings")
    print()
    print("⚠️  IMPORTANT: Keep command-private-key.pem SECRET!")
    print("   This file is used to sign commands and must not be shared.")
    print()
    print("After uploading the public key, run:")
    print("   .venv/bin/python test_signed_commands.py")
    
    return True


if __name__ == "__main__":
    if generate_command_keys():
        print("\n✅ Key generation completed successfully!")
    else:
        print("\n❌ Key generation failed!")
        sys.exit(1)

#!/usr/bin/env python3
"""
Generate Tesla Fleet API key pair for domain verification
"""

import os
import subprocess
import sys


def generate_keys():
    """Generate private and public key pair for Tesla Fleet API"""
    print("Generating Tesla Fleet API key pair...")
    
    # Generate private key
    print("1. Generating private key...")
    private_key_cmd = [
        'openssl', 'ecparam', '-genkey', '-name', 'prime256v1', '-noout', '-out', 'private-key.pem'
    ]
    
    try:
        subprocess.run(private_key_cmd, check=True)
        print("✅ Private key generated: private-key.pem")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to generate private key: {e}")
        return False
    except FileNotFoundError:
        print("❌ OpenSSL not found. Install it with: brew install openssl")
        return False
    
    # Generate public key
    print("2. Generating public key...")
    public_key_cmd = [
        'openssl', 'ec', '-in', 'private-key.pem', '-pubout', '-out', 'public-key.pem'
    ]
    
    try:
        subprocess.run(public_key_cmd, check=True)
        print("✅ Public key generated: public-key.pem")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to generate public key: {e}")
        return False
    
    # Create the directory structure for GitHub Pages
    print("3. Creating GitHub Pages directory structure...")
    os.makedirs('.well-known/appspecific', exist_ok=True)
    
    # Copy public key to the required location
    import shutil
    shutil.copy('public-key.pem', '.well-known/appspecific/com.tesla.3p.public-key.pem')
    print("✅ Public key copied to .well-known/appspecific/com.tesla.3p.public-key.pem")
    
    # Create index.html for GitHub Pages
    index_html = """<!DOCTYPE html>
<html>
<head>
    <title>Tesla Fleet API Keys</title>
</head>
<body>
    <h1>Tesla Fleet API Public Key</h1>
    <p>This site hosts the public key for Tesla Fleet API integration.</p>
    <p>Public key location: <a href="/.well-known/appspecific/com.tesla.3p.public-key.pem">/.well-known/appspecific/com.tesla.3p.public-key.pem</a></p>
</body>
</html>"""
    
    with open('index.html', 'w') as f:
        f.write(index_html)
    print("✅ Created index.html")
    
    # Display public key content
    print("\n" + "="*50)
    print("PUBLIC KEY CONTENT:")
    print("="*50)
    with open('public-key.pem', 'r') as f:
        print(f.read())
    
    print("="*50)
    print("NEXT STEPS:")
    print("="*50)
    print("1. Upload these files to your GitHub repository:")
    print("   - index.html")
    print("   - .well-known/appspecific/com.tesla.3p.public-key.pem")
    print()
    print("2. Your domain will be: https://yourusername.github.io/tesla-fleet-api")
    print()
    print("3. Test the public key URL after uploading:")
    print("   https://yourusername.github.io/tesla-fleet-api/.well-known/appspecific/com.tesla.3p.public-key.pem")
    print()
    print("4. Keep private-key.pem SECRET - do NOT upload it to GitHub!")
    
    return True


if __name__ == "__main__":
    if generate_keys():
        print("\n✅ Key generation completed successfully!")
    else:
        print("\n❌ Key generation failed!")
        sys.exit(1)

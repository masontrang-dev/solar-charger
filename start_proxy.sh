#!/bin/bash
# Start Tesla HTTP Proxy for vehicle commands
# This must be running for charging commands to work

cd "$(dirname "$0")/vehicle-command"

# Check if required files exist
if [ ! -f "tesla-http-proxy" ]; then
    echo "❌ tesla-http-proxy not found. Please build it first:"
    echo "   cd vehicle-command && go build ./cmd/tesla-http-proxy"
    exit 1
fi

if [ ! -f "config/tls-key.pem" ] || [ ! -f "config/tls-cert.pem" ]; then
    echo "❌ TLS certificates not found in config/"
    echo "   Please generate them or check your setup"
    exit 1
fi

# Set the key name (should match what you used with tesla-keygen)
export TESLA_KEY_NAME=${TESLA_KEY_NAME:-solarcharger}

echo "🚗 Starting Tesla HTTP Proxy..."
echo "Key name: $TESLA_KEY_NAME"
echo "Port: 8080"
echo ""
echo "Press Ctrl+C to stop"
echo ""

./tesla-http-proxy \
    -tls-key config/tls-key.pem \
    -cert config/tls-cert.pem \
    -port 8080 \
    -verbose

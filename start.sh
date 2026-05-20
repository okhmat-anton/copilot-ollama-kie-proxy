#!/bin/bash
# Start script for Ollama-KIE.AI Proxy
# This script can be used directly or as part of systemd service

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Load environment
if [ -f .env ]; then
    export $(cat .env | grep -v '#' | xargs)
fi

# Check if required environment variable is set
if [ -z "$KIE_AI_API_KEY" ]; then
    echo "❌ Error: KIE_AI_API_KEY is not set"
    echo "Please configure .env file or set the environment variable"
    exit 1
fi

# Create logs directory
mkdir -p logs

# Get host and port from config
HOST=${PROXY_HOST:-127.0.0.1}
PORT=${PROXY_PORT:-11434}

echo "🚀 Starting Ollama-KIE.AI Proxy"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Host: $HOST"
echo "Port: $PORT"
echo "Log Directory: ./logs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Start the service
python -m uvicorn main:app --host "$HOST" --port "$PORT" --workers 4

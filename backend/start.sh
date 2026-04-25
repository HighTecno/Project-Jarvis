#!/bin/bash

# Load .env file if it exists
if [ -f .env ]; then
    export $(cat .env | grep -v '#' | xargs)
    echo "✅ Loaded environment variables from .env"
else
    echo "⚠️  .env file not found. Copy .env.example to .env and fill in your values."
    exit 1
fi

# Run the server with sudo (needed for Tailscale certs)
if [ "$USE_SSL" = "true" ]; then
    echo "🔒 Starting with HTTPS (Tailscale)"
    sudo -E python run.py
else
    echo "🌐 Starting with HTTP"
    python run.py

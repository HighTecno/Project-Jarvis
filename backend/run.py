#!/usr/bin/env python3
import argparse
import os
import sys

# Add repo root to path so 'backend' package is importable
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, repo_root)

import uvicorn
from backend.config import HOST, PORT, USE_SSL, SSL_CERTFILE, SSL_KEYFILE
from backend.main import app
from backend.tui import launch_tui


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run Jarvis backend server or TUI client.")
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Launch terminal UI client instead of API server.",
    )
    parser.add_argument(
        "--url",
        default=os.getenv("JARVIS_BASE_URL", "http://127.0.0.1:8000"),
        help="Jarvis API base URL for TUI mode.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("JARVIS_API_KEY"),
        help="API key for TUI mode (optional if AUTH_ENABLED=false).",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.tui:
        print(f"Starting Jarvis TUI against {args.url}")
        launch_tui(base_url=args.url, api_key=args.api_key)
        return

    if USE_SSL and SSL_CERTFILE and SSL_KEYFILE:
        print("Starting with HTTPS (SSL/TLS)")
        print(f"  Cert: {SSL_CERTFILE}")
        print(f"  Key:  {SSL_KEYFILE}")
        uvicorn.run(app, host=HOST, port=PORT, ssl_certfile=SSL_CERTFILE, ssl_keyfile=SSL_KEYFILE)
    else:
        print("Starting with HTTP")
        uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()

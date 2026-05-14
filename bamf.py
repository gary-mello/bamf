"""
Unified executable entry point for bamf.

Web UI:
    bamf-web.exe

CLI:
    bamf-cli.exe
"""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="bamf GitHub repo tooling")
    parser.add_argument("--cli", action="store_true", help="start the terminal CLI instead of the web UI")
    parser.add_argument("--web", action="store_true", help="start the local web UI (default)")
    parser.add_argument("--host", default="127.0.0.1", help="web UI bind host")
    parser.add_argument("--port", type=int, default=8000, help="web UI bind port")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")
    args, remaining = parser.parse_known_args()

    if args.cli:
        sys.argv = [sys.argv[0], *remaining]
        from main import main as cli_main

        cli_main()
        return

    from web_app import run_server

    run_server(host=args.host, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()

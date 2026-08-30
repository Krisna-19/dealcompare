#!/usr/bin/env python3
"""
DealCompare frontend static server.

Serves the frontend *as the web root* so that http://<host>:<port>/ loads the
actual application (frontend/index.html) and the relative resource paths used
by index.html (css/style.css, js/app.js) resolve correctly.

This is the fix for the previous behaviour where a static server pointed at
the project root showed a "Directory listing for /" instead of the UI — the
web root must be this `frontend/` directory, not the repository root.

The default port (5500) deliberately matches the origin already in the API's
CORS allow-list (app/core/config.py -> ALLOWED_ORIGINS), so the browser is
allowed to call http://127.0.0.1:8000/search from this page.

Run from anywhere:

    python frontend/serve.py            # serve on 127.0.0.1:5500, open browser
    python frontend/serve.py --port 8000 --no-open

The separate API must be running on port 8000 for searches to work,
e.g.  uvicorn app.main:app --port 8000
"""

import argparse
import os
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

# Web root is ALWAYS this frontend/ directory, regardless of CWD.
FRONTEND_DIR = os.path.dirname(os.path.abspath(__file__))


def build_handler(directory):
    """Return a SimpleHTTPRequestHandler subclass rooted at `directory`."""
    return partial(
        SimpleHTTPRequestHandler,
        directory=directory,
    )


def open_browser(url, host):
    """Open the UI in the default browser (skipped for non-loopback hosts)."""
    # Only auto-open for localhost targets; a remote host can't open a local
    # browser, and doing so would just fail silently.
    if host in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
        webbrowser.open(url)
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description="DealCompare frontend static server")
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Interface to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port", type=int, default=5500,
        help="Port to serve on (default: 5500, matching the API CORS allow-list)",
    )
    parser.add_argument(
        "--no-open", action="store_true",
        help="Do not auto-open the browser",
    )
    args = parser.parse_args()

    handler = build_handler(FRONTEND_DIR)
    httpd = ThreadingHTTPServer((args.host, args.port), handler)

    url = f"http://127.0.0.1:{args.port}/"
    print(f"DealCompare frontend serving: {url}")
    print(f"Web root: {FRONTEND_DIR}")
    print(f"Entry point: index.html (NOT a directory listing)")
    print("Press Ctrl+C to stop.")

    if not args.no_open:
        # Open shortly after bind so the server is ready.
        threading.Timer(0.5, open_browser, args=(url, args.host)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()

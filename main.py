#!/usr/bin/env python3
"""HTTP API to update the POS display, with a default clock view."""

import http.server
import json
import threading
import time
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from display import SerialDisplay, load_config


cfg = load_config()
display = SerialDisplay(cfg)
display_lock = threading.Lock()
view_state = "default"  # 'default' or 'custom'
stop_event = threading.Event()

DEFAULT_LINE1 = "Hello, Devii".center(20)


def default_view():
    """Return the default static line1 and the current date/time line2."""
    line2 = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return DEFAULT_LINE1, line2


def update_default():
    with display_lock:
        if not display.is_open:
            display.open()
        line1, line2 = default_view()
        display.set_text(line1=line1, line2=line2)


def default_loop():
    """Background thread that keeps the default clock view updated."""
    while not stop_event.is_set():
        if view_state == "default":
            try:
                update_default()
            except Exception as e:
                print(f"Default view error: {e}")
            time.sleep(1)
        else:
            time.sleep(0.2)


def json_response(handler, code, data):
    body = json.dumps(data).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class APIHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(fmt % args)

    def do_GET(self):
        global view_state

        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/health":
            json_response(
                self,
                200,
                {
                    "status": "ok" if display.is_open else "error",
                    "port": display.port,
                    "baud": display.baud,
                    "mode": display.mode,
                    "open": display.is_open,
                    "view": view_state,
                },
            )
            return

        if path == "/display":
            line1 = qs.get("line1", [""])[0]
            line2 = qs.get("line2", [""])[0]
            if line1 == "" and line2 == "":
                json_response(
                    self, 400, {"error": "provide line1 and/or line2 query param"}
                )
                return

            try:
                with display_lock:
                    if not display.is_open:
                        display.open()
                    display.set_text(line1=line1, line2=line2)
                view_state = "custom"
                json_response(self, 200, {"ok": True, "line1": line1, "line2": line2})
            except Exception as e:
                json_response(self, 500, {"error": str(e)})
            return

        if path == "/reset":
            try:
                view_state = "default"
                update_default()
                json_response(self, 200, {"ok": True, "view": "default"})
            except Exception as e:
                json_response(self, 500, {"error": str(e)})
            return

        json_response(self, 404, {"error": "not found"})


def main():
    # Open the serial port and show the default view immediately on startup.
    try:
        update_default()
    except Exception as e:
        print(f"Could not open display: {e}")

    api_cfg = cfg.get("api", {})
    host = api_cfg.get("host", "0.0.0.0")
    port = api_cfg.get("port", 8000)

    # Start the default clock view in the background.
    t = threading.Thread(target=default_loop, daemon=True)
    t.start()

    server = http.server.HTTPServer((host, port), APIHandler)
    print(f"POS Display API listening on http://{host}:{port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        stop_event.set()
        display.close()


if __name__ == "__main__":
    main()

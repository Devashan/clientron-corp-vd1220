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
view_state = "default"  # 'default', 'custom' or 'scroll'
stop_event = threading.Event()

DEFAULT_LINE1 = "Hello, Devii".center(20)

# Ticker defaults. `gap` is the run of blanks shown between the end of the
# text and the start of the next repeat so the wrap-around is readable.
DEFAULT_SCROLL_SPEED = 0.3
MIN_SCROLL_SPEED = 0.05
MAX_SCROLL_SPEED = 5.0
DEFAULT_SCROLL_GAP = "   "

scroll_lock = threading.Lock()
scroll_state = {
    "line1": "",
    "line2": "",
    "offset1": 0,
    "offset2": 0,
    "speed": DEFAULT_SCROLL_SPEED,
    "gap": DEFAULT_SCROLL_GAP,
    # What is currently on each line, so a line that has not moved can be
    # left alone instead of being redrawn.
    "frame1": None,
    "frame2": None,
}


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


def ticker_frame(text, offset, width, gap):
    """Return the `width`-wide window of `text` starting at `offset`.

    Text that already fits the display is returned unchanged. Longer text is
    treated as an endless loop of `text + gap`, so the window wraps from the
    tail back onto the head without a jump.
    """
    if len(text) <= width:
        return text
    loop = text + gap
    # Repeat enough of the head that a full window can always be sliced.
    return (loop + loop[:width])[offset % len(loop):][:width]


def next_offset(text, offset, width, gap):
    """Advance a line's ticker position, or hold it if the text fits."""
    if len(text) <= width:
        return 0
    return (offset + 1) % (len(text) + len(gap))


def draw_scroll_frames(frame1, frame2):
    """Put the given frames on the display, rewriting as little as possible.

    A line whose content has not changed is left untouched, and on displays
    with cursor addressing the changed lines are written in place. Without
    this the whole display would be cleared every tick and a short, static
    line would visibly blink alongside the scrolling one.

    Callers must hold `scroll_lock`.
    """
    changed = [
        (n, frame)
        for n, frame, shown in (
            (1, frame1, scroll_state["frame1"]),
            (2, frame2, scroll_state["frame2"]),
        )
        if frame != shown
    ]
    if not changed:
        return

    with display_lock:
        if not display.is_open:
            display.open()
        if display.supports_line_addressing:
            for n, frame in changed:
                display.set_line(n, frame)
        else:
            # No cursor control in raw mode: both lines go out together.
            display.set_text(line1=frame1, line2=frame2)

    scroll_state["frame1"] = frame1
    scroll_state["frame2"] = frame2


def scroll_loop():
    """Background thread that animates the ticker view."""
    while not stop_event.is_set():
        if view_state != "scroll":
            time.sleep(0.2)
            continue

        try:
            with scroll_lock:
                width = display.line_length
                gap = scroll_state["gap"]
                text1, text2 = scroll_state["line1"], scroll_state["line2"]
                # Advance first, then render: the frame at the current offset
                # is already on the display.
                scroll_state["offset1"] = next_offset(
                    text1, scroll_state["offset1"], width, gap
                )
                scroll_state["offset2"] = next_offset(
                    text2, scroll_state["offset2"], width, gap
                )
                speed = scroll_state["speed"]
                draw_scroll_frames(
                    ticker_frame(text1, scroll_state["offset1"], width, gap),
                    ticker_frame(text2, scroll_state["offset2"], width, gap),
                )
        except Exception as e:
            print(f"Scroll view error: {e}")
            speed = DEFAULT_SCROLL_SPEED

        time.sleep(speed)


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

        if path == "/scroll":
            line1 = qs.get("line1", [""])[0]
            line2 = qs.get("line2", [""])[0]
            if line1 == "" and line2 == "":
                json_response(
                    self, 400, {"error": "provide line1 and/or line2 query param"}
                )
                return

            speed = DEFAULT_SCROLL_SPEED
            if "speed" in qs:
                try:
                    speed = float(qs["speed"][0])
                except ValueError:
                    json_response(self, 400, {"error": "speed must be a number"})
                    return
                speed = min(max(speed, MIN_SCROLL_SPEED), MAX_SCROLL_SPEED)

            gap = qs.get("gap", [DEFAULT_SCROLL_GAP])[0]

            try:
                width = display.line_length
                with scroll_lock:
                    scroll_state.update(
                        line1=line1,
                        line2=line2,
                        offset1=0,
                        offset2=0,
                        speed=speed,
                        gap=gap,
                    )
                    # Draw the first frame here so the response and the display
                    # agree even before the ticker thread's next tick. This is
                    # the one full redraw: whatever the previous view left
                    # behind gets cleared, and from here the ticker only
                    # rewrites lines as they move.
                    frame1 = ticker_frame(line1, 0, width, gap)
                    frame2 = ticker_frame(line2, 0, width, gap)
                    with display_lock:
                        if not display.is_open:
                            display.open()
                        display.set_text(line1=frame1, line2=frame2)
                    scroll_state["frame1"] = frame1
                    scroll_state["frame2"] = frame2

                view_state = "scroll"
                json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "view": "scroll",
                        "line1": line1,
                        "line2": line2,
                        "speed": speed,
                        "gap": gap,
                        "width": width,
                        "scrolling": {
                            "line1": len(line1) > width,
                            "line2": len(line2) > width,
                        },
                    },
                )
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

    # Start the default clock and ticker views in the background. Each only
    # touches the display while its own view is selected.
    threading.Thread(target=default_loop, daemon=True).start()
    threading.Thread(target=scroll_loop, daemon=True).start()

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

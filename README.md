# POS Pricing Display API

A minimal Python project to control an RS-232 POS customer / pricing display from a small HTTP API.

## Hardware

This setup is currently configured for a **Clientron VD1220** 20×2 VFD on `ESC/POS` mode, but the driver also supports `raw` and `cd5220` modes.

## Requirements

- Python 3.10+
- `pyserial` (already installed on this system)
- Membership in the `dialout` group for serial access

Only `pyserial` is required; the API uses the Python standard library.

## Quick start

1. **Serial permissions**

   Add your user to the `dialout` group and re-log in:

   ```bash
   sudo usermod -a -G dialout $USER
   ```

   Then log out and back in. Until then you can run with:

   ```bash
   sg dialout -c "python3 main.py"
   ```

2. **Start the API server**

   ```bash
   cd /home/ppos/Documents/pos-display
   python3 main.py
   ```

   The server binds to `0.0.0.0:8000`.

3. **Default view**

   On startup the display shows:

   ```
       Hello, Devii       (centered)
   2026-08-03 16:45:30    (updates every second)
   ```

4. **Update the display via GET query params**

   ```bash
   curl -G 'http://localhost:8000/display' \
        --data-urlencode 'line1=Sale' \
        --data-urlencode 'line2=$12.34'
   ```

5. **Scroll long text (ticker view)**

   `/scroll` takes the same `line1` / `line2` params, but any line longer than
   the display width (20 chars) scrolls continuously instead of being cut off.
   Lines that already fit stay put, so you can pair a scrolling message with a
   static price.

   ```bash
   curl -G 'http://localhost:8000/scroll' \
        --data-urlencode 'line1=Welcome to Clientron - ask about our specials' \
        --data-urlencode 'line2=$12.34'
   ```

   Optional params:

   - `speed` – seconds between steps (default `0.3`, clamped to `0.05`–`5`).
     Lower is faster.
   - `gap` – blanks shown between the end of the text and the start of the next
     repeat (default three spaces).

   ```bash
   curl -G 'http://localhost:8000/scroll' \
        --data-urlencode 'line1=Fresh coffee, all day' \
        --data-urlencode 'speed=0.15' \
        --data-urlencode 'gap=  ***  '
   ```

   The ticker keeps running until you call `/display` or `/reset`.

6. **Reset to the default clock view**

   ```bash
   curl http://localhost:8000/reset
   ```

7. **Check service status**

   ```bash
   curl http://localhost:8000/health
   ```

## Tailscale access

If Tailscale is running, the API is reachable from any device on your tailnet at:

```
http://<tailscale-ip>:8000/display?line1=Hello&line2=World
```

Replace `<tailscale-ip>` with this device's Tailscale IP (`100.98.42.83`).

## Start on boot (systemd)

A systemd unit file is included: `pos-display.service`.

Install and enable it:

```bash
sudo cp /home/ppos/Documents/pos-display/pos-display.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pos-display
```

It will start automatically on boot after the network and Tailscale are available.

## Files

- `config.json` – serial port, baud rate, and display mode.
- `discover.py` – interactive probe to find the display.
- `display.py` – serial driver (`raw`, `cd5220`, `escpos`).
- `main.py` – HTTP API server with default clock and scrolling ticker views.
- `pos-display.service` – systemd unit for startup.
- `requirements.txt` – only `pyserial`.

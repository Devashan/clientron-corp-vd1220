#!/usr/bin/env python3
"""Low-level serial driver for POS customer/pricing displays."""

import json
import serial
from pathlib import Path


class SerialDisplay:
    """Send text to a serial POS pole / customer display."""

    MODES = {"raw", "escpos", "cd5220"}

    def __init__(self, cfg):
        serial_cfg = cfg.get("serial", {})
        self.port = serial_cfg.get("port")
        self.baud = serial_cfg.get("baud", 9600)
        self.mode = serial_cfg.get("mode", "raw")
        self.timeout = serial_cfg.get("timeout", 1)
        self.encoding = serial_cfg.get("encoding", "ascii")
        self.line_length = serial_cfg.get("line_length", 20)
        self.lines = serial_cfg.get("lines", 2)
        if self.mode not in self.MODES:
            raise ValueError(f"Unsupported mode '{self.mode}'. Use one of {self.MODES}")
        self._ser = None

    @property
    def is_open(self):
        return self._ser is not None and self._ser.is_open

    def open(self):
        if not self.port:
            raise ValueError("No serial port configured (run discover.py first).")
        self._ser = serial.Serial(
            self.port,
            self.baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
        )

    def close(self):
        if self._ser:
            self._ser.close()
            self._ser = None

    def _encode(self, text):
        if text is None:
            return b""
        return text.encode(self.encoding, "replace")

    def set_text(self, text=None, line1=None, line2=None):
        """Write text to the display.

        If `text` is provided it is sent as-is. Otherwise line1/line2 are
        combined depending on the configured mode.
        """
        if not self.is_open:
            self.open()

        if self.mode == "raw":
            data = self._raw_payload(text, line1, line2)
        elif self.mode == "escpos":
            data = self._escpos_payload(text, line1, line2)
        elif self.mode == "cd5220":
            data = self._cd5220_payload(text, line1, line2)

        self._ser.write(data)
        self._ser.flush()

    def _raw_payload(self, text, line1, line2):
        if text is not None:
            return self._encode(text)
        l1 = (line1 or "")[: self.line_length]
        l2 = (line2 or "")[: self.line_length]
        parts = [l1]
        if self.lines > 1:
            parts.append("\n")
            parts.append(l2)
        return self._encode("".join(parts))

    def _escpos_payload(self, text, line1, line2):
        # EPSON ESC/POS customer display commands for CD5220-compatible VFDs.
        # ESC @ (0x1b 0x40) = initialize, 0x0c = clear.
        # US $ x y (0x1f 0x24 x y) = set cursor, x=1-20, y=0x01/0x02.
        init = b"\x1b\x40"
        clear = b"\x0c"
        if text is not None:
            return init + clear + self._encode(text)
        l1 = (line1 or "")[: self.line_length]
        l2 = (line2 or "")[: self.line_length]
        return (
            init
            + clear
            + b"\x1f\x24\x01\x01"
            + self._encode(l1)
            + b"\x1f\x24\x01\x02"
            + self._encode(l2)
        )

    def _cd5220_payload(self, text, line1, line2):
        # CD5220/UTC style VFD commands.
        # ESC @ (0x1b 0x40) = initialize, 0x0c = clear display.
        # ESC Q A <data> CR = upper line, ESC Q B <data> CR = lower line.
        init = b"\x1b\x40"
        clear = b"\x0c"
        if text is not None:
            return init + clear + self._encode(text)
        l1 = (line1 or "")[: self.line_length]
        l2 = (line2 or "")[: self.line_length]
        return (
            init
            + clear
            + b"\x1b\x51\x41"
            + self._encode(l1)
            + b"\x0d"
            + b"\x1b\x51\x42"
            + self._encode(l2)
            + b"\x0d"
        )


def load_config(path="config.json"):
    with open(path) as f:
        return json.load(f)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Send text to the POS display.")
    parser.add_argument("--config", default="config.json", help="Config file path.")
    parser.add_argument("--mode", choices=SerialDisplay.MODES, help="Override mode.")
    parser.add_argument("--line1", default="Hello")
    parser.add_argument("--line2", default="World")
    parser.add_argument("--text", default=None, help="Send raw text instead of lines.")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.mode:
        cfg["serial"]["mode"] = args.mode
    d = SerialDisplay(cfg)
    d.set_text(text=args.text, line1=args.line1, line2=args.line2)
    print(f"Sent to {d.port} at {d.baud} ({d.mode} mode).")
    d.close()


if __name__ == "__main__":
    main()

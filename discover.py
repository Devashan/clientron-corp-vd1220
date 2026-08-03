#!/usr/bin/env python3
"""Interactive probe to find which serial port/baud the display uses."""

import json

from display import SerialDisplay, load_config


def save_config(cfg, path="config.json"):
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)


def probe(port, baud, mode, message="Hello POS display"):
    cfg = {
        "serial": {
            "port": port,
            "baud": baud,
            "mode": mode,
            "timeout": 1,
            "encoding": "ascii",
            "line_length": 20,
            "lines": 2,
        }
    }
    try:
        d = SerialDisplay(cfg)
        d.set_text(line1=message, line2="")
        d.close()
        return True, None
    except Exception as e:
        return False, e


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Find the POS display serial port.")
    parser.add_argument("--mode", default="raw", choices=SerialDisplay.MODES)
    args = parser.parse_args()

    cfg = load_config()
    discovery = cfg.get("discovery", {})
    ports = discovery.get("ports", [f"/dev/ttyS{i}" for i in range(6)])
    bauds = discovery.get("bauds", [9600, 19200])
    message = discovery.get("message", "Hello POS display")

    print("Serial display discovery")
    print("========================")
    print(f"Test message: {message!r}")
    print(f"Protocol mode: {args.mode}")
    print("Look at the physical display and answer the prompts.\n")

    for baud in bauds:
        for port in ports:
            print(f"Trying {port} @ {baud} baud...", end=" ")
            ok, err = probe(port, baud, args.mode, message)
            if not ok:
                print(f"FAILED ({err})")
                continue

            answer = input("Did the display show the test text? (y/n/q): ").strip().lower()
            if answer == "y":
                cfg["serial"]["port"] = port
                cfg["serial"]["baud"] = baud
                cfg["serial"]["mode"] = args.mode
                save_config(cfg)
                print(f"\nSaved: {port} @ {baud} baud ({args.mode} mode) to config.json")
                return 0
            elif answer == "q":
                print("Aborted.")
                return 1

    print("\nNo working combination found.")
    print(f"If the display didn't respond in '{args.mode}' mode, try another mode:")
    print("  python3 discover.py --mode cd5220")
    print("  python3 discover.py --mode escpos")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

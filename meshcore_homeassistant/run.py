"""Translate Supervisor options into the existing server environment."""

import json
import os
import re
import sys


def main():
    with open("/data/options.json", encoding="utf-8") as file:
        options = json.load(file)
    address = options.get("bluetooth_address", "").strip()
    if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", address):
        sys.exit("Set bluetooth_address to the radio's Linux Bluetooth MAC address.")
    os.environ["MESHCORE_ADDR"] = address
    os.environ["MESHCORE_TIMEOUT"] = str(options.get("timeout", 30))
    os.execv(sys.executable, [sys.executable, "/app/src/server.py"])


if __name__ == "__main__":
    main()

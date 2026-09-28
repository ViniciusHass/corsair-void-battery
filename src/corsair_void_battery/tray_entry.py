"""PyInstaller entry point: tray mode is the executable's default."""

from __future__ import annotations

import sys

from corsair_void_battery.cli import main

if __name__ == "__main__":
    main(["--tray", *sys.argv[1:]])

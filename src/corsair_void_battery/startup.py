"""Manage per-user Windows startup for the notification-tray application."""

from __future__ import annotations

import subprocess
import sys
import winreg
from pathlib import Path

APP_NAME = "CorsairVoidBattery"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def startup_command() -> str:
    """Return the command stored in the current user's Run registry key."""

    if getattr(sys, "frozen", False):
        arguments = [sys.executable, "--tray"]
    else:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        arguments = [str(pythonw), "-m", "corsair_void_battery", "--tray"]
    return subprocess.list2cmdline(arguments)


def is_startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
    except FileNotFoundError:
        return False
    return bool(value)


def set_startup_enabled(enabled: bool) -> None:
    """Create or remove the current user's startup registry entry."""

    if enabled:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY,
            access=winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command())
        return

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY,
            access=winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, APP_NAME)
    except FileNotFoundError:
        pass

"""Build a standalone Windows tray executable."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .tray import create_battery_icon

_STOP_TRAY_SCRIPT = r"""
$target = [IO.Path]::GetFullPath($env:CORSAIR_VOID_BUILD_TARGET)
$processes = @(
    Get-Process -Name 'CorsairVoidBattery' -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Path -and [String]::Equals(
                [IO.Path]::GetFullPath($_.Path),
                $target,
                [StringComparison]::OrdinalIgnoreCase
            )
        }
)
if ($processes.Count -eq 0) {
    exit 0
}
$processes | Stop-Process -Force
exit 10
"""


def _stop_running_tray(executable: Path) -> bool:
    """Stop only tray processes running from the exact build output path."""

    powershell = shutil.which("powershell.exe")
    if powershell is None:
        return False

    environment = os.environ.copy()
    environment["CORSAIR_VOID_BUILD_TARGET"] = str(executable.resolve())
    completed = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", _STOP_TRAY_SCRIPT],
        capture_output=True,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
        env=environment,
        text=True,
    )
    if completed.returncode == 10:
        return True
    if completed.returncode != 0:
        error = completed.stderr.strip() or "unknown PowerShell error"
        raise RuntimeError(f"could not stop the existing tray executable: {error}")
    return False


def _start_tray(executable: Path) -> None:
    subprocess.Popen(
        [str(executable)],
        close_fds=True,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )


def build_tray_executable() -> Path:
    """Build and return ``dist/CorsairVoidBattery.exe`` with PyInstaller."""

    import PyInstaller.__main__

    project_root = Path(__file__).resolve().parents[2]
    build_directory = project_root / "build" / "pyinstaller"
    distribution_directory = project_root / "dist"
    executable = distribution_directory / "CorsairVoidBattery.exe"
    icon_path = build_directory / "CorsairVoidBattery.ico"
    build_directory.mkdir(parents=True, exist_ok=True)
    create_battery_icon(75).save(
        icon_path,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)],
    )

    tray_was_running = _stop_running_tray(executable) if executable.exists() else False
    try:
        PyInstaller.__main__.run(
            [
                str(project_root / "src" / "corsair_void_battery" / "tray_entry.py"),
                "--name=CorsairVoidBattery",
                "--onefile",
                "--windowed",
                "--clean",
                "--noconfirm",
                f"--icon={icon_path}",
                f"--paths={project_root / 'src'}",
                "--hidden-import=pystray._win32",
                f"--distpath={distribution_directory}",
                f"--workpath={build_directory / 'work'}",
                f"--specpath={build_directory}",
            ]
        )
    finally:
        if tray_was_running and executable.exists():
            _start_tray(executable)
    return executable

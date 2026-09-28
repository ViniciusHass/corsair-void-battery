# Corsair VOID Wireless V2 battery probe

Small Windows utility for enumerating Corsair HID interfaces and probing the
Corsair VOID Wireless V2 2.4 GHz receiver for battery data.

## Setup

Requires Python 3.14 and [uv](https://docs.astral.sh/uv/).

```powershell
uv sync
```

The project targets Python 3.12 syntax/style in Ruff and mypy, while the local
uv environment is pinned to Python 3.14.

Run the checks with:

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run python -m unittest discover -s tests
```

## Run the monitor

```powershell
uv run corsair-void-battery
```

The normal path reads the receiver directly through raw HID. iCUE and its SDK
are not required, and the query works whether iCUE is open or closed.

The default command runs continuously and redraws a single status line:

```text
Corsair VOID Wireless V2 [###########---------]  54% (HID) | next check in 60s
```

It checks the battery every 60 seconds while connected. If the dongle is
unplugged, it keeps running and re-enumerates after 10 minutes, so reconnecting
it in the same or another USB port is handled automatically. Change either
interval with `--watch SECONDS` and `--retry-seconds SECONDS`.
The plain command stays alive until you press `Ctrl+C`; `--once` is the only
normal monitoring option that exits after one reading.

The iCUE SDK is available only as an explicit optional mode:

```powershell
uv sync --extra icue
uv run --extra icue corsair-void-battery --icue --once
```

Without `--icue`, the SDK is neither imported nor started. The SDK runs in an
isolated worker when requested, so a native SDK crash cannot terminate the
battery utility itself.

For a single check instead of continuous monitoring, use:

```powershell
uv run corsair-void-battery --once
```

## Windows notification tray

Run the monitor in the notification area beside the Windows clock:

```powershell
uv run corsair-void-battery --tray
```

The tray icon shows the battery state. Hover over it for the exact percentage,
or right-click it to refresh, enable or disable **Start with Windows**, and
exit. Install startup directly from the command line with:

```powershell
uv run corsair-void-battery --install-startup
```

Startup uses the project's `pythonw.exe`, so Windows launches the tray monitor
without opening a terminal. Remove it with
`uv run corsair-void-battery --remove-startup`.

### Build a standalone executable

Other Windows users can clone or extract the source and build a no-console tray
executable on their own machine:

```powershell
uv sync --extra build
uv run --extra build corsair-void-battery --build-executable
```

The result is `dist/CorsairVoidBattery.exe`. Double-clicking it starts directly
in the notification tray without a console window. The persistent console
monitor remains the default behavior of the normal `corsair-void-battery`
command. If that executable is already running, the builder stops only the
matching tray process, replaces the file, and starts the tray again.

For a short retry interval while testing:

```powershell
uv run corsair-void-battery --retry-seconds 5
```

Add `--diagnostic` to display every Corsair HID interface and raw response.

The diagnostic lists the Corsair VID/PID, HID interface, usage page, usage,
raw reports, and any parsed battery response. Use JSON output when capturing
reports for protocol work:

```powershell
uv run corsair-void-battery --json --once
```

The known VOID Wireless V2 receiver is `VID 0x1B1C`, `PID 0x2A08`, interface
`4`, usage page `0xFF42`, usage `1`. The utility uses the V2 receiver handshake
and battery request. It temporarily enables software mode for the query and
restores hardware mode before closing the device. The Windows report
descriptor requires a 64-byte output report with report ID `2`; the probe uses
that size and rejects invalid or unsolicited packets instead of displaying a
guessed battery level.

If the output says `Battery unavailable`, the receiver was found but the
headset did not answer the V2 battery request. Make sure the headset is powered
on and paired to the dongle. The receiver can still enumerate on Windows while
its vendor battery endpoint is unavailable.

## Commits and releases

Commit messages should use [Conventional Commits](https://www.conventionalcommits.org/).
Semantic Versioning (SemVer) applies to release numbers, not directly to commit
messages. The commit format is:

```text
<type>[optional scope]: <description>
```

Examples:

```text
fix(hid): handle a disconnected receiver
feat(tray): add a refresh menu item
docs: explain the release process
test(protocol): cover a new battery report
```

The commit type communicates the intended SemVer change:

- `fix:` normally produces a PATCH release, such as `0.1.1`.
- `feat:` normally produces a MINOR release, such as `0.2.0`.
- A `!` after the type or scope, or a `BREAKING CHANGE:` footer, produces a
  MAJOR release, such as `1.0.0`.
- `docs:`, `test:`, `refactor:`, `chore:`, and `ci:` normally do not create a
  release unless they include a breaking change.

### Automatic releases on `main`

[Python Semantic Release](https://python-semantic-release.readthedocs.io/) can
read these commit messages and, after a change reaches `main`:

1. Determine the next SemVer version.
2. Update `project.version` in `pyproject.toml`.
3. Update the changelog.
4. Commit the version change.
5. Create a tag such as `v0.2.0`.
6. Create a GitHub release.

The project configuration for this tool is:

```toml
[tool.semantic_release]
version_toml = ["pyproject.toml:project.version"]
tag_format = "v{version}"
build_command = "python -m pip install uv && uv lock"
```

The release workflow runs only after changes reach `main` and needs
`contents: write` permission. It is stored in
`.github/workflows/release.yml` and has this core structure:

```yaml
name: Release

on:
  push:
    branches: ["main"]

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: python-semantic-release/python-semantic-release@v10.7.0
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          push: "true"
          tag: "true"
          vcs_release: "true"
```

The validation workflow checks every change; this separate release workflow
makes a version commit and tag only on `main`. The existing `v0.1.0` tag is the
initial release baseline. Make sure it is pushed to GitHub before the first
automatic release if it is not already there:

```powershell
git push origin v0.1.0
```

## License

Licensed under the [MIT License](LICENSE). You may use, copy, modify, and
distribute this project subject to the license terms.

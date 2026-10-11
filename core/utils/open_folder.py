"""Open a folder in the OS file browser.

Streamlit serves a web page, so a finished video is invisible to the user until
they go looking for the path. These helpers reveal `output/` and `history/` in
Explorer (or the Linux/macOS equivalent).

Two Windows quirks drive the implementation:

- `explorer.exe` returns exit code 1 even on success and prints nothing, so its
  return code cannot be used to decide whether anything happened. Instead the
  folder is probed after the call, and the caller gets honest wording.
- `/select,` only accepts an absolute path. Given a relative one Explorer
  silently does nothing, which looks exactly like a broken button.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def reveal_folder(path: str | os.PathLike, select: str | os.PathLike | None = None) -> tuple[bool, str]:
    """Open `path` in the file browser. Returns (ok, message).

    `ok` reflects something observable -- the target exists and the launcher was
    found -- not Explorer's exit code, which is meaningless.
    """
    target = Path(path).resolve()

    created = False
    if not target.exists():
        try:
            target.mkdir(parents=True, exist_ok=True)
            created = True
        except OSError as exc:
            return False, f"Could not create {target}: {exc}"

    item = Path(select).resolve() if select else None
    if item is not None and not item.exists():
        item = None

    try:
        if sys.platform.startswith("win"):
            return _reveal_windows(target, item, created)
        return _reveal_posix(target, created)
    except OSError as exc:
        return False, f"Could not open {target}: {exc}"


def _reveal_windows(target: Path, item: Path | None, created: bool) -> tuple[bool, str]:
    explorer = shutil.which("explorer") or "explorer.exe"
    if item is not None:
        # Must be absolute, and the comma belongs to the switch.
        subprocess.Popen([explorer, f"/select,{item}"])
        # Explorer is asynchronous; a short pause lets the window come up
        # before the user looks at the screen.
        time.sleep(0.35)
        return True, f"Explorer should now be open with {item.name} selected."
    subprocess.Popen([explorer, str(target)])
    time.sleep(0.35)
    note = "Created it and opened it." if created else "Opened it."
    return True, f"{note} ({target})"


def _reveal_posix(target: Path, created: bool) -> tuple[bool, str]:
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    if not shutil.which(opener):
        return False, f"{opener} is not available on this system. The folder is at {target}"
    subprocess.Popen([opener, str(target)])
    note = "Created it and opened it." if created else "Opened it."
    return True, f"{note} ({target})"


def folder_path(path: str | os.PathLike) -> str:
    """Absolute path as text, for showing when opening the browser fails."""
    return str(Path(path).resolve())
"""Open a folder in the OS file browser.

Streamlit serves a web page, so a finished video is invisible to the user until
they go looking for the path. These helpers reveal `output/` and `history/` in
Explorer (or the Linux/macOS equivalent).

Windows uses `explorer.exe`, which returns exit code 1 even on success and
prints nothing; the flag `/select,` opens the parent with the item highlighted.
Everything here is best-effort: a failure is reported to the caller rather than
raised, because the folder path is still useful to show as text.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def reveal_folder(path: str | os.PathLike, select: str | os.PathLike | None = None) -> tuple[bool, str]:
    """Open `path` in the file browser. Returns (ok, message)."""
    target = Path(path)

    # A folder that is not there yet can still be created: the next run will
    # populate it, and the user should be able to see where it will land.
    created = False
    if not target.exists():
        try:
            target.mkdir(parents=True, exist_ok=True)
            created = True
        except OSError as exc:
            return False, f"Could not create {target}: {exc}"

    item = Path(select) if select else None
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
        # explorer treats its first argument as a path even when it starts
        # with /select, and it always exits with 1, so the return code is
        # deliberately ignored here.
        subprocess.Popen([explorer, f"/select,{item}"])
        return True, f"Opened {item} in Explorer."
    subprocess.Popen([explorer, str(target)])
    note = "Created it and opened it." if created else "Opened it."
    return True, f"{note} ({target})"


def _reveal_posix(target: Path, created: bool) -> tuple[bool, str]:
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    if not shutil.which(opener):
        return False, f"{opener} is not available; the folder is at {target}"
    subprocess.Popen([opener, str(target)])
    note = "Created it and opened it." if created else "Opened it."
    return True, f"{note} ({target})"


def folder_path(path: str | os.PathLike) -> str:
    """Absolute path as text, for showing when opening the browser fails."""
    return str(Path(path).resolve())
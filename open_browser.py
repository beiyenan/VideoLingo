"""Open VideoLingo in the browser once it actually answers.

Called by open_browser.bat. Polls the health endpoint instead of sleeping for a
fixed time: a fixed 15s sleep opens the browser before a slow start is ready,
and needlessly delays a fast one.

With --check it only reports whether the server is already up (used by the
launcher to avoid starting a second instance on an occupied port).

Exit codes: 0 = server answered (and browser opened, unless --check), 1 = timed out.
"""
import subprocess
import sys
import time
import urllib.error
import urllib.request

CHECK_ONLY = "--check" in sys.argv
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
URL = ARGS[0] if ARGS else "http://localhost:8501"
HEALTH = URL.rstrip("/") + "/_stcore/health"
TIMEOUT_SECONDS = 120


def is_up():
    try:
        with urllib.request.urlopen(HEALTH, timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def wait_until_ready(deadline):
    while time.time() < deadline:
        if is_up():
            return True
        time.sleep(1)
    return False


def main():
    # --check is instant: the launcher only needs to know "already running?".
    if CHECK_ONLY:
        return 0 if is_up() else 1
    if not wait_until_ready(time.time() + TIMEOUT_SECONDS):
        print("VideoLingo did not answer within %d seconds." % TIMEOUT_SECONDS)
        print("Please visit %s manually once it is running." % URL)
        return 1
    subprocess.Popen(["cmd", "/c", "start", "", URL])
    return 0


if __name__ == "__main__":
    sys.exit(main())
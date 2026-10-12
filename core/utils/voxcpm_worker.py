"""Release the VRAM the local VoxCPM dubbing worker is holding.

The worker is deliberately persistent - it loads the 2B model once and then
serves one job per subtitle line, which saves ~35s per line. The flip side is
that it keeps its weights in VRAM while idle. Local ASR (Qwen3-ASR) needs
several GB of its own, so on an 8GB card the two cannot coexist: the ASR stage
has to let the worker go before it loads its model.

Stopping it is safe - the next dubbing run starts a fresh one, the only cost
being the one-off load. It is refused while jobs are still in flight, so a
dubbing run in progress is never cut short.
"""

import time
from pathlib import Path

from core.utils.config_utils import load_key

WORKER_MARK = "videolingo_worker.py"


def root() -> Path:
    return Path(str(load_key("voxcpm.root") or r"E:\VoxCPM"))


def job_dir() -> Path:
    return root() / "videolingo_jobs"


def _pid_from_marker() -> int | None:
    pid_file = job_dir() / "WORKER_PID"
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _live_worker_pids() -> list[int]:
    """Every running process that looks like the VoxCPM worker.

    The marker only knows about the worker this checkout started last, and an
    older one (another interpreter, an earlier install) can still be alive and
    holding memory, so match on the command line as well.
    """
    pids = set()
    marked = _pid_from_marker()
    if marked:
        pids.add(marked)
    try:
        import psutil

        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmdline = proc.info.get("cmdline") or []
            except Exception:
                continue
            if any(WORKER_MARK in str(part) for part in cmdline):
                pids.add(int(proc.info["pid"]))
    except Exception:
        # psutil missing or a process vanished mid-scan: the marker alone is
        # still enough for the common case.
        pass
    return sorted(pid for pid in pids if _alive(pid))


def _alive(pid) -> bool:
    try:
        import psutil

        return psutil.pid_exists(int(pid)) and psutil.Process(int(pid)).is_running()
    except Exception:
        return False


def is_running() -> bool:
    return bool(_live_worker_pids())


def busy() -> bool:
    """True while a dubbing job has been posted but not answered yet."""
    directory = job_dir()
    if not directory.is_dir():
        return False
    for request in directory.glob("*.json"):
        if request.stem == "WORKER_READY":
            continue
        if not request.with_suffix(".done").exists() and not request.with_suffix(".error").exists():
            return True
    return False


def _clear_markers():
    for name in ("WORKER_READY", "WORKER_PID"):
        try:
            (job_dir() / name).unlink()
        except (FileNotFoundError, OSError):
            # A safe-delete shim can reject this; the marker being stale is
            # harmless, custom_tts re-checks the PID before trusting it.
            pass


def stop(timeout: float = 15.0) -> tuple[str, str]:
    """Stop the worker. Returns ("stopped" | "idle" | "busy", message)."""
    pids = _live_worker_pids()
    if not pids:
        _clear_markers()
        return "idle", "The dubbing worker was not running."
    if busy():
        return "busy", (
            "The dubbing worker is still generating audio, so it was left alone. "
            "Wait for the dubbing to finish, then switch the recognition runtime again."
        )

    killed = []
    for pid in pids:
        try:
            import psutil

            proc = psutil.Process(pid)
            proc.terminate()
            killed.append(proc)
        except Exception:
            pass

    deadline = time.time() + timeout
    while time.time() < deadline and _live_worker_pids():
        time.sleep(0.3)
    # A worker that ignored SIGTERM (a stuck CUDA call) has to be forced.
    for proc in killed:
        try:
            if proc.is_running():
                proc.kill()
        except Exception:
            pass

    still = _live_worker_pids()
    if still:
        return "busy", f"The dubbing worker (PID {', '.join(map(str, still))}) did not exit."

    _clear_markers()
    return "stopped", f"Stopped the dubbing worker to free its VRAM (PID {', '.join(map(str, pids))})."

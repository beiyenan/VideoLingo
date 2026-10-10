"""VideoLingo custom TTS backend backed by a local VoxCPM2 worker.

Design notes
------------
VoxCPM2 is a 2B model: loading it costs ~20s. VideoLingo synthesises one file
per subtitle line, so a naive subprocess call per line would reload the model
hundreds of times. Instead a long-lived worker (``videolingo_worker.py`` in the
VoxCPM folder) loads once and consumes JSON job files from a shared directory.

If the worker is not running, this backend starts it automatically and waits for
it to report READY, so a cold start costs the load time only once.
"""

import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

from rich import print as rprint
from core.utils import *

# Root of the local VoxCPM2 installation (the folder holding models/ and venv/).
# Override it with `voxcpm.root` in config.yaml when it lives somewhere else.
VOXCPM_ROOT = Path(str(load_key("voxcpm.root") or r"E:\VoxCPM"))
VOXCPM_PYTHON = VOXCPM_ROOT / "venv" / "Scripts" / "python.exe"
WORKER_SCRIPT = VOXCPM_ROOT / "videolingo_worker.py"
JOB_DIR = VOXCPM_ROOT / "videolingo_jobs"
WORKER_LOG = VOXCPM_ROOT / "worker.log"

# Where _9_refer_audio.py cuts the original speaker out of the current video.
REFERS_DIR = Path("output") / "audio" / "refers"

# A line longer than this gets split by the worker on punctuation.
SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？；!?;,.，、\n])")


def _safe_unlink(path):
    """Remove a file without tripping the environment's safe-delete shim.

    Path.unlink()/os.remove can raise when the recycle-bin fallback fails, which
    would break the job bookkeeping below.
    """
    try:
        os.remove(str(path))
    except (FileNotFoundError, OSError):
        pass


def _cfg():
    ref = str(load_key("voxcpm.reference_wav") or "").strip()
    if ref and not Path(ref).is_absolute():
        # Same cwd mismatch as save_path: anchor it to the VideoLingo repo.
        ref = str(Path(ref).resolve())
    return {
        "reference_wav": ref,
        "cfg_value": float(load_key("voxcpm.cfg_value") or 2.0),
        "inference_timesteps": int(load_key("voxcpm.inference_timesteps") or 10),
    }


def _refer_mode():
    try:
        return int(load_key("voxcpm.refer_mode") or 2)
    except (TypeError, ValueError):
        return 2


def _clip_from_video(number, mode):
    """Pick the reference clip for one line out of the current video's audio.

    mode 2 -> the first clip, i.e. one voice for the whole video
    mode 3 -> the clip belonging to this very line, so a multi-speaker video
              keeps each speaker with their own voice
    """
    candidates = []
    if mode == 3 and number is not None:
        candidates.append(REFERS_DIR / f"{number}.wav")
    # Fall back to clip 1 so a missing per-line clip degrades to a single voice
    # instead of dropping into a random one.
    candidates.append(REFERS_DIR / "1.wav")
    for path in candidates:
        if path.is_file():
            return str(path.resolve())
    return None


def _resolve_reference(number):
    """Return the reference audio path for this line, per the chosen mode."""
    mode = _refer_mode()
    if mode == 1:
        return _cfg()["reference_wav"] or None
    if mode == 4:
        return None
    clip = _clip_from_video(number, mode)
    if clip is None:
        raise RuntimeError(
            f"VoxCPM refer mode {mode} needs the original audio clips in {REFERS_DIR.resolve()}, "
            f"but none were found. Run the 'Extract reference audio' step, or switch the "
            f"reference mode in the sidebar to 1 (your own file) or 4 (random voice)."
        )
    return clip


def _worker_is_alive():
    """True when a READY marker exists and the PID it names is still running."""
    ready = JOB_DIR / "WORKER_READY"
    pid_file = JOB_DIR / "WORKER_PID"
    if not ready.exists() or not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except Exception:
        return False
    return _pid_alive(pid)


def _pid_alive(pid):
    """Cheap cross-platform liveness check that avoids spawning tasklist."""
    try:
        if sys.platform.startswith("win"):
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not handle:
                return False
            try:
                code = ctypes.c_ulong()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return code.value == STILL_ACTIVE
                return False
            finally:
                kernel32.CloseHandle(handle)
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def _start_worker():
    if not VOXCPM_PYTHON.exists():
        raise RuntimeError(f"VoxCPM venv python not found: {VOXCPM_PYTHON}")
    if not WORKER_SCRIPT.exists():
        raise RuntimeError(f"VoxCPM worker script not found: {WORKER_SCRIPT}")
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    rprint(f"[cyan]Starting persistent VoxCPM worker (first load ~20-40s)...[/cyan]")
    env = dict(os.environ)
    env["VOXCPM_JOB_DIR"] = str(JOB_DIR)
    env["VOXCPM_MODEL_PATH"] = str(VOXCPM_ROOT / "models")
    env.setdefault("VOXCPM_DEVICE", "cuda")
    log = open(WORKER_LOG, "a", encoding="utf-8", buffering=1)
    # DETACHED_PROCESS + own console so the worker survives VideoLingo exiting.
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(
        [str(VOXCPM_PYTHON), str(WORKER_SCRIPT)],
        cwd=str(VOXCPM_ROOT),
        stdout=log,
        stderr=log,
        env=env,
        creationflags=flags,
        close_fds=True,
    )


def _submit(job, timeout=1800):
    """Drop a job file, wait for .done/.error. Returns None on success."""
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    name = f"vl_{uuid.uuid4().hex[:12]}"
    req = JOB_DIR / f"{name}.json"
    done = JOB_DIR / f"{name}.done"
    err = JOB_DIR / f"{name}.error"
    req.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")

    deadline = time.time() + timeout
    while time.time() < deadline:
        if done.exists():
            _safe_unlink(done)
            return None
        if err.exists():
            tb = err.read_text(encoding="utf-8", errors="replace")
            _safe_unlink(err)
            raise RuntimeError(f"VoxCPM worker failed:\n{tb[-1500:]}")
        time.sleep(0.2)
    raise TimeoutError(f"VoxCPM worker timed out after {timeout}s for job {name}")


def _ensure_worker():
    """Make sure a worker is up; start one if it is not."""
    if _worker_is_alive():
        return
    # Stale markers from a killed worker would confuse the check.
    _safe_unlink(JOB_DIR / "WORKER_READY")
    _safe_unlink(JOB_DIR / "WORKER_PID")
    _start_worker()
    t0 = time.time()
    deadline = t0 + 300
    while time.time() < deadline:
        if _worker_is_alive():
            rprint(f"[green]VoxCPM worker ready ({time.time() - t0:.1f}s)[/green]")
            return
        time.sleep(1.0)
    raise RuntimeError(
        "VoxCPM worker did not become ready. Check E:\\VoxCPM\\worker.log for details."
    )


def custom_tts(text, save_path, number=None, task_df=None):
    """VideoLingo TTS hook: write Chinese speech to `save_path`.

    Uses the persistent local VoxCPM2 worker so the model is loaded only once.

    `number` is the subtitle index, used by refer mode 3 to pick that line's
    own clip out of the video as the voice reference.
    """
    if not text or not str(text).strip():
        return
    text = str(text).strip()
    # VideoLingo passes repo-relative paths such as
    # "output/audio/tmp/1_0_temp.wav", but the worker runs with its own working
    # directory (E:\VoxCPM). Resolve against this process' cwd so the audio
    # lands where VideoLingo looks for it.
    save_path = Path(save_path).resolve()
    save_path.parent.mkdir(parents=True, exist_ok=True)

    conf = _cfg()
    reference = _resolve_reference(number)
    mode = _refer_mode()
    if reference:
        rprint(f"[cyan]VoxCPM ref mode {mode}: {Path(reference).name}[/cyan]")
    else:
        rprint("[yellow]VoxCPM has no reference audio; this line gets a random voice.[/yellow]")
    # The worker returns 48kHz wav; VideoLingo rescales later in the pipeline.
    _ensure_worker()
    _submit({
        "text": text,
        "output": str(save_path),
        "reference_wav": reference or "",
        "cfg_value": conf["cfg_value"],
        "inference_timesteps": conf["inference_timesteps"],
    })

    if not save_path.exists():
        raise RuntimeError(f"VoxCPM produced no audio at {save_path}")
    rprint(f"[green]VoxCPM2 wrote {save_path.name}[/green]")


if __name__ == "__main__":
    out = "custom_tts_test.wav"
    custom_tts("你好，这是一段通过 VideoLingo 接口生成的测试语音。", out)
    print("saved:", out)

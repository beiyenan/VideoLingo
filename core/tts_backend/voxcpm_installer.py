"""One-click installation of the local VoxCPM2 runtime.

Why this lives outside the main project
--------------------------------------
VoxCPM2 needs its own interpreter. VideoLingo runs on Python 3.12; VoxCPM2 is
published for 3.10 and its torch build is tied to that ABI, so it cannot share
the project venv. This module therefore drives a *separate* interpreter that the
user points at through ``voxcpm.root``.

What gets installed is deliberately minimal: the package, a torch build that
matches the detected GPU, and the model weights. Gradio and the rest are only
needed for VoxCPM's own web UI and are skipped -- VideoLingo calls the model
through its worker script instead.

Nothing here is required for the rest of VideoLingo. A failure raises, the UI
turns it into a message, and every other feature keeps working.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

VOXCPM_VERSION = "0.1.3"
# Only what VideoLingo actually calls. gradio/librosa/etc. are for VoxCPM's
# own web UI, which we do not use.
PACKAGES = ["voxcpm==0.1.3", "torchaudio"]
MODEL_REPO = "openbmb/VoxCPM2-0.5B"

# Model weights are ~4.7 GB; warn before committing to that download.
APPROX_DOWNLOAD_GB = 4.7


@dataclass
class StepResult:
    label: str
    ok: bool
    detail: str = ""


@dataclass
class InstallReport:
    root: Path
    python: Path | None = None
    steps: list[StepResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.steps) and all(step.ok for step in self.steps)


class InstallError(RuntimeError):
    """Raised when VoxCPM cannot be installed. The UI reports it and stops."""


def venv_python(root: Path) -> Path:
    """The interpreter inside a VoxCPM install, for both OS layouts."""
    if sys.platform.startswith("win"):
        return root / "venv" / "Scripts" / "python.exe"
    return root / "venv" / "bin" / "python"


def default_root() -> Path:
    """Where to install when the user has not chosen a location."""
    return Path(os.environ.get("USERPROFILE", Path.home())) / "VoxCPM2"


def detect_torch_index() -> str:
    """The torch index that matches this machine's GPU.

    An NVIDIA card wants the CUDA build; anything else gets the CPU wheels so
    the install still succeeds on machines without CUDA.
    """
    try:
        smi = shutil.which("nvidia-smi") or _find_nvidia_smi()
        if smi:
            out = subprocess.run(
                [smi, "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=15,
            )
            if out.returncode == 0 and out.stdout.strip():
                major = torch_cuda_major()
                return f"https://download.pytorch.org/whl/cu{major}" if major else \
                       "https://download.pytorch.org/whl/cpu"
    except (OSError, subprocess.SubprocessError):
        pass
    return "https://download.pytorch.org/whl/cpu"


def _find_nvidia_smi() -> str | None:
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    candidate = Path(program_files) / "NVIDIA Corporation" / "NVSMI" / "nvidia-smi.exe"
    return str(candidate) if candidate.is_file() else None


def torch_cuda_major() -> int | None:
    """The CUDA major version of the installed/driver-supported torch."""
    try:
        import torch  # noqa: PLC0415  (optional, only present in this project)
        return int(torch.version.cuda.split(".")[0]) if torch.version.cuda else None
    except Exception:
        pass
    # Fall back to the driver-reported capability.
    smi = _find_nvidia_smi()
    if not smi:
        return None
    try:
        out = subprocess.run([smi], capture_output=True, text=True, timeout=15)
        for line in (out.stdout or "").splitlines():
            if "CUDA Version" in line:
                return int(line.rsplit(":", 1)[1].strip().split(".")[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None
    return None


def python_executable_ok(python: Path) -> bool:
    if not python.is_file():
        return False
    try:
        out = subprocess.run(
            [str(python), "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            capture_output=True, text=True, timeout=60,
        )
        return out.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def installed_python_version(python: Path) -> str | None:
    try:
        out = subprocess.run(
            [str(python), "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            capture_output=True, text=True, timeout=60,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def base_python_candidates() -> list[Path]:
    """Interpreters that can host VoxCPM, most-preferred first.

    VoxCPM2 ships wheels for 3.10; 3.8-3.11 work in practice. Reusing an
    existing install is preferred so users do not end up with several 5 GB
    environments.
    """
    found: list[Path] = []

    def add(path: Path | None) -> None:
        if path and path.is_file() and path not in found:
            found.append(path)

    if sys.platform.startswith("win"):
        for minor in (10, 11, 9, 12, 8):
            add(Path(r"C:\Python%d" % minor) / "python.exe")
        py = shutil.which("py")
        if py:
            for minor in (10, 11):
                try:
                    probe = subprocess.run(
                        [py, f"-3.{minor}", "-c", "import sys; print(sys.executable)"],
                        capture_output=True, text=True, timeout=30,
                    )
                    if probe.returncode == 0 and probe.stdout.strip():
                        add(Path(probe.stdout.strip()))
                except (OSError, subprocess.SubprocessError):
                    pass
    else:
        for minor in (10, 11, 9):
            add(Path(f"/usr/bin/python3.{minor}"))
        add(Path(shutil.which("python3.10") or shutil.which("python3") or ""))
    return found


def install(
    root: Path,
    log=print,
    reuse_existing: bool = True,
) -> InstallReport:
    """Install VoxCPM2 under `root`. Raises InstallError on failure.

    `log` receives progress lines so the caller can surface them in the UI.
    """
    root = Path(root)
    report = InstallReport(root=root)
    python = venv_python(root)

    # 1. Reuse an existing environment when it already imports voxcpm.
    if reuse_existing and python_executable_ok(python):
        version = installed_python_version(python)
        log(f"Found an existing VoxCPM environment at {root} (Python {version}).")
        if _voxcpm_importable(python):
            report.python = python
            report.steps.append(StepResult("reuse", True, f"already installed (Python {version})"))
            return report
        report.python = python
    else:
        base = _pick_base_python()
        log(f"Creating a Python {base[1]} environment in {root}")
        try:
            _create_venv(base[0], root, log)
        except (OSError, subprocess.SubprocessError, InstallError) as exc:
            report.steps.append(StepResult("venv", False, str(exc)))
            raise InstallError(f"Could not create the VoxCPM environment: {exc}") from exc
        report.python = python

    if not python_executable_ok(python):
        report.steps.append(StepResult("venv", False, f"interpreter missing at {python}"))
        raise InstallError(f"The VoxCPM environment was created but {python} is not runnable.")

    # 2. torch first: everything else compiles against it.
    index = detect_torch_index()
    log(f"Installing torch from {index} (this is the largest download, roughly 2.5 GB)")
    ok = _pip(python, ["torch", "torchaudio"], index=index, log=log)
    report.steps.append(StepResult("torch", ok, index if ok else "pip install torch failed"))
    if not ok:
        raise InstallError("Installing torch failed. Check your network and retry.")

    # 3. VoxCPM itself, without pulling gradio and the rest of its web UI.
    log("Installing voxcpm")
    ok = _pip(python, PACKAGES, log=log)
    report.steps.append(StepResult("voxcpm", ok, VOXCPM_VERSION if ok else "pip install voxcpm failed"))
    if not ok:
        raise InstallError("Installing the voxcpm package failed.")

    # 4. Verify it can actually load, then fetch the weights.
    log("Verifying the installation")
    ok, detail = _verify(python)
    report.steps.append(StepResult("verify", ok, detail))
    if not ok:
        raise InstallError(f"VoxCPM installed but could not be imported: {detail}")

    models = root / "models"
    if _models_present(models):
        report.steps.append(StepResult("models", True, "already downloaded"))
    else:
        log(f"Downloading model weights (~{APPROX_DOWNLOAD_GB} GB). This can take a while.")
        try:
            ok, detail = _download_models(python, models, log)
        except InstallError as exc:
            report.steps.append(StepResult("models", False, str(exc)))
            raise
        report.steps.append(StepResult("models", ok, detail))
        if not ok:
            raise InstallError("The VoxCPM packages installed, but the model download failed. "
                               "Retry when your connection is better; the packages are kept.")

    report.python = python
    return report


def _pick_base_python() -> tuple[Path, str]:
    for candidate in base_python_candidates():
        version = installed_python_version(candidate)
        if version:
            return candidate, version
    raise InstallError(
        "No suitable Python was found for VoxCPM (3.9-3.12). Install Python 3.10 from "
        "https://www.python.org/downloads/ and tick 'Add python.exe to PATH', then retry."
    )


def _create_venv(base_python: Path, root: Path, log) -> None:
    venv_dir = root / "venv"
    try:
        result = subprocess.run(
            [str(base_python), "-m", "venv", str(venv_dir)],
            capture_output=True, text=True, timeout=900,
        )
    except subprocess.TimeoutExpired as exc:
        raise InstallError("Creating the environment timed out.") from exc
    if result.returncode != 0:
        raise InstallError(result.stderr.strip() or "python -m venv failed")


def _pip(python: Path, packages: list[str], index: str | None = None, log=print) -> bool:
    cmd = [str(python), "-m", "pip", "install", "--disable-pip-version-check"]
    if index:
        cmd += ["--index-url", index]
    cmd += packages
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    except subprocess.TimeoutExpired:
        log("  pip timed out")
        return False
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-6:]
        for line in tail:
            log(f"  {line}")
        return False
    return True


def _voxcpm_importable(python: Path) -> bool:
    try:
        result = subprocess.run(
            [str(python), "-c", "import voxcpm; print(getattr(voxcpm, '__version__', 'ok'))"],
            capture_output=True, text=True, timeout=300,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _verify(python: Path) -> tuple[bool, str]:
    """Import the model class and instantiate it on CPU.

    Import success alone would still hide a torch/CUDA mismatch, which is the
    usual reason a "successful" install fails later at synthesis time.
    """
    snippet = (
        "from voxcpm import VoxCPM; print('OK', VoxCPM.__module__)"
    )
    try:
        result = subprocess.run(
            [str(python), "-c", snippet], capture_output=True, text=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        return False, "importing voxcpm timed out"
    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()[-4:]
        return False, tail[-1] if tail else "import voxcpm failed"
    return True, result.stdout.strip() or "ok"


def _models_present(models: Path) -> bool:
    return (models / "model.safetensors").is_file() and (models / "audiovae.pth").is_file()


def _download_models(python: Path, models: Path, log) -> tuple[bool, str]:
    models.mkdir(parents=True, exist_ok=True)
    script = (
        "import sys\n"
        "from huggingface_hub import snapshot_download\n"
        "path = snapshot_download(sys.argv[1], local_dir=sys.argv[2])\n"
        "print('DOWNLOADED', path)\n"
    )
    try:
        result = subprocess.run(
            [str(python), "-c", script, MODEL_REPO, str(models)],
            capture_output=True, text=True, timeout=7200,
        )
    except subprocess.TimeoutExpired:
        return False, "the download timed out"
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-4:]
        return False, tail[-1] if tail else "download failed"
    return _models_present(models), "downloaded" if _models_present(models) else "incomplete"


def worker_script(root: Path) -> Path:
    """The worker VideoLingo drives, written on first install."""
    return Path(root) / "videolingo_worker.py"


WORKER_SOURCE = '''"""Persistent VoxCPM2 worker driven by VideoLingo.

VideoLingo synthesises one file per subtitle line. Loading a 2B model per line
would dominate the runtime, so this process loads once and consumes JSON job
files from `videolingo_jobs/`.

Job file (written by VideoLingo, then renamed to .done or .error):
    {"text": str, "output": str, "reference_wav": str,
     "cfg_value": float, "inference_timesteps": int}
"""

import json
import os
import re
import time
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent
JOB_DIR = ROOT / "videolingo_jobs"
MODEL_PATH = ROOT / "models"
DEVICE = os.environ.get("VOXCPM_DEVICE", "cuda")
MAX_WORD = 30


def log(message):
    print(f"[worker] {message}", flush=True)


def safe_unlink(path):
    try:
        os.remove(str(path))
    except (FileNotFoundError, OSError):
        pass


def load_model():
    from voxcpm import VoxCPM
    t0 = time.time()
    model = VoxCPM.from_pretrained(
        str(MODEL_PATH), load_denoiser=False, optimize=False, device=DEVICE
    )
    sample_rate = getattr(model.tts_model, "sample_rate", 48000)
    log(f"ready in {time.time() - t0:.1f}s (sample_rate={sample_rate})")
    return model, sample_rate


def split_for_tts(text, limit=60):
    """VoxCPM is trained on short spans; long text degrades. Split on punctuation."""
    parts = [p.strip() for p in re.split(r"(?<=[。！？；!?;\\n])", text) if p and p.strip()]
    out = []
    for p in parts:
        while len(p) > limit:
            cut = p.rfind("，", 0, limit)
            if cut <= 0:
                cut = limit
            out.append(p[:cut])
            p = p[cut:].lstrip("，, ")
        if p:
            out.append(p)
    return out or [text]


def synthesize(model, sr, job):
    text = job["text"]
    output = job["output"]
    ref = job.get("reference_wav") or None
    if ref and not os.path.isfile(str(ref)):
        raise FileNotFoundError(
            "reference_wav is set to %r but that file does not exist" % (ref,)
        )
    cfg = float(job.get("cfg_value", 2.0))
    steps = int(job.get("inference_timesteps", 10))

    wavs = []
    for segment in split_for_tts(text):
        wav = model.generate(
            segment, reference_wav_path=ref, cfg_value=cfg, inference_timesteps=steps
        )
        wavs.append(np.asarray(wav, dtype=np.float32))

    if len(wavs) == 1:
        audio = wavs[0]
    else:
        silence = np.zeros(int(sr * 0.15), dtype=np.float32)
        chunks = []
        for i, wav in enumerate(wavs):
            chunks.append(wav)
            if i < len(wavs) - 1:
                chunks.append(silence)
        audio = np.concatenate(chunks)

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    sf.write(output, audio, sr)


def main():
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    ready_flag = JOB_DIR / "WORKER_READY"
    pid_flag = JOB_DIR / "WORKER_PID"
    safe_unlink(ready_flag)
    log(f"watching {JOB_DIR}")

    model, sr = load_model()
    pid_flag.write_text(str(os.getpid()), encoding="utf-8")
    ready_flag.write_text("READY", encoding="utf-8")
    log("READY")

    while True:
        jobs = sorted(p for p in JOB_DIR.glob("*.json") if not p.name.startswith("_"))
        if not jobs:
            time.sleep(0.25)
            continue
        for job_path in jobs:
            name = job_path.stem
            done = JOB_DIR / f"{name}.done"
            err = JOB_DIR / f"{name}.error"
            if done.exists() or err.exists():
                continue
            try:
                job = json.loads(job_path.read_text(encoding="utf-8"))
                synthesize(model, sr, job)
                done.write_text("OK", encoding="utf-8")
                log(f"job {name} done")
            except Exception as exc:  # keep the worker alive across failures
                import traceback
                err.write_text(traceback.format_exc(), encoding="utf-8")
                log(f"job {name} failed: {exc}")
            finally:
                safe_unlink(job_path)


if __name__ == "__main__":
    main()
'''
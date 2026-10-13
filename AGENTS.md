# AGENTS.md

How to work on this repository. Read this before changing anything.

VideoLingo turns a video into a subtitled, dubbed video. This fork keeps
**recognition in the cloud and dubbing on the local GPU**, so an 8 GB card
never has to hold an ASR model and a TTS model at the same time, and dubbing
costs nothing per minute.

Upstream: `Huanshere/VideoLingo` (kept as the `upstream` remote). The relevant
history is in `git log`; the user-facing summary is the fork block at the top
of `README.md`.

## Running it

```bash
uv run start.py                    # server on :8501, no --port flag (see pitfalls)
curl http://127.0.0.1:8501/_stcore/health   # -> ok
```

- Port lives in `.streamlit/config.toml`, not on the command line.
- `run_portable.bat` is the double-click launcher (path-independent, opens the
  browser once the server answers, no-ops if it is already running).
- `fileWatcherType = "none"`: **restart the server after every code change** or
  the running page keeps the old modules.

## Layout

| Path | What it is |
|---|---|
| `st.py` | Streamlit entry point; the a/b/c sections and the result buttons |
| `start.py` | Spawns `streamlit run st.py` |
| `core/_1_ytdlp.py` … `_12_dub_to_vid.py` | The pipeline, numbered by stage |
| `core/asr_backend/` | Recognition: `siliconflow_asr.py`, `qwen_asr_local.py`, `whisperX_local.py`, `mai_asr.py`, `audio_preprocess.py`, `transcription_cache.py` |
| `core/tts_backend/` | `custom_tts.py` (local VoxCPM2) plus the upstream cloud backends |
| `core/st_utils/` | Sidebar and page widgets |
| `core/utils/` | Helpers incl. `voxcpm_worker.py` (VRAM control) and `open_folder.py` |
| `translations/` | `zh-CN.json` etc.; `translations.py` does the lookup |
| `config.yaml` | Every setting. Real API keys live here locally — see red lines |

## Parts specific to this fork

**Cloud ASR (`siliconflow_asr.py`).** SiliconFlow returns sentence-level
segments only. `process_transcription()` drops any "word" over 30 characters,
which silently ate every long sentence, so `_estimate_words()` synthesises
word-level timings by spreading each sentence over its own time span. The cache
identity in `transcription_cache.py` must be bumped whenever this changes, or
old bad results keep coming back.

**Local dubbing (`custom_tts.py` + `E:\VoxCPM\videolingo_worker.py`).** The 2B
model costs ~35 s to load, so a detached worker loads it once and consumes JSON
job files from `voxcpm.root/videolingo_jobs`, answering with `.done`/`.error`.
The worker never exits by itself. Reference audio is mandatory: without it the
model samples a new random speaker per line ("every line is a different
person"). `refer_mode` 1–4 selects the source of that reference.

**VRAM.** The worker holds its weights while idle, so local recognition
(Qwen3-ASR) cannot load afterwards on an 8 GB card. `core/utils/voxcpm_worker.py`
stops it — from the sidebar when local runtime is chosen, and again in
`_2_asr.py` right before a model loads. It refuses to stop while jobs are in
flight.

**Keep the original audio.** `_12_dub_to_vid.py` attenuates the video's own
track and mixes it under the dub (`normalize=0` + `alimiter`).

## Pitfalls that cost real time here

1. **`os.remove` / `Path.unlink` go through a safe-delete shim** that raises
   when the recycle-bin fallback fails. In the worker and job bookkeeping use
   bare `os.remove` inside `try/except`.
2. **`ffprobe` rejects `-nostdin`** and exits 1 (ffmpeg accepts it). A wrapped
   probe then silently reports "no audio stream" and the feature dies quietly.
3. **`amix` defaults to `normalize=1`**, which scales every input by 1/n and
   pulled the dubbing down 6 dB. Mix with `normalize=0` plus a limiter.
4. **Missing translations fail silently** — `translate()` returns the English
   key. After adding any `t("...")` in `core/st_utils/`, add the key to
   `translations/zh-CN.json` and AST-scan for keys with no entry.
5. **`py_compile` only checks syntax.** Twice it passed on calls whose
   signature no longer matched; only running the real call chain caught it.
6. **Windows batch files must be GBK/ASCII + CRLF.** In Python, write Windows
   paths with forward slashes (`'C:/Users/W/...'`) — `\U` is a truncated
   unicode escape and `SyntaxError`s.
7. **`uv run` has no `--port`.** Configure the port in
   `.streamlit/config.toml`.
8. **`explorer /select,` needs an absolute path** and returns exit 1 whether it
   worked or not; never treat its return code as success.
9. **VoxCPM2 must install into its own Python 3.10 venv** — the project runs
   3.12 and the torch wheels are ABI-incompatible.

## Changing things

1. Use the repo venv: `.venv/Scripts/python.exe` (Windows).
2. **Verify by running it.** `streamlit.testing.v1.AppTest` executes `st.py`
   headlessly and reports exceptions the server log never shows:
   `AppTest.from_file("st.py").run()` then inspect `at.exception`. No pytest
   install needed. For a state that is hard to reach, stub the call that gates
   it (e.g. `find_media_file` raising "No media file found" renders the initial
   screen).
3. **Stub anything that touches data before testing it.** `cleanup()`,
   delete helpers, `rmtree`. A layout test once really archived a finished
   render. Mock where the name is *used* (`mock.patch.object(module, "f")`),
   not where it was defined.
4. Change the UI text in English in code, add the Chinese entry, AST-scan.
5. Restart the server, hit the health endpoint, and, for audio work, verify
   numerically (synthetic clips + FFT) instead of eyeballing a command string.

## Red lines

- **Never commit a real API key.** `config.yaml` is tracked and holds them
  locally. To commit config changes, blank the keys first and restore the file
  byte-for-byte afterwards. Scan before every commit:
  `git diff --cached | grep -cE "sk-[A-Za-z0-9]{20,}"` must be 0.
- `output/`, `history/`, `config.yaml.local`, `run.bat`, `open_browser.bat` are
  gitignored on purpose — done renders, local keys, machine-specific paths.
- Don't commit the `keep_original_audio`-style machine choices as new defaults
  (e.g. leave `whisper.runtime` at the value upstream users expect).

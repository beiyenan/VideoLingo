"""Provider grouping without changing existing TTS method/config identifiers."""

import streamlit as st

PROVIDERS = {
    "OpenLux": ("openai_tts",),
    "302.ai": ("f5tts",),
    "SiliconFlow": ("sf_fish_tts", "sf_cosyvoice2"),
    "Fish Audio": ("fish_audio",),
    "Microsoft Edge": ("edge_tts",),
    "Local service": ("gpt_sovits",),
    "Custom provider": ("custom_tts",),
}
KEY_PATHS = {
    "OpenLux": ("openai_tts.api_key",),
    "302.ai": ("f5tts.302_api",),
    "SiliconFlow": ("sf_fish_tts.api_key", "sf_cosyvoice2.api_key"),
    "Fish Audio": ("fish_audio.api_key",),
}

# ------------
# Provider labels
# ------------
# These names are UI copy and have an entry in every translations/*.json.
# Every other provider name is a company or product name. The dropdown shows it
# as written. It is not a translation key: translate() would warn, then return
# the same text.
TRANSLATED_PROVIDERS = {"Local service", "Custom provider"}


def voxcpm_status(root):
    """Where the local VoxCPM2 install stands for the folder in `root`.

    Returns (ready, python_or_None, worker_present, note).
    """
    from pathlib import Path
    from core.tts_backend import voxcpm_installer as vi
    try:
        base = Path(root) if root else vi.default_root()
    except Exception:
        return False, None, False, ""
    python = vi.venv_python(base)
    if not python.is_file():
        return False, None, False, ""
    if not vi._models_present(base / "models"):
        return False, python, False, "models"
    return True, python, vi.worker_script(base).is_file(), ""


def _voxcpm_install_panel(root_value):
    """Install/repair control for the local VoxCPM2 runtime.

    Everything here is optional: a failure is shown and nothing else about
    VideoLingo is affected.
    """
    import time as _time
    from core.utils.config_utils import load_key_or as _lko
    from translations.translations import translate as _t
    from core.tts_backend import voxcpm_installer as vi

    ready, python, worker_present, missing = voxcpm_status(root_value)
    if ready and worker_present:
        st.success(_t("VoxCPM2 is ready at %s") % (root_value or str(vi.default_root())))
        return
    if ready and not worker_present:
        st.warning(_t("VoxCPM2 is installed, but its worker script is missing. "
                      "Click repair to write it again."))
    else:
        st.info(_t("VoxCPM2 is not installed yet. Installing it downloads about 5 GB "
                   "(PyTorch plus model weights). Everything else in VideoLingo works "
                   "without it."))
        if missing == "models":
            st.warning(_t("The VoxCPM2 packages are installed but the model weights are "
                          "missing. Repair downloads them."))

    target = root_value.strip() or str(vi.default_root())
    action_label = _t("Repair VoxCPM2") if ready else _t("Install VoxCPM2 now")
    if not st.button(action_label, key="voxcpm_install", width="stretch"):
        return

    progress = st.progress(0.0, text=_t("Preparing..."))
    state = {"pct": 0.05}

    def on_log(message):
        state["pct"] = min(state["pct"] + 0.04, 0.95)
        try:
            progress.progress(state["pct"], text=message)
        except Exception:
            pass
        print(message, flush=True)

    try:
        report = vi.install(Path(target), log=on_log)
    except vi.InstallError as exc:
        progress.empty()
        st.error(_t("VoxCPM2 installation failed: %s") % exc)
        st.caption(_t("This does not affect the rest of VideoLingo. You can retry later, "
                      "or set voxcpm.root in config.yaml to an existing install."))
        return
    except Exception as exc:  # unexpected, but must not take the page down
        progress.empty()
        st.error(_t("VoxCPM2 installation failed unexpectedly: %s") % exc)
        return

    worker = vi.worker_script(Path(target))
    try:
        worker.write_text(vi.WORKER_SOURCE, encoding="utf-8")
    except OSError as exc:
        progress.empty()
        st.error(_t("VoxCPM2 installed, but the worker script could not be written: %s") % exc)
        return

    # Point the TTS backend at the new install so it works immediately.
    try:
        from core.utils.config_utils import save_settings
        save_settings({"voxcpm.root": target})
    except Exception:
        pass

    progress.progress(1.0, text=_t("Done"))
    time.sleep(0.4)
    progress.empty()
    st.success(_t("VoxCPM2 is installed at %s") % target)
    st.caption(_t("Restart VideoLingo so the dubbing worker picks up the new install."))
    _time.sleep(0)


def provider_label(name):
    """Label of one TTS provider in the current display language."""
    if name not in TRANSLATED_PROVIDERS:
        return name
    from translations.translations import translate as t
    return t(name)


def configured_keys(provider, method, load_key):
    """Prefer the selected method; reuse a sole existing key without writing it."""
    paths = KEY_PATHS[provider]
    values = {path: str(load_key(path) or "") for path in paths}  # YAML reads a digits-only key as int
    usable = {path: value for path, value in values.items()
              if value and not value.startswith("YOUR_")}
    current = paths[PROVIDERS[provider].index(method)]
    conflict = len(set(usable.values())) > 1
    value = usable.get(current, "" if conflict else next(iter(usable.values()), ""))
    return value, conflict


def save_settings(values):
    """Write `section.key` values; a section that an older config.yaml does not have is created."""
    from core.utils import config_utils

    with config_utils.lock:
        with open(config_utils.CONFIG_PATH, encoding="utf-8") as file:
            data = config_utils.yaml.load(file)
        for path, value in values.items():
            section, key = path.split(".")
            if not isinstance(data.get(section), dict):
                data[section] = {}
            data[section][key] = value
        with open(config_utils.CONFIG_PATH, "w", encoding="utf-8") as file:
            config_utils.yaml.dump(data, file)


def save_provider_key(provider, value):
    """Update legacy fields together; never migrate credentials on page render."""
    save_settings({path: value for path in KEY_PATHS[provider]})


def select_tts_method(labels):
    import streamlit as st
    from translations.translations import translate as t
    from core.utils.config_utils import load_key, load_key_or, update_key

    current = load_key("tts_method")
    provider = next((name for name, methods in PROVIDERS.items() if current in methods), None)
    chosen = st.selectbox(t("TTS Provider"), list(PROVIDERS),
                          index=list(PROVIDERS).index(provider) if provider else None,
                          format_func=provider_label)
    if chosen is None:
        st.warning(t("The dubbing method of your configuration is not available any more. Select another one."))
        return None
    methods = PROVIDERS[chosen]
    if len(methods) == 1:  # nothing to choose: no box
        selected = methods[0]
    else:
        # After a provider switch the old method is not in the list: take the provider's first one
        selected = st.selectbox(t("TTS Method"), methods,
                                index=methods.index(current) if current in methods else 0,
                                format_func=lambda method: labels[method])
    if selected is None:
        return None
    if selected != current:
        update_key("tts_method", selected)
        st.rerun()
    if chosen in KEY_PATHS:
        load_optional = lambda path: load_key_or(path, "")  # a provider that is newer than the config.yaml
        value, conflict = configured_keys(chosen, selected, load_optional)
        if conflict:
            st.warning(t("Existing methods use different keys. Editing this field replaces all keys for this provider."))
        entered = st.text_input(t("Provider API Key"), value=value, type="password",
                                help=t("Shared by all TTS methods under this provider."))
        if entered != value:
            save_provider_key(chosen, entered)
            st.rerun()
        # A sole legacy key is shown for convenience, but only saving propagates it.
        if value and any(load_optional(p) != value for p in KEY_PATHS[chosen]):
            if st.button(t("Use this key for all methods"), key=f"tts_share_{chosen}"):
                save_provider_key(chosen, value)
                st.rerun()
    # GPT-SoVITS needs a separate server next to the repo; warn instead of
    # letting the run fail deep inside the pipeline with a directory error.
    if selected == "gpt_sovits":
        from pathlib import Path as _Path
        _repo = _Path(__file__).resolve().parent.parent.parent.parent
        _has = any(d.is_dir() and d.name.startswith("GPT-SoVITS-v2") for d in _repo.iterdir())
        if not _has:
            st.warning(t("GPT-SoVITS was not found next to the VideoLingo folder "
                         "(expected a GPT-SoVITS-v2* directory in %s). This method will fail. "
                         "Use Custom provider to drive a local model such as VoxCPM2.") % _repo)
    # VoxCPM2 runs locally through a persistent worker: no API key, but a few
    # generation parameters are worth exposing next to the provider picker.
    if selected == "custom_tts":
        from core.utils.config_utils import load_key_or as _lko
        st.markdown(f"**{t('VoxCPM reference audio mode')}**")
        _mode_options = {
            1: t("Mode 1: Use the audio file you specify"),
            2: t("Mode 2: Use the first audio clip of this video"),
            3: t("Mode 3: Use each line's own audio clip as reference"),
            4: t("Mode 4: No reference (a new random voice per line)"),
        }
        _mode = st.selectbox(
            t("Refer Mode"),
            options=list(_mode_options.keys()),
            format_func=lambda x: _mode_options[x],
            index=list(_mode_options.keys()).index(int(_lko("voxcpm.refer_mode", 2) or 2))
            if int(_lko("voxcpm.refer_mode", 2) or 2) in _mode_options else 1,
            help=t("Mode 1 keeps one fixed voice across videos. Mode 2 clones this "
                  "video's first speaker so every video gets its own voice. "
                  "Mode 3 follows the original speaker line by line, which suits "
                  "interviews. Mode 4 has no reference at all, so every line is "
                  "spoken in a different random voice."),
        )
        if _mode != int(_lko("voxcpm.refer_mode", 2) or 2):
            save_settings({"voxcpm.refer_mode": _mode})
            st.rerun()
        _ref = st.text_input(
            t("VoxCPM reference audio (used by Mode 1)"),
            value=_lko("voxcpm.reference_wav", ""),
            help=t("Give a 5-15s clean single-speaker clip. This path is only read in Mode 1; "
                  "the other modes take their reference from the video being processed."),
        )
        if _mode == 1 and not str(_lko("voxcpm.reference_wav", "") or "").strip():
            st.warning(t("Mode 1 needs a reference audio file, otherwise every line will be "
                          "spoken in a different random voice."))
        if _ref != _lko("voxcpm.reference_wav", ""):
            save_settings({"voxcpm.reference_wav": _ref})
            st.rerun()
        _cfg = st.slider(t("VoxCPM CFG strength"), 0.5, 5.0,
                         float(_lko("voxcpm.cfg_value", 2.0)), 0.1)
        if abs(_cfg - float(_lko("voxcpm.cfg_value", 2.0))) > 1e-6:
            save_settings({"voxcpm.cfg_value": _cfg})
            st.rerun()
        _root = st.text_input(
            t("VoxCPM install folder"),
            value=str(_lko("voxcpm.root", "")),
            help=t("The folder that contains the VoxCPM2 models/ and venv/ directories. "
                   "Changing it takes effect after restarting VideoLingo."),
        )
        if _root != str(_lko("voxcpm.root", "")):
            save_settings({"voxcpm.root": _root})
            st.rerun()
        _voxcpm_install_panel(_root)
        _steps = st.slider(t("VoxCPM inference steps"), 4, 30,
                           int(_lko("voxcpm.inference_timesteps", 10)), 1)
        if _steps != int(_lko("voxcpm.inference_timesteps", 10)):
            save_settings({"voxcpm.inference_timesteps": _steps})
            st.rerun()
        st.caption(t("Local VoxCPM2 keeps a worker process warm; the first line after a "
                     "restart spends ~30s loading the model, later lines take ~10s each."))
    return selected

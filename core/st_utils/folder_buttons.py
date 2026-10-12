"""The action rows shown under the subtitles and dubbing results.

Two stacked rows that stay aligned across sections: the first row holds the
download / destructive / archiving actions, the second row the folder openers.
All four buttons once shared a single line and the labels ran together;
stacked, each row reads as one thing you can do.

`result_actions` returns a dict of *which* button was pressed (True/False per
key), so the caller can act on it and decide whether to rerun.
"""

import os

import streamlit as st

from core.utils.open_folder import folder_path, reveal_folder

OUTPUT_DIR = "output"
HISTORY_DIR = "history"


def _button_row(labels: dict, key_prefix: str) -> dict:
    """Render {key: label} on a single line; return {key: was_pressed}."""
    clicked = {}
    columns = st.columns(len(labels))
    for column, (key, label) in zip(columns, labels.items()):
        with column:
            clicked[key] = bool(st.button(label, key=f"{key_prefix}_{key}", width="stretch"))
    return clicked


def _mixed_row(cells: list, key_prefix: str) -> dict:
    """Render one row of widgets; each cell is (key, spec).

    A str spec becomes a stretch button whose press is reported; a callable
    spec draws itself (e.g. a download button) and reports nothing.
    """
    clicked = {}
    columns = st.columns(len(cells))
    for column, (key, spec) in zip(columns, cells):
        with column:
            if callable(spec):
                spec()
            else:
                clicked[key] = bool(st.button(spec, key=f"{key_prefix}_{key}", width="stretch"))
    return clicked


def result_actions(t, key_prefix: str, allow_delete: bool, lead=None) -> dict:
    """Two stacked rows. Returns {key: was_pressed} for every button rendered.

    `lead` is an optional zero-arg callable drawn at the start of the first
    row (the subtitle section puts its download button there), so that row
    lines up with the dubbing section's delete/archive row.
    """
    first_row = []
    if lead is not None:
        first_row.append(("lead", lead))
    if allow_delete:
        first_row.append(("delete", t("Delete dubbing files")))
    first_row.append(("archive", t("Archive to 'history'")))

    openers = {
        "open_output": t("Open the output folder"),
        "open_history": t("Open the history folder"),
    }

    clicked = _mixed_row(first_row, f"{key_prefix}_act")
    clicked.update(_button_row(openers, f"{key_prefix}_open"))
    return clicked


def history_button(t, key_prefix: str = "init") -> bool:
    """A single history opener, for screens without result actions.

    The initial screen has no output yet, so once everything was archived
    there is no way back into 'history' - this button is that way back.
    """
    clicked = _button_row({"open_history": t("Open the history folder")}, f"{key_prefix}_open")
    if clicked.get("open_history"):
        open_folder("open_history")
        return True
    return False


def handle_action(clicked: dict, delete_handler=None) -> bool:
    """Run the action whose button was pressed. Returns True if one fired."""
    if clicked.get("delete") and delete_handler is not None:
        delete_handler()
        return True
    if clicked.get("archive"):
        from core.utils.onekeycleanup import cleanup
        cleanup()
        return True
    return False


def open_folder(key: str, select_dub_video: bool = False) -> None:
    """Called after a rerun when one of the folder buttons was pressed."""
    if key == "open_output":
        target = OUTPUT_DIR
        select = os.path.join(target, "output_dub.mp4") if select_dub_video else None
        ok, message = reveal_folder(target, select)
    elif key == "open_history":
        target = HISTORY_DIR
        ok, message = reveal_folder(target)
    else:
        return

    if ok:
        # A brief toast, not a green block: the Explorer window is the real
        # confirmation, and a permanent banner just crowds the page.
        st.toast(message, icon="📂")
    else:
        st.warning(message)
        st.code(folder_path(target), language=None)
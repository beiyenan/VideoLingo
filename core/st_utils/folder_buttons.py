"""The action rows shown under the subtitles and dubbing results.

Two stacked rows: the destructive/archiving actions on top, the folder openers
underneath. All four shared one line in an earlier revision and the labels ran
together; stacked, each row reads as one thing you can do.

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


def result_actions(t, key_prefix: str, allow_delete: bool) -> dict:
    """Two stacked rows. Returns {key: was_pressed} for every button rendered."""
    actions = {}
    if allow_delete:
        actions["delete"] = t("Delete dubbing files")
    actions["archive"] = t("Archive to 'history'")

    openers = {
        "open_output": t("Open the output folder"),
        "open_history": t("Open the history folder"),
    }

    clicked = {}
    if actions:
        clicked.update(_button_row(actions, f"{key_prefix}_act"))
    clicked.update(_button_row(openers, f"{key_prefix}_open"))
    return clicked


def folder_actions(t, key_prefix: str) -> dict:
    """Only the two folder openers, for sections without delete/archive."""
    return _button_row({
        "open_output": t("Open the output folder"),
        "open_history": t("Open the history folder"),
    }, f"{key_prefix}_open")


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
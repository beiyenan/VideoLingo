"""Buttons that reveal the working folders in the OS file browser.

The web page lists the results, but a finished .mp4 still has to be found on
disk. `output/` holds the current run and `history/` the archived ones.
"""

import os

import streamlit as st

from core.utils.open_folder import folder_path, reveal_folder

OUTPUT_DIR = "output"
HISTORY_DIR = "history"


def output_folder_buttons(t, key_prefix: str, select_dub_video: bool = False):
    """Render the `output` and `history` openers side by side.

    `select_dub_video` highlights the finished video in Explorer when it exists,
    which is the file people are usually after.
    """
    left, right = st.columns(2)

    with left:
        if st.button(t("Open the output folder"), key=f"{key_prefix}_open_output",
                     width="stretch"):
            target = OUTPUT_DIR
            select = os.path.join(target, "output_dub.mp4") if select_dub_video else None
            ok, message = reveal_folder(target, select)
            if ok:
                st.success(message)
            else:
                st.warning(message)
                st.code(folder_path(target), language=None)

    with right:
        if st.button(t("Open the history folder"), key=f"{key_prefix}_open_history",
                     width="stretch"):
            ok, message = reveal_folder(HISTORY_DIR)
            if ok:
                st.success(message)
            else:
                st.warning(message)
                st.code(folder_path(HISTORY_DIR), language=None)
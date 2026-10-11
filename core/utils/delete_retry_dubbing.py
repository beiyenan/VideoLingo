"""Remove the dubbing products so dubbing can be redone.

Only the dubbing stage is discarded: recognition, translation and subtitles are
kept, so retrying does not pay for those again.
"""

import os
import shutil

# The dubbing stage writes dub.mp3 (not dub.wav) plus the segment folder; the
# older list also named dub.wav, which nothing produces any more.
DUBBING_FILES = [
    os.path.join("output", "dub.mp3"),
    os.path.join("output", "dub.wav"),
    os.path.join("output", "normalized_dub.wav"),
    os.path.join("output", "dub.srt"),
    os.path.join("output", "dub_src.srt"),
    os.path.join("output", "output_dub.mp4"),
]

DUBBING_DIRS = [
    os.path.join("output", "audio", "segs"),
    os.path.join("output", "audio", "tmp"),
]


def delete_dubbing_files():
    for file_path in DUBBING_FILES:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"Deleted: {file_path}")
            except Exception as e:
                print(f"Error deleting {file_path}: {str(e)}")
        else:
            print(f"File not found: {file_path}")

    for folder in DUBBING_DIRS:
        if os.path.exists(folder):
            try:
                shutil.rmtree(folder)
                print(f"Deleted folder and contents: {folder}")
            except Exception as e:
                print(f"Error deleting folder {folder}: {str(e)}")
        else:
            print(f"Folder not found: {folder}")


if __name__ == "__main__":
    delete_dubbing_files()
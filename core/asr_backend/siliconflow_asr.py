"""SiliconFlow cloud ASR backend (OpenAI-compatible /v1/audio/transcriptions).

Default model: XingChenAGI/XingChenASR-V3.2-Ultra (free tier on SiliconFlow).

Note: the timestamped `segments` array is only returned when
`response_format=verbose_json` is sent, so that is mandatory here.
"""

import os
import time
import re
import requests

from core.asr_backend.audio_preprocess import audio_slice_wav
from rich import print as rprint
from core.utils import *

def _sf_base_url():
    return str(load_key("whisper.siliconflow_base_url") or "https://api.siliconflow.cn/v1").rstrip("/")


def _sf_model():
    return str(load_key("whisper.siliconflow_model") or "XingChenAGI/XingChenASR-V3.2-Ultra")


def _sf_api_key():
    # config.yaml first, then the ambient environment.
    key = str(load_key("whisper.siliconflow_api_key") or "").strip()
    if key:
        return key
    return str(os.environ.get("SILICONFLOW_API_KEY") or "").strip()


def _resolve_language():
    lang = str(load_key("whisper.language") or "auto").lower()
    # The API takes ISO-639-1; anything unknown/auto is simply not sent so the
    # server can auto-detect.
    if lang in ("auto", "", "none"):
        return None
    return {"zh": "zh", "cn": "zh", "zh-cn": "zh", "en": "en", "ja": "ja", "ko": "ko"}.get(lang, lang)


def _normalise_text(text):
    """Strip the quotes/decorations cloud ASR adds around each segment.

    SiliconFlow returns each segment wrapped in double quotes (e.g. '"We did
    that."'). Downstream subtitle alignment concatenates the word column and
    matches sentences against it with remove_punctuation(), which does not drop
    quote characters, so leftovers would break every match. Normalise here so
    the rest of the pipeline sees plain text like the other ASR backends.
    """
    if not text:
        return ""
    text = str(text)
    # Strip matching surrounding quotes/brackets, possibly nested.
    pairs = (('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"), ("「", "」"), ("『", "』"))
    changed = True
    while changed and len(text) >= 2:
        changed = False
        for a, b in pairs:
            if text.startswith(a) and text.endswith(b):
                text = text[len(a):-len(b)].strip()
                changed = True
    # Remove any stray inner quotes the API may leave behind.
    text = text.replace('"', "").replace("'", "").replace("“", "").replace("”", "")
    return re.sub(r"\s+", " ", text).strip()


# Downstream `process_transcription()` drops any "word" longer than 30 chars.
# SiliconFlow returns sentence-level segments only, so without a word split a
# single long sentence is treated as one word and silently thrown away -- that
# is what used to reduce a 770s video to 8 subtitle lines.
MAX_WORD_LEN = 30

_TOKEN_RE = re.compile(
    r"[A-Za-z0-9]+(?:['’][A-Za-z]+)?"      # latin words / numbers
    r"|[\u3040-\u30ff]"                     # kana
    r"|[\u3400-\u9fff]"                     # CJK ideographs
    r"|[^\sA-Za-z0-9\u3040-\u30ff\u3400-\u9fff]"  # single punctuation
)


def _split_into_words(text, max_len=MAX_WORD_LEN):
    """Split a sentence into tokens no longer than `max_len` characters."""
    tokens = _TOKEN_RE.findall(text)
    words = []
    for token in tokens:
        while len(token) > max_len:
            words.append(token[:max_len])
            token = token[max_len:]
        if token:
            words.append(token)
    return words


def _estimate_words(text, seg_start, seg_end):
    """Build word-level entries for one sentence segment.

    The API gives no word timings, so the segment duration is distributed over
    the tokens proportionally to their length. This is accurate enough for
    subtitle alignment, and it keeps every token under the 30-character cap
    that `process_transcription()` enforces.
    """
    words = _split_into_words(text)
    if not words:
        return []
    if seg_end <= seg_start:
        seg_end = seg_start + 0.001

    weights = [max(len(w), 1) for w in words]
    total = sum(weights)
    span = seg_end - seg_start

    entries = []
    cursor = seg_start
    for i, (word, weight) in enumerate(zip(words, weights)):
        if i == len(words) - 1:
            word_end = seg_end
        else:
            word_end = cursor + span * weight / total
        entries.append({"word": word, "start": round(cursor, 3), "end": round(word_end, 3)})
        cursor = word_end
    return entries


def transcribe_audio_siliconflow(raw_audio_path, vocal_audio_path, start=None, end=None):
    rprint(f"[cyan]Transcribing audio with SiliconFlow {_sf_model()}...[/cyan]")

    api_key = _sf_api_key()
    if not api_key:
        raise RuntimeError(
            "SiliconFlow API key is missing. Fill in whisper.siliconflow_api_key in "
            "config.yaml or set the SILICONFLOW_API_KEY environment variable."
        )

    # Reuse the same FFmpeg slice helper the other cloud backends use.
    audio_data = audio_slice_wav(vocal_audio_path, start, end)

    files = {
        "file": ("audio.wav", audio_data, "audio/wav"),
    }
    data = {
        "model": _sf_model(),
        # Required: without this the API returns only plain text, no segments,
        # and the subtitle alignment stage has nothing to work with.
        "response_format": "verbose_json",
    }
    language = _resolve_language()
    if language:
        data["language"] = language

    url = f"{_sf_base_url()}/audio/transcriptions"
    t0 = time.time()
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        data=data,
        files=files,
        timeout=600,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"SiliconFlow ASR failed with HTTP {response.status_code}: {response.text[:500]}"
        )

    payload = response.json()
    raw_segments = payload.get("segments") or []
    segments = []
    for seg in raw_segments:
        text = _normalise_text(seg.get("text") or "")
        if not text:
            continue
        seg_start = float(seg.get("start") or 0.0)
        seg_end = float(seg.get("end") or 0.0)
        # Segments come back relative to the slice we sent; shift to absolute time.
        if start is not None:
            seg_start += start
            seg_end += start
        if seg_end <= seg_start:
            seg_end = seg_start
        segments.append({
            "start": seg_start,
            "end": seg_end,
            "text": text,
            "words": _estimate_words(text, seg_start, seg_end),
        })

    rprint(f"[green]Transcription completed in {time.time() - t0:.2f} seconds "
           f"({len(segments)} segments)[/green]")

    return {"segments": segments, "language": payload.get("language")}


if __name__ == "__main__":
    file_path = input("Enter local audio file path (the same file is used as source and vocal): ")
    print(transcribe_audio_siliconflow(file_path, file_path))

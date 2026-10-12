import os
import subprocess
import json
import math

import cv2
from rich.console import Console

from core._1_ytdlp import find_video_files
from core.utils import *
from core.utils.models import *
from core.utils.subtitle_style import get_subtitle_filters

console = Console()

DUB_VIDEO = "output/output_dub.mp4"

# How far the original sound is pushed down when it is kept under the dubbing.
# Far enough to read as a presence rather than a second, competing voice.
DEFAULT_ORIGINAL_GAIN = -14.0
DUB_SUB_FILE = 'output/dub.srt'
DUB_SRC_SUB_FILE = 'output/dub_src.srt'
DUB_AUDIO = 'output/dub.mp3'

def normalize_dub_audio(audio_path, output_path):
    """Measure gated loudness, then apply one peak-limited gain to the whole dub."""
    check_cancel()
    measured = subprocess.run(
        ['ffmpeg', '-hide_banner', '-nostdin', '-i', str(audio_path),
         '-af', 'loudnorm=I=-20:TP=-1:LRA=11:print_format=json', '-f', 'null', '-'],
        check=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
    )
    # FFmpeg can write its final progress summary after the measurement object.
    stats, _ = json.JSONDecoder().raw_decode(measured.stderr[measured.stderr.rfind('{'):])
    loudness, peak = float(stats['input_i']), float(stats['input_tp'])
    # Silence/very short clips may not have a measurable integrated loudness.
    # Preserve their level rather than applying an infinite or guessed gain.
    gain = min(-20.0 - loudness, -1.0 - peak) if math.isfinite(loudness) and math.isfinite(peak) else 0.0
    check_cancel()
    subprocess.run(
        ['ffmpeg', '-hide_banner', '-nostdin', '-y', '-i', str(audio_path),
         '-af', f'volume={gain:.8f}dB', '-c:a', 'pcm_s24le', str(output_path)],
        check=True, capture_output=True,
    )

def _video_has_audio(video_path) -> bool:
    """True when the input carries an audio track to keep under the dub."""
    try:
        probe = subprocess.run(
            # No -nostdin here: ffprobe rejects it, and the failure would be
            # swallowed below and silently disable the whole feature.
            ['ffprobe', '-hide_banner', '-v', 'error',
             '-select_streams', 'a', '-show_entries', 'stream=codec_type',
             '-of', 'csv=p=0', str(video_path)],
            check=True, capture_output=True, text=True,
            encoding='utf-8', errors='replace',
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
    return 'audio' in probe.stdout


def merge_video_audio():
    """Merge video and audio, and reduce video volume"""
    from core._1_ytdlp import is_audio_only_input
    if is_audio_only_input():
        rprint("[bold green]🎵 Audio-only input: skipping dubbing video merge. Dubbed audio is in the `output` directory.[/bold green]")
        return

    VIDEO_FILE = find_video_files()
    background_file = _BACKGROUND_AUDIO_FILE
    
    burn_subtitles = load_key("burn_subtitles")

    # Normalize dub audio
    normalized_dub_audio = 'output/normalized_dub.wav'
    normalize_dub_audio(DUB_AUDIO, normalized_dub_audio)
    
    keep_original = bool(load_key("keep_original_audio")) and _video_has_audio(VIDEO_FILE)
    original_gain = float(load_key("original_audio_gain") or DEFAULT_ORIGINAL_GAIN)
    has_background = os.path.isfile(background_file)

    cmd = ['ffmpeg', '-y', '-i', VIDEO_FILE]
    index = 1
    background_index = None
    if has_background:
        background_index = index
        cmd.extend(['-i', background_file])
        index += 1
    dub_index = index
    cmd.extend(['-i', normalized_dub_audio])
    index += 1

    # Everything that sits *under* the dubbing voice: the original sound, kept
    # well below it, plus the separated background when it exists.
    bed = []
    filters = []
    if keep_original:
        filters.append(f'[0:a]volume={original_gain:.2f}dB[orig]')
        bed.append('[orig]')
        rprint(f"[cyan]Keeping the original audio under the dubbing at {original_gain:+.1f} dB.[/cyan]")
    if background_index is not None:
        bed.append(f'[{background_index}:a]')

    if bed:
        if len(bed) == 1:
            filters.append(f'{bed[0]}anull[bed]')
        else:
            filters.append(f'{"".join(bed)}amix=inputs={len(bed)}:duration=first[bed]')
        # normalize=0 keeps the dubbing at the level it has on its own, so the
        # gain above means "this much below the dubbing" rather than "this much,
        # then halved again by amix". The limiter catches the peaks where the
        # two happen to line up.
        filters.append(
            f'[bed][{dub_index}:a]amix=inputs=2:duration=first:dropout_transition=3:normalize=0,'
            f'alimiter=limit=0.97[a]'
        )
    else:
        rprint('[yellow]Original background audio is unavailable; exporting the dubbed voice alone.[/yellow]')

    if burn_subtitles:
        # Merge video and audio with the subtitles of the dub
        video = cv2.VideoCapture(VIDEO_FILE)
        TARGET_WIDTH = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
        TARGET_HEIGHT = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
        video.release()
        rprint(f"[bold green]Video resolution: {TARGET_WIDTH}x{TARGET_HEIGHT}[/bold green]")

        subtitle_filter = get_subtitle_filters('dubbed', DUB_SRC_SUB_FILE, DUB_SUB_FILE)
        filters.insert(0, f'[0:v]scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=decrease,'
                          f'pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2,'
                          f'{subtitle_filter}[v]')
    else:
        rprint("[bold yellow]Subtitles are not burned in: the dubbed audio is merged into the original video.[/bold yellow]")
    if filters:
        cmd.extend(['-filter_complex', ';'.join(filters)])

    cmd.extend(['-map', '[v]' if burn_subtitles else '0:v:0', '-map', '[a]' if bed else f'{dub_index}:a'])
    encoder = []
    if load_key("ffmpeg_gpu"):
        rprint("[bold green]Using GPU acceleration...[/bold green]")
        encoder = ['-c:v', 'h264_nvenc']
    audio_output = ['-c:a', 'aac', '-b:a', '192k', DUB_VIDEO]

    if burn_subtitles:
        subprocess.run(cmd + encoder + audio_output, check=True)
    else:
        try:
            # The picture is not touched, so it is copied as it is
            subprocess.run(cmd + ['-c:v', 'copy'] + audio_output, check=True)
        except subprocess.CalledProcessError:
            rprint("[yellow]The video stream cannot be copied into MP4, encoding it again...[/yellow]")
            subprocess.run(cmd + encoder + audio_output, check=True)
    rprint(f"[bold green]Video and audio successfully merged into {DUB_VIDEO}[/bold green]")

if __name__ == '__main__':
    merge_video_audio()

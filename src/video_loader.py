"""
src/video_loader.py — Prepare a downloaded video for sending to the chat.

Big or high-bitrate videos are first compressed with ffmpeg (H.265, max 720p, 2000 kbps) and the
result is kept next to the original as a hidden preview file (`.<name>.720p_h265.mp4`, the file viewer
skips dot files) so the next request re-uses it.
Everything here is blocking (ffmpeg runs for minutes): run it in an executor. Pure logic: the bot
owns the Telegram I/O (the upload itself goes through Telethon, not the Bot API, to avoid its limits).
"""

import logging
import os
import shutil
import subprocess
from typing import Callable, Optional

logger = logging.getLogger(__name__)

COMPRESSED_SUFFIX = ".720p_h265"
COMPRESS_IF_LARGER_THAN = 500 * 1024 * 1024   # bytes
COMPRESS_IF_BITRATE_ABOVE = 4000              # kbps (overall, audio included)
MAX_UPLOAD_BYTES = 2000 * 1000 * 1000         # Telegram's MTProto limit for non-premium accounts is 2 GB
TARGET_HEIGHT = 720
TARGET_BITRATE_KBPS = 2000


def find_ffmpeg() -> Optional[str]:
    """ffmpeg from FFMPEG_PATH or PATH, None if not installed."""
    configured = os.environ.get('FFMPEG_PATH', '').strip().strip('"')
    if configured and os.path.isfile(configured):
        return configured
    return shutil.which('ffmpeg')


def is_compressed_name(name: str) -> bool:
    return os.path.splitext(name)[0].endswith(COMPRESSED_SUFFIX)


def compressed_path(path: str) -> str:
    folder, name = os.path.split(path)
    return os.path.join(folder, f".{os.path.splitext(name)[0]}{COMPRESSED_SUFFIX}.mp4")


def bitrate_kbps(size_bytes: int, duration: float) -> float:
    return size_bytes * 8 / duration / 1000 if duration > 0 else 0.0


def needs_compression(path: str, duration: float) -> bool:
    """Too big or too high a bitrate (an already compressed copy never is)."""
    if is_compressed_name(os.path.basename(path)):
        return False
    size = os.path.getsize(path)
    return size > COMPRESS_IF_LARGER_THAN or bitrate_kbps(size, duration) > COMPRESS_IF_BITRATE_ABOVE


def existing_compressed(path: str) -> Optional[str]:
    """A previously made compressed copy that is still valid (not older than the original)."""
    out = compressed_path(path)
    try:
        if os.path.getsize(out) > 0 and os.path.getmtime(out) >= os.path.getmtime(path):
            return out
    except OSError:
        pass
    return None


def compress_video(src: str, duration: float, progress: Callable[[float], None]) -> str:
    """Compress `src` to H.265 / 720p / 2000 kbps next to it and return the new path.

    `progress(fraction)` is called from this (worker) thread. Raises RuntimeError on failure.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError('找不到 ffmpeg（請安裝並加入 PATH，或設定環境變數 FFMPEG_PATH）')

    dst = compressed_path(src)
    tmp = dst + '.part'            # unfinished
    cmd = [
        ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-nostats', '-progress', 'pipe:1',
        '-i', src, '-map', '0:v:0', '-map', '0:a:0?',
        '-vf', f"scale=-2:'min({TARGET_HEIGHT},ih)'",
        '-c:v', 'libx265', '-preset', 'fast', '-b:v', f'{TARGET_BITRATE_KBPS}k',
        '-maxrate', f'{int(TARGET_BITRATE_KBPS * 1.2)}k', '-bufsize', f'{TARGET_BITRATE_KBPS * 2}k',
        '-pix_fmt', 'yuv420p', '-tag:v', 'hvc1', '-x265-params', 'log-level=error',
        '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', '-f', 'mp4', tmp,
    ]
    logger.info(f"壓縮影片: {src}")
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding='utf-8', errors='replace', creationflags=flags)
    try:
        for line in proc.stdout:
            key, _, value = line.strip().partition('=')
            if key == 'out_time_us' or key == 'out_time_ms':      # both are microseconds
                if value.lstrip('-').isdigit() and duration > 0:
                    progress(min(max(int(value) / 1_000_000 / duration, 0.0), 1.0))
        error = proc.stderr.read()
        code = proc.wait()
    except BaseException:
        proc.kill()
        raise
    if code != 0 or not os.path.exists(tmp):
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise RuntimeError(f'ffmpeg 壓縮失敗: {(error or "").strip()[-300:] or code}')
    os.replace(tmp, dst)
    logger.info(f"壓縮完成: {dst}")
    return dst

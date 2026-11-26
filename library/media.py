"""
library/media.py — Per-file metadata stored next to the file (hidden, so the chat file viewer skips it).

  <folder>/video.mp4
  <folder>/.video.mp4.meta.json     title, actors, series, source, cached video info,
                                    "download": the bot's download record (owned by src/records.py, v3.3.0)
  <folder>/.video.mp4.shots/01.jpg  auto screenshots shown before playback (photos: one thumbnail)

Blocking functions (ffprobe / ffmpeg / OpenCV): call them from a worker thread.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

VIDEO_EXTS = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.wmv', '.flv', '.m4v', '.ts'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
SHOT_COUNT = 9
SHOT_WIDTH = 640
THUMB_MAX = (640, 1280)          # photo thumbnail: at most this wide / tall
META_VERSION = 1
_meta_lock = threading.RLock()   # the library and the bot (download records) both write sidecars

# what browsers play without help (the frontend still double-checks with canPlayType)
DIRECT_CONTAINERS = {'.mp4', '.m4v', '.webm', '.mov'}
DIRECT_VIDEO_CODECS = {'h264', 'vp8', 'vp9', 'av1', 'hevc'}
DIRECT_AUDIO_CODECS = {None, 'aac', 'mp3', 'opus', 'vorbis'}

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def is_video(name: str) -> bool:
    return not name.startswith('.') and os.path.splitext(name)[1].lower() in VIDEO_EXTS


def is_image(name: str) -> bool:
    return not name.startswith('.') and os.path.splitext(name)[1].lower() in IMAGE_EXTS


def is_media(name: str) -> bool:
    return is_video(name) or is_image(name)


def kind_of(name: str) -> str:
    return 'photo' if is_image(name) else 'video'


def meta_path(video: str) -> str:
    folder, name = os.path.split(video)
    return os.path.join(folder, f".{name}.meta.json")


def shots_dir(video: str) -> str:
    folder, name = os.path.split(video)
    return os.path.join(folder, f".{name}.shots")


def thread_limit(share: int = 1) -> int:
    """CPU threads one ffmpeg / worker may use: MAX_THREADS (default 16, at most the cores, set in the
    Windows app) split between `share` jobs that run at the same time. Read live, so a change applies
    to the next ffmpeg started."""
    try:
        limit = int(os.environ.get('MAX_THREADS') or 16)
    except ValueError:
        limit = 16
    limit = max(1, min(limit, os.cpu_count() or limit))
    return max(1, limit // max(1, share))


def threads_args(share: int = 1) -> List[str]:
    """ffmpeg's -threads option for its share of MAX_THREADS (put it before -i for decoding and before
    the output for encoding / filtering)."""
    return ['-threads', str(thread_limit(share))]


def find_tool(name: str) -> Optional[str]:
    """ffmpeg / ffprobe from FFMPEG_PATH's folder or PATH."""
    configured = os.environ.get('FFMPEG_PATH', '').strip().strip('"')
    if configured:
        candidate = os.path.join(os.path.dirname(configured), name + ('.exe' if os.name == 'nt' else ''))
        if os.path.isfile(candidate):
            return candidate
    return shutil.which(name)


# ─── sidecar metadata ────────────────────────────────────────────────────────

def default_meta(video: str) -> dict:
    return {
        'version': META_VERSION,
        'title': os.path.splitext(os.path.basename(video))[0],
        'actors': [],
        'series': '',
        'source': '',
        'added': time.time(),
        'info': None,           # see probe_info()
        'info_mtime': 0,        # video mtime the info / shots were made for
        'shots': [],
        'shots_mtime': 0,
        'uid': uuid.uuid4().hex,   # stable identity (moves / renames keep the sidecar)
        'group': '',               # versions of the same video share a group id
        'not_same': [],            # uids the user split off: never group with them again
    }


def load_meta(video: str) -> dict:
    meta = default_meta(video)
    try:
        with open(meta_path(video), encoding='utf-8') as f:
            stored = json.load(f)
        if isinstance(stored, dict):
            meta.update(stored)
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"讀取影片資訊失敗 {video}: {e}")
    return meta


def read_sidecar(video: str) -> dict:
    """The sidecar as stored (no defaults); {} if there is none."""
    try:
        with open(meta_path(video), encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning(f"讀取資訊檔失敗 {video}: {e}")
        return {}


def _write_sidecar(video: str, data: dict):
    path = meta_path(video)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    _hide(path)


def save_meta(video: str, meta: dict):
    """Write the library's fields; the "download" record on disk is kept as is (src/records.py owns it)."""
    with _meta_lock:
        on_disk = read_sidecar(video)
        stored = on_disk.get('download')
        data = {k: v for k, v in meta.items() if k != 'download'}
        if stored:
            data['download'] = stored
        # the bot may have added the Telegram message text after the library loaded this sidecar
        if 'description' not in data and on_disk.get('description'):
            data['description'] = on_disk['description']
        _write_sidecar(video, data)


def set_download(video: str, record: dict, defaults: Optional[dict] = None):
    """Store the bot's download record in the file's sidecar (creating it if needed);
    `defaults` fill library fields that aren't set yet (e.g. a title kept from before a deletion)."""
    with _meta_lock:
        data = read_sidecar(video) or {'version': META_VERSION}
        data['download'] = record
        for key, value in (defaults or {}).items():
            if not data.get(key):
                data[key] = value
        _write_sidecar(video, data)


def _hide(path: str):
    """Also hide the file in Windows Explorer (the leading dot already hides it from the viewer)."""
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x02)
        except Exception:
            pass


def clean_tags(values) -> List[str]:
    seen, out = set(), []
    for v in values or []:
        v = str(v).strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v[:100])
    return out


# ─── video info ──────────────────────────────────────────────────────────────

def _bit_depth(stream: dict) -> Optional[int]:
    raw = stream.get('bits_per_raw_sample')
    if raw and str(raw).isdigit():
        return int(raw)
    m = re.search(r'p(\d{2})(le|be)?$', stream.get('pix_fmt') or '')
    if m:
        return int(m.group(1))
    return 8 if stream.get('pix_fmt') else None


def _fps(rate: str) -> Optional[float]:
    try:
        num, _, den = (rate or '').partition('/')
        return round(float(num) / float(den or 1), 3) if float(den or 1) else None
    except ValueError:
        return None


def probe_info(video: str) -> dict:
    """Width, height, bit rate, bit depth, codecs, duration, fps, size. Raises RuntimeError."""
    ffprobe = find_tool('ffprobe')
    if not ffprobe:
        raise RuntimeError('找不到 ffprobe（請安裝 ffmpeg 並加入 PATH，或設定 FFMPEG_PATH）')
    out = subprocess.run(
        [ffprobe, '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', video],
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60, creationflags=_NO_WINDOW,
    )
    if out.returncode != 0:
        err = out.stderr.strip()
        if 'moov atom not found' in err or 'Invalid data found' in err:
            raise RuntimeError('檔案不完整或已損毀（下載可能未完成或曾被中斷），請重新下載')
        raise RuntimeError(f'ffprobe 失敗: {err[-200:]}')
    data = json.loads(out.stdout or '{}')
    fmt = data.get('format') or {}
    streams = data.get('streams') or []
    v = next((s for s in streams if s.get('codec_type') == 'video'
              and not (s.get('disposition') or {}).get('attached_pic')), {})
    a = next((s for s in streams if s.get('codec_type') == 'audio'), {})
    duration = float(fmt.get('duration') or v.get('duration') or 0)
    size = int(fmt.get('size') or os.path.getsize(video))
    bit_rate = int(fmt.get('bit_rate') or 0) or (int(size * 8 / duration) if duration else 0)
    return {
        'width': v.get('width'),
        'height': v.get('height'),
        'bit_rate': bit_rate,                                  # bits / s, whole file
        'video_bit_rate': int(v['bit_rate']) if str(v.get('bit_rate', '')).isdigit() else None,
        'bit_depth': _bit_depth(v),
        'video_codec': v.get('codec_name'),
        'profile': v.get('profile'),
        'pix_fmt': v.get('pix_fmt'),
        'fps': _fps(v.get('avg_frame_rate') or v.get('r_frame_rate')),
        'audio_codec': a.get('codec_name'),
        'audio_channels': a.get('channels'),
        'audio_sample_rate': int(a['sample_rate']) if str(a.get('sample_rate', '')).isdigit() else None,
        'duration': duration,
        'size': size,
        'container': fmt.get('format_name'),
    }


def direct_playable(video: str, info: Optional[dict]) -> bool:
    """Probably playable by browsers as-is (HEVC only where the browser says so: decided client-side)."""
    if not info:
        return False
    ext = os.path.splitext(video)[1].lower()
    return (ext in DIRECT_CONTAINERS and info.get('video_codec') in DIRECT_VIDEO_CODECS
            and info.get('audio_codec') in DIRECT_AUDIO_CODECS and (info.get('bit_depth') or 8) <= 10)


def mime_codecs(video: str, info: Optional[dict]) -> str:
    """A `video/...; codecs=...` string for the frontend's canPlayType check."""
    ext = os.path.splitext(video)[1].lower()
    mime = 'video/webm' if ext == '.webm' else 'video/mp4'
    codec = {'h264': 'avc1.640028', 'hevc': 'hvc1.1.6.L120.90', 'vp9': 'vp09.00.10.08',
             'vp8': 'vp8', 'av1': 'av01.0.08M.08'}.get((info or {}).get('video_codec'), '')
    audio = {'aac': 'mp4a.40.2', 'mp3': 'mp4a.6B', 'opus': 'opus', 'vorbis': 'vorbis'}.get(
        (info or {}).get('audio_codec'), '')
    codecs = ', '.join(c for c in (codec, audio) if c)
    return f'{mime}; codecs="{codecs}"' if codecs else mime


# ─── live transcode levels ───────────────────────────────────────────────────

# (key, label, short side, max video kbps, audio kbps): the player's 畫質 menu, besides 原始
STREAM_LEVELS = (
    ('2160', '2160p', 2160, 16000, 160),
    ('1080h', '1080p 高', 1080, 8000, 160),
    ('1080l', '1080p 低', 1080, 4500, 128),
    ('720h', '720p 高', 720, 4000, 128),
    ('720l', '720p 低', 720, 2000, 128),
    ('480h', '480p 高', 480, 1500, 96),
    ('480l', '480p 低', 480, 800, 96),
)
STREAM_DEFAULT = '720h'
_encoder: Optional[str] = None
_encoder_lock = threading.Lock()


def stream_level(key: str) -> tuple:
    return next((l for l in STREAM_LEVELS if l[0] == key), None) or stream_level(STREAM_DEFAULT)


def stream_qualities(info: Optional[dict]) -> List[dict]:
    """Levels offered for a video: none above its resolution (the 480p ones always)."""
    w, h = (info or {}).get('width') or 0, (info or {}).get('height') or 0
    short, long_ = min(w, h), max(w, h)
    return [{'key': key, 'label': label, 'kbps': video + audio}
            for key, label, side, video, audio in STREAM_LEVELS
            if side == 480 or not short or short >= side * 0.9 or long_ >= side * 16 / 9 * 0.9]


def stream_encoder() -> str:
    """'nvenc' when an NVIDIA GPU can encode H.264 here, else 'cpu' (tested once; blocking).
    STREAM_ENCODER=cpu in .env forces the CPU."""
    global _encoder
    with _encoder_lock:
        if _encoder is None:
            _encoder = 'cpu'
            ffmpeg = find_tool('ffmpeg')
            if ffmpeg and os.environ.get('STREAM_ENCODER', '').strip().lower() != 'cpu':
                try:
                    test = subprocess.run(
                        [ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
                         'color=c=black:s=256x256:d=0.2', '-c:v', 'h264_nvenc', '-f', 'null', '-'],
                        capture_output=True, timeout=30, creationflags=_NO_WINDOW)
                    if test.returncode == 0:
                        _encoder = 'nvenc'
                except Exception:
                    pass
            logger.info(f"影片庫即時轉檔編碼器：{'NVIDIA NVENC (GPU)' if _encoder == 'nvenc' else 'libx264 (CPU)'}")
        return _encoder


def stream_command(ffmpeg: str, path: str, start: float, key: str, encoder: str) -> List[str]:
    """ffmpeg arguments for a fragmented H.264/AAC MP4 of `path` from `start` s at level `key`:
    fits a 16:9 box of the level (portrait: turned), never upscales, video capped at the level's bit rate."""
    _, _, side, video, audio = stream_level(key)
    box = (side * 16 // 9 + 1) // 2 * 2                          # 2160 -> 3840, 720 -> 1280, 480 -> 854
    scale = (f"scale=w='if(gte(iw,ih),min({box},iw),min({side},iw))':h='if(gte(iw,ih),min({side},ih),min({box},ih))'"
             f":force_original_aspect_ratio=decrease:force_divisible_by=2,format=yuv420p")
    rate = ['-maxrate', f'{video}k', '-bufsize', f'{video * 2}k']
    if encoder == 'nvenc':
        codec = ['-c:v', 'h264_nvenc', '-preset', 'p4', '-rc', 'vbr', '-cq', '23',
                 '-b:v', f'{video * 3 // 4}k', *rate, '-profile:v', 'high']
    else:
        codec = ['-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency', '-crf', '23', *rate]
    return [ffmpeg, '-hide_banner', '-loglevel', 'error',
            *(['-hwaccel', 'cuda'] if encoder == 'nvenc' else []),
            *threads_args(), '-ss', f'{start:.3f}', '-i', path, '-map', '0:v:0', '-map', '0:a:0?', '-sn', '-dn',
            '-vf', scale, *codec, *threads_args(), '-g', '48', '-c:a', 'aac', '-b:a', f'{audio}k', '-ac', '2',
            '-movflags', 'frag_keyframe+empty_moov+default_base_moof', '-f', 'mp4', 'pipe:1']


# ─── screenshots ─────────────────────────────────────────────────────────────

def make_screenshots(video: str, duration: float, count: int = SHOT_COUNT) -> List[str]:
    """`count` evenly spaced frames as JPEGs in the hidden shots folder. Returns the file names."""
    ffmpeg = find_tool('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('找不到 ffmpeg（請安裝並加入 PATH，或設定 FFMPEG_PATH）')
    folder = shots_dir(video)
    if os.path.isdir(folder):
        for old in os.listdir(folder):
            try:
                os.remove(os.path.join(folder, old))
            except OSError:
                pass
    os.makedirs(folder, exist_ok=True)
    _hide(folder)

    names = []
    threads = threads_args(share=2)          # the library makes screenshots in 2 background workers
    for i in range(count):
        t = duration * (i + 1) / (count + 1) if duration > 0 else 0
        name = f"{i + 1:02d}.jpg"
        out = os.path.join(folder, name)
        subprocess.run(
            [ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', *threads, '-ss', f'{t:.2f}', '-i', video,
             '-frames:v', '1', '-vf', f'scale={SHOT_WIDTH}:-2', '-q:v', '4', *threads, out],
            capture_output=True, timeout=120, creationflags=_NO_WINDOW,
        )
        if os.path.exists(out) and os.path.getsize(out) > 0:
            names.append(name)
        if duration <= 0:
            break
    if not names:
        raise RuntimeError('無法擷取影片截圖')
    return names


# ─── hover preview clip ──────────────────────────────────────────────────────

PREVIEW_NAME = 'preview.mp4'        # in the shots folder (removed / regenerated with the screenshots)
PREVIEW_PARTS = 6                   # short pieces from across the video
PREVIEW_PART_SECONDS = 1.5
PREVIEW_HEIGHT = 360


def preview_path(video: str) -> str:
    return os.path.join(shots_dir(video), PREVIEW_NAME)


def fresh_preview(video: str) -> Optional[str]:
    """The cached preview clip when it is newer than the video file, else None."""
    out = preview_path(video)
    try:
        if os.path.getsize(out) > 0 and os.path.getmtime(out) >= os.path.getmtime(video):
            return out
    except OSError:
        pass
    return None


def make_preview(video: str, duration: float) -> str:
    """A small muted clip for the hover preview: PREVIEW_PARTS pieces of PREVIEW_PART_SECONDS from across
    the video (the whole start of a short one), 360p H.264. Each piece is read with a fast seek, so a long
    video costs no more than a short one. Returns the path; raises RuntimeError."""
    ffmpeg = find_tool('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('找不到 ffmpeg（請安裝並加入 PATH，或設定 FFMPEG_PATH）')
    folder = shots_dir(video)
    os.makedirs(folder, exist_ok=True)
    _hide(folder)
    out = preview_path(video)
    tmp = out + '.part.mp4'
    threads = threads_args(share=2)
    scale = f'scale=-2:{PREVIEW_HEIGHT}:force_original_aspect_ratio=decrease,setsar=1,fps=24,format=yuv420p'
    if duration <= PREVIEW_PARTS * PREVIEW_PART_SECONDS * 2:
        # short video: its first seconds
        inputs = ['-t', f'{min(duration or 6, PREVIEW_PARTS * PREVIEW_PART_SECONDS):.2f}', '-i', video]
        graph = f'[0:v]{scale}[v]'
    else:
        inputs, parts = [], []
        for i in range(PREVIEW_PARTS):
            t = duration * (i + 0.5) / PREVIEW_PARTS
            inputs += ['-ss', f'{t:.2f}', '-t', f'{PREVIEW_PART_SECONDS}', '-i', video]
            parts.append(f'[{i}:v]{scale}[p{i}]')
        graph = ';'.join(parts) + ';' + ''.join(f'[p{i}]' for i in range(PREVIEW_PARTS)) + f'concat=n={PREVIEW_PARTS}:v=1:a=0[v]'
    result = subprocess.run(
        [ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', *threads, *inputs, '-filter_complex', graph, '-map', '[v]',
         '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '30', '-movflags', '+faststart', *threads, tmp],
        capture_output=True, timeout=180, creationflags=_NO_WINDOW,
    )
    if result.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
        try:
            os.remove(tmp)
        except OSError:
            pass
        err = result.stderr.decode('utf-8', 'replace').strip().splitlines()
        raise RuntimeError(f"無法產生預覽片段：{err[-1] if err else result.returncode}")
    os.replace(tmp, out)
    return out


# ─── photos ──────────────────────────────────────────────────────────────────

def process_image(path: str) -> Tuple[dict, List[str]]:
    """Info (size, format, bit depth) and a thumbnail (.shots/01.jpg) of a photo. Raises RuntimeError."""
    ext = os.path.splitext(path)[1].lower()
    folder = shots_dir(path)
    if os.path.isdir(folder):
        shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder, exist_ok=True)
    _hide(folder)
    out = os.path.join(folder, '01.jpg')
    size = os.path.getsize(path)

    if ext == '.gif':                               # animated: ffmpeg takes the first frame
        info = probe_info(path)
        info = {'width': info.get('width'), 'height': info.get('height'), 'size': size, 'format': 'GIF',
                'bit_depth': 8, 'channels': None, 'duration': info.get('duration') or None}
        make_screenshots(path, 0, count=1)
        return info, ['01.jpg']

    import cv2
    import numpy as np
    data = np.fromfile(path, dtype=np.uint8)          # cv2.imread can't open non-ASCII paths on Windows
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)      # applies the EXIF rotation, like browsers do
    if image is None:
        raise RuntimeError('無法讀取圖片（檔案不完整或格式不支援）')
    height, width = image.shape[:2]
    bit_depth, channels = 8, 3
    if ext == '.png':                                 # the only common format with 16-bit / alpha
        raw = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
        if raw is not None:
            bit_depth = 16 if raw.dtype == np.uint16 else 8
            channels = 1 if raw.ndim == 2 else raw.shape[2]
    scale = min(1.0, THUMB_MAX[0] / width, THUMB_MAX[1] / height)
    thumb = cv2.resize(image, (max(1, round(width * scale)), max(1, round(height * scale))),
                       interpolation=cv2.INTER_AREA) if scale < 1 else image
    ok, encoded = cv2.imencode('.jpg', thumb, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        raise RuntimeError('無法產生縮圖')
    encoded.tofile(out)
    fmt = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.webp': 'WebP', '.bmp': 'BMP'}.get(ext, ext[1:].upper())
    return {'width': width, 'height': height, 'size': size, 'format': fmt,
            'bit_depth': bit_depth, 'channels': channels}, ['01.jpg']


def remove_sidecars(video: str):
    try:
        os.remove(meta_path(video))
    except OSError:
        pass
    shutil.rmtree(shots_dir(video), ignore_errors=True)

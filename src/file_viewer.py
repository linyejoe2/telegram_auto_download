"""
src/file_viewer.py — Browse the downloads folder from the Telegram chat.

Inline-keyboard folder browser (all sub folders of a level on one keyboard, like the folder
selector), folder video previews (1 screenshot per video at 15s, sent in lazily generated
batches: this folder, or recursively all sub folders), file details (reachable with
`/files <file>`), single file previews (a video shows 3 screenshots: ~15s in, the middle,
15s before the end) and deletion of files / empty folders after a confirmation. Pure logic:
the bot owns the Telegram I/O and the owner check.

Callback data (all prefixed `fv_`, index based so they stay under Telegram's 64-byte limit):
  fv_cd:i  fv_f:i  fv_load  fv_up  fv_pv  fv_pva  fv_ph  fv_pha  fv_pn  fv_back  fv_prev  fv_del  fv_deld  fv_yes  fv_no  fv_close
"""

import io
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

NAME_LIMIT = 18
PREVIEW_EDGE_SECONDS = 15
FOLDERS_PER_ROW = 2
MAX_FILE_BUTTONS = 30             # files listed under the folders (no paging; Telegram caps a keyboard at 100 buttons)
FILE_NAME_LIMIT = 26
PREVIEW_BATCH = 10              # one Telegram album
PREVIEW_FRAME_SECONDS = 15      # the single screenshot of a folder preview
PREVIEW_MAX_WIDTH = 1280

VIDEO_EXTS = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.wmv', '.flv', '.m4v', '.ts'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
AUDIO_EXTS = {'.mp3', '.m4a', '.wav', '.flac', '.ogg', '.opus', '.aac'}
ARCHIVE_EXTS = {'.zip', '.rar', '.7z', '.tar', '.gz'}
DOC_EXTS = {'.pdf', '.doc', '.docx', '.txt', '.xls', '.xlsx', '.ppt', '.pptx'}


# ─── formatting helpers ──────────────────────────────────────────────────────

def fmt_size(num_bytes: float) -> str:
    size = float(num_bytes)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f"{size:.0f} {unit}" if unit == 'B' else f"{size:.1f} {unit}"
        size /= 1024


def fmt_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def file_icon(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    if ext in VIDEO_EXTS:
        return '🎬'
    if ext in IMAGE_EXTS:
        return '🖼'
    if ext in AUDIO_EXTS:
        return '🎵'
    if ext in ARCHIVE_EXTS:
        return '🗜'
    if ext in DOC_EXTS:
        return '📄'
    return '📎'


def is_previewable(name: str) -> bool:
    ext = os.path.splitext(name)[1].lower()
    return ext in VIDEO_EXTS or ext in IMAGE_EXTS


def _short(name: str, limit: int = NAME_LIMIT) -> str:
    return name if len(name) <= limit else name[:limit - 1] + '…'


# ─── source link ─────────────────────────────────────────────────────────────

def source_link(record: Optional[dict]) -> Optional[str]:
    """Where a downloaded file came from, built from its download record.

    X account downloads  -> the tweet (message_id holds the tweet id)
    YouTube / X / ... links -> the original URL (file_id holds it)
    Telegram media       -> t.me/c/<channel>/<message> (works for channels you are a member of)
    """
    if not record:
        return None
    file_id = str(record.get('file_id') or '')
    message_id = record.get('message_id') or 0
    if str(record.get('file_unique_id') or '').startswith('xprofile_') and message_id:
        return f"https://x.com/i/status/{message_id}"
    if file_id.lower().startswith(('http://', 'https://')):
        return file_id
    chat_id = str(record.get('chat_id') or '0')
    if chat_id.startswith('-100'):
        chat_id = chat_id[4:]
    if chat_id not in ('', '0') and message_id:
        return f"https://t.me/c/{chat_id}/{message_id}"
    return None


# ─── previews (blocking: run in an executor) ─────────────────────────────────

def preview_times(duration: float) -> List[float]:
    """Timestamps (seconds) to screenshot: ~15s in, the middle, 15s before the end.

    Videos shorter than 45s can't fit three distinct frames that far apart, so they use
    10% / 50% / 90% of the duration instead.
    """
    if duration >= PREVIEW_EDGE_SECONDS * 3:
        return [PREVIEW_EDGE_SECONDS, duration / 2, duration - PREVIEW_EDGE_SECONDS]
    return [duration * 0.1, duration * 0.5, duration * 0.9]


def probe_video(path: str) -> Optional[Tuple[float, int, int]]:
    """Return (duration_seconds, width, height) or None if the video can't be read."""
    import cv2
    cap = cv2.VideoCapture(path)
    try:
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        duration = frames / fps if fps > 0 and frames > 0 else 0
        return duration, width, height
    finally:
        cap.release()


def _encode_jpeg_cv(frame) -> bytes:
    import cv2
    height, width = frame.shape[:2]
    if width > PREVIEW_MAX_WIDTH:
        scale = PREVIEW_MAX_WIDTH / width
        frame = cv2.resize(frame, (PREVIEW_MAX_WIDTH, int(height * scale)))
    ok, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise ValueError('無法編碼預覽圖片')
    return buffer.tobytes()


def build_video_preview(path: str) -> List[Tuple[bytes, str]]:
    import cv2
    cap = cv2.VideoCapture(path)
    try:
        if not cap.isOpened():
            raise ValueError('無法開啟影片')
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        if fps <= 0 or total <= 0:
            raise ValueError('無法讀取影片長度')
        duration = total / fps

        frames = []
        for t in preview_times(duration):
            index = min(int(t * fps), int(total) - 1)
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, index))
            ok, frame = cap.read()
            if ok:
                frames.append((_encode_jpeg_cv(frame), f"▶️ {fmt_duration(t)} / {fmt_duration(duration)}"))
        if not frames:
            raise ValueError('無法擷取影片畫面')
        return frames
    finally:
        cap.release()


def build_image_preview(path: str) -> List[Tuple[bytes, str]]:
    from PIL import Image
    with Image.open(path) as img:
        width, height = img.size
        img = img.convert('RGB')
        img.thumbnail((1600, 1600))
        buffer = io.BytesIO()
        img.save(buffer, 'JPEG', quality=88)
    return [(buffer.getvalue(), f"{width}x{height}")]


def build_preview(path: str) -> List[Tuple[bytes, str]]:
    """Return [(jpeg_bytes, caption), ...] — 1 image, or 3 video screenshots. Raises ValueError."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in VIDEO_EXTS:
            return build_video_preview(path)
        if ext in IMAGE_EXTS:
            return build_image_preview(path)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f'無法產生預覽: {e}')
    raise ValueError('此檔案類型不支援預覽')


def build_frame_preview(path: str) -> Tuple[bytes, str]:
    """One screenshot at 15s (the middle for videos shorter than 16s). Raises ValueError."""
    import cv2
    cap = cv2.VideoCapture(path)
    try:
        if not cap.isOpened():
            raise ValueError('無法開啟影片')
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        if fps <= 0 or total <= 0:
            raise ValueError('無法讀取影片長度')
        duration = total / fps
        t = PREVIEW_FRAME_SECONDS if duration > PREVIEW_FRAME_SECONDS + 1 else duration / 2
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, min(int(t * fps), int(total) - 1)))
        ok, frame = cap.read()
        if not ok:
            raise ValueError('無法擷取影片畫面')
        return _encode_jpeg_cv(frame), f"▶️ {fmt_duration(t)} / {fmt_duration(duration)}"
    finally:
        cap.release()


def list_media(directory: str, recursive: bool, exts: set) -> List[str]:
    """Files with one of `exts` in a folder (optionally with all sub folders), grouped by folder, sorted by name."""
    def is_video(name: str) -> bool:
        return not name.startswith('.') and os.path.splitext(name)[1].lower() in exts

    found: List[str] = []
    try:
        if recursive:
            for root, dirs, files in os.walk(directory):
                dirs[:] = sorted((d for d in dirs if not d.startswith('.')), key=str.lower)
                found.extend(os.path.join(root, f) for f in sorted(files, key=str.lower) if is_video(f))
        else:
            with os.scandir(directory) as it:
                names = [i.name for i in it if i.is_file() and is_video(i.name)]
            found = [os.path.join(directory, n) for n in sorted(names, key=str.lower)]
    except OSError as e:
        logger.warning(f"無法讀取資料夾 {directory}: {e}")
    return found


def list_videos(directory: str, recursive: bool) -> List[str]:
    return list_media(directory, recursive, VIDEO_EXTS)


def list_photos(directory: str, recursive: bool) -> List[str]:
    return list_media(directory, recursive, IMAGE_EXTS)


def build_batch_preview(paths: List[str], names: List[str]) -> Tuple[List[Tuple[bytes, str]], int]:
    """[(jpeg, caption)] for each readable video (1 screenshot) / photo, plus the number that failed. Blocking."""
    frames, failed = [], 0
    for path, name in zip(paths, names):
        try:
            if os.path.splitext(path)[1].lower() in IMAGE_EXTS:
                data, label = build_image_preview(path)[0]
            else:
                data, label = build_frame_preview(path)
        except Exception as e:
            logger.warning(f"預覽失敗 {path}: {e}")
            failed += 1
            continue
        caption = f"{name}\n{label}"
        link = source_link(FileViewer._find_record(path))
        if link:
            caption += f"\n🔗 {link}"
        frames.append((data, caption))
    return frames, failed


# ─── browser state & rendering ───────────────────────────────────────────────

@dataclass
class Entry:
    name: str
    is_dir: bool
    size: int = 0
    mtime: float = 0.0


@dataclass
class ViewState:
    rel_path: str = ""                       # relative to the downloads folder
    entries: List[Entry] = field(default_factory=list)   # sub folders as last rendered (callbacks index into this)
    preview_files: List[str] = field(default_factory=list)    # absolute paths of the running folder preview
    preview_pos: int = 0                     # how many of them were already sent
    preview_kind: str = "video"              # "video" or "photo"
    preview_label: str = ""
    selected: Optional[str] = None           # file name whose detail page is open
    pending_delete: Optional[str] = None     # absolute path awaiting confirmation


@dataclass
class PreviewBatch:
    paths: List[str]                         # videos to screenshot now
    names: List[str]                         # their display names (relative to the browsed folder)
    text: str                                # progress text for the control message below the album
    markup: Optional[InlineKeyboardMarkup]   # "next page" button, None when everything was shown
    new_message: bool                        # True: first batch (pressed message is the folder list)


@dataclass
class ViewResult:
    text: Optional[str]                      # None = nothing to edit
    markup: Optional[InlineKeyboardMarkup] = None
    preview_path: Optional[str] = None       # caller should send a preview of this file
    batch: Optional[PreviewBatch] = None     # caller should send these folder-preview screenshots
    load_path: Optional[str] = None          # caller should upload this video to the chat (Telethon)


class FileViewer:
    def __init__(self, base_path: Callable[[], str]):
        self._base_path = base_path
        self.states: Dict[int, ViewState] = {}

    # ── paths ──

    def _base(self) -> str:
        return os.path.realpath(self._base_path())

    def _resolve(self, rel: str) -> Optional[str]:
        """Absolute path for `rel`, or None if it would leave the downloads folder."""
        base = self._base()
        target = os.path.realpath(os.path.join(base, rel))
        try:
            common = os.path.commonpath([base, target])
        except ValueError:  # different drives
            return None
        return target if os.path.normcase(common) == os.path.normcase(base) else None

    def _rel_of(self, absolute: str) -> str:
        rel = os.path.relpath(absolute, self._base())
        return "" if rel == "." else rel

    @staticmethod
    def _display(rel: str) -> str:
        return "/" + rel.replace(os.sep, "/") if rel else "/"

    def _state(self, user_id: int) -> ViewState:
        return self.states.setdefault(user_id, ViewState())

    @staticmethod
    def _list(directory: str) -> List[Entry]:
        folders, files = [], []
        try:
            with os.scandir(directory) as it:
                for item in it:
                    if item.name.startswith('.') or item.name.endswith('.part'):
                        continue  # hidden files and in-progress downloads
                    try:
                        if item.is_dir():
                            folders.append(Entry(item.name, True))
                        else:
                            st = item.stat()
                            files.append(Entry(item.name, False, st.st_size, st.st_mtime))
                    except OSError:
                        continue
        except OSError as e:
            logger.warning(f"無法讀取資料夾 {directory}: {e}")
        folders.sort(key=lambda e: e.name.lower())
        files.sort(key=lambda e: e.mtime, reverse=True)  # newest downloads first
        return folders + files

    # ── public API ──

    def start(self, user_id: int, arg: str = "") -> ViewResult:
        """Open the viewer at the root, or at `arg` (a folder or file inside the downloads folder)."""
        self.states[user_id] = state = ViewState()
        arg = arg.strip().strip('"').strip("/\\")
        note = ""
        if arg:
            target = self._resolve(arg)
            if target and os.path.isdir(target):
                state.rel_path = self._rel_of(target)
            elif target and os.path.isfile(target):
                state.rel_path = self._rel_of(os.path.dirname(target))
                state.selected = os.path.basename(target)
                return self._render_detail(user_id)
            else:
                note = f"❓ 找不到「{arg}」，已顯示根目錄\n\n"
        return self._render_list(user_id, note)

    def handle_callback(self, user_id: int, data: str) -> ViewResult:
        state = self._state(user_id)
        action, _, arg = data.partition(':')

        if action == 'fv_close':
            self.states.pop(user_id, None)
            return ViewResult("📂 已關閉檔案瀏覽")

        if action == 'fv_cd':
            entry = self._entry(state, arg)
            if entry and entry.is_dir:
                state.rel_path = os.path.join(state.rel_path, entry.name)
                state.selected = None
        elif action == 'fv_f':
            entry = self._entry(state, arg)
            if entry and not entry.is_dir:
                state.selected = entry.name
                return self._render_detail(user_id)
        elif action in ('fv_pv', 'fv_pva', 'fv_ph', 'fv_pha'):
            kind = 'photo' if action in ('fv_ph', 'fv_pha') else 'video'
            recursive = action in ('fv_pva', 'fv_pha')
            directory = self._resolve(state.rel_path)
            lister = list_photos if kind == 'photo' else list_videos
            files = lister(directory, recursive) if directory else []
            if not files:
                return self._render_list(user_id, "❓ 沒有可載入的" + ("照片" if kind == 'photo' else "影片") + "\n\n")
            state.preview_files, state.preview_pos, state.preview_kind = files, 0, kind
            where = self._display(state.rel_path)
            state.preview_label = f"{where}（含子資料夾）" if recursive else where
            return ViewResult(None, batch=self._next_batch(state, True))
        elif action == 'fv_pn':
            if state.preview_pos >= len(state.preview_files):
                return ViewResult("⚠️ 預覽已結束或已過期，請重新選擇資料夾預覽")
            return ViewResult(None, batch=self._next_batch(state, False))
        elif action == 'fv_up':
            state.rel_path = os.path.dirname(state.rel_path)
            state.selected = None
        elif action == 'fv_back':
            state.selected = state.pending_delete = None
        elif action == 'fv_load':
            path = self._selected_path(state)
            if path and os.path.splitext(path)[1].lower() in VIDEO_EXTS:
                return ViewResult(None, load_path=path)
        elif action == 'fv_prev':
            path = self._selected_path(state)
            if path and is_previewable(state.selected):
                return ViewResult(None, preview_path=path)
        elif action == 'fv_del':
            path = self._selected_path(state)
            if path:
                state.pending_delete = path
                return self._render_confirm(state)
        elif action == 'fv_deld':
            directory = self._resolve(state.rel_path)
            if state.rel_path and directory and os.path.isdir(directory) and not os.listdir(directory):
                state.pending_delete = directory
                return self._render_confirm(state)
        elif action == 'fv_no':
            state.pending_delete = None
            if state.selected:
                return self._render_detail(user_id)
        elif action == 'fv_yes':
            return self._delete_pending(user_id)

        return self._render_list(user_id)

    # ── internals ──

    @staticmethod
    def _entry(state: ViewState, index: str) -> Optional[Entry]:
        if index.isdigit() and int(index) < len(state.entries):
            return state.entries[int(index)]
        return None

    def _selected_path(self, state: ViewState) -> Optional[str]:
        if not state.selected:
            return None
        path = self._resolve(os.path.join(state.rel_path, state.selected))
        return path if path and os.path.isfile(path) else None

    def _delete_pending(self, user_id: int) -> ViewResult:
        state = self._state(user_id)
        path, state.pending_delete = state.pending_delete, None
        if not path or not self._resolve(self._rel_of(path)) or os.path.normcase(path) == os.path.normcase(self._base()):
            return self._render_list(user_id)
        name = os.path.basename(path)
        try:
            if os.path.isdir(path):
                os.rmdir(path)                       # only succeeds for empty folders
                state.rel_path = os.path.dirname(state.rel_path)
            else:
                os.remove(path)
            logger.info(f"檔案瀏覽：已刪除 {path}")
            note = f"🗑 已刪除「{name}」\n\n"
        except OSError as e:
            logger.warning(f"檔案瀏覽：刪除失敗 {path}: {e}")
            note = f"❌ 刪除失敗：{e.strerror or e}\n\n"
        state.selected = None
        return self._render_list(user_id, note)

    def _next_batch(self, state: ViewState, new_message: bool) -> PreviewBatch:
        start = state.preview_pos
        paths = state.preview_files[start:start + PREVIEW_BATCH]
        state.preview_pos = start + len(paths)
        total, shown = len(state.preview_files), state.preview_pos
        photo = state.preview_kind == 'photo'
        unit = "張照片" if photo else "部影片"
        base = self._resolve(state.rel_path) or self._base()
        names = [os.path.relpath(p, base) for p in paths]
        text = f"{'🖼' if photo else '🎞'} {state.preview_label}\n已{'載入' if photo else '預覽'} {shown}/{total} {unit}"
        markup = None
        if shown < total:
            label = f"▶️ 下一頁（剩餘 {total - shown} {unit[0]}）"
            markup = InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data="fv_pn")]])
        else:
            text += "\n✅ 已全部" + ("載入" if photo else "預覽")
        return PreviewBatch(paths, names, text, markup, new_message)

    def _render_list(self, user_id: int, note: str = "") -> ViewResult:
        state = self._state(user_id)
        directory = self._resolve(state.rel_path)
        if directory is None or not os.path.isdir(directory):
            state.rel_path, directory = "", self._base()

        entries = self._list(directory)
        folders = [e for e in entries if e.is_dir]
        files = [e for e in entries if not e.is_dir]
        shown_files = files[:MAX_FILE_BUTTONS]          # newest first
        state.entries = folders + shown_files          # fv_cd / fv_f index into this (folders first)
        state.selected = state.pending_delete = None

        counts = {'video': 0, 'photo': 0, 'other': 0}
        for e in files:
            ext = os.path.splitext(e.name)[1].lower()
            counts['video' if ext in VIDEO_EXTS else 'photo' if ext in IMAGE_EXTS else 'other'] += 1
        total = sum(e.size for e in files)
        lines = [f"📂 {self._display(state.rel_path)}",
                 f"📁 {len(folders)} 個資料夾 | 影片 {counts['video']} 個 | 照片 {counts['photo']} 個 | "
                 f"檔案 {counts['other']} 個 | {fmt_size(total)}"]
        if not entries:
            lines.append("（空資料夾）")

        keyboard = []
        for i in range(0, len(folders), FOLDERS_PER_ROW):
            row = []
            for idx in range(i, min(i + FOLDERS_PER_ROW, len(folders))):
                name = folders[idx].name
                row.append(InlineKeyboardButton(f"📁 {_short(name)}", callback_data=f"fv_cd:{idx}"))
            keyboard.append(row)

        # files of this level (newest first) -> tap for details / source link / preview / delete
        for offset, entry in enumerate(shown_files):
            label = f"{file_icon(entry.name)} {_short(entry.name, FILE_NAME_LIMIT)} · {fmt_size(entry.size)}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"fv_f:{len(folders) + offset}")])
        if len(files) > len(shown_files):
            lines.append(f"（只列出最新 {len(shown_files)} 個檔案，共 {len(files)} 個）")

        # video previews: this level, and (when any exist below) all sub folders
        all_videos = len(list_videos(directory, True)) if folders or counts['video'] else 0
        if counts['video']:
            keyboard.append([InlineKeyboardButton(f"🎞 預覽資料夾影片 ({counts['video']})", callback_data="fv_pv")])
        if all_videos > counts['video']:
            keyboard.append([InlineKeyboardButton(f"🎞 預覽資料夾內所有影片 ({all_videos})", callback_data="fv_pva")])

        # photo loading: same idea
        all_photos = len(list_photos(directory, True)) if folders or counts['photo'] else 0
        if counts['photo']:
            keyboard.append([InlineKeyboardButton(f"🖼 載入照片 ({counts['photo']})", callback_data="fv_ph")])
        if all_photos > counts['photo']:
            keyboard.append([InlineKeyboardButton(f"🖼 載入所有照片 ({all_photos})", callback_data="fv_pha")])

        actions = []
        if state.rel_path:
            actions.append(InlineKeyboardButton("⬆️ 返回上級", callback_data="fv_up"))
            if not entries:
                actions.append(InlineKeyboardButton("🗑 刪除此資料夾", callback_data="fv_deld"))
        actions.append(InlineKeyboardButton("❌ 關閉", callback_data="fv_close"))
        keyboard.append(actions)

        return ViewResult(note + "\n".join(lines), InlineKeyboardMarkup(keyboard))

    def _render_detail(self, user_id: int) -> ViewResult:
        state = self._state(user_id)
        path = self._selected_path(state)
        if not path:
            return self._render_list(user_id, "❓ 檔案已不存在\n\n")

        st = os.stat(path)
        name = state.selected
        lines = [f"{file_icon(name)} {name}",
                 f"📦 大小: {fmt_size(st.st_size)}",
                 f"🕒 修改時間: {time.strftime('%Y-%m-%d %H:%M', time.localtime(st.st_mtime))}",
                 f"📁 位置: {self._display(state.rel_path)}"]
        if os.path.splitext(name)[1].lower() in VIDEO_EXTS:
            info = probe_video(path)
            if info and info[0] > 0:
                lines.append(f"⏱ 時長: {fmt_duration(info[0])} | {info[1]}x{info[2]}")

        record = self._find_record(path)
        link = source_link(record)
        if link:
            lines.append(f"🔗 來源: {link}")
        else:
            lines.append("🔗 來源: 未知（沒有這個檔案的下載記錄）" if not record else "🔗 來源: 未知")
        if record and record.get('download_date'):
            lines.append(f"📥 下載時間: {str(record['download_date'])[:16]}")

        keyboard = []
        if link:
            keyboard.append([InlineKeyboardButton("🔗 開啟來源", url=link)])
        if os.path.splitext(name)[1].lower() in VIDEO_EXTS:
            keyboard.append([InlineKeyboardButton("📤 載入影片", callback_data="fv_load")])
        if is_previewable(name):
            keyboard.append([InlineKeyboardButton("🖼 預覽", callback_data="fv_prev")])
        keyboard.append([InlineKeyboardButton("🗑 刪除", callback_data="fv_del"),
                         InlineKeyboardButton("⬅️ 返回", callback_data="fv_back")])
        return ViewResult("\n".join(lines), InlineKeyboardMarkup(keyboard))

    @staticmethod
    def _find_record(path: str) -> Optional[dict]:
        try:
            from .database import DatabaseManager
            return DatabaseManager().find_download(path)
        except Exception as e:
            logger.warning(f"查詢下載記錄失敗: {e}")
            return None

    def _render_confirm(self, state: ViewState) -> ViewResult:
        what = "資料夾" if os.path.isdir(state.pending_delete) else "檔案"
        text = (f"⚠️ 確定要刪除{what}「{os.path.basename(state.pending_delete)}」嗎？\n"
                f"此動作無法復原。")
        keyboard = [[InlineKeyboardButton("✅ 確認刪除", callback_data="fv_yes"),
                     InlineKeyboardButton("↩️ 取消", callback_data="fv_no")]]
        return ViewResult(text, InlineKeyboardMarkup(keyboard))

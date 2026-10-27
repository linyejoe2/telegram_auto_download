"""
src/file_viewer.py — Browse the downloads folder from the Telegram chat.

Inline-keyboard file browser (folders, files, pagination), file details, image / video
previews (a video shows 3 screenshots: ~15s in, the middle, 15s before the end) and
deletion of files / empty folders after a confirmation. Pure logic: the bot owns the
Telegram I/O and the owner check.

Callback data (all prefixed `fv_`, index based so they stay under Telegram's 64-byte limit):
  fv_cd:i  fv_f:i  fv_pg:n  fv_up  fv_back  fv_prev  fv_del  fv_deld  fv_yes  fv_no  fv_close
"""

import io
import logging
import math
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

PAGE_SIZE = 8
NAME_LIMIT = 26
PREVIEW_EDGE_SECONDS = 15
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
    page: int = 0
    entries: List[Entry] = field(default_factory=list)   # as last rendered (callbacks index into this)
    selected: Optional[str] = None           # file name whose detail page is open
    pending_delete: Optional[str] = None     # absolute path awaiting confirmation


@dataclass
class ViewResult:
    text: Optional[str]                      # None = nothing to edit
    markup: Optional[InlineKeyboardMarkup] = None
    preview_path: Optional[str] = None       # caller should send a preview of this file


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
                state.page, state.selected = 0, None
        elif action == 'fv_f':
            entry = self._entry(state, arg)
            if entry and not entry.is_dir:
                state.selected = entry.name
                return self._render_detail(user_id)
        elif action == 'fv_pg':
            state.page = int(arg) if arg.lstrip('-').isdigit() else 0
        elif action == 'fv_up':
            state.rel_path = os.path.dirname(state.rel_path)
            state.page, state.selected = 0, None
        elif action == 'fv_back':
            state.selected = state.pending_delete = None
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
        state.page = 0
        return self._render_list(user_id, note)

    def _render_list(self, user_id: int, note: str = "") -> ViewResult:
        state = self._state(user_id)
        directory = self._resolve(state.rel_path)
        if directory is None or not os.path.isdir(directory):
            state.rel_path, directory = "", self._base()

        entries = self._list(directory)
        state.entries = entries
        state.selected = state.pending_delete = None
        pages = max(1, math.ceil(len(entries) / PAGE_SIZE))
        state.page = min(max(state.page, 0), pages - 1)

        folders = sum(1 for e in entries if e.is_dir)
        files = len(entries) - folders
        total = sum(e.size for e in entries if not e.is_dir)
        lines = [f"📂 {self._display(state.rel_path)}",
                 f"📁 {folders} 個資料夾 | 📄 {files} 個檔案 | {fmt_size(total)}"]
        if pages > 1:
            lines.append(f"第 {state.page + 1}/{pages} 頁")
        if not entries:
            lines.append("（空資料夾）")

        keyboard = []
        start = state.page * PAGE_SIZE
        for offset, entry in enumerate(entries[start:start + PAGE_SIZE]):
            index = start + offset
            if entry.is_dir:
                try:
                    count = len(os.listdir(os.path.join(directory, entry.name)))
                except OSError:
                    count = 0
                label, data = f"📁 {_short(entry.name)} ({count})", f"fv_cd:{index}"
            else:
                label, data = f"{file_icon(entry.name)} {_short(entry.name)} · {fmt_size(entry.size)}", f"fv_f:{index}"
            keyboard.append([InlineKeyboardButton(label, callback_data=data)])

        paging = []
        if state.page > 0:
            paging.append(InlineKeyboardButton("◀️ 上一頁", callback_data=f"fv_pg:{state.page - 1}"))
        if state.page < pages - 1:
            paging.append(InlineKeyboardButton("下一頁 ▶️", callback_data=f"fv_pg:{state.page + 1}"))
        if paging:
            keyboard.append(paging)

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

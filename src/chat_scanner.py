"""/chats: download every photo and video of a group or channel the logged-in account has joined.

- `list_chats()` lists the account's groups and channels (Telethon dialogs, most recent first);
  `render_chat_list()` pages them as inline buttons (`ch_pick:<i>`, `ch_pg:<page>`, `ch_x`).
- `scan_chat()` walks the whole history with Telegram's photo/video filter and keeps only the ids that
  aren't downloaded yet (checked BEFORE downloading, so a second run, or a run after a restart, only
  fetches what is missing), plus the album captions used as the files' description.
- A started download is saved in `<downloads>/.tad/chat_jobs.json` until it finishes or is stopped,
  so the bot resumes it after a restart (rescanning and skipping what is already there).
"""
import json
import logging
import os
import time
from datetime import datetime
from typing import Awaitable, Callable, Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telethon.tl.types import InputMessagesFilterPhotoVideo, MessageMediaPhoto

logger = logging.getLogger(__name__)

PAGE_SIZE = 10
JOBS_FILE = 'chat_jobs.json'


# ─── chat list ───────────────────────────────────────────────────────────────

async def list_chats(client, query: str = '') -> List[dict]:
    """Groups and channels the account is in, most recently active first: [{id, title, kind, entity}]."""
    needle = query.strip().lower()
    chats = []
    async for d in client.iter_dialogs():
        if not (d.is_group or d.is_channel):
            continue
        title = d.name or str(d.id)
        if needle and needle not in title.lower():
            continue
        chats.append({'id': d.id, 'title': title, 'kind': 'group' if d.is_group else 'channel', 'entity': d.entity})
    return chats


def render_chat_list(chats: List[dict], page: int, query: str = ''):
    """(text, markup) for one page of the chat list."""
    pages = max(1, (len(chats) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(page, 0), pages - 1)
    found = f"名稱含「{query}」的" if query else ""
    if not chats:
        text = f"找不到{found}群組或頻道。\n用法：/chats 或 /chats 關鍵字"
        return text, InlineKeyboardMarkup([[InlineKeyboardButton("✖ 關閉", callback_data="ch_x")]])
    text = (f"📚 選擇要下載的{found}群組 / 頻道（共 {len(chats)} 個，第 {page + 1}/{pages} 頁）\n"
            f"會掃描全部的照片與影片，已下載過的會略過。\n可用 /chats 關鍵字 搜尋名稱")
    rows = []
    for i in range(page * PAGE_SIZE, min(len(chats), (page + 1) * PAGE_SIZE)):
        c = chats[i]
        icon = '👥' if c['kind'] == 'group' else '📢'
        title = c['title'] if len(c['title']) <= 40 else c['title'][:39] + '…'
        rows.append([InlineKeyboardButton(f"{icon} {title}", callback_data=f"ch_pick:{i}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ 上一頁", callback_data=f"ch_pg:{page - 1}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("下一頁 ▶", callback_data=f"ch_pg:{page + 1}"))
    nav.append(InlineKeyboardButton("✖ 關閉", callback_data="ch_x"))
    rows.append(nav)
    return text, InlineKeyboardMarkup(rows)


# ─── scan ────────────────────────────────────────────────────────────────────

def is_photo(message) -> bool:
    return isinstance(getattr(message, 'media', None), MessageMediaPhoto)


async def scan_chat(client, entity, is_downloaded: Callable, media_size: Callable,
                    on_progress: Optional[Callable[[dict], Awaitable[None]]] = None,
                    should_stop: Optional[Callable[[], bool]] = None) -> dict:
    """Every photo / video of the chat, oldest first. Returns
    {ids (not downloaded yet), captions {grouped_id: text}, total, photos, videos, done, size, stopped}."""
    result = {'ids': [], 'captions': {}, 'total': 0, 'photos': 0, 'videos': 0, 'done': 0, 'size': 0,
              'stopped': False}
    last = 0.0
    async for m in client.iter_messages(entity, filter=InputMessagesFilterPhotoVideo(), reverse=True):
        if should_stop and should_stop():
            result['stopped'] = True
            break
        if not getattr(m, 'media', None):
            continue
        result['total'] += 1
        result['photos' if is_photo(m) else 'videos'] += 1
        if m.grouped_id and (m.message or '').strip():
            result['captions'].setdefault(m.grouped_id, m.message.strip())
        if is_downloaded(m):
            result['done'] += 1
        else:
            result['ids'].append(m.id)
            result['size'] += media_size(m) or 0
        if on_progress and time.monotonic() - last > 3:
            last = time.monotonic()
            await on_progress(result)
    return result


def scan_summary(title: str, scan: dict) -> str:
    size = scan['size'] / 1024 ** 3
    size_text = f"{size:.2f} GB" if size >= 1 else f"{scan['size'] / 1024 ** 2:.1f} MB"
    return (f"📚 「{title}」共 {scan['total']} 個媒體（照片 {scan['photos']}、影片 {scan['videos']}）\n"
            f"已下載過（含已刪除）：{scan['done']} 個\n"
            f"將下載：{len(scan['ids'])} 個，約 {size_text}")


# ─── saved jobs (resume after a restart) ─────────────────────────────────────

def _jobs_path(base: str) -> str:
    from config.config import get_data_dir
    return os.path.join(get_data_dir(base), JOBS_FILE)


def load_jobs(base: str) -> Dict[str, dict]:
    try:
        with open(_jobs_path(base), encoding='utf-8') as f:
            data = json.load(f)
        jobs = data.get('jobs') if isinstance(data, dict) else None
        return jobs if isinstance(jobs, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning(f"讀取 {JOBS_FILE} 失敗: {e}")
        return {}


def _write_jobs(base: str, jobs: Dict[str, dict]):
    path = _jobs_path(base)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'version': 1, 'jobs': jobs}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def save_job(base: str, job: dict):
    """Remember a started chat download: {chat_id, title, folder (relative to the downloads folder), user_id}."""
    try:
        jobs = load_jobs(base)
        saved = {k: job[k] for k in ('chat_id', 'title', 'folder', 'user_id')}
        saved['started'] = job.get('started') or datetime.now().isoformat(timespec='seconds')
        jobs[str(job['chat_id'])] = saved
        _write_jobs(base, jobs)
    except Exception as e:
        logger.warning(f"儲存頻道下載工作失敗: {e}")


def remove_job(base: str, chat_id):
    try:
        jobs = load_jobs(base)
        if jobs.pop(str(chat_id), None) is not None:
            _write_jobs(base, jobs)
    except Exception as e:
        logger.warning(f"移除頻道下載工作失敗: {e}")

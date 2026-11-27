"""主演 / 系列 typed in the bot right before a download (v3.9.0).

The bot asks after the folder is confirmed; the answer is one message:

    主演（多位用逗號、頓號分隔）
    系列（可省略）

The tags of the running download live in a context variable, so `DownloadRecords.record_download()`
writes them into every file's sidecar no matter which downloader (Telegram, YouTube, X, /chats...)
recorded it; tasks started by the download inherit it.
"""
import contextvars
import re
from typing import Optional

from library.media import clean_tags

SERIES_MAX = 200
_EMPTY = {'-', '－', '—', '無', 'none', 'n/a', 'x'}
_SPLIT = re.compile(r'\s*[,，、;；/／&＆]+\s*')
_LABEL = re.compile(r'^(主演|演員|actors?|系列|series)\s*[:：]\s*(.*)$', re.I)

_current = contextvars.ContextVar('download_tags', default=None)


def normalize(tags) -> Optional[dict]:
    """{'actors': [...], 'series': str} or None when there is nothing to set."""
    if not isinstance(tags, dict):
        return None
    actors = clean_tags(a for a in (tags.get('actors') or []) if isinstance(a, str))
    series = str(tags.get('series') or '').strip()[:SERIES_MAX]
    return {'actors': actors, 'series': series} if actors or series else None


def parse(text: str) -> Optional[dict]:
    """First line 主演, second line 系列. Lines may also be labelled (「系列：…」 in any order);
    「-」 leaves a field empty (e.g. only a 系列). None when nothing was given."""
    fields = {}
    plain = []
    for line in (text or '').splitlines():
        line = line.strip()
        if not line:
            continue
        m = _LABEL.match(line)
        if m:
            key = 'series' if m.group(1).lower() in ('系列', 'series') else 'actors'
            fields[key] = m.group(2).strip()
        else:
            plain.append(line)
    for key in ('actors', 'series'):
        if key not in fields and plain:
            fields[key] = plain.pop(0)
    actors = fields.get('actors', '')
    series = fields.get('series', '')
    actors = [] if actors.lower() in _EMPTY else _SPLIT.split(actors)
    series = '' if series.lower() in _EMPTY else series
    return normalize({'actors': actors, 'series': series})


def describe(tags: Optional[dict]) -> str:
    """「主演：A、B ｜ 系列：S」 ('' without tags)."""
    tags = normalize(tags)
    if not tags:
        return ''
    parts = []
    if tags['actors']:
        parts.append(f"主演：{'、'.join(tags['actors'])}")
    if tags['series']:
        parts.append(f"系列：{tags['series']}")
    return ' ｜ '.join(parts)


def current() -> Optional[dict]:
    """Tags of the download running in this task (None = none)."""
    return _current.get()


def use(tags):
    """Set the tags for this task and the tasks it starts; returns the token for `reset()`."""
    return _current.set(normalize(tags))


def reset(token):
    _current.reset(token)

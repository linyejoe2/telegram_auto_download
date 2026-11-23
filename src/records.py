"""
src/records.py — Download records kept next to the files (v3.3.0, replaces the SQLite database).

Every downloaded file's record lives in its hidden sidecar `.<file>.meta.json` under "download"
(the same file the web library keeps title / actors / screenshot info in), so records move, rename
and travel with the files: another PC that opens the same downloads folder sees the same history.

  <downloads>/.tad/deleted.json   records of deleted downloads: not offered again by the startup scan
                                   or /rescan, listed on the web library's 下載紀錄 page (download again)

An in-memory index built by walking the folder answers the bot's "already downloaded?" checks; it is
refreshed in the background (other PCs may add files) and kept current for changes made here.
The returned records keep the old database row keys (file_unique_id, file_id, message_id, chat_id,
file_name, file_path, file_size, file_type, mime_type, download_date, message_date).
"""

import json
import logging
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from library import media

logger = logging.getLogger(__name__)

DELETED_FILE = 'deleted.json'
REFRESH_SECONDS = 120          # re-walk the folder at most this often (another PC may have added files)
META_SUFFIX = '.meta.json'
KEPT_LIBRARY_FIELDS = ('title', 'actors', 'series', 'source')   # restored when a deleted file comes back


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _date_str(value) -> Optional[str]:
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _url_key(url: str) -> str:
    return str(url or '').split('?')[0]


def _is_url(value) -> bool:
    return str(value or '').lower().startswith(('http://', 'https://'))


def media_kind(name: str) -> str:
    """'video' / 'photo' (shown in the web library) or 'file'."""
    if media.is_video(name):
        return 'video'
    if media.is_image(name):
        return 'photo'
    return 'file'


class DownloadRecords:
    """Singleton; every public method works on the current DOWNLOADS_PATH (switches when it changes)."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._lock = threading.RLock()
            inst.root = None
            inst._live: Dict[str, str] = {}          # file_unique_id -> media path
            inst._recs: Dict[str, dict] = {}         # media path -> record
            inst._orphans: Dict[str, dict] = {}      # sidecar left behind without its file (moved / deleted outside the app)
            inst._deleted: Dict[str, dict] = {}      # deleted.json
            inst._cache: Dict[str, Tuple[float, Optional[dict]]] = {}   # sidecar path -> (mtime, record)
            inst._built = 0.0
            inst._refreshing = False
            cls._instance = inst
        return cls._instance

    # ─── locations ───────────────────────────────────────────────────────────

    def _deleted_path(self) -> str:
        from config.config import get_data_dir
        return os.path.join(get_data_dir(self.root), DELETED_FILE)

    def _rel(self, path: str) -> str:
        """Path relative to the downloads folder ('/' separated), or the absolute path if outside it."""
        try:
            rel = os.path.relpath(os.path.abspath(path), self.root)
        except ValueError:
            return path
        if rel == '..' or rel.startswith('..' + os.sep) or os.path.isabs(rel):
            return path
        return rel.replace(os.sep, '/')

    def _abs(self, stored: str) -> str:
        if not stored or os.path.isabs(stored):
            return stored
        return os.path.join(self.root, *stored.split('/'))

    # ─── index ───────────────────────────────────────────────────────────────

    def _ensure(self):
        from config.config import get_downloads_dir
        root = get_downloads_dir()
        with self._lock:
            if root != self.root:
                self.root = root
                self._cache = {}
                self._migrate_database()
                self._build()
                return
            stale = time.time() - self._built > REFRESH_SECONDS and not self._refreshing
            if stale:
                self._refreshing = True
        if stale:
            threading.Thread(target=self._background_refresh, daemon=True, name='records-refresh').start()

    def _background_refresh(self):
        try:
            with self._lock:
                root = self.root
            self._build(root)
        except Exception as e:
            logger.warning(f"下載紀錄索引更新失敗: {e}")
        finally:
            self._refreshing = False

    def refresh(self):
        """Re-read the folder now (e.g. after the web library rescanned)."""
        self._ensure()
        self._build()

    def _read_sidecar(self, sidecar: str, mtime: float) -> Optional[dict]:
        cached = self._cache.get(sidecar)
        if cached and cached[0] == mtime:
            return cached[1]
        try:
            with open(sidecar, encoding='utf-8') as f:
                data = json.load(f)
            record = data.get('download') if isinstance(data, dict) else None
            record = record if isinstance(record, dict) and record.get('file_unique_id') else None
        except Exception:
            record = None
        self._cache[sidecar] = (mtime, record)
        return record

    def _walk(self, root: str):
        """(folder, names, sidecar entries) for every non-hidden folder below root."""
        stack = [root]
        while stack:
            folder = stack.pop()
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue
            names = set()
            sidecars = []
            for e in entries:
                if e.name.startswith('.'):
                    if e.name.endswith(META_SUFFIX) and e.is_file():
                        sidecars.append(e)
                    continue
                if e.is_dir():
                    stack.append(e.path)
                else:
                    names.add(e.name)
            yield folder, names, sidecars

    def _build(self, root: str = None):
        root = root or self.root
        started = time.time()
        live, recs, orphans, seen = {}, {}, {}, set()
        for folder, names, sidecars in self._walk(root):
            for e in sidecars:
                try:
                    mtime = e.stat().st_mtime
                except OSError:
                    continue
                seen.add(e.path)
                record = self._read_sidecar(e.path, mtime)
                if not record:
                    continue
                name = e.name[1:-len(META_SUFFIX)]
                path = os.path.join(folder, name)
                uid = record['file_unique_id']
                if name in names:
                    if uid not in live:
                        live[uid] = path
                        recs[path] = record
                else:
                    orphans[uid] = dict(record, file_path=path, sidecar=e.path)
        deleted = self._load_deleted(root)
        with self._lock:
            if root != self.root:
                return                                   # DOWNLOADS_PATH changed meanwhile
            self._live, self._recs, self._orphans, self._deleted = live, recs, orphans, deleted
            self._cache = {k: v for k, v in self._cache.items() if k in seen}
            self._built = time.time()
        logger.info(f"下載紀錄索引：{len(live)} 個檔案，{len(deleted) + len(orphans)} 個已刪除"
                     f"（{time.time() - started:.1f} 秒）")

    # ─── deleted.json ────────────────────────────────────────────────────────

    def _load_deleted(self, root: str = None) -> Dict[str, dict]:
        from config.config import get_data_dir
        path = os.path.join(get_data_dir(root or self.root), DELETED_FILE)
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            records = data.get('records') if isinstance(data, dict) else None
            return {k: v for k, v in (records or {}).items() if isinstance(v, dict)}
        except FileNotFoundError:
            return {}
        except Exception as e:
            logger.warning(f"讀取 {DELETED_FILE} 失敗: {e}")
            return {}

    def _update_deleted(self, add: Dict[str, dict] = None, remove: Iterable[str] = ()):
        """Re-read (another PC may have changed it), apply, write atomically."""
        remove = [k for k in remove if k]
        if not add and not remove:
            return
        with self._lock:
            records = self._load_deleted()
            records.update(add or {})
            for key in remove:
                records.pop(key, None)
            path = self._deleted_path()
            tmp = f"{path}.{os.getpid()}.tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump({'version': 1, 'records': records}, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
            self._deleted = records

    # ─── migration from the SQLite database (v3.2.0 and earlier) ─────────────

    def _migrate_database(self):
        from config.config import get_database_path, get_legacy_database_path
        for db in (get_database_path(self.root), get_legacy_database_path()):
            if os.path.isfile(db):
                try:
                    self._import_database(db)
                    os.replace(db, db + '.migrated')
                except Exception as e:
                    logger.error(f"下載記錄搬移失敗（{db}），之後會再試一次: {e}")
                return

    def _import_database(self, db: str):
        connection = sqlite3.connect(db)
        connection.row_factory = sqlite3.Row
        try:
            rows = [dict(r) for r in connection.execute("SELECT * FROM downloads").fetchall()]
        finally:
            connection.close()
        attached, deleted = 0, {}
        for row in rows:
            stored = row.pop('file_path', '') or ''
            row.pop('id', None)
            path = self._abs(stored)
            record = self._make_record(**{k: row.get(k) for k in (
                'file_unique_id', 'file_id', 'message_id', 'chat_id', 'file_name', 'original_file_name',
                'file_size', 'file_type', 'mime_type', 'message_date')})
            record['download_date'] = self._local_time(row.get('download_date')) or record['download_date']
            inside = not os.path.isabs(self._rel(path))
            if inside and os.path.isfile(path):
                if not (media.read_sidecar(path).get('download')):
                    media.set_download(path, record)
                attached += 1
            else:
                deleted[record['file_unique_id']] = dict(record, file_path=self._rel(path), deleted_date=None)
        self._update_deleted(add=deleted)
        logger.info(f"已將資料庫 {db} 的 {len(rows)} 筆下載記錄搬到檔案旁的資訊檔："
                    f"{attached} 個檔案、{len(deleted)} 筆已刪除 / 不在下載資料夾")

    @staticmethod
    def _local_time(value) -> Optional[str]:
        """SQLite CURRENT_TIMESTAMP (UTC) -> local time."""
        if not value:
            return None
        try:
            utc = datetime.strptime(str(value)[:19], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            return utc.astimezone().strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            return str(value)

    @staticmethod
    def _make_record(file_unique_id, file_id, message_id, chat_id, file_name, original_file_name=None,
                     file_size=None, file_type=None, mime_type=None, message_date=None) -> dict:
        return {
            'file_unique_id': str(file_unique_id),
            'file_id': str(file_id or ''),
            'message_id': int(message_id or 0),
            'chat_id': int(chat_id or 0),
            'file_name': file_name,
            'original_file_name': original_file_name,
            'file_size': file_size,
            'file_type': file_type,
            'mime_type': mime_type,
            'download_date': _now(),
            'message_date': _date_str(message_date),
        }

    # ─── queries (same names as the old DatabaseManager) ─────────────────────

    def _out(self, record: dict, path: str, deleted: bool) -> dict:
        out = {k: v for k, v in record.items() if k != 'sidecar'}
        out['file_path'] = path
        out['deleted'] = deleted
        return out

    def is_file_downloaded(self, file_unique_id: str) -> bool:
        """Downloaded before (the file may have been deleted since: then it isn't offered again)."""
        self._ensure()
        uid = str(file_unique_id)
        with self._lock:
            return uid in self._live or uid in self._deleted or uid in self._orphans

    def get_downloaded_file_info(self, file_unique_id: str) -> Optional[dict]:
        """The record; `file_path` is where the file is (or was, when `deleted`)."""
        self._ensure()
        uid = str(file_unique_id)
        with self._lock:
            path = self._live.get(uid)
            if path and path in self._recs:
                return self._out(self._recs[path], path, False)
            if uid in self._orphans:
                return self._out(self._orphans[uid], self._orphans[uid]['file_path'], True)
            if uid in self._deleted:
                record = self._deleted[uid]
                return self._out(record, self._abs(record.get('file_path') or ''), True)
        return None

    def is_url_downloaded(self, url: str) -> bool:
        """A YouTube / X / ... link downloaded before (query parameters ignored)."""
        self._ensure()
        key = _url_key(url)
        with self._lock:
            records = list(self._recs.values()) + list(self._orphans.values()) + list(self._deleted.values())
        return any(_url_key(r.get('file_id')) == key for r in records if _is_url(r.get('file_id')))

    def find_download(self, file_path: str) -> Optional[dict]:
        """The record of a file on disk: its own sidecar, else a left-behind sidecar with the same
        name and size (the file was moved without its hidden files)."""
        record = media.read_sidecar(file_path).get('download')
        if isinstance(record, dict) and record.get('file_unique_id'):
            return self._out(record, file_path, False)
        self._ensure()
        name = os.path.basename(file_path)
        try:
            size = os.path.getsize(file_path)
        except OSError:
            return None
        with self._lock:
            for record in self._orphans.values():
                if record.get('file_name') == name and record.get('file_size') == size:
                    return self._out(record, file_path, False)
        return None

    def get(self, key: str) -> Optional[dict]:
        return self.get_downloaded_file_info(key)

    def plan_redownload(self, path: str) -> Tuple[Optional[dict], str]:
        """How to download an existing (e.g. broken) file again: (record, note) or (None, reason).

        1. the file's own record (sidecar)
        2. a deleted / left-behind record with the same file name (e.g. moved before v3.2.0, when the
           database kept the old path): same size first, then same folder
        3. no record at all (an interrupted download was never recorded): the Telegram message id in the
           file name (<id>_<name>, photo_<id>_<date>, document_<id>_<date>) and the channels files were
           downloaded from, nearest folder first; the bot checks which one has a message that would be
           saved under exactly this name
        The returned record's file_path is the current path (download into the file's folder).
        """
        path = os.path.abspath(path)
        record = media.read_sidecar(path).get('download')
        if isinstance(record, dict) and record.get('file_unique_id'):
            return self._out(record, path, False), '會從原本的來源重新下載'
        self._ensure()
        name = os.path.basename(path)
        try:
            size = os.path.getsize(path)
        except OSError:
            size = None
        with self._lock:
            same_name = [r for r in list(self._orphans.values()) + list(self._deleted.values())
                         if r.get('file_name') == name]
        if same_name:
            folder = os.path.dirname(self._rel(path))
            same_name.sort(key=lambda r: (r.get('file_size') != size,
                                          os.path.dirname(str(r.get('file_path') or '')) != folder))
            return self._out(same_name[0], path, True), '找到同檔名的下載紀錄，會從那個來源重新下載'

        m = re.match(r'^(?:photo_|document_)?(\d{1,11})_', name)
        if not m:
            return None, '找不到下載紀錄，檔名也看不出來源：請把原訊息重新轉傳給 Bot'
        chats = self._candidate_chats(path)
        if not chats:
            return None, '找不到下載紀錄，也沒有曾下載過的頻道可以比對：請把原訊息重新轉傳給 Bot'
        guess = {'file_unique_id': '', 'file_id': '', 'message_id': int(m.group(1)), 'chat_id': 0,
                 'file_name': name, 'file_path': path, 'candidate_chats': chats, 'deleted': False}
        return guess, (f'找不到下載紀錄：會依檔名中的訊息編號 {m.group(1)}，在 {len(chats)} 個曾下載過的頻道中'
                       f'尋找檔名相同的原訊息')

    def _candidate_chats(self, path: str, limit: int = 20) -> List[int]:
        """Channels files were downloaded from, those of files nearest to `path` first (same folder,
        then parent folders), then the rest by how often they were used."""
        target = os.path.normcase(os.path.dirname(os.path.abspath(path)))
        score: Dict[int, Tuple[int, int]] = {}
        with self._lock:
            records = [(p, r) for p, r in self._recs.items()]
            records += [(self._abs(r.get('file_path') or ''), r) for r in self._deleted.values()]
        for p, r in records:
            chat = r.get('chat_id')
            if not chat or str(r.get('file_unique_id', '')).startswith('xprofile_'):
                continue
            folder = os.path.normcase(os.path.dirname(p))
            depth = 0 if folder == target else 1 if target.startswith(folder + os.sep) or folder.startswith(target + os.sep) else 2
            best, count = score.get(chat, (2, 0))
            score[chat] = (min(best, depth), count + 1)
        ordered = sorted(score, key=lambda c: (score[c][0], -score[c][1]))
        return [int(c) for c in ordered[:limit]]

    # ─── changes ─────────────────────────────────────────────────────────────

    def record_download(self, file_unique_id: str, file_id: str, message_id: int, chat_id: int,
                        file_name: str, file_path: str, original_file_name: str = None, file_size: int = None,
                        file_type: str = None, mime_type: str = None, message_date=None) -> bool:
        self._ensure()
        try:
            record = self._make_record(file_unique_id, file_id, message_id, chat_id, file_name,
                                       original_file_name, file_size, file_type, mime_type, message_date)
            uid = record['file_unique_id']
            path = os.path.abspath(file_path)
            with self._lock:
                previous = self._deleted.get(uid) or self._orphans.get(uid)
                # the same link downloaded again (its fingerprint may differ): drop the old deleted entry
                same_url = [k for k, r in self._deleted.items()
                            if _is_url(file_id) and _url_key(r.get('file_id')) == _url_key(file_id)]
            restore = {k: previous['library'][k] for k in KEPT_LIBRARY_FIELDS
                       if previous and k in (previous.get('library') or {})}
            media.set_download(path, record, restore)
            with self._lock:
                self._live[uid] = path
                self._recs[path] = record
                orphan = self._orphans.pop(uid, None)
            if orphan and orphan.get('sidecar'):
                try:
                    os.remove(orphan['sidecar'])
                except OSError:
                    pass
            self._update_deleted(remove=[uid] + same_url)
            logger.debug(f"記錄文件下載: {file_name}")
            return True
        except Exception as e:
            logger.error(f"記錄下載信息時出錯: {e}")
            return False

    def forget_file(self, path: str):
        """A downloaded file was deleted: keep its record in deleted.json, remove its hidden sidecars."""
        self._ensure()
        path = os.path.abspath(path)
        sidecar = media.read_sidecar(path)
        record = sidecar.get('download')
        if isinstance(record, dict) and record.get('file_unique_id'):
            uid = record['file_unique_id']
            kept = {k: sidecar[k] for k in KEPT_LIBRARY_FIELDS if sidecar.get(k)}
            entry = dict(record, file_path=self._rel(path), deleted_date=_now())
            if kept:
                entry['library'] = kept
            with self._lock:
                self._live.pop(uid, None)
                self._recs.pop(path, None)
            self._update_deleted(add={uid: entry})
        media.remove_sidecars(path)
        try:                                             # the bot's 「載入影片」 compressed copy
            from src.video_loader import compressed_path
            os.remove(compressed_path(path))
        except (ImportError, OSError):
            pass

    def empty_unsourced_files(self, min_age: float = 600) -> List[str]:
        """0-byte files in the downloads folder without a source link: no download record that gives
        one and no 來源 typed in the web library. Files changed in the last `min_age` seconds are
        skipped (a download that just started can still be 0 bytes)."""
        self._ensure()
        from src.file_viewer import source_link
        now, found = time.time(), []
        for folder, names, _ in self._walk(self.root):
            for name in names:
                path = os.path.join(folder, name)
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                if stat.st_size != 0 or now - stat.st_mtime < min_age:
                    continue
                sidecar = media.read_sidecar(path)
                if str(sidecar.get('source') or '').strip() or source_link(self.find_download(path)):
                    continue
                found.append(path)
        return sorted(found, key=str.lower)

    def delete_files(self, paths: Iterable[str]) -> Tuple[int, List[str]]:
        """Delete files with their hidden sidecars; returns (deleted count, error texts)."""
        deleted, errors = 0, []
        for path in paths:
            try:
                os.remove(path)
                self.forget_file(path)
                deleted += 1
            except OSError as e:
                errors.append(f"{self._rel(path)}: {e.strerror or e}")
        logger.info(f"清除 0 位元組且沒有來源的檔案：刪除 {deleted} 個，失敗 {len(errors)} 個")
        return deleted, errors

    def file_moved(self, src: str, dst: str):
        """A file was moved / renamed together with its sidecars."""
        src, dst = os.path.abspath(src), os.path.abspath(dst)
        with self._lock:
            record = self._recs.pop(src, None)
            if record:
                self._recs[dst] = record
                self._live[record['file_unique_id']] = dst

    def folder_moved(self, src: str, dst: str):
        prefix = os.path.normcase(os.path.abspath(src)) + os.sep
        dst = os.path.abspath(dst)
        with self._lock:
            for path in [p for p in self._recs if os.path.normcase(p).startswith(prefix)]:
                self.file_moved(path, dst + path[len(prefix) - 1:])

    # ─── views ───────────────────────────────────────────────────────────────

    def all_records(self) -> List[dict]:
        """Every record (existing first by date), for the history page and the GUI."""
        self._ensure()
        with self._lock:
            out = [self._out(r, p, False) for p, r in self._recs.items()]
            out += [self._out(r, r['file_path'], True) for r in self._orphans.values()]
            out += [self._out(r, self._abs(r.get('file_path') or ''), True)
                    for uid, r in self._deleted.items() if uid not in self._live and uid not in self._orphans]
        out.sort(key=lambda r: str(r.get('download_date') or ''), reverse=True)
        return out

    def get_recent_downloads(self, limit: int = 10) -> List[dict]:
        return [r for r in self.all_records() if not r['deleted']][:limit]

    def get_download_statistics(self) -> dict:
        records = [r for r in self.all_records() if not r['deleted']]
        by_type: Dict[str, int] = {}
        for r in records:
            by_type[r.get('file_type') or 'unknown'] = by_type.get(r.get('file_type') or 'unknown', 0) + 1
        total = sum(r.get('file_size') or 0 for r in records)
        return {
            'total_files': len(records),
            'total_size_bytes': total,
            'total_size_mb': round(total / (1024 * 1024), 2),
            'unique_chats': len({r.get('chat_id') for r in records if r.get('chat_id')}),
            'files_by_type': by_type,
        }

    def cleanup_missing_files(self) -> Tuple[int, int]:
        """Move left-behind sidecars (file gone) into deleted.json."""
        self._ensure()
        with self._lock:
            orphans = list(self._orphans.values())
        for record in orphans:
            self.forget_file(record['file_path'])
        self._build()
        with self._lock:
            return len(orphans), len(self._recs) + len(orphans)

    def history(self, q: str = '', status: str = '', kind: str = '', offset: int = 0, limit: int = 100) -> dict:
        """Filtered page of all records for the 下載紀錄 page."""
        records = self.all_records()
        counts = {'all': len(records), 'exists': sum(not r['deleted'] for r in records)}
        counts['deleted'] = counts['all'] - counts['exists']
        needle = (q or '').strip().lower()
        items = []
        for r in records:
            if status == 'exists' and r['deleted'] or status == 'deleted' and not r['deleted']:
                continue
            rel = self._rel(r['file_path'] or '')
            name = os.path.basename(r['file_path'] or '') or r.get('file_name') or ''
            k = media_kind(name)
            if kind and k != kind:
                continue
            if needle and not any(needle in str(s or '').lower() for s in (name, rel, r.get('original_file_name'), r.get('file_id'))):
                continue
            items.append((r, rel, name, k))
        page = items[max(0, offset):max(0, offset) + max(1, min(limit, 500))]
        from src.file_viewer import source_link
        return {
            'total': len(items),
            'counts': counts,
            'items': [{
                'key': r['file_unique_id'],
                'file': name,
                'rel': rel,
                'folder': os.path.dirname(rel),
                'kind': k,
                'size': r.get('file_size'),
                'date': r.get('download_date'),
                'deleted_date': r.get('deleted_date'),
                'deleted': r['deleted'],
                'source': source_link(r),
                'inside': not os.path.isabs(rel),
            } for r, rel, name, k in page],
        }

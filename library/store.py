"""
library/store.py — The video index behind the web library.

Scans the downloads folder for videos, loads each one's sidecar metadata, and fills in missing
video info / screenshots in background threads. A video's id is its path relative to the downloads
folder, base64url-encoded, so links survive restarts; every id is checked to stay inside the folder.
"""

import base64
import logging
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional

from . import media

logger = logging.getLogger(__name__)

BACKGROUND_WORKERS = 2
_BAD_NAME_CHARS = set('<>:"/\\|?*')


class LibraryError(Exception):
    """A request the library refuses; `status` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def check_name(name: str) -> str:
    """A safe single file / folder name (no paths, no hidden names, valid on Windows)."""
    name = str(name or '').strip()
    if (not name or name in ('.', '..') or name.startswith('.') or name.endswith(('.', ' ')) or len(name) > 200
            or any(c in _BAD_NAME_CHARS or ord(c) < 32 for c in name)):
        raise LibraryError('名稱不合法（不可空白、不可以 . 開頭，也不能包含 \\ / : * ? " < > |）')
    return name


def _sidecars(video: str) -> list:
    """Hidden files that belong to a video and move / rename with it."""
    paths = [media.meta_path(video), media.shots_dir(video)]
    try:
        from src.video_loader import compressed_path    # the bot's 「載入影片」 compressed copy
        paths.append(compressed_path(video))
    except ImportError:
        pass
    return paths


def encode_id(rel: str) -> str:
    return base64.urlsafe_b64encode(rel.replace(os.sep, '/').encode('utf-8')).decode('ascii').rstrip('=')


def decode_id(vid: str) -> Optional[str]:
    try:
        return base64.urlsafe_b64decode(vid + '=' * (-len(vid) % 4)).decode('utf-8')
    except Exception:
        return None


class Library:
    def __init__(self, base_path: Callable[[], str]):
        self._base_path = base_path
        self.entries: Dict[str, dict] = {}      # id -> {'path', 'rel', 'meta', 'error'}
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=BACKGROUND_WORKERS, thread_name_prefix='library')
        self._pending = set()                    # ids with a background job queued / running
        self.last_scan = 0.0

    # ── paths ──

    def base(self) -> str:
        return os.path.realpath(self._base_path())

    def resolve(self, vid: str) -> Optional[str]:
        """Absolute path of a video id, or None if it isn't a video inside the downloads folder."""
        rel = decode_id(vid)
        if not rel or os.path.isabs(rel) or '\0' in rel:
            return None
        base = self.base()
        target = os.path.realpath(os.path.join(base, rel))
        try:
            inside = os.path.normcase(os.path.commonpath([base, target])) == os.path.normcase(base)
        except ValueError:
            return None
        if not inside or not os.path.isfile(target) or not media.is_video(os.path.basename(target)):
            return None
        return target

    # ── scanning ──

    def scan(self) -> int:
        """Rebuild the index from disk; queue info / screenshot jobs for videos that need them."""
        base = self.base()
        found = {}
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for name in files:
                if media.is_video(name):
                    path = os.path.join(root, name)
                    rel = os.path.relpath(path, base).replace(os.sep, '/')
                    found[encode_id(rel)] = (path, rel)

        with self._lock:
            for vid in list(self.entries):
                if vid not in found:
                    del self.entries[vid]
            for vid, (path, rel) in found.items():
                if vid not in self.entries:
                    self.entries[vid] = {'path': path, 'rel': rel, 'meta': media.load_meta(path), 'error': None}
            self.last_scan = time.time()
            todo = [vid for vid, e in self.entries.items() if self._needs_refresh(e)]
        for vid in todo:
            self.queue_refresh(vid)
        logger.info(f"影片庫掃描完成：{len(found)} 部影片，{len(todo)} 部需要產生資訊/截圖")
        return len(found)

    @staticmethod
    def _needs_refresh(entry: dict) -> bool:
        meta = entry['meta']
        try:
            mtime = os.path.getmtime(entry['path'])
        except OSError:
            return False
        if entry.get('error') and entry.get('error_mtime') == mtime:
            return False            # failed before for this exact file: don't retry every scan
        return (not meta.get('info') or meta.get('info_mtime') != mtime or not meta.get('shots')
                or meta.get('shots_mtime') != mtime or not meta.get('source_checked'))

    def queue_refresh(self, vid: str, force_shots: bool = False):
        with self._lock:
            if vid in self._pending or vid not in self.entries:
                return
            self._pending.add(vid)
        self._pool.submit(self._refresh, vid, force_shots)

    def _refresh(self, vid: str, force_shots: bool):
        try:
            with self._lock:
                entry = self.entries.get(vid)
                if not entry:
                    return
                path, meta = entry['path'], dict(entry['meta'])
            mtime = os.path.getmtime(path)
            info, shots = meta.get('info'), meta.get('shots')
            if not info or meta.get('info_mtime') != mtime:
                info = media.probe_info(path)
            shots_ok = shots and meta.get('shots_mtime') == mtime and all(
                os.path.exists(os.path.join(media.shots_dir(path), s)) for s in shots)
            if force_shots or not shots_ok:
                shots = media.make_screenshots(path, info.get('duration') or 0)
            source = None if meta.get('source_checked') else self._lookup_source(path)

            with self._lock:                     # merge: the user may have edited tags meanwhile
                entry = self.entries.get(vid)
                if not entry:
                    return
                current = entry['meta']
                current.update({'info': info, 'info_mtime': mtime, 'shots': shots, 'shots_mtime': mtime,
                                'source_checked': True})
                if source and not current.get('source'):
                    current['source'] = source
                media.save_meta(path, current)
                entry['error'] = None
        except Exception as e:
            logger.warning(f"影片資訊/截圖產生失敗 {vid}: {e}")
            with self._lock:
                if vid in self.entries:
                    self.entries[vid]['error'] = str(e)
                    try:
                        self.entries[vid]['error_mtime'] = os.path.getmtime(self.entries[vid]['path'])
                    except OSError:
                        pass
        finally:
            with self._lock:
                self._pending.discard(vid)

    @staticmethod
    def _lookup_source(path: str) -> Optional[str]:
        """Where the file came from, from the bot's download database (same as the chat file viewer)."""
        try:
            from src.database import DatabaseManager
            from src.file_viewer import source_link
            return source_link(DatabaseManager().find_download(path))
        except Exception as e:
            logger.debug(f"查詢來源失敗 {path}: {e}")
            return None

    @property
    def processing(self) -> int:
        with self._lock:
            return len(self._pending)

    # ── views ──

    def summary(self, vid: str, entry: dict) -> dict:
        meta, info = entry['meta'], entry['meta'].get('info') or {}
        folder = os.path.dirname(entry['rel'])
        return {
            'id': vid,
            'title': meta.get('title') or os.path.basename(entry['rel']),
            'file': os.path.basename(entry['rel']),
            'folder': folder,
            'actors': meta.get('actors') or [],
            'series': meta.get('series') or '',
            'duration': info.get('duration'),
            'width': info.get('width'),
            'height': info.get('height'),
            'size': info.get('size') or self._size(entry['path']),
            'added': meta.get('added'),
            'cover': f"/media/{vid}/shots/{meta['shots'][0]}" if meta.get('shots') else None,
            'ready': bool(meta.get('info') and meta.get('shots')),
        }

    def detail(self, vid: str) -> Optional[dict]:
        with self._lock:
            entry = self.entries.get(vid)
            if not entry:
                return None
            data = self.summary(vid, entry)
            meta = entry['meta']
            info = meta.get('info')
            data.update({
                'source': meta.get('source') or '',
                'info': info,
                'shots': [f"/media/{vid}/shots/{s}" for s in meta.get('shots') or []],
                'direct': media.direct_playable(entry['path'], info),
                'mime': media.mime_codecs(entry['path'], info),
                'processing': vid in self._pending,
                'error': entry.get('error'),
            })
            return data

    @staticmethod
    def _size(path: str) -> int:
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    def list(self) -> List[dict]:
        with self._lock:
            return [self.summary(vid, e) for vid, e in self.entries.items()]

    def tags(self) -> dict:
        actors, series = {}, {}
        with self._lock:
            for e in self.entries.values():
                for a in e['meta'].get('actors') or []:
                    actors[a] = actors.get(a, 0) + 1
                s = e['meta'].get('series')
                if s:
                    series[s] = series.get(s, 0) + 1
        as_list = lambda d: sorted(({'name': k, 'count': v} for k, v in d.items()), key=lambda x: x['name'].lower())
        return {'actors': as_list(actors), 'series': as_list(series)}

    # ── changes ──

    def update(self, vid: str, fields: dict) -> Optional[dict]:
        with self._lock:
            entry = self.entries.get(vid)
            if not entry:
                return None
            meta = entry['meta']
            if 'title' in fields:
                meta['title'] = str(fields['title'] or '').strip()[:300] or os.path.splitext(os.path.basename(entry['path']))[0]
            if 'actors' in fields:
                meta['actors'] = media.clean_tags(fields['actors'])
            if 'series' in fields:
                meta['series'] = str(fields['series'] or '').strip()[:200]
            if 'source' in fields:
                meta['source'] = str(fields['source'] or '').strip()[:2000]
            media.save_meta(entry['path'], meta)
        return self.detail(vid)

    def delete(self, vid: str) -> bool:
        with self._lock:
            entry = self.entries.get(vid)
            if not entry:
                return False
            os.remove(entry['path'])
            media.remove_sidecars(entry['path'])
            try:                                 # hidden compressed copy made by the bot's 「載入影片」
                from src.video_loader import compressed_path
                os.remove(compressed_path(entry['path']))
            except (ImportError, OSError):
                pass
            del self.entries[vid]
        logger.info(f"影片庫：已刪除 {entry['path']}")
        return True

    # ── folders & file management ──

    def _folder(self, rel: str) -> str:
        """Absolute path of a folder given relative to the downloads folder ('' = the root)."""
        rel = str(rel or '').strip().strip('/\\')
        base = self.base()
        target = os.path.realpath(os.path.join(base, rel))
        try:
            inside = os.path.normcase(os.path.commonpath([base, target])) == os.path.normcase(base)
        except ValueError:
            inside = False
        if not inside or any(part.startswith('.') for part in rel.replace('\\', '/').split('/') if part):
            raise LibraryError('資料夾不在下載資料夾內', 403)
        if not os.path.isdir(target):
            raise LibraryError('找不到資料夾', 404)
        return target

    def _rel(self, path: str) -> str:
        rel = os.path.relpath(path, self.base()).replace(os.sep, '/')
        return '' if rel == '.' else rel

    def _is_base(self, path: str) -> bool:
        return os.path.normcase(path) == os.path.normcase(self.base())

    def _check_not_busy(self, path: str):
        """Refuse to move a video (or a folder holding one) while its info / screenshots are being made."""
        prefix = os.path.normcase(path.rstrip(os.sep) + os.sep)
        with self._lock:
            for vid in self._pending:
                entry = self.entries.get(vid)
                if entry and (os.path.normcase(entry['path']) == os.path.normcase(path)
                              or os.path.normcase(entry['path']).startswith(prefix)):
                    raise LibraryError('影片正在產生資訊/截圖，請稍後再試', 409)

    def folders(self) -> List[dict]:
        """Every (non-hidden) folder with the number of videos directly inside it."""
        base = self.base()
        direct = {}
        with self._lock:
            for e in self.entries.values():
                folder = os.path.dirname(e['rel'])
                direct[folder] = direct.get(folder, 0) + 1
        out = [{'path': '', 'videos': direct.get('', 0)}]
        for root, dirs, _ in os.walk(base):
            dirs[:] = sorted((d for d in dirs if not d.startswith('.')), key=str.lower)
            for d in dirs:
                rel = self._rel(os.path.join(root, d))
                out.append({'path': rel, 'videos': direct.get(rel, 0)})
        return out

    def create_folder(self, parent: str, name: str) -> str:
        target = os.path.join(self._folder(parent), check_name(name))
        if os.path.exists(target):
            raise LibraryError('已經有同名的資料夾或檔案', 409)
        os.makedirs(target)
        logger.info(f"影片庫：建立資料夾 {target}")
        return self._rel(target)

    def rename_folder(self, rel: str, name: str) -> str:
        src = self._folder(rel)
        if self._is_base(src):
            raise LibraryError('不能重新命名根目錄')
        dst = os.path.join(os.path.dirname(src), check_name(name))
        self._move_path(src, dst)
        self.scan()
        return self._rel(dst)

    def delete_folder(self, rel: str):
        src = self._folder(rel)
        if self._is_base(src):
            raise LibraryError('不能刪除根目錄')
        if os.listdir(src):
            raise LibraryError('只能刪除空的資料夾', 409)
        os.rmdir(src)
        logger.info(f"影片庫：刪除資料夾 {src}")

    def rename_video(self, vid: str, name: str) -> str:
        """Rename the file (the extension is kept when left out); returns the new id."""
        src = self.resolve(vid)
        if not src:
            raise LibraryError('找不到影片', 404)
        name = check_name(name)
        ext = os.path.splitext(src)[1]
        if os.path.splitext(name)[1].lower() != ext.lower():
            name += ext
        dst = os.path.join(os.path.dirname(src), name)
        self._move_video(src, dst)
        self.scan()
        return encode_id(self._rel(dst))

    def move(self, video_ids: List[str], folders: List[str], dest: str) -> dict:
        """Move videos (with their hidden sidecars) and folders into `dest`; returns moved / failed."""
        target = self._folder(dest)
        moved, failed = [], []
        for vid in video_ids or []:
            src = self.resolve(str(vid))
            try:
                if not src:
                    raise LibraryError('找不到影片', 404)
                self._move_video(src, os.path.join(target, os.path.basename(src)))
                moved.append(os.path.basename(src))
            except (LibraryError, OSError) as e:
                failed.append({'name': os.path.basename(src or str(vid)), 'error': str(e)})
        for rel in folders or []:
            try:
                src = self._folder(rel)
                if self._is_base(src):
                    raise LibraryError('不能移動根目錄')
                if os.path.normcase(target + os.sep).startswith(os.path.normcase(src + os.sep)):
                    raise LibraryError('不能把資料夾移到它自己裡面')
                self._move_path(src, os.path.join(target, os.path.basename(src)))
                moved.append(os.path.basename(src))
            except (LibraryError, OSError) as e:
                failed.append({'name': str(rel), 'error': str(e)})
        self.scan()
        return {'moved': moved, 'failed': failed}

    def _move_path(self, src: str, dst: str):
        if os.path.normcase(src) == os.path.normcase(dst):
            return
        if os.path.exists(dst):
            raise LibraryError(f'「{os.path.basename(dst)}」已經存在', 409)
        self._check_not_busy(src)
        shutil.move(src, dst)
        logger.info(f"影片庫：{src} -> {dst}")

    def _move_video(self, src: str, dst: str):
        if os.path.normcase(src) == os.path.normcase(dst):
            return
        if os.path.exists(dst):
            raise LibraryError(f'「{os.path.basename(dst)}」已經存在', 409)
        self._check_not_busy(src)
        with self._lock:
            entry = self.entries.get(encode_id(self._rel(src)))
            shutil.move(src, dst)
            for old, new in zip(_sidecars(src), _sidecars(dst)):
                if os.path.exists(old):
                    try:
                        shutil.move(old, new)
                    except OSError as e:
                        logger.warning(f"移動附屬檔失敗 {old}: {e}")
            if entry:                            # a default title follows the file name
                meta = entry['meta']
                if meta.get('title') == os.path.splitext(os.path.basename(src))[0]:
                    meta['title'] = os.path.splitext(os.path.basename(dst))[0]
                    media.save_meta(dst, meta)
        logger.info(f"影片庫：{src} -> {dst}")

    def shutdown(self):
        self._pool.shutdown(wait=False, cancel_futures=True)

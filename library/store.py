"""
library/store.py — The media index behind the web library.

Scans the downloads folder for videos and photos (v3.3.0), loads each one's sidecar metadata, and fills
in missing info / screenshots (photos: one thumbnail) in background threads. An item's id is its path
relative to the downloads folder, base64url-encoded, so links survive restarts; every id is checked to
stay inside the folder. Deleting / moving a file keeps the bot's download records (src/records.py) current.
"""

import base64
import logging
import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional

from . import media, similarity

logger = logging.getLogger(__name__)

BACKGROUND_WORKERS = 2
MEDIA_URL = '/library/media'   # matches server.PREFIX
SETTLE_SECONDS = 90          # a file changed more recently may still be downloading / copying: wait
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


def _records():
    from src.records import DownloadRecords
    return DownloadRecords()


def _mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


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
        self.entries: Dict[str, dict] = {}      # id -> {'path', 'rel', 'kind', 'meta', 'meta_mtime', 'error'}
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=BACKGROUND_WORKERS, thread_name_prefix='library')
        self._pending = set()                    # ids with a background job queued / running
        self.last_scan = 0.0
        self.deferred = 0                        # videos skipped by the last scan because they're still changing
        # versions (same video in another quality / with a watermark), see library/similarity.py
        self.threshold = similarity.DEFAULT_THRESHOLD   # percent
        self.on_grouped: Optional[Callable[[str], None]] = None   # e.g. a Telegram notice
        self.matching_ready = False              # set after the full check at startup
        self._sigs: Dict[str, tuple] = {}        # path -> (shots_mtime, signature)

    # ── paths ──

    def base(self) -> str:
        return os.path.realpath(self._base_path())

    def resolve(self, vid: str) -> Optional[str]:
        """Absolute path of an item id, or None if it isn't a video / photo inside the downloads folder."""
        rel = decode_id(vid)
        if not rel or os.path.isabs(rel) or '\0' in rel:
            return None
        base = self.base()
        target = os.path.realpath(os.path.join(base, rel))
        try:
            inside = os.path.normcase(os.path.commonpath([base, target])) == os.path.normcase(base)
        except ValueError:
            return None
        if not inside or not os.path.isfile(target) or not media.is_media(os.path.basename(target)):
            return None
        return target

    # ── scanning ──

    def scan(self) -> int:
        """Rebuild the index from disk; queue info / screenshot jobs for items that need them."""
        base = self.base()
        found = {}
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for name in files:
                if media.is_media(name):
                    path = os.path.join(root, name)
                    rel = os.path.relpath(path, base).replace(os.sep, '/')
                    found[encode_id(rel)] = (path, rel)

        with self._lock:
            for vid in list(self.entries):
                if vid not in found:
                    del self.entries[vid]
            for vid, (path, rel) in found.items():
                if vid not in self.entries:
                    self.entries[vid] = {'path': path, 'rel': rel, 'kind': media.kind_of(path),
                                         'meta': media.load_meta(path), 'meta_mtime': _mtime(media.meta_path(path)),
                                         'error': None}
                elif vid not in self._pending:
                    self._sync_meta(self.entries[vid])
            self.last_scan = time.time()
            todo = [vid for vid, e in self.entries.items() if self._needs_refresh(e)]
            fresh = [vid for vid in todo if self._still_changing(self.entries[vid]['path'])]
            todo = [vid for vid in todo if vid not in fresh]
            self.deferred = len(fresh)
        for vid in todo:
            self.queue_refresh(vid)
        photos = sum(1 for e in self.entries.values() if e['kind'] == 'photo')
        logger.info(f"影片庫掃描完成：{len(found) - photos} 部影片、{photos} 張照片，{len(todo)} 個需要產生資訊/截圖"
                    + (f"，{self.deferred} 部仍在寫入中，稍後再處理" if self.deferred else ""))
        return len(found)

    @staticmethod
    def _sync_meta(entry: dict):
        """Reload the sidecar if something else changed it (the bot's download record, another PC)."""
        mtime = _mtime(media.meta_path(entry['path']))
        if mtime != entry.get('meta_mtime'):
            entry['meta'] = media.load_meta(entry['path'])
            entry['meta_mtime'] = mtime

    @staticmethod
    def _save(entry: dict):
        media.save_meta(entry['path'], entry['meta'])
        entry['meta_mtime'] = _mtime(media.meta_path(entry['path']))

    @staticmethod
    def _still_changing(path: str) -> bool:
        try:
            return time.time() - os.path.getmtime(path) < SETTLE_SECONDS
        except OSError:
            return True

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
                path, meta, kind = entry['path'], dict(entry['meta']), entry['kind']
            mtime = os.path.getmtime(path)
            info, shots = meta.get('info'), meta.get('shots')
            shots_ok = shots and meta.get('shots_mtime') == mtime and all(
                os.path.exists(os.path.join(media.shots_dir(path), s)) for s in shots)
            if kind == 'photo':
                if force_shots or not shots_ok or not info or meta.get('info_mtime') != mtime:
                    info, shots = media.process_image(path)
            else:
                if not info or meta.get('info_mtime') != mtime:
                    info = media.probe_info(path)
                if force_shots or not shots_ok:
                    shots = media.make_screenshots(path, info.get('duration') or 0)
            source = None if meta.get('source_checked') else self._lookup_source(path)

            with self._lock:                     # merge: the user may have edited tags meanwhile
                entry = self.entries.get(vid)
                if not entry:
                    return
                self._sync_meta(entry)
                current = entry['meta']
                current.update({'info': info, 'info_mtime': mtime, 'shots': shots, 'shots_mtime': mtime,
                                'source_checked': True})
                if source and not current.get('source'):
                    current['source'] = source
                self._save(entry)
                entry['error'] = None
            if self.matching_ready and kind == 'video':
                self._match_new(vid)
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
        """Where the file came from, from the bot's download record (same as the chat file viewer)."""
        try:
            from src.file_viewer import source_link
            return source_link(_records().find_download(path))
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
            'kind': entry['kind'],
            'title': meta.get('title') or os.path.basename(entry['rel']),
            'file': os.path.basename(entry['rel']),
            'folder': folder,
            'actors': meta.get('actors') or [],
            'series': meta.get('series') or '',
            'description': meta.get('description') or '',   # Telegram message text; matched by the search
            'duration': info.get('duration'),
            'width': info.get('width'),
            'height': info.get('height'),
            'bit_rate': info.get('bit_rate'),
            'size': info.get('size') or self._size(entry['path']),
            'added': meta.get('added'),
            'cover': f"{MEDIA_URL}/{vid}/shots/{meta['shots'][0]}" if meta.get('shots') else None,
            'ready': bool(meta.get('info') and meta.get('shots')),
            'error': entry.get('error'),
            'group': meta.get('group') or '',
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
                'shots': [f"{MEDIA_URL}/{vid}/shots/{s}" for s in meta.get('shots') or []],
                'direct': media.direct_playable(entry['path'], info),
                'mime': media.mime_codecs(entry['path'], info),
                'qualities': media.stream_qualities(info) if entry['kind'] == 'video' else [],
                'processing': vid in self._pending,
                'error': entry.get('error'),
                'versions': self._versions(vid, entry) if entry['kind'] == 'video' else [],
            })
            if entry['kind'] == 'photo':
                data['neighbors'] = self._neighbors(vid, entry)
            return data

    def _neighbors(self, vid: str, entry: dict) -> dict:
        """Previous / next photo in the same folder (by file name), for ← / → on the photo page."""
        folder = os.path.dirname(entry['rel'])
        photos = sorted(((os.path.basename(e['rel']).lower(), i) for i, e in self.entries.items()
                         if e['kind'] == 'photo' and os.path.dirname(e['rel']) == folder))
        ids = [i for _, i in photos]
        pos = ids.index(vid)
        around = [pos + 1, pos - 1, pos + 2, pos - 2]          # preloaded by the photo page, nearest first
        return {'prev': ids[pos - 1] if pos > 0 else None, 'next': ids[pos + 1] if pos + 1 < len(ids) else None,
                'preload': [ids[i] for i in around if 0 <= i < len(ids)],
                'index': pos + 1, 'total': len(ids)}

    def _versions(self, vid: str, entry: dict) -> List[dict]:
        """All files of this video's group (best quality first), for the line switcher."""
        gid = entry['meta'].get('group')
        members = self._group_members(gid) if gid else [(vid, entry)]
        out = []
        for mid, m in sorted(members, key=lambda x: self._quality(x[1]), reverse=True):
            info = m['meta'].get('info') or {}
            out.append({'id': mid, 'file': os.path.basename(m['rel']), 'folder': os.path.dirname(m['rel']),
                        'width': info.get('width'), 'height': info.get('height'), 'bit_rate': info.get('bit_rate'),
                        'size': info.get('size') or self._size(m['path']), 'duration': info.get('duration'),
                        'video_codec': info.get('video_codec')})
        return out

    @staticmethod
    def _size(path: str) -> int:
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    def list(self, kind: str = '') -> List[dict]:
        """All items, or only 'video' / 'photo'."""
        with self._lock:
            return [self.summary(vid, e) for vid, e in self.entries.items() if not kind or e['kind'] == kind]

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
            if not self._apply(vid, fields):
                return None
        return self.detail(vid)

    def update_many(self, vids: List[str], add_actors=(), remove_actors=(), series=None) -> dict:
        """Bulk edit of the selected items: add / remove 主演, set 系列 ('' clears it, None leaves it)."""
        add = media.clean_tags(add_actors)
        drop = {a.lower() for a in media.clean_tags(remove_actors)}
        updated, missing = 0, 0
        with self._lock:
            for vid in dict.fromkeys(str(v) for v in vids or []):
                entry = self.entries.get(vid)
                if not entry:
                    missing += 1
                    continue
                kept = [a for a in entry['meta'].get('actors') or [] if a.lower() not in drop]
                fields = {'actors': kept + add}
                if series is not None:
                    fields['series'] = series
                self._apply(vid, fields)
                updated += 1
        return {'updated': updated, 'missing': missing}

    def delete_many(self, vids: List[str]) -> dict:
        """Delete several items (same as delete() for each); returns deleted count / failed."""
        deleted, failed = 0, []
        for vid in dict.fromkeys(str(v) for v in vids or []):
            entry = self.entries.get(vid)
            name = os.path.basename(entry['rel']) if entry else vid
            try:
                if not self.delete(vid):
                    raise LibraryError('找不到檔案', 404)
                deleted += 1
            except (LibraryError, OSError) as e:
                failed.append({'name': name, 'error': getattr(e, 'strerror', None) or str(e)})
        return {'deleted': deleted, 'failed': failed}

    def _apply(self, vid: str, fields: dict) -> bool:
        """Write title / actors / series / source to the sidecar (and the other versions); caller holds the lock."""
        entry = self.entries.get(vid)
        if not entry:
            return False
        meta = entry['meta']
        if 'title' in fields:
            meta['title'] = str(fields['title'] or '').strip()[:300] or os.path.splitext(os.path.basename(entry['path']))[0]
        if 'actors' in fields:
            meta['actors'] = media.clean_tags(fields['actors'])
        if 'series' in fields:
            meta['series'] = str(fields['series'] or '').strip()[:200]
        if 'source' in fields:
            meta['source'] = str(fields['source'] or '').strip()[:2000]
        if 'description' in fields:              # per file (not shared by the versions)
            meta['description'] = str(fields['description'] or '').strip()[:5000]
        self._save(entry)
        if meta.get('group'):                # title / actors / series are shared by all versions
            for mid, m in self._group_members(meta['group']):
                if mid != vid:
                    m['meta'].update({k: meta[k] for k in ('title', 'actors', 'series') if k in meta})
                    self._save(m)
        return True

    def delete(self, vid: str) -> bool:
        with self._lock:
            entry = self.entries.get(vid)
            if not entry:
                return False
            os.remove(entry['path'])
            # keeps the download record in .tad/deleted.json (下載紀錄 / not offered again), removes
            # the sidecars and the bot's 「載入影片」 compressed copy
            _records().forget_file(entry['path'])
            del self.entries[vid]
            self._dissolve_if_single(entry['meta'].get('group'))
        logger.info(f"影片庫：已刪除 {entry['path']}")
        return True

    # ── versions: grouping the same video (other quality / watermark) ──

    @staticmethod
    def _quality(entry: dict) -> tuple:
        info = entry['meta'].get('info') or {}
        return (min(info.get('width') or 0, info.get('height') or 0), info.get('bit_rate') or 0)

    def _group_members(self, gid: str) -> List[tuple]:
        return [(vid, e) for vid, e in self.entries.items() if gid and e['meta'].get('group') == gid]

    def _dissolve_if_single(self, gid: str):
        """A group with one file left is no group any more."""
        members = self._group_members(gid) if gid else []
        if len(members) == 1:
            vid, e = members[0]
            e['meta']['group'] = ''
            self._save(e)

    def _signature(self, entry: dict):
        meta = entry['meta']
        if not meta.get('shots') or not meta.get('info'):
            return None
        cached = self._sigs.get(entry['path'])
        if cached and cached[0] == meta.get('shots_mtime'):
            return cached[1]
        try:
            sig = similarity.load_signature(entry['path'], meta['shots'])
        except Exception as e:
            logger.debug(f"相似度特徵讀取失敗 {entry['path']}: {e}")
            sig = None
        if sig is not None:
            self._sigs[entry['path']] = (meta.get('shots_mtime'), sig)
        return sig

    @staticmethod
    def _excluded(a: dict, b: dict) -> bool:
        return b['meta'].get('uid') in (a['meta'].get('not_same') or []) or \
            a['meta'].get('uid') in (b['meta'].get('not_same') or [])

    def _comparable(self, a: dict, b: dict) -> bool:
        da = (a['meta'].get('info') or {}).get('duration') or 0
        db = (b['meta'].get('info') or {}).get('duration') or 0
        same_group = a['meta'].get('group') and a['meta'].get('group') == b['meta'].get('group')
        return (da > 0 and db > 0 and abs(da - db) <= similarity.DURATION_TOLERANCE
                and not same_group and not self._excluded(a, b))

    def _score(self, a: dict, b: dict):
        sa, sb = self._signature(a), self._signature(b)
        if sa is None or sb is None:
            return None
        return similarity.similarity(sa, sb)

    def _join(self, vids: List[str]):
        """Put these videos (and their current groups) into one group with shared title / actors / series."""
        with self._lock:
            members = {}
            gids = [self.entries[v]['meta'].get('group') for v in vids if v in self.entries]
            for v in vids:
                if v in self.entries:
                    members[v] = self.entries[v]
            for gid in filter(None, gids):
                members.update(dict(self._group_members(gid)))
            if len(members) < 2:
                return
            gid = next(filter(None, gids), None) or 'g' + uuid.uuid4().hex[:12]
            ordered = sorted(members.values(), key=self._quality, reverse=True)
            # an edited title wins over a default one (= the file name)
            edited = [e for e in ordered
                      if e['meta'].get('title') and e['meta']['title'] != os.path.splitext(os.path.basename(e['path']))[0]]
            title = (edited or ordered)[0]['meta'].get('title')
            actors = media.clean_tags([a for e in ordered for a in e['meta'].get('actors') or []])
            series = next((e['meta']['series'] for e in ordered if e['meta'].get('series')), '')
            for e in members.values():
                e['meta'].update({'group': gid, 'title': title, 'actors': actors, 'series': series})
                self._save(e)

    def _match_new(self, vid: str):
        """A video just got its info / screenshots: group it with a matching version, if any."""
        with self._lock:
            entry = self.entries.get(vid)
            if not entry:
                return
            candidates = [(oid, o) for oid, o in self.entries.items() if oid != vid and self._comparable(entry, o)]
        best = None
        for oid, other in candidates:
            score = self._score(entry, other)
            if score is not None and score >= self.threshold and (best is None or score > best[1]):
                best = (oid, score)
        if not best:
            return
        self._join([vid, best[0]])
        with self._lock:
            title = entry['meta'].get('title')
            other = self.entries.get(best[0])
            count = len(self._group_members(entry['meta'].get('group')))
            other_file = os.path.basename(other['rel']) if other else ''
        logger.info(f"影片庫：{entry['rel']} 與 {other_file} 相似度 {best[1]:.0f}%，歸類為同一部片")
        if self.on_grouped:
            try:
                self.on_grouped(f"🔁 新影片「{os.path.basename(entry['rel'])}」與「{other_file}」相似度 {best[1]:.0f}%，"
                                f"已歸類為同一部片「{title}」（{count} 個版本，可在網頁影片庫切換）")
            except Exception as e:
                logger.warning(f"相似影片通知失敗: {e}")

    def check_all(self) -> int:
        """Full check (at startup): compare every pair of videos with lengths within ±3 s."""
        with self._lock:
            ready = [(vid, e) for vid, e in self.entries.items()
                     if (e['meta'].get('info') or {}).get('duration') and e['meta'].get('shots')]
        ready.sort(key=lambda x: x[1]['meta']['info']['duration'])
        pairs = 0
        for i, (vid, a) in enumerate(ready):
            da = a['meta']['info']['duration']
            for oid, b in ready[i + 1:]:
                if b['meta']['info']['duration'] - da > similarity.DURATION_TOLERANCE:
                    break
                if not self._comparable(a, b):
                    continue
                score = self._score(a, b)
                pairs += 1
                if score is not None and score >= self.threshold:
                    logger.info(f"影片庫：{a['rel']} 與 {b['rel']} 相似度 {score:.0f}%，歸類為同一部片")
                    self._join([vid, oid])
        self.matching_ready = True
        logger.info(f"影片庫：相似影片全面檢查完成（比對 {pairs} 組）")
        return pairs

    def merge_many(self, vids: List[str]) -> dict:
        """Multi-select 「嘗試合併」: compare the selected videos with the same check as the automatic
        grouping (lengths within ±3 s, screenshot similarity >= threshold) and group the ones that match
        (a match of a match joins too). Pairs split by hand before (not_same) are compared as well, since
        the user asked; files merged this way lose that mark for each other."""
        with self._lock:
            items, photos = [], 0
            for vid in dict.fromkeys(str(v) for v in vids or []):
                entry = self.entries.get(vid)
                if not entry:
                    continue
                if entry['kind'] == 'video':
                    items.append((vid, entry))
                else:
                    photos += 1
        ready = [(vid, e) for vid, e in items if self._signature(e) is not None]
        parent = {vid: vid for vid, _ in ready}

        def root(v):
            while parent[v] != v:
                parent[v] = parent[parent[v]]
                v = parent[v]
            return v

        best = {}                     # vid -> best score with any other selected video of similar length
        edges = []                    # (vid, vid, score) at or above the threshold
        for i, (va, a) in enumerate(ready):
            for vb, b in ready[i + 1:]:
                gid = a['meta'].get('group')
                if gid and gid == b['meta'].get('group'):      # already versions of each other
                    parent[root(va)] = root(vb)
                    continue
                da = (a['meta'].get('info') or {}).get('duration') or 0
                db = (b['meta'].get('info') or {}).get('duration') or 0
                if not (da > 0 and db > 0 and abs(da - db) <= similarity.DURATION_TOLERANCE):
                    continue
                score = self._score(a, b)
                if score is None:
                    continue
                for v in (va, vb):
                    best[v] = max(best.get(v, 0), score)
                if score >= self.threshold:
                    edges.append((va, vb, score))
                    parent[root(va)] = root(vb)

        components = {}
        for vid, _ in ready:
            components.setdefault(root(vid), []).append(vid)
        groups, already, unmatched = [], 0, []
        for members in components.values():
            scores = [s for a, b, s in edges if a in members and b in members]
            if len(members) > 1 and not scores:
                already += 1
                continue
            if len(members) == 1:
                vid = members[0]
                e = self.entries.get(vid)
                unmatched.append({'name': os.path.basename(e['rel']) if e else vid,
                                  'reason': 'low' if vid in best else 'length',
                                  'best': round(best[vid]) if vid in best else None})
                continue
            self._join(members)
            with self._lock:
                gid = next((self.entries[v]['meta'].get('group') for v in members if v in self.entries), '')
                group = self._group_members(gid)
                uids = {m['meta'].get('uid') for _, m in group}
                for _, m in group:
                    marks = m['meta'].get('not_same') or []
                    kept = [u for u in marks if u not in uids]
                    if len(kept) != len(marks):
                        m['meta']['not_same'] = kept
                        self._save(m)
                title = group[0][1]['meta'].get('title') if group else ''
                files = [os.path.basename(self.entries[v]['rel']) for v in members if v in self.entries]
            logger.info(f"影片庫：手動合併 {len(members)} 部（相似度 {min(scores):.0f}%–{max(scores):.0f}%）為「{title}」")
            groups.append({'title': title, 'files': files, 'versions': len(group),
                           'min': round(min(scores)), 'max': round(max(scores))})
        for vid, e in items:
            if vid not in parent:      # no signature: not processed yet, or its screenshots can't be read
                ready_meta = e['meta'].get('shots') and e['meta'].get('info')
                unmatched.append({'name': os.path.basename(e['rel']), 'reason': 'unreadable' if ready_meta else 'not_ready',
                                  'best': None})
        return {'groups': groups, 'already': already, 'unmatched': unmatched, 'photos': photos,
                'threshold': self.threshold}

    def ungroup(self, vid: str) -> Optional[dict]:
        """Split this file out of its group; it will never be grouped with those files again."""
        with self._lock:
            entry = self.entries.get(vid)
            if not entry:
                return None
            gid = entry['meta'].get('group')
            if not gid:
                return self.detail(vid)
            for oid, other in self._group_members(gid):
                if oid == vid:
                    continue
                entry['meta'].setdefault('not_same', []).append(other['meta']['uid'])
                other['meta'].setdefault('not_same', []).append(entry['meta']['uid'])
                self._save(other)
            entry['meta']['group'] = ''
            self._save(entry)
            self._dissolve_if_single(gid)
        logger.info(f"影片庫：{entry['rel']} 已從版本群組移出")
        return self.detail(vid)

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
                    raise LibraryError('檔案正在產生資訊/截圖，請稍後再試', 409)

    def folders(self) -> List[dict]:
        """Every (non-hidden) folder with the number of videos / photos directly inside it."""
        base = self.base()
        direct = {}
        with self._lock:
            for e in self.entries.values():
                counts = direct.setdefault(os.path.dirname(e['rel']), {'video': 0, 'photo': 0})
                counts[e['kind']] += 1
        node = lambda rel: {'path': rel, 'videos': direct.get(rel, {}).get('video', 0),
                            'photos': direct.get(rel, {}).get('photo', 0)}
        out = [node('')]
        for root, dirs, _ in os.walk(base):
            dirs[:] = sorted((d for d in dirs if not d.startswith('.')), key=str.lower)
            for d in dirs:
                out.append(node(self._rel(os.path.join(root, d))))
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
            raise LibraryError('找不到檔案', 404)
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
                    raise LibraryError('找不到檔案', 404)
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
        _records().folder_moved(src, dst)
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
            _records().file_moved(src, dst)
            if entry:                            # a default title follows the file name
                meta = entry['meta']
                if meta.get('title') == os.path.splitext(os.path.basename(src))[0]:
                    meta['title'] = os.path.splitext(os.path.basename(dst))[0]
                    media.save_meta(dst, meta)
        logger.info(f"影片庫：{src} -> {dst}")

    def shutdown(self):
        self._pool.shutdown(wait=False, cancel_futures=True)

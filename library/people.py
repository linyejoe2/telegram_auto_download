"""
library/people.py — 人物資料庫 (v3.6.0): the faces behind the 主演 tags, kept up to date by itself.

Every person has an id, a name ('' = 未命名人物 #num) and face references (128-number SFace vectors,
see library/recognize.py):
  - named people come from the 主演 tags: the face of a tagged item's matching person is a reference
    (re-derived whenever the item's tags or file change);
  - unnamed people are faces seen in new items that matched nobody; their references are kept here.
New items (seen by the library after the database was created) are recognised as soon as their
screenshots are ready: a face matching a named person (similarity >= recognize.FACE_MATCH) gets that
主演 tag automatically (marked in the sidecar's `auto_actors`), a face matching an unnamed person joins
it, any other face starts a new 未命名人物. Existing items are only recognised after 「掃描全部未掃描的
項目」 on the 人物 page (`scan_all`, survives restarts).

Tags stay the source of truth: renaming / merging / deleting a person renames / removes the 主演 tag on
the items, removing an item from a person removes the tag and remembers it in the item's `not_people`
(so it isn't added again); removing an auto-added tag by hand does the same.

Stored in <downloads>/.tad/people.json (people, references, state) and people.npy (the vectors,
one row per reference). Per item (sidecar): people_scan (file mtime recognised), auto_actors, not_people.
"""

import json
import logging
import os
import threading
import time
import uuid
from typing import Dict, List, Optional

import numpy as np

from . import media
from .recognize import FACE_MATCH, MEDIA_URL, FaceModel, analyze

logger = logging.getLogger(__name__)

POLL_SECONDS = 60
SAVE_SECONDS = 30
VERSION = 1


class People:
    def __init__(self, library):
        self.library = library
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stop = False
        self._thread: Optional[threading.Thread] = None
        self._face: Optional[FaceModel] = None
        self._base = None
        self._last_save = 0.0
        self._dirty = False
        self.status = {'phase': 'idle', 'done': 0, 'total': 0, 'error': None}
        self._reset()

    def _reset(self):
        self.people: Dict[str, dict] = {}       # pid -> {id, name, num, created}
        self.refs: List[dict] = []              # {pid, uid, pi, src: 'tag'|'face', feat}
        self.tagged: Dict[str, str] = {}        # item uid -> tags/file key the tag references were made for
        self.since = time.time()                # items the library saw after this are "new"
        self.scan_all = False
        self.next_num = 1
        self._matrix = None

    # ── storage ──

    def _dir(self) -> str:
        folder = os.path.join(self.library.base(), '.tad')
        if not os.path.isdir(folder):
            os.makedirs(folder, exist_ok=True)
            media._hide(folder)
        return folder

    def _load(self):
        base = self.library.base()
        if base == self._base:
            return
        self._reset()
        self._base = base
        folder = self._dir()
        try:
            with open(os.path.join(folder, 'people.json'), encoding='utf-8') as f:
                data = json.load(f)
            with open(os.path.join(folder, 'people.npy'), 'rb') as f:
                feats = np.load(f) if data.get('refs') else np.zeros((0, 128), np.float32)
        except FileNotFoundError:
            self._dirty = True                  # new database: `since` = now
            return
        except (OSError, ValueError) as e:
            logger.warning(f"人物資料庫讀取失敗，重新建立: {e}")
            self._dirty = True
            return
        if len(feats) != len(data.get('refs') or []):
            logger.warning("人物資料庫的臉部資料不完整，重新建立參考")
            data['refs'], data['tagged'], feats = [], {}, np.zeros((0, 128), np.float32)
        self.people = {p['id']: p for p in data.get('people') or []}
        self.refs = [{**r, 'feat': feats[i]} for i, r in enumerate(data.get('refs') or [])]
        self.tagged = data.get('tagged') or {}
        self.since = data.get('since') or time.time()
        self.scan_all = bool(data.get('scan_all'))
        self.next_num = data.get('next_num') or 1

    def _save(self, force: bool = False):
        if not self._dirty or (not force and time.time() - self._last_save < SAVE_SECONDS):
            return
        folder = self._dir()
        data = {'version': VERSION, 'since': self.since, 'scan_all': self.scan_all, 'next_num': self.next_num,
                'people': list(self.people.values()),
                'refs': [{k: v for k, v in r.items() if k != 'feat'} for r in self.refs],
                'tagged': self.tagged}
        feats = np.stack([r['feat'] for r in self.refs]).astype(np.float32) if self.refs else np.zeros((0, 128), np.float32)
        try:
            tmp = os.path.join(folder, 'people.npy.tmp')
            with open(tmp, 'wb') as f:
                np.save(f, feats)
            os.replace(tmp, os.path.join(folder, 'people.npy'))
            tmp = os.path.join(folder, 'people.json.tmp')
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, os.path.join(folder, 'people.json'))
            self._dirty = False
            self._last_save = time.time()
        except OSError as e:
            logger.warning(f"人物資料庫儲存失敗: {e}")

    def _changed(self):
        self._dirty = True
        self._matrix = None

    # ── worker ──

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True, name='people')
        self._thread.start()

    def shutdown(self):
        self._stop = True
        self._wake.set()

    def wake(self):
        self._wake.set()

    def _run(self):
        time.sleep(5)                           # let the library's first scan start
        while not self._stop:
            try:
                self._cycle()
                self.status['error'] = None
            except Exception as e:
                logger.warning(f"人物資料庫更新失敗: {e}", exc_info=not isinstance(e, RuntimeError))
                self.status['error'] = str(e)
            finally:
                self.status.update(phase='idle', done=0, total=0)
                with self._lock:
                    self._save(force=True)
            self._wake.wait(POLL_SECONDS)
            self._wake.clear()

    def _face_model(self) -> FaceModel:
        if self._face is None:
            self._face = FaceModel()
        return self._face

    def _snapshot(self) -> List[dict]:
        lib = self.library
        out = []
        with lib._lock:
            for vid, e in lib.entries.items():
                meta = e['meta']
                if not meta.get('uid'):
                    continue
                out.append({'vid': vid, 'uid': meta['uid'], 'path': e['path'], 'rel': e['rel'], 'kind': e['kind'],
                            'actors': list(meta.get('actors') or []), 'group': meta.get('group') or '',
                            'ready': bool(meta.get('info') and meta.get('shots')) and not e.get('error'),
                            'mtime': meta.get('info_mtime') or 0, 'added': meta.get('added') or 0,
                            'duration': (meta.get('info') or {}).get('duration') or 0,
                            'people_scan': meta.get('people_scan'), 'auto': list(meta.get('auto_actors') or []),
                            'not': list(meta.get('not_people') or []),
                            'cover': f"{MEDIA_URL}/{vid}/shots/{meta['shots'][0]}" if meta.get('shots') else None})
        return out

    def _cycle(self):
        with self._lock:
            self._load()
        snap = self._snapshot()
        if not snap:
            return
        self._sync(snap)
        while not self._stop:
            with self._lock:
                todo = [e for e in self._snapshot() if e['ready'] and e['people_scan'] != e['mtime']
                        and (e['added'] >= self.since or self.scan_all)]
            if not todo:
                break
            total = len(todo)
            for i, e in enumerate(todo):
                if self._stop or not (e['added'] >= self.since or self.scan_all):
                    break
                self.status.update(phase='scan', done=i, total=total)
                self._recognize(e)
                with self._lock:
                    self._save()
            else:
                continue
            break
        with self._lock:
            if self.scan_all and not any(e['ready'] and e['people_scan'] != e['mtime'] for e in self._snapshot()):
                self.scan_all = False
                self._dirty = True
                logger.info("人物資料庫：全部項目掃描完成")

    def _faces(self, e: dict) -> Optional[dict]:
        try:
            data = analyze(e['path'], e['kind'], e['duration'], self._face_model)
        except RuntimeError as err:
            if '模型' in str(err):
                raise
            return None
        except Exception as err:
            logger.debug(f"人物資料庫：無法分析 {e['rel']}: {err}")
            return None
        return data if data['persons'] else None

    # ── matching ──

    def _name_pid(self, name: str, create: bool = True) -> Optional[str]:
        low = name.strip().lower()
        for p in self.people.values():
            if p['name'] and p['name'].lower() == low:
                return p['id']
        if not create or not low:
            return None
        return self._new_person(name.strip())

    def _new_person(self, name: str = '') -> str:
        pid = 'p' + uuid.uuid4().hex[:10]
        self.people[pid] = {'id': pid, 'name': name, 'num': 0 if name else self.next_num, 'created': time.time()}
        if not name:
            self.next_num += 1
        self._changed()
        return pid

    def _index(self):
        if self._matrix is None:
            self._matrix = (np.stack([r['feat'] for r in self.refs]) if self.refs else np.zeros((0, 128), np.float32),
                            np.array([r['pid'] for r in self.refs]), np.array([r['uid'] for r in self.refs]))
        return self._matrix

    def _ranked(self, feat, uid: str, group_of: Dict[str, str], skip=(), only=None) -> List[tuple]:
        """[(score, pid)] best first: mean of the 3 closest references; the item's own faces and its
        other versions don't count."""
        matrix, pids, uids = self._index()
        if not len(matrix):
            return []
        group = group_of.get(uid)
        keep = uids != uid
        if group:
            keep &= np.array([group_of.get(u) != group for u in uids])
        sims = matrix @ feat
        out = []
        for pid in set(pids[keep].tolist()):
            if pid in skip or (only is not None and pid not in only):
                continue
            s = np.sort(sims[keep & (pids == pid)])[::-1][:3]
            out.append((float(s.mean()), pid))
        return sorted(out, reverse=True)

    def _drop_refs(self, cond):
        before = len(self.refs)
        self.refs = [r for r in self.refs if not cond(r)]
        if len(self.refs) != before:
            self._changed()

    # ── 主演 tags -> named people ──

    def _sync(self, snap: List[dict]):
        group_of = {e['uid']: e['group'] for e in snap}
        present = set(group_of)
        with self._lock:
            self._drop_refs(lambda r: r['uid'] not in present)
            for uid in [u for u in self.tagged if u not in present]:
                del self.tagged[uid]
                self._dirty = True
            for e in snap:
                for a in e['actors']:
                    self._name_pid(a)
            # an auto-added tag removed by hand: "not this person" from now on
            for e in snap:
                gone = [a for a in e['auto'] if a.lower() not in {x.lower() for x in e['actors']}]
                if gone:
                    marks = set(e['not']) | {pid for pid in (self._name_pid(a, create=False) for a in gone) if pid}
                    self.library.set_fields(e['vid'], {'auto_actors': [a for a in e['auto'] if a not in gone],
                                                       'not_people': sorted(marks)})
        todo = []
        for e in snap:
            key = f"{e['mtime']}|" + '|'.join(sorted(a.lower() for a in e['actors']))
            if not e['actors']:
                if e['uid'] in self.tagged:
                    with self._lock:
                        self._drop_refs(lambda r: r['uid'] == e['uid'] and r['src'] == 'tag')
                        del self.tagged[e['uid']]
                        self._dirty = True
                continue
            if e['ready'] and self.tagged.get(e['uid']) != key:
                todo.append((e, key))
        for i, (e, key) in enumerate(todo):
            if self._stop:
                return
            self.status.update(phase='sync', done=i, total=len(todo))
            data = self._faces(e)
            with self._lock:
                self._derive(e, data, group_of)
                self.tagged[e['uid']] = key
                self._dirty = True
                self._save()
        with self._lock:                         # people nobody is tagged with / no face left
            names = {a.lower() for e in self._snapshot() for a in e['actors']}
            have = {r['pid'] for r in self.refs}
            for pid, p in list(self.people.items()):
                if pid not in have and not (p['name'] and p['name'].lower() in names):
                    del self.people[pid]
                    self._changed()

    def _derive(self, e: dict, data: Optional[dict], group_of: Dict[str, str]):
        """The tag references of one item: which of its faces is which of its 主演."""
        uid = e['uid']
        self._drop_refs(lambda r: r['uid'] == uid and r['src'] == 'tag')
        if not data:
            return
        feats, count = data['feats'], len(data['persons'])
        pids = [self._name_pid(a) for a in e['actors']]
        assigned = {}
        if len(pids) == 1:
            ranked = [(self._ranked(feats[pi], uid, group_of, only={pids[0]}) or [(0.0, None)])[0][0]
                      for pi in range(count)]
            best = int(np.argmax(ranked)) if count > 1 and max(ranked) >= FACE_MATCH else 0
            assigned[best] = pids[0]
        else:
            left = list(pids)
            for pi in range(count):
                ranked = self._ranked(feats[pi], uid, group_of, only=set(left))
                if ranked and ranked[0][0] >= FACE_MATCH:
                    assigned[pi] = ranked[0][1]
                    left.remove(ranked[0][1])
            rest = [pi for pi in range(count) if pi not in assigned]
            if len(left) == 1 and len(rest) == 1:
                assigned[rest[0]] = left[0]
        # a face now known by its tag no longer belongs to an unnamed person
        self._drop_refs(lambda r: r['uid'] == uid and r['src'] == 'face' and r['pi'] in assigned
                        and r['pid'] != assigned[r['pi']])
        for pi, pid in assigned.items():
            if not any(r['uid'] == uid and r['pi'] == pi and r['pid'] == pid for r in self.refs):
                self.refs.append({'pid': pid, 'uid': uid, 'pi': pi, 'src': 'tag', 'feat': feats[pi]})
        self._changed()

    # ── recognising an item ──

    def _recognize(self, e: dict):
        data = self._faces(e)
        snap_groups = {x['uid']: x['group'] for x in self._snapshot()}
        add = []
        with self._lock:
            uid = e['uid']
            self._drop_refs(lambda r: r['uid'] == uid and r['src'] == 'face')   # file changed: start over
            if data:
                known = {r['pi']: r['pid'] for r in self.refs if r['uid'] == uid}
                taken = set(known.values())
                tagged = {a.lower() for a in e['actors']}
                for pi in range(len(data['persons'])):
                    if pi in known:
                        continue
                    feat = data['feats'][pi]
                    ranked = self._ranked(feat, uid, snap_groups, skip=set(e['not']) | taken)
                    if ranked and ranked[0][0] >= FACE_MATCH:
                        pid = ranked[0][1]
                        name = self.people[pid]['name']
                        if name:
                            if name.lower() not in tagged:
                                add.append(name)
                                tagged.add(name.lower())
                        else:
                            self.refs.append({'pid': pid, 'uid': uid, 'pi': pi, 'src': 'face', 'feat': feat})
                    else:
                        pid = self._new_person()
                        self.refs.append({'pid': pid, 'uid': uid, 'pi': pi, 'src': 'face', 'feat': feat})
                    taken.add(pid)
                    self._changed()
        if add:
            self.library.update_many([e['vid']], add_actors=add)
            logger.info(f"人物資料庫：{e['rel']} 自動加上主演 {'、'.join(add)}")
        self.library.set_fields(e['vid'], {'people_scan': e['mtime'], 'auto_actors': e['auto'] + add})

    # ── the 人物 page ──

    def _uid_map(self, snap) -> Dict[str, dict]:
        return {e['uid']: e for e in snap}

    def _members(self, pid: str, snap: List[dict]) -> List[dict]:
        """Items of a person: tagged with its name (named) or holding one of its faces (unnamed)."""
        person = self.people[pid]
        faces = {}
        for r in self.refs:
            if r['pid'] == pid:
                faces.setdefault(r['uid'], r['pi'])
        out = []
        for e in snap:
            if person['name']:
                if person['name'].lower() not in {a.lower() for a in e['actors']}:
                    continue
            elif e['uid'] not in faces:
                continue
            pi = faces.get(e['uid'])
            out.append({'id': e['vid'], 'name': os.path.basename(e['rel']), 'folder': os.path.dirname(e['rel']),
                        'kind': e['kind'], 'cover': e['cover'],
                        'face': f"{MEDIA_URL}/{e['vid']}/ai/face_{pi + 1}.jpg" if pi is not None else None,
                        'auto': any(a.lower() == (person['name'] or '').lower() for a in e['auto'])})
        return out

    @staticmethod
    def label(person: dict) -> str:
        return person['name'] or f"未命名人物 #{person['num']}"

    def overview(self) -> dict:
        snap = self._snapshot()
        with self._lock:
            self._load()
            out = []
            for pid, p in self.people.items():
                members = self._members(pid, snap)
                if not members and not p['name']:
                    continue
                cover = next((m['face'] for m in members if m['face']), None) or next((m['cover'] for m in members if m['cover']), None)
                out.append({'id': pid, 'name': p['name'], 'label': self.label(p), 'num': p['num'],
                            'count': len(members), 'auto': sum(1 for m in members if m['auto']), 'cover': cover,
                            'faces': sum(1 for r in self.refs if r['pid'] == pid)})
            unscanned = sum(1 for e in snap if e['ready'] and e['people_scan'] != e['mtime'])
            return {'people': out, 'status': dict(self.status), 'scan_all': self.scan_all, 'unscanned': unscanned,
                    'items': len(snap)}

    def detail(self, pid: str) -> Optional[dict]:
        snap = self._snapshot()
        with self._lock:
            p = self.people.get(pid)
            if not p:
                return None
            return {'id': pid, 'name': p['name'], 'label': self.label(p), 'num': p['num'],
                    'items': self._members(pid, snap)}

    def rename(self, pid: str, name: str) -> dict:
        """Name / rename a person (tags follow); a name that already exists merges into that person."""
        name = str(name or '').strip()[:100]
        if not name:
            raise ValueError('請輸入名字')
        # the lock is held throughout, so the worker can't turn the half-renamed tags into new people
        with self._lock:
            p = self.people.get(pid)
            if not p:
                raise KeyError(pid)
            other = self._name_pid(name, create=False)
            if other and other != pid:
                return self.merge(pid, other)
            old, label = p['name'], self.label(p)
            p['name'] = name
            if old:
                self.library.replace_actor(old, name)
            else:
                uids = {r['uid'] for r in self.refs if r['pid'] == pid}
                self.library.update_many([e['vid'] for e in self._snapshot() if e['uid'] in uids], add_actors=[name])
            self._retag(old, name)
            self._changed()
            self._save(force=True)
        self.wake()
        logger.info(f"人物資料庫：{label} -> {name}")
        return {'id': pid}

    def _retag(self, old: str, new: str):
        """Keep the tag keys in step so the renamed items aren't analysed again."""
        if not old:
            return
        for uid, key in list(self.tagged.items()):
            mtime, _, names = key.partition('|')
            parts = [new.lower() if n == old.lower() else n for n in names.split('|')]
            self.tagged[uid] = f"{mtime}|" + '|'.join(sorted(dict.fromkeys(parts)))

    def merge(self, pid: str, into: str) -> dict:
        """Move a person into another (the same person seen twice); the result keeps a name if either had one."""
        with self._lock:
            src, dst = self.people.get(pid), self.people.get(into)
            if not src or not dst or pid == into:
                raise KeyError(pid)
            final = dst['name'] or src['name']
            uid_vid = {e['uid']: e['vid'] for e in self._snapshot()}
            label_src, label_dst = self.label(src), self.label(dst)
            dst['name'] = final
            if src['name'] and src['name'] != final:
                self.library.replace_actor(src['name'], final)
            for owner, had in ((into, label_dst != final), (pid, not src['name'])):
                if final and had:                # unnamed faces of either side get the name as a tag
                    vids = [uid_vid[r['uid']] for r in self.refs if r['pid'] == owner and r['uid'] in uid_vid]
                    self.library.update_many(vids, add_actors=[final])
            for r in self.refs:
                if r['pid'] == pid:
                    r['pid'] = into
            del self.people[pid]
            self._retag(src['name'], final)
            self._changed()
            self._save(force=True)
        self.wake()
        logger.info(f"人物資料庫：{label_src} 合併到 {label_dst}")
        return {'id': into}

    def delete(self, pid: str) -> dict:
        """Forget a person; a named one's 主演 tag is removed from every item."""
        with self._lock:
            p = self.people.get(pid)
            if not p:
                raise KeyError(pid)
            removed = self.library.replace_actor(p['name'], '') if p['name'] else 0
            self._drop_refs(lambda r: r['pid'] == pid)
            self.people.pop(pid, None)
            self._changed()
            self._save(force=True)
        self.wake()
        logger.info(f"人物資料庫：刪除 {self.label(p)}（{removed} 個項目移除主演）")
        return {'removed': removed}

    def remove_items(self, pid: str, vids: List[str]) -> dict:
        """"Not this person" for some items: tag removed, face reference dropped, never added again."""
        with self._lock:
            p = self.people.get(pid)
            if not p:
                raise KeyError(pid)
            snap = {e['vid']: e for e in self._snapshot()}
            low = (p['name'] or '').lower()
            done = 0
            for vid in vids:
                e = snap.get(vid)
                if not e:
                    continue
                # marks first: the sync must not read the removed tag as "an auto tag removed by hand" twice
                self.library.set_fields(vid, {'not_people': sorted(set(e['not']) | {pid}),
                                              'auto_actors': [a for a in e['auto'] if a.lower() != low]})
                if low:
                    kept = [a for a in e['actors'] if a.lower() != low]
                    if len(kept) != len(e['actors']):
                        self.library.update(vid, {'actors': kept})
                self._drop_refs(lambda r: r['pid'] == pid and r['uid'] == e['uid'])
                done += 1
            self._save(force=True)
        self.wake()
        return {'removed': done}

    def set_scan_all(self, on: bool) -> dict:
        with self._lock:
            self._load()
            self.scan_all = bool(on)
            self._dirty = True
            self._save(force=True)
        self.wake()
        logger.info(f"人物資料庫：{'開始' if on else '停止'}掃描全部項目")
        return {'scan_all': self.scan_all}

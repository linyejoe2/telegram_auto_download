"""
library/server.py — aiohttp server for the web video library.

Everything lives under PREFIX (/library); "/" answers an empty page.
  /library/api/...            JSON API (login, videos / photos, tags, edit, delete, rescan,
                              download history + download again, AI 辨識 queue)     — login required
  /library/media/<id>/file    original file with HTTP range support (direct play)    — login required
  /library/media/<id>/stream  live H.264 transcode via ffmpeg, ?t=<start s>&q=<level> — login required
  /library/media/<id>/shots/  auto screenshots                                       — login required
  /library/media/<id>/ai/     face / body crops made by AI 辨識                       — login required
  /library/...                the React frontend (library/static, built by `npm run build` in frontend/)

Settings come from .env: WEB_PORT, WEB_HOST, WEB_PASSWORD_HASH, WEB_SECRET (see config.config).
LibraryServer runs the app on its own event loop in a background thread (GUI) or inside asyncio (CLI).
"""

import asyncio
import json
import logging
import os
import re
import sys
import threading
from typing import Callable, Optional

from aiohttp import web

from . import media
from .auth import Sessions, verify_password
from .people import People
from .recognize import AI_FILE_RE, Recognizer
from .recognize import status as recognition_status
from .store import Library, LibraryError, encode_id

logger = logging.getLogger(__name__)

COOKIE = 'tad_session'
PREFIX = '/library'          # the whole web app (frontend, API, media) lives under this path
RESCAN_SECONDS = 5 * 60
_SHOT_RE = re.compile(r'^\d{2}\.jpg$')
_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0


def static_dir() -> str:
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, 'library', 'static')


def _client(request: web.Request) -> str:
    """Client address; trust forwarding headers only from a local reverse proxy / tunnel."""
    remote = request.remote or ''
    if remote in ('127.0.0.1', '::1'):
        forwarded = request.headers.get('CF-Connecting-IP') or request.headers.get('X-Forwarded-For', '')
        if forwarded:
            return forwarded.split(',')[0].strip()
    return remote


def _session_tokens(request: web.Request):
    """Every value of the session cookie: a browser can send two (an old one stored for path "/"
    before the app moved to /library, and the current one), and request.cookies keeps only the last."""
    for part in request.headers.get('Cookie', '').split(';'):
        name, _, value = part.strip().partition('=')
        if name == COOKIE and value:
            yield value.strip('"')


def _expire_root_cookie(response: web.StreamResponse):
    """Delete the session cookie stored for path "/" by versions before the move to /library.
    Added as a raw header: response.cookies holds one entry per name, already used for /library."""
    response.headers.add('Set-Cookie', f'{COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict')


def _is_https(request: web.Request) -> bool:
    return request.secure or request.headers.get('X-Forwarded-Proto', '').lower() == 'https'


class LibraryServer:
    def __init__(self, base_path: Callable[[], str], password_hash: str, secret: str,
                 port: int = 8765, host: str = '0.0.0.0', similarity_threshold: Optional[float] = None,
                 on_grouped: Optional[Callable[[str], None]] = None,
                 on_redownload: Optional[Callable[[dict], Optional[str]]] = None):
        if not password_hash:
            raise ValueError('尚未設定網頁影片庫密碼')
        self.library = Library(base_path)
        if similarity_threshold:
            self.library.threshold = similarity_threshold
        self.library.on_grouped = on_grouped
        self.recognizer = Recognizer(self.library)      # AI 辨識 queue (library/recognize.py)
        self.people = People(self.library)              # 人物資料庫, auto 主演 tags (library/people.py)
        self.library.on_change = self.people.wake
        self.recognizer.people = self.people            # AI 辨識 reuses the database's 主演 faces
        # download a deleted file again through the running bot: returns an error text or None
        self.on_redownload = on_redownload
        self.sessions = Sessions(secret, password_hash)
        self.password_hash = password_hash
        self.port, self.host = port, host
        self._runner: Optional[web.AppRunner] = None
        self._rescan_task = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    # ── app ──

    def build_app(self) -> web.Application:
        app = web.Application(middlewares=[self._security_middleware], client_max_size=1024 * 1024)
        r = app.router
        r.add_post(PREFIX + '/api/login', self.login)
        r.add_post(PREFIX + '/api/logout', self.logout)
        r.add_get(PREFIX + '/api/session', self.session)
        r.add_get(PREFIX + '/api/status', self.status)
        r.add_get(PREFIX + '/api/videos', self.list_videos)
        r.add_get(PREFIX + '/api/videos/{id}', self.get_video)
        r.add_patch(PREFIX + '/api/videos/{id}', self.update_video)
        r.add_delete(PREFIX + '/api/videos/{id}', self.delete_video)
        r.add_post(PREFIX + '/api/videos/{id}/screenshots', self.regenerate_shots)
        r.add_get(PREFIX + '/api/tags', self.tags)
        r.add_get(PREFIX + '/api/folders', self.list_folders)
        r.add_post(PREFIX + '/api/folders', self.create_folder)
        r.add_post(PREFIX + '/api/folders/rename', self.rename_folder)
        r.add_post(PREFIX + '/api/folders/delete', self.delete_folder)
        r.add_post(PREFIX + '/api/videos/{id}/rename', self.rename_video)
        r.add_post(PREFIX + '/api/videos/{id}/ungroup', self.ungroup_video)
        r.add_post(PREFIX + '/api/videos/{id}/redownload', self.redownload_video)
        r.add_post(PREFIX + '/api/move', self.move)
        r.add_post(PREFIX + '/api/series/rename', self.rename_series)
        r.add_post(PREFIX + '/api/batch/update', self.batch_update)
        r.add_post(PREFIX + '/api/batch/delete', self.batch_delete)
        r.add_post(PREFIX + '/api/batch/compare', self.batch_compare)
        r.add_post(PREFIX + '/api/batch/merge', self.batch_merge)
        r.add_post(PREFIX + '/api/batch/deep-compare', self.deep_compare)
        r.add_get(PREFIX + '/api/recognition', self.recognition_jobs)
        r.add_post(PREFIX + '/api/recognition', self.recognition_add)
        r.add_get(PREFIX + '/api/recognition/status', self.recognition_status)
        r.add_get(PREFIX + '/api/recognition/{job}', self.recognition_job)
        r.add_delete(PREFIX + '/api/recognition/{job}', self.recognition_remove)
        r.add_post(PREFIX + '/api/recognition/{job}/cancel', self.recognition_cancel)
        r.add_post(PREFIX + '/api/recognition/{job}/apply', self.recognition_apply)
        r.add_get(PREFIX + '/api/people', self.people_list)
        r.add_post(PREFIX + '/api/people/scan', self.people_scan)
        r.add_get(PREFIX + '/api/people/{pid}', self.people_detail)
        r.add_delete(PREFIX + '/api/people/{pid}', self.people_delete)
        r.add_post(PREFIX + '/api/people/{pid}/rename', self.people_rename)
        r.add_post(PREFIX + '/api/people/{pid}/merge', self.people_merge)
        r.add_post(PREFIX + '/api/people/{pid}/remove', self.people_remove)
        r.add_post(PREFIX + '/api/rescan', self.rescan)
        r.add_get(PREFIX + '/api/history', self.history)
        r.add_post(PREFIX + '/api/history/redownload', self.redownload)
        r.add_get(PREFIX + '/media/{id}/file', self.media_file)
        r.add_get(PREFIX + '/media/{id}/stream', self.media_stream)
        r.add_get(PREFIX + '/media/{id}/shots/{name}', self.media_shot)
        r.add_get(PREFIX + '/media/{id}/ai/{name}', self.media_ai)
        r.add_get('/', self.blank)
        r.add_get(PREFIX, self.to_app)
        r.add_get(PREFIX + '/{tail:.*}', self.frontend)
        return app

    @web.middleware
    async def _security_middleware(self, request: web.Request, handler):
        path = request.path
        public = path in (PREFIX + '/api/login', PREFIX + '/api/session') or \
            not path.startswith((PREFIX + '/api/', PREFIX + '/media/'))
        if not public and not self._authenticated(request):
            return web.json_response({'error': 'unauthorized'}, status=401)
        response = await handler(request)
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'no-referrer')
        if path.startswith(PREFIX + '/api/'):
            response.headers.setdefault('Cache-Control', 'no-store')
        return response

    # ── auth ──

    def _authenticated(self, request: web.Request) -> bool:
        return any(self.sessions.valid(token) for token in _session_tokens(request))

    async def login(self, request: web.Request):
        client = _client(request)
        wait = self.sessions.locked_for(client)
        if wait:
            return web.json_response({'error': f'嘗試次數過多，請 {wait // 60 + 1} 分鐘後再試'}, status=429)
        try:
            password = str((await request.json()).get('password') or '')
        except Exception:
            password = ''
        ok = await asyncio.get_running_loop().run_in_executor(None, verify_password, password, self.password_hash)
        if not ok:
            self.sessions.failed(client)
            logger.warning(f"影片庫登入失敗：{client}")
            await asyncio.sleep(1)
            return web.json_response({'error': '密碼錯誤'}, status=401)
        self.sessions.succeeded(client)
        response = web.json_response({'ok': True})
        response.set_cookie(COOKIE, self.sessions.issue(), max_age=30 * 24 * 3600, httponly=True,
                            samesite='Strict', secure=_is_https(request), path=PREFIX)
        _expire_root_cookie(response)
        logger.info(f"影片庫登入：{client}")
        return response

    async def logout(self, request: web.Request):
        response = web.json_response({'ok': True})
        response.del_cookie(COOKIE, path=PREFIX)
        _expire_root_cookie(response)
        return response

    async def session(self, request: web.Request):
        return web.json_response({'authenticated': self._authenticated(request)})

    # ── api ──

    async def status(self, request: web.Request):
        return web.json_response({'videos': len(self.library.entries), 'processing': self.library.processing,
                                  'last_scan': self.library.last_scan})

    async def list_videos(self, request: web.Request):
        kind = request.query.get('kind', '')
        kind = kind if kind in ('video', 'photo') else ''
        return web.json_response({'videos': self.library.list(kind), 'processing': self.library.processing})

    def _detail_or_404(self, vid: str):
        data = self.library.detail(vid)
        if data is None:
            raise web.HTTPNotFound(text=json.dumps({'error': 'not found'}), content_type='application/json')
        return data

    async def get_video(self, request: web.Request):
        data = self._detail_or_404(request.match_info['id'])
        if data.get('error'):                     # broken file: say whether / how it can be downloaded again
            path = self.library.resolve(data['id'])
            plan, note = None, ''
            if path:
                plan, note = await asyncio.get_running_loop().run_in_executor(
                    None, self._records().plan_redownload, path)
            data['redownload'] = {'possible': bool(plan), 'note': note, 'bot': self.on_redownload is not None}
        return web.json_response(data)

    async def redownload_video(self, request: web.Request):
        """Download a broken file again (it is replaced once the source is reachable)."""
        path = self.library.resolve(request.match_info['id'])
        if not path:
            return web.json_response({'error': 'not found'}, status=404)
        if self.on_redownload is None:
            return web.json_response({'error': '這台電腦的程式沒有在執行 Bot，無法重新下載'}, status=503)
        plan, note = await asyncio.get_running_loop().run_in_executor(None, self._records().plan_redownload, path)
        if not plan:
            return web.json_response({'error': note}, status=404)
        error = self.on_redownload(plan, path)
        if error:
            return web.json_response({'error': error}, status=503)
        logger.info(f"影片庫：重新下載損毀的檔案 {path}（{note}）")
        return web.json_response({'ok': True, 'note': note}, status=202)

    async def update_video(self, request: web.Request):
        try:
            fields = await request.json()
        except Exception:
            return web.json_response({'error': 'invalid json'}, status=400)
        if not isinstance(fields, dict):
            return web.json_response({'error': 'invalid json'}, status=400)
        data = await asyncio.get_running_loop().run_in_executor(
            None, self.library.update, request.match_info['id'], fields)
        if data is None:
            return web.json_response({'error': 'not found'}, status=404)
        return web.json_response(data)

    async def delete_video(self, request: web.Request):
        try:
            ok = await asyncio.get_running_loop().run_in_executor(None, self.library.delete, request.match_info['id'])
        except OSError as e:
            return web.json_response({'error': f'刪除失敗：{e.strerror or e}'}, status=500)
        return web.json_response({'ok': True}) if ok else web.json_response({'error': 'not found'}, status=404)

    async def regenerate_shots(self, request: web.Request):
        vid = request.match_info['id']
        self._detail_or_404(vid)
        self.library.queue_refresh(vid, force_shots=True)
        return web.json_response({'ok': True})

    async def tags(self, request: web.Request):
        return web.json_response(self.library.tags())

    # ── folders & file management (drag & drop, rename, new folder) ──

    async def _run(self, fn, *args):
        """Run a blocking library change; LibraryError / OSError become JSON errors."""
        try:
            return await asyncio.get_running_loop().run_in_executor(None, fn, *args), None
        except LibraryError as e:
            return None, web.json_response({'error': str(e)}, status=e.status)
        except OSError as e:
            return None, web.json_response({'error': f'檔案操作失敗：{e.strerror or e}'}, status=500)

    @staticmethod
    async def _body(request: web.Request) -> dict:
        try:
            data = await request.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    async def list_folders(self, request: web.Request):
        folders, error = await self._run(self.library.folders)
        return error if error is not None else web.json_response({'folders': folders})

    async def create_folder(self, request: web.Request):
        body = await self._body(request)
        path, error = await self._run(self.library.create_folder, body.get('parent', ''), body.get('name', ''))
        return error if error is not None else web.json_response({'path': path})

    async def rename_folder(self, request: web.Request):
        body = await self._body(request)
        path, error = await self._run(self.library.rename_folder, body.get('path', ''), body.get('name', ''))
        return error if error is not None else web.json_response({'path': path})

    async def delete_folder(self, request: web.Request):
        body = await self._body(request)
        _, error = await self._run(self.library.delete_folder, body.get('path', ''))
        return error if error is not None else web.json_response({'ok': True})

    async def rename_video(self, request: web.Request):
        body = await self._body(request)
        vid, error = await self._run(self.library.rename_video, request.match_info['id'], body.get('name', ''))
        return error if error is not None else web.json_response({'id': vid})

    async def ungroup_video(self, request: web.Request):
        data, error = await self._run(self.library.ungroup, request.match_info['id'])
        if error:
            return error
        return web.json_response(data) if data else web.json_response({'error': 'not found'}, status=404)

    async def move(self, request: web.Request):
        body = await self._body(request)
        videos = [str(v) for v in body.get('videos') or [] if isinstance(v, str)]
        folders = [str(f) for f in body.get('folders') or [] if isinstance(f, str)]
        result, error = await self._run(self.library.move, videos, folders, body.get('dest', ''))
        return error if error is not None else web.json_response(result)

    @staticmethod
    def _strings(value) -> list:
        return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []

    async def rename_series(self, request: web.Request):
        """Rename a 系列 on every item: {old, new} -> {updated, name} (an existing name merges)."""
        body = await self._body(request)
        old, new = body.get('old'), body.get('new')
        if not isinstance(old, str) or not isinstance(new, str):
            return web.json_response({'error': '缺少系列名稱'}, status=400)
        result, error = await self._run(self.library.rename_series, old, new)
        return error if error is not None else web.json_response(result)

    async def batch_update(self, request: web.Request):
        """Multi-select edit: {ids, add_actors, remove_actors, series?} (series '' clears, absent = unchanged)."""
        body = await self._body(request)
        ids = self._strings(body.get('ids'))
        if not ids:
            return web.json_response({'error': '沒有選取任何項目'}, status=400)
        series = body.get('series')
        result, error = await self._run(self.library.update_many, ids, self._strings(body.get('add_actors')),
                                        self._strings(body.get('remove_actors')),
                                        series if isinstance(series, str) else None)
        return error if error is not None else web.json_response(result)

    async def batch_delete(self, request: web.Request):
        """Multi-select delete: {ids} -> {deleted, failed: [{name, error}]}."""
        body = await self._body(request)
        ids = self._strings(body.get('ids'))
        if not ids:
            return web.json_response({'error': '沒有選取任何項目'}, status=400)
        result, error = await self._run(self.library.delete_many, ids)
        return error if error is not None else web.json_response(result)

    async def batch_compare(self, request: web.Request):
        """Multi-select 「嘗試合併」 step 1 (changes nothing): {ids} -> {items, pairs: [[id, id, score]], photos, threshold}."""
        body = await self._body(request)
        ids = self._strings(body.get('ids'))
        if len(ids) < 2:
            return web.json_response({'error': '請至少選取兩部影片'}, status=400)
        result, error = await self._run(self.library.compare_many, ids)
        return error if error is not None else web.json_response(result)

    async def deep_compare(self, request: web.Request):
        """加強比對 of exactly two videos: {ids: [a, b]} -> score, offset, scale, previews… (takes seconds to minutes)."""
        body = await self._body(request)
        ids = self._strings(body.get('ids'))
        if len(ids) != 2:
            return web.json_response({'error': '加強比對只能選兩部影片'}, status=400)
        result, error = await self._run(self.library.deep_compare, ids[0], ids[1])
        return error if error is not None else web.json_response(result)

    async def batch_merge(self, request: web.Request):
        """Multi-select 「嘗試合併」 step 2: {groups: [[id, ...], ...]} -> {groups: [{title, versions}]}."""
        body = await self._body(request)
        groups = [g for g in (self._strings(g) for g in body.get('groups') or [] if isinstance(g, list)) if len(g) > 1]
        if not groups:
            return web.json_response({'error': '沒有要合併的影片'}, status=400)
        result, error = await self._run(self.library.join_groups, groups)
        return error if error is not None else web.json_response(result)

    # ── AI 辨識 (library/recognize.py) ──

    async def recognition_jobs(self, request: web.Request):
        jobs = await asyncio.get_running_loop().run_in_executor(None, self.recognizer.jobs)
        return web.json_response({'jobs': jobs})

    async def recognition_status(self, request: web.Request):
        """Face models present, Ollama reachable and the vision model used (a few seconds when Ollama is down)."""
        data = await asyncio.get_running_loop().run_in_executor(None, recognition_status)
        return web.json_response(data)

    async def recognition_add(self, request: web.Request):
        """Queue 辨識主演 / 辨識系列: {kind: 'actor'|'series', ids} -> the queued job."""
        body = await self._body(request)
        ids = self._strings(body.get('ids'))
        if not ids:
            return web.json_response({'error': '沒有選取任何項目'}, status=400)
        try:
            job = await asyncio.get_running_loop().run_in_executor(None, self.recognizer.add, body.get('kind'), ids)
        except ValueError as e:
            return web.json_response({'error': str(e)}, status=400)
        return web.json_response({'job': job})

    async def recognition_job(self, request: web.Request):
        job = await asyncio.get_running_loop().run_in_executor(None, self.recognizer.job, request.match_info['job'])
        return web.json_response(job) if job else web.json_response({'error': '找不到辨識工作'}, status=404)

    async def recognition_cancel(self, request: web.Request):
        ok = self.recognizer.cancel(request.match_info['job'])
        return web.json_response({'ok': True}) if ok else web.json_response({'error': '找不到辨識工作'}, status=404)

    async def recognition_remove(self, request: web.Request):
        ok = await asyncio.get_running_loop().run_in_executor(None, self.recognizer.remove, request.match_info['job'])
        return web.json_response({'ok': True}) if ok else web.json_response({'error': '找不到辨識工作'}, status=404)

    async def recognition_apply(self, request: web.Request):
        """Use / skip results: {entries: [{key, action: 'apply'|'reject', name?, items?}]} -> {job, updated, missing}."""
        body = await self._body(request)
        entries = [e for e in body.get('entries') or [] if isinstance(e, dict)]
        if not entries:
            return web.json_response({'error': '沒有要套用的結果'}, status=400)
        try:
            result = await asyncio.get_running_loop().run_in_executor(
                None, self.recognizer.apply, request.match_info['job'], entries)
        except ValueError as e:
            return web.json_response({'error': str(e)}, status=400)
        return web.json_response(result)

    # ── 人物資料庫 (library/people.py) ──

    async def _people_call(self, fn, *args):
        try:
            return web.json_response(await asyncio.get_running_loop().run_in_executor(None, fn, *args))
        except KeyError:
            return web.json_response({'error': '找不到這個人物'}, status=404)
        except ValueError as e:
            return web.json_response({'error': str(e)}, status=400)

    async def people_list(self, request: web.Request):
        """{people: [{id, name, label, num, count, auto, cover, faces}], status, scan_all, unscanned, items}."""
        return await self._people_call(self.people.overview)

    async def people_detail(self, request: web.Request):
        data = await asyncio.get_running_loop().run_in_executor(None, self.people.detail, request.match_info['pid'])
        return web.json_response(data) if data else web.json_response({'error': '找不到這個人物'}, status=404)

    async def people_scan(self, request: web.Request):
        """{on: true} recognises every item not scanned yet (in the background), {on: false} stops."""
        body = await self._body(request)
        return await self._people_call(self.people.set_scan_all, bool(body.get('on')))

    async def people_rename(self, request: web.Request):
        """{name}: name / rename (主演 tags follow); an existing name merges into that person."""
        body = await self._body(request)
        return await self._people_call(self.people.rename, request.match_info['pid'], body.get('name', ''))

    async def people_merge(self, request: web.Request):
        body = await self._body(request)
        return await self._people_call(self.people.merge, request.match_info['pid'], str(body.get('into') or ''))

    async def people_remove(self, request: web.Request):
        """{items: [id]}: not this person (tag removed, never added again)."""
        body = await self._body(request)
        return await self._people_call(self.people.remove_items, request.match_info['pid'], self._strings(body.get('items')))

    async def people_delete(self, request: web.Request):
        return await self._people_call(self.people.delete, request.match_info['pid'])

    async def rescan(self, request: web.Request):
        count = await asyncio.get_running_loop().run_in_executor(None, self.library.scan)
        return web.json_response({'videos': count, 'processing': self.library.processing})

    # ── download history (src/records.py) ──

    @staticmethod
    def _records():
        from src.records import DownloadRecords
        return DownloadRecords()

    async def history(self, request: web.Request):
        q = request.query
        try:
            offset, limit = int(q.get('offset', 0)), int(q.get('limit', 100))
        except ValueError:
            offset, limit = 0, 100
        data = await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._records().history(q.get('q', ''), q.get('status', ''), q.get('kind', ''), offset, limit))
        with self.library._lock:
            for item in data['items']:            # existing videos / photos open their page in the library
                vid = encode_id(item['rel']) if item['inside'] and not item['deleted'] else None
                item['id'] = vid if vid in self.library.entries else None
        data['redownload'] = self.on_redownload is not None
        return web.json_response(data)

    async def redownload(self, request: web.Request):
        key = str((await self._body(request)).get('key') or '')
        record = await asyncio.get_running_loop().run_in_executor(None, self._records().get, key)
        if not record:
            return web.json_response({'error': '找不到這筆下載紀錄'}, status=404)
        if not record['deleted']:
            return web.json_response({'error': '檔案還在，不需要重新下載'}, status=409)
        if self.on_redownload is None:
            return web.json_response({'error': '這台電腦的程式沒有在執行 Bot，無法重新下載'}, status=503)
        error = self.on_redownload(record)
        if error:
            return web.json_response({'error': error}, status=503)
        logger.info(f"影片庫：重新下載 {record.get('file_name')}")
        return web.json_response({'ok': True}, status=202)

    # ── media ──

    def _video_path(self, request: web.Request) -> str:
        path = self.library.resolve(request.match_info['id'])
        if not path:
            raise web.HTTPNotFound()
        return path

    async def media_file(self, request: web.Request):
        return web.FileResponse(self._video_path(request), headers={'Cache-Control': 'private, max-age=3600'})

    async def media_shot(self, request: web.Request):
        name = request.match_info['name']
        if not _SHOT_RE.match(name):
            raise web.HTTPNotFound()
        path = os.path.join(media.shots_dir(self._video_path(request)), name)
        if not os.path.isfile(path):
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={'Cache-Control': 'private, max-age=86400'})

    async def media_ai(self, request: web.Request):
        """Face / body crops made by AI 辨識 (face_N.jpg, body_N.jpg in the shots folder)."""
        name = request.match_info['name']
        if not AI_FILE_RE.match(name):
            raise web.HTTPNotFound()
        path = os.path.join(media.shots_dir(self._video_path(request)), name)
        if not os.path.isfile(path):
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={'Cache-Control': 'private, no-cache'})

    async def media_stream(self, request: web.Request):
        """Fragmented MP4 (H.264 + AAC) from `t` seconds on; the player restarts it to seek."""
        path = self._video_path(request)
        ffmpeg = media.find_tool('ffmpeg')
        if not ffmpeg:
            return web.json_response({'error': '找不到 ffmpeg'}, status=503)
        try:
            start = max(0.0, float(request.query.get('t', 0)))
        except ValueError:
            start = 0.0
        key = request.query.get('q') or media.STREAM_DEFAULT
        encoder = await asyncio.get_running_loop().run_in_executor(None, media.stream_encoder)

        async def spawn(encoder):
            return await asyncio.create_subprocess_exec(
                *media.stream_command(ffmpeg, path, start, key, encoder),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, creationflags=_NO_WINDOW)

        proc = await spawn(encoder)
        chunk = await proc.stdout.read(256 * 1024)
        if not chunk and encoder != 'cpu' and await proc.wait() != 0:
            # GPU encoder unavailable right now (e.g. NVENC session limit): use the CPU for this stream
            logger.warning('影片庫：GPU 轉檔失敗，改用 CPU')
            proc = await spawn('cpu')
            chunk = await proc.stdout.read(256 * 1024)
        response = web.StreamResponse(headers={'Content-Type': 'video/mp4', 'Cache-Control': 'no-store'})
        await response.prepare(request)
        try:
            while chunk:
                await response.write(chunk)
                chunk = await proc.stdout.read(256 * 1024)
        except (ConnectionResetError, asyncio.CancelledError):
            pass                              # viewer seeked / closed the player
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
        return response

    async def blank(self, request: web.Request):
        """The site root stays empty: the library is only at /library."""
        return web.Response(text='', content_type='text/html')

    async def to_app(self, request: web.Request):
        # keep the query: the router writes the library page as /library?folder=… (reload must keep the filters)
        query = request.query_string
        raise web.HTTPFound(PREFIX + '/' + (f'?{query}' if query else ''))

    async def frontend(self, request: web.Request):
        root = static_dir()
        rel = request.match_info['tail']           # path after /library/ (assets are built with base /library/)
        if rel:
            target = os.path.realpath(os.path.join(root, rel))
            if (os.path.normcase(target).startswith(os.path.normcase(os.path.realpath(root)) + os.sep)
                    and os.path.isfile(target)):
                cache = 'public, max-age=31536000, immutable' if rel.startswith('assets/') else 'no-cache'
                return web.FileResponse(target, headers={'Cache-Control': cache})
        index = os.path.join(root, 'index.html')
        if not os.path.isfile(index):
            return web.Response(text='網頁介面尚未建置：請在 frontend/ 執行 npm install && npm run build', status=503)
        return web.FileResponse(index, headers={'Cache-Control': 'no-cache'})   # SPA route

    # ── lifecycle ──

    async def start(self):
        self._runner = web.AppRunner(self.build_app(), access_log=None)
        await self._runner.setup()
        await web.TCPSite(self._runner, self.host, self.port).start()
        logger.info(f"網頁影片庫已啟動：http://{self.host}:{self.port}{PREFIX}/")
        self._rescan_task = asyncio.create_task(self._rescan_loop())
        self.recognizer.start()             # continues jobs left in .tad/recognition.json
        self.people.start()                 # builds / updates the people database, recognises new items

    async def _rescan_loop(self):
        loop = asyncio.get_running_loop()
        while True:
            try:
                await loop.run_in_executor(None, self.library.scan)
                if not self.library.matching_ready:
                    # full similarity check once everything has its screenshots; new videos are
                    # matched one by one afterwards (and announced through on_grouped)
                    while self.library.processing:
                        await asyncio.sleep(2)
                    await loop.run_in_executor(None, self.library.check_all)
            except Exception as e:
                logger.warning(f"影片庫掃描失敗: {e}")
            # come back soon for files that were still being written
            await asyncio.sleep(60 if self.library.deferred else RESCAN_SECONDS)

    async def stop(self):
        if self._rescan_task:
            self._rescan_task.cancel()
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        self.recognizer.shutdown()
        self.people.shutdown()
        self.library.shutdown()
        logger.info("網頁影片庫已停止")

    def start_in_thread(self, timeout: float = 10):
        """Run on a private event loop in a daemon thread (GUI). Raises if the port can't be opened."""
        started, failure = threading.Event(), []

        def run():
            from concurrent.futures import ThreadPoolExecutor
            self._loop = asyncio.new_event_loop()
            # named, so the Windows app's Diagnostics tab tells this pool from the bot's (both were "asyncio_N")
            # at most MAX_THREADS of them (at least 2, so one slow request doesn't hold up the others)
            self._loop.set_default_executor(ThreadPoolExecutor(max_workers=max(2, media.thread_limit()),
                                                               thread_name_prefix='web-library-worker'))
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self.start())
            except Exception as e:
                failure.append(e)
                started.set()
                return
            started.set()
            self._loop.run_forever()
            self._loop.run_until_complete(self.stop())
            self._loop.close()

        self._thread = threading.Thread(target=run, daemon=True, name='web-library')
        self._thread.start()
        started.wait(timeout)
        if failure:
            raise failure[0]

    def stop_thread(self, timeout: float = 10):
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout)
        self._thread = self._loop = None

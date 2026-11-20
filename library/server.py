"""
library/server.py — aiohttp server for the web video library.

  /api/...            JSON API (login, videos, tags, edit, delete, rescan)   — login required
  /media/<id>/file    original file with HTTP range support (direct play)    — login required
  /media/<id>/stream  live H.264 transcode via ffmpeg, ?t=<start seconds>    — login required
  /media/<id>/shots/  auto screenshots                                       — login required
  everything else     the React frontend (library/static, built by `npm run build` in frontend/)

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
from .store import Library, LibraryError

logger = logging.getLogger(__name__)

COOKIE = 'tad_session'
RESCAN_SECONDS = 5 * 60
STREAM_HEIGHTS = (480, 720, 1080)
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


def _is_https(request: web.Request) -> bool:
    return request.secure or request.headers.get('X-Forwarded-Proto', '').lower() == 'https'


class LibraryServer:
    def __init__(self, base_path: Callable[[], str], password_hash: str, secret: str,
                 port: int = 8765, host: str = '0.0.0.0'):
        if not password_hash:
            raise ValueError('尚未設定網頁影片庫密碼')
        self.library = Library(base_path)
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
        r.add_post('/api/login', self.login)
        r.add_post('/api/logout', self.logout)
        r.add_get('/api/session', self.session)
        r.add_get('/api/status', self.status)
        r.add_get('/api/videos', self.list_videos)
        r.add_get('/api/videos/{id}', self.get_video)
        r.add_patch('/api/videos/{id}', self.update_video)
        r.add_delete('/api/videos/{id}', self.delete_video)
        r.add_post('/api/videos/{id}/screenshots', self.regenerate_shots)
        r.add_get('/api/tags', self.tags)
        r.add_get('/api/folders', self.list_folders)
        r.add_post('/api/folders', self.create_folder)
        r.add_post('/api/folders/rename', self.rename_folder)
        r.add_post('/api/folders/delete', self.delete_folder)
        r.add_post('/api/videos/{id}/rename', self.rename_video)
        r.add_post('/api/move', self.move)
        r.add_post('/api/rescan', self.rescan)
        r.add_get('/media/{id}/file', self.media_file)
        r.add_get('/media/{id}/stream', self.media_stream)
        r.add_get('/media/{id}/shots/{name}', self.media_shot)
        r.add_get('/{tail:.*}', self.frontend)
        return app

    @web.middleware
    async def _security_middleware(self, request: web.Request, handler):
        path = request.path
        public = path in ('/api/login', '/api/session') or not path.startswith(('/api/', '/media/'))
        if not public and not self.sessions.valid(request.cookies.get(COOKIE)):
            return web.json_response({'error': 'unauthorized'}, status=401)
        response = await handler(request)
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'no-referrer')
        if path.startswith('/api/'):
            response.headers.setdefault('Cache-Control', 'no-store')
        return response

    # ── auth ──

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
                            samesite='Strict', secure=_is_https(request), path='/')
        logger.info(f"影片庫登入：{client}")
        return response

    async def logout(self, request: web.Request):
        response = web.json_response({'ok': True})
        response.del_cookie(COOKIE, path='/')
        return response

    async def session(self, request: web.Request):
        return web.json_response({'authenticated': self.sessions.valid(request.cookies.get(COOKIE))})

    # ── api ──

    async def status(self, request: web.Request):
        return web.json_response({'videos': len(self.library.entries), 'processing': self.library.processing,
                                  'last_scan': self.library.last_scan})

    async def list_videos(self, request: web.Request):
        return web.json_response({'videos': self.library.list(), 'processing': self.library.processing})

    def _detail_or_404(self, vid: str):
        data = self.library.detail(vid)
        if data is None:
            raise web.HTTPNotFound(text=json.dumps({'error': 'not found'}), content_type='application/json')
        return data

    async def get_video(self, request: web.Request):
        return web.json_response(self._detail_or_404(request.match_info['id']))

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
        return error or web.json_response({'folders': folders})

    async def create_folder(self, request: web.Request):
        body = await self._body(request)
        path, error = await self._run(self.library.create_folder, body.get('parent', ''), body.get('name', ''))
        return error or web.json_response({'path': path})

    async def rename_folder(self, request: web.Request):
        body = await self._body(request)
        path, error = await self._run(self.library.rename_folder, body.get('path', ''), body.get('name', ''))
        return error or web.json_response({'path': path})

    async def delete_folder(self, request: web.Request):
        body = await self._body(request)
        _, error = await self._run(self.library.delete_folder, body.get('path', ''))
        return error or web.json_response({'ok': True})

    async def rename_video(self, request: web.Request):
        body = await self._body(request)
        vid, error = await self._run(self.library.rename_video, request.match_info['id'], body.get('name', ''))
        return error or web.json_response({'id': vid})

    async def move(self, request: web.Request):
        body = await self._body(request)
        videos = [str(v) for v in body.get('videos') or [] if isinstance(v, str)]
        folders = [str(f) for f in body.get('folders') or [] if isinstance(f, str)]
        result, error = await self._run(self.library.move, videos, folders, body.get('dest', ''))
        return error or web.json_response(result)

    async def rescan(self, request: web.Request):
        count = await asyncio.get_running_loop().run_in_executor(None, self.library.scan)
        return web.json_response({'videos': count, 'processing': self.library.processing})

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
        height = int(request.query.get('h', 720)) if request.query.get('h', '').isdigit() else 720
        height = height if height in STREAM_HEIGHTS else 720

        proc = await asyncio.create_subprocess_exec(
            ffmpeg, '-hide_banner', '-loglevel', 'error', '-ss', f'{start:.3f}', '-i', path,
            '-map', '0:v:0', '-map', '0:a:0?', '-sn', '-dn',
            '-vf', f"scale=-2:'min({height},ih)',format=yuv420p",
            '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency', '-crf', '23',
            '-g', '48', '-c:a', 'aac', '-b:a', '160k', '-ac', '2',
            '-movflags', 'frag_keyframe+empty_moov+default_base_moof', '-f', 'mp4', 'pipe:1',
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, creationflags=_NO_WINDOW,
        )
        response = web.StreamResponse(headers={'Content-Type': 'video/mp4', 'Cache-Control': 'no-store'})
        await response.prepare(request)
        try:
            while True:
                chunk = await proc.stdout.read(256 * 1024)
                if not chunk:
                    break
                await response.write(chunk)
        except (ConnectionResetError, asyncio.CancelledError):
            pass                              # viewer seeked / closed the player
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
        return response

    async def frontend(self, request: web.Request):
        root = static_dir()
        rel = request.match_info['tail']
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
        logger.info(f"網頁影片庫已啟動：http://{self.host}:{self.port}")
        self._rescan_task = asyncio.create_task(self._rescan_loop())

    async def _rescan_loop(self):
        loop = asyncio.get_running_loop()
        while True:
            try:
                await loop.run_in_executor(None, self.library.scan)
            except Exception as e:
                logger.warning(f"影片庫掃描失敗: {e}")
            await asyncio.sleep(RESCAN_SECONDS)

    async def stop(self):
        if self._rescan_task:
            self._rescan_task.cancel()
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        self.library.shutdown()
        logger.info("網頁影片庫已停止")

    def start_in_thread(self, timeout: float = 10):
        """Run on a private event loop in a daemon thread (GUI). Raises if the port can't be opened."""
        started, failure = threading.Event(), []

        def run():
            self._loop = asyncio.new_event_loop()
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

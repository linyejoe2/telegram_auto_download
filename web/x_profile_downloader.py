"""
web/x_profile_downloader.py — Download all media (and optional screenshots) of an X account.

Flow:
  1. start_flow()      — scan the account with gallery-dl, show counts + mode buttons
  2. on_mode_chosen()  — user picked a mode (media / media+screenshot / screenshot only),
                         show the folder keyboard
  3. download()        — called after folder confirmed; download media, take screenshots
"""

import asyncio
import logging
import os
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

COOKIE_BROWSER = 'firefox'
MAX_CONCURRENT_DOWNLOADS = 5
MAX_CONCURRENT_SCREENSHOTS = 3

# Mode callback data
MODE_MEDIA = 'xp_media'
MODE_BOTH = 'xp_both'
MODE_SHOT = 'xp_shot'


@dataclass
class MediaItem:
    tweet_id: int
    num: int
    url: str
    kind: str       # photo / video / animated_gif
    ext: str


@dataclass
class ProfileScan:
    username: str
    url: str
    total_posts: int = 0
    media_post_ids: List[int] = field(default_factory=list)
    items: List[MediaItem] = field(default_factory=list)
    mode: str = MODE_MEDIA

    @property
    def videos(self) -> int:
        return sum(1 for i in self.items if i.kind != 'photo')

    @property
    def photos(self) -> int:
        return sum(1 for i in self.items if i.kind == 'photo')


# Pending scans keyed by user_id (between scan and folder confirmation)
_pending: Dict[int, ProfileScan] = {}


class XProfileDownloader:

    # ─── step 1: scan ────────────────────────────────────────────────────────

    def _scan_blocking(self, username: str) -> ProfileScan:
        # Run gallery-dl in-process: in the frozen exe sys.executable is the app itself,
        # so spawning "python -m gallery_dl" is not possible.
        from gallery_dl import config, job

        config.clear()
        config.set(('extractor', 'twitter'), 'text-tweets', True)
        config.set((), 'cookies', (COOKIE_BROWSER,))
        data_job = job.DataJob(f'https://x.com/{username}/tweets', file=None)
        data_job.run()
        messages = data_job.data
        for msg in messages:
            if msg[0] == -1:
                raise RuntimeError(f"{msg[1].get('error')}: {msg[1].get('message')}")

        scan = ProfileScan(username=username, url=f'https://x.com/{username}')
        seen_posts, media_posts = set(), set()
        for msg in messages:
            if msg[0] == 2:
                seen_posts.add(msg[1]['tweet_id'])
            elif msg[0] == 3:
                meta = msg[2]
                tid = meta['tweet_id']
                seen_posts.add(tid)
                media_posts.add(tid)
                scan.items.append(MediaItem(
                    tweet_id=tid, num=meta.get('num', 1), url=msg[1],
                    kind=meta.get('type', 'photo'), ext=meta.get('extension', 'jpg'),
                ))
        scan.total_posts = len(seen_posts)
        scan.media_post_ids = sorted(media_posts)
        return scan

    async def start_flow(self, username: str, user_id: int, processing_msg) -> None:
        loop = asyncio.get_event_loop()
        task = loop.run_in_executor(None, self._scan_blocking, username)

        started = time.time()
        while not task.done():
            await asyncio.sleep(5)
            await _safe_edit(
                processing_msg,
                f"🔍 正在掃描 @{username} 的貼文...（已 {int(time.time() - started)} 秒，貼文多時需要數分鐘）",
            )

        try:
            scan = await task
        except Exception as e:
            logger.error(f"X 帳號掃描失敗: {e}")
            await processing_msg.edit_text(f"❌ 掃描失敗: {e}")
            return

        if not scan.items:
            await processing_msg.edit_text(
                f"@{username} 共 {scan.total_posts} 篇文章，但沒有找到任何媒體"
            )
            return

        _pending[user_id] = scan
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬇️ 下載媒體", callback_data=MODE_MEDIA)],
            [InlineKeyboardButton("⬇️📸 下載媒體 + 截圖", callback_data=MODE_BOTH)],
            [InlineKeyboardButton("📸 只截圖", callback_data=MODE_SHOT)],
        ])
        await processing_msg.edit_text(
            f"🐦 @{username}\n"
            f"文章 {scan.total_posts} 篇（含媒體 {len(scan.media_post_ids)} 篇）\n"
            f"影片 {scan.videos} 部\n"
            f"照片 {scan.photos} 張\n\n"
            f"請選擇下載內容（沒有媒體的文章不會下載）：",
            reply_markup=markup,
        )

    # ─── step 2: mode chosen → folder keyboard ───────────────────────────────

    async def on_mode_chosen(self, mode: str, user_id: int, message, folder_navigator) -> None:
        scan = _pending.get(user_id)
        if not scan:
            await message.edit_text("此操作已過期，請重新發送帳號網址")
            return
        scan.mode = mode

        nav_text, markup = folder_navigator.start_folder_selection(user_id, [], {})
        state = folder_navigator.get_user_state(user_id)
        state.pending_url = scan.url
        state.url_type = 'x_profile'
        await message.edit_text(nav_text, reply_markup=markup)

    # ─── step 3: download ────────────────────────────────────────────────────

    async def download(self, user_id: int, dest_dir: str, processing_msg) -> None:
        scan = _pending.pop(user_id, None)
        if not scan:
            await processing_msg.edit_text("❌ 找不到掃描結果，請重新發送帳號網址")
            return

        dest = os.path.join(dest_dir, f'x_{scan.username}')
        os.makedirs(dest, exist_ok=True)

        ok = skipped = failed = 0
        if scan.mode in (MODE_MEDIA, MODE_BOTH):
            ok, skipped, failed = await self._download_media(scan, dest, processing_msg)

        shots_ok = shots_failed = 0
        shot_error = None
        if scan.mode in (MODE_SHOT, MODE_BOTH):
            shots_ok, shots_failed, shot_error = await self._take_screenshots(
                scan, os.path.join(dest, 'screenshots'), processing_msg
            )

        lines = ["✅ 完成！", f"📁 {dest}"]
        if scan.mode != MODE_SHOT:
            lines.append(f"⬇️ 媒體 成功 {ok} / 略過(已存在) {skipped} / 失敗 {failed}")
        if scan.mode != MODE_MEDIA:
            lines.append(f"📸 截圖 成功 {shots_ok} / 失敗 {shots_failed}")
            if shot_error:
                lines.append(f"⚠️ {shot_error}")
        await processing_msg.edit_text("\n".join(lines))

    async def _download_media(self, scan: ProfileScan, dest: str, msg):
        from src.database import DatabaseManager
        db = DatabaseManager()
        loop = asyncio.get_event_loop()
        sem = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
        counts = {'ok': 0, 'skipped': 0, 'failed': 0}
        total = len(scan.items)
        last_edit = [0.0]

        async def one(item: MediaItem):
            name = f"{item.tweet_id}_{item.num}.{item.ext}"
            path = os.path.join(dest, name)
            uid = f"xprofile_{item.tweet_id}_{item.num}"
            if os.path.exists(path) or db.is_file_downloaded(uid):
                counts['skipped'] += 1
                return
            async with sem:
                try:
                    await loop.run_in_executor(None, _fetch, item.url, path)
                except Exception as e:
                    logger.warning(f"下載失敗 {item.url}: {e}")
                    counts['failed'] += 1
                    if os.path.exists(path):
                        os.remove(path)
                    return
            db.record_download(
                file_unique_id=uid, file_id=item.url, message_id=item.tweet_id, chat_id=0,
                file_name=name, file_path=path, original_file_name=name,
                file_size=os.path.getsize(path),
                file_type='photo' if item.kind == 'photo' else 'video',
                mime_type='image/jpeg' if item.kind == 'photo' else 'video/mp4',
            )
            counts['ok'] += 1
            now = time.time()
            if now - last_edit[0] > 3:
                last_edit[0] = now
                done = counts['ok'] + counts['skipped'] + counts['failed']
                await _safe_edit(msg, f"⬇️ 下載中 {done}/{total}（失敗 {counts['failed']}）")

        await asyncio.gather(*(one(i) for i in scan.items))
        return counts['ok'], counts['skipped'], counts['failed']

    async def _take_screenshots(self, scan: ProfileScan, shot_dir: str, msg):
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return 0, 0, "未安裝 playwright：pip install playwright && playwright install chromium"

        os.makedirs(shot_dir, exist_ok=True)
        cookies = await asyncio.get_event_loop().run_in_executor(None, _load_cookies)
        ids = scan.media_post_ids
        sem = asyncio.Semaphore(MAX_CONCURRENT_SCREENSHOTS)
        counts = {'ok': 0, 'failed': 0}
        last_edit = [0.0]

        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
            except Exception as e:
                return 0, 0, f"無法啟動 Chromium，請執行 playwright install chromium（{str(e)[:80]}）"
            context = await browser.new_context(
                viewport={'width': 800, 'height': 1200}, color_scheme='light',
                device_scale_factor=2, locale='zh-TW',
            )
            if cookies:
                await context.add_cookies(cookies)

            async def one(tweet_id: int):
                path = os.path.join(shot_dir, f"{tweet_id}.png")
                if os.path.exists(path):
                    counts['ok'] += 1
                    return
                async with sem:
                    page = await context.new_page()
                    try:
                        await page.goto(f"https://x.com/{scan.username}/status/{tweet_id}",
                                        wait_until='domcontentloaded', timeout=45000)
                        tweet = page.locator('article[data-testid="tweet"]').first
                        await tweet.wait_for(timeout=30000)
                        await page.wait_for_timeout(1500)  # let images settle
                        await tweet.screenshot(path=path)
                        counts['ok'] += 1
                    except Exception as e:
                        logger.warning(f"截圖失敗 {tweet_id}: {e}")
                        counts['failed'] += 1
                    finally:
                        await page.close()
                now = time.time()
                if now - last_edit[0] > 3:
                    last_edit[0] = now
                    await _safe_edit(
                        msg, f"📸 截圖中 {counts['ok'] + counts['failed']}/{len(ids)}（失敗 {counts['failed']}）"
                    )

            await asyncio.gather(*(one(t) for t in ids))
            await browser.close()
        return counts['ok'], counts['failed'], None


# ─── helpers ─────────────────────────────────────────────────────────────────

def _fetch(url: str, path: str) -> None:
    tmp = path + '.part'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, 'wb') as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)
    os.replace(tmp, path)


def _load_cookies() -> Optional[list]:
    """Read X cookies from the browser (same source gallery-dl uses) for Playwright."""
    try:
        from yt_dlp.cookies import extract_cookies_from_browser
        jar = extract_cookies_from_browser(COOKIE_BROWSER)
    except Exception as e:
        logger.warning(f"讀取瀏覽器 cookies 失敗: {e}")
        return None
    return [
        {'name': c.name, 'value': c.value, 'domain': c.domain, 'path': c.path or '/',
         'secure': bool(c.secure)}
        for c in jar if c.domain.lstrip('.') in ('x.com', 'twitter.com')
        or c.domain.endswith(('.x.com', '.twitter.com'))
    ]


async def _safe_edit(msg, text: str) -> None:
    try:
        await msg.edit_text(text)
    except Exception:
        pass

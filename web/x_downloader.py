"""
web/x_downloader.py — Download videos from X (Twitter) via yt-dlp.

Flow:
  1. start_flow()  — fetch metadata, store pending_url, show folder keyboard
  2. download()    — called after folder confirmed; download, pHash, dedup, DB record
"""

import asyncio
import logging
import os
import sys
import time
import uuid

logger = logging.getLogger(__name__)

# Ensure the project root is importable (for src.phasher, src.database)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


class XDownloader:

    # ─── metadata ────────────────────────────────────────────────────────────

    async def get_info(self, url: str) -> dict | None:
        """Fetch post metadata without downloading (runs in a thread)."""
        import yt_dlp

        opts = {'quiet': True, 'no_warnings': True, 'cookiesfrombrowser': ('firefox',)}
        loop = asyncio.get_event_loop()

        def _extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            return await loop.run_in_executor(None, _extract)
        except Exception as e:
            logger.error(f"X 影片資訊獲取失敗: {e}")
            return None

    # ─── step 1: show info + folder picker ───────────────────────────────────

    async def start_flow(self, url: str, user_id: int, processing_msg, folder_navigator) -> None:
        """Fetch metadata, attach pending_url to NavigationState, show folder keyboard."""
        await processing_msg.edit_text("🔍 正在獲取 X 貼文資訊...")

        info = await self.get_info(url)
        if not info:
            await processing_msg.edit_text("❌ 無法獲取影片資訊，請確認網址是否正確或貼文是否包含影片")
            return

        # X posts: 'description' holds the tweet text; fall back to 'title'
        description = info.get('description') or info.get('title') or ''
        uploader = info.get('uploader') or info.get('uploader_id') or 'Unknown'
        duration = info.get('duration') or 0
        filesize = info.get('filesize') or info.get('filesize_approx') or 0

        # Trim long tweet text for display
        preview = description[:80] + ('…' if len(description) > 80 else '')
        duration_str = f"{int(duration) // 60}:{int(duration) % 60:02d}" if duration else "未知"
        size_str = f"{filesize / (1024 ** 2):.1f} MB" if filesize else "未知"

        # Set pending_url BEFORE start_folder_selection (doesn't reset these fields)
        state = folder_navigator.get_user_state(user_id)
        state.pending_url = url
        state.url_type = 'x'

        nav_text, markup = folder_navigator.start_folder_selection(user_id, [], {})

        # Re-assert after start_folder_selection as a safety measure
        state = folder_navigator.get_user_state(user_id)
        state.pending_url = url
        state.url_type = 'x'

        info_text = (
            f"🐦 @{uploader}\n"
            f"{preview}\n"
            f"⏱ 時長: {duration_str}  📦 大小: {size_str}\n\n"
            f"{nav_text}"
        )
        await processing_msg.edit_text(info_text, reply_markup=markup)

    # ─── step 2: download after folder confirmed ──────────────────────────────

    async def download(self, url: str, dest_dir: str, processing_msg) -> None:
        """
        Download the video, compute pHash as file_unique_id, check for duplicates,
        and record in the database.
        """
        import yt_dlp
        from src.phasher import get_video_phash_from_path
        from src.database import DatabaseManager

        os.makedirs(dest_dir, exist_ok=True)

        uid = uuid.uuid4().hex[:8]
        outtmpl = os.path.join(dest_dir, f'x_{uid}.%(ext)s')

        loop = asyncio.get_event_loop()
        last_edit = [0.0]

        def _progress_hook(d):
            if d['status'] != 'downloading':
                return
            now = time.time()
            if now - last_edit[0] < 3:
                return
            last_edit[0] = now

            downloaded = d.get('downloaded_bytes', 0) or 0
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            speed = d.get('speed') or 0

            if total:
                pct = downloaded / total * 100
                speed_mb = speed / (1024 ** 2)
                text = f"⬇️ 下載中: {pct:.1f}%  速度: {speed_mb:.1f} MB/s"
            else:
                text = f"⬇️ 已下載: {downloaded / (1024 ** 2):.1f} MB"

            asyncio.run_coroutine_threadsafe(_safe_edit(processing_msg, text), loop)

        opts = {
            'outtmpl': outtmpl,
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [_progress_hook],
            'cookiesfrombrowser': ('firefox',),
        }

        error: list = [None]

        def _do_download():
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
            except Exception as e:
                error[0] = e

        await loop.run_in_executor(None, _do_download)

        if error[0]:
            await processing_msg.edit_text(f"❌ 下載失敗: {error[0]}")
            return

        # Locate output file via UUID suffix
        matches = [
            os.path.join(dest_dir, f)
            for f in os.listdir(dest_dir)
            if uid in f
        ]
        if not matches:
            await processing_msg.edit_text("❌ 下載完成但找不到輸出檔案")
            return

        file_path = max(matches, key=os.path.getsize)
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)

        # ── pHash → file_unique_id ──
        await processing_msg.edit_text("🔢 正在計算影片指紋...")
        try:
            phash = await loop.run_in_executor(
                None, lambda: get_video_phash_from_path(file_path)
            )
        except Exception as e:
            logger.warning(f"pHash 計算失敗: {e}")
            phash = None

        file_unique_id = phash if phash else f"x_{file_size}_{abs(hash(url))}"

        # ── Duplicate check ──
        db = DatabaseManager()
        if phash and db.is_file_downloaded(file_unique_id):
            existing = db.get_downloaded_file_info(file_unique_id)
            existing_path = existing.get('file_path', '未知') if existing else '未知'
            try:
                os.remove(file_path)
            except Exception:
                pass
            await processing_msg.edit_text(
                f"⚠️ 此影片已於之前下載過\n📁 檔案位置: {existing_path}"
            )
            return

        # ── Record in DB ──
        db.record_download(
            file_unique_id=file_unique_id,
            file_id=url,
            message_id=0,
            chat_id=0,
            file_name=file_name,
            file_path=file_path,
            original_file_name=file_name,
            file_size=file_size,
            file_type='video',
            mime_type='video/mp4',
        )

        await processing_msg.edit_text(
            f"✅ 下載完成！\n"
            f"📄 {file_name}\n"
            f"📦 {file_size / (1024 ** 2):.1f} MB\n"
            f"📁 {dest_dir}"
        )


async def _safe_edit(msg, text: str) -> None:
    try:
        await msg.edit_text(text)
    except Exception:
        pass

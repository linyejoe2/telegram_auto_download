"""
web/url_parser.py — URL detection and dispatch to site-specific downloaders.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Generic URL detector
_URL_RE = re.compile(r'https?://\S+', re.IGNORECASE)

# YouTube patterns (youtube.com/watch, /shorts, /embed, youtu.be)
_YOUTUBE_RE = re.compile(
    r'https?://(www\.)?(youtube\.com/(watch|shorts|embed|v)/|youtu\.be/)[\w\-]',
    re.IGNORECASE
)

# X / Twitter patterns (x.com or twitter.com .../status/...)
_X_RE = re.compile(
    r'https?://(www\.)?(x\.com|twitter\.com)/[^/\s]+/status/\d+',
    re.IGNORECASE
)


def extract_url(text: str) -> Optional[str]:
    """Return the first HTTP(S) URL found in text, or None."""
    if not text:
        return None
    m = _URL_RE.search(text)
    return m.group(0).rstrip('.,)') if m else None


def detect_type(url: str) -> Optional[str]:
    """Return a downloader type string, or None if unsupported."""
    if _YOUTUBE_RE.match(url):
        return 'youtube'
    if _X_RE.match(url):
        return 'x'
    return None


async def handle_url(url: str, url_type: str, user_id: int, processing_msg, folder_navigator) -> bool:
    """
    Start the download flow for a detected URL:
      1. Fetch metadata from the appropriate downloader
      2. Store pending_url on the navigation state
      3. Show the folder-selection keyboard

    Returns True if handled, False otherwise.
    """
    if url_type == 'youtube':
        from .youtube_downloader import YouTubeDownloader
        await YouTubeDownloader().start_flow(url, user_id, processing_msg, folder_navigator)
        return True

    if url_type == 'x':
        from .x_downloader import XDownloader
        await XDownloader().start_flow(url, user_id, processing_msg, folder_navigator)
        return True

    await processing_msg.edit_text("❌ 不支援的連結類型，目前支援 YouTube 及 X (Twitter)")
    return False


async def download_confirmed(
    user_id: int,
    url: str,
    url_type: str,
    processing_msg,
    folder_navigator,
) -> None:
    """
    Called after the user confirms the destination folder.
    Delegates to the appropriate site-specific downloader.
    """
    selected_path = folder_navigator.get_selected_path(user_id)

    if url_type == 'youtube':
        from .youtube_downloader import YouTubeDownloader
        await YouTubeDownloader().download(url, selected_path, processing_msg)
    elif url_type == 'x':
        from .x_downloader import XDownloader
        await XDownloader().download(url, selected_path, processing_msg)
    else:
        await processing_msg.edit_text(f"❌ 不支援的下載類型: {url_type}")

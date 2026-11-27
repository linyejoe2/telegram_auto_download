"""Description text of a downloaded post / video (v3.10.0).

Telegram downloads store the message text as the file's 描述 (`description` in the sidecar). The same is
done for X, Pornhub and YouTube: `from_info()` takes it from yt-dlp's info dict, and X account downloads use
the tweet text gallery-dl reports (`content`). `DownloadRecords.record_download(description=...)` writes it.
"""
import re

# X adds the post's own media link (https://t.co/...) at the end of the text
_TRAILING_TCO = re.compile(r'(?:\s*https?://t\.co/\w+)+\s*$')


def clean(text) -> str:
    return _TRAILING_TCO.sub('', str(text or '')).strip()


def from_info(info) -> str:
    """The video's description from a yt-dlp info dict, else its title ('' when neither); for a playlist
    (an X post with several videos) the first entry that has one."""
    if not isinstance(info, dict):
        return ''
    candidates = [info] + [e for e in (info.get('entries') or []) if isinstance(e, dict)]
    for key in ('description', 'title'):
        for d in candidates:
            text = clean(d.get(key))
            if text:
                return text
    return ''

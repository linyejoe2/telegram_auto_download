"""
Telegram Auto Download Bot - Source Package

This package contains the modular components of the Telegram media download bot:
- bot.py: Main bot logic and message handling
- downloader.py: Media download functionality with concurrent processing
- monitor.py: Real-time monitoring and progress tracking
"""

from .bot import TelegramMediaBot
from .downloader import MediaDownloader
from .monitor import DownloadMonitor

__version__ = "0.2.1"
__all__ = ["TelegramMediaBot", "MediaDownloader", "DownloadMonitor"]
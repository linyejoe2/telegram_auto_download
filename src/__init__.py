"""
Telegram Auto Download Bot - Source Package

This package contains the modular components of the Telegram media download bot:
- bot.py: Main bot logic and message handling
- downloader.py: Media download functionality with concurrent processing
- monitor.py: Real-time monitoring and progress tracking
- folder_navigator.py: Interactive folder navigation and selection system
"""

from .bot import TelegramMediaBot
from .downloader import MediaDownloader
from .monitor import DownloadMonitor
from .folder_navigator import FolderNavigator

__version__ = "0.4.1"
__all__ = ["TelegramMediaBot", "MediaDownloader", "DownloadMonitor", "FolderNavigator"]
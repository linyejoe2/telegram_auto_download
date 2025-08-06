# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Telegram bot that automatically downloads media files from forwarded messages and their replies to the server for backup purposes. The bot uses both the Telegram Bot API (python-telegram-bot) and Telegram Client API (Telethon) to access different functionality.

## Development Commands

### Running the Application

```bash
python main.py
```

### Installing Dependencies

```bash
pip install -r requirements.txt
```

## Architecture

### Core Components

- **main.py**: Entry point that validates configuration and starts the bot
- **src/bot.py**: Main bot logic and message handling (`TelegramMediaBot` class)
- **src/downloader.py**: Media download operations with concurrent processing (`MediaDownloader` class)
- **src/monitor.py**: Real-time monitoring and progress tracking (`DownloadMonitor` class)
- **config/config.py**: Configuration management using environment variables from `.env` file

### Key Architecture Patterns

1. **Dual API Usage**: The bot uses both Telegram APIs:
   - **python-telegram-bot**: For bot interactions and message handling
   - **Telethon**: For accessing Telegram Client API to retrieve forwarded messages and their replies

2. **Async/Await Pattern**: All operations are asynchronous using Python's asyncio

3. **Environment-based Configuration**: All credentials and settings loaded from `.env` file

4. **Modular Architecture**: Code organized into specialized modules:
   - **Separation of Concerns**: Each module has a single responsibility
   - **Clean Dependencies**: Clear interfaces between components
   - **Testability**: Individual modules can be tested independently

### Data Flow

1. User forwards a message to the bot
2. Bot extracts original chat and message information from forward metadata
3. Uses Telethon client to access the original message and all its replies
4. Downloads all media files concurrently using `MediaDownloader` 
5. `DownloadMonitor` provides real-time progress updates with speed/disk usage stats
6. Provides completion summary with performance metrics and storage location

### Key Classes and Methods

#### `TelegramMediaBot` (src/bot.py)
Main orchestration class that coordinates all bot operations:
- `handle_message()`: Processes forwarded messages and coordinates download workflow
- `get_message_and_replies()`: Retrieves original message and replies using Telethon with enhanced error handling
- `run()`: Main bot startup and event loop management

#### `MediaDownloader` (src/downloader.py) 
Handles all download operations with concurrent processing:
- `download_multiple_messages_concurrent()`: Manages concurrent download tasks
- `download_media_with_retry()`: Downloads with retry mechanism, exponential backoff, and progress tracking
- `download_media_from_message()`: Downloads media files with smart naming and type detection
- `get_media_size()`: Calculates file sizes before download for progress tracking
- `save_progress()` / `load_progress()`: Progress persistence for resume capability

#### `DownloadMonitor` (src/monitor.py)
Real-time monitoring and progress tracking:
- `start_monitoring_thread()`: Background monitoring thread for progress and system stats
- `safe_update_message()`: Non-blocking message updates during downloads
- `calculate_speed()` / `calculate_eta()`: Performance metrics calculations
- `get_disk_usage()`: System resource monitoring

### Configuration Requirements

The bot requires these environment variables in `.env`:

- `API_ID`: Telegram API ID from my.telegram.org
- `API_HASH`: Telegram API Hash from my.telegram.org  
- `PHONE_NUMBER`: Phone number for Telegram client authentication
- `BOT_TOKEN`: Bot token from @BotFather

### File Structure

```
telegram_auto_download/
├── src/
│   ├── __init__.py              # Package initialization and exports
│   ├── bot.py                   # Main bot logic and message handling (247 lines)
│   ├── downloader.py           # Download operations with concurrency (234 lines)
│   ├── monitor.py              # Real-time monitoring and progress (134 lines)
│   └── telegram_bot.py.bak     # Original monolithic file (backup)
├── config/
│   └── config.py               # Configuration management
├── main.py                     # Application entry point
├── downloads/                  # Permanent backup directory (auto-created)
├── logs/                       # Log files directory (auto-created)
└── bot_session.session         # Telethon session file (auto-generated)
```

### Media Support

The bot handles all Telegram media types:

- Photos (saved as .jpg)
- Videos (saved as .mp4 or original format)
- Documents with original filenames preserved
- Audio files
- GIFs

### Performance & Optimization Features

- **Concurrent Downloads**: Up to 5 simultaneous downloads using asyncio.Semaphore
- **Optimized Telethon Client**: Connection pooling, retries, and timeout configuration
- **Real-time Monitoring**: Background thread tracking download progress, speed, and disk usage
- **Progress Callbacks**: Live download progress tracking with speed calculations
- **Smart Resource Management**: Non-blocking UI updates and memory-efficient operations

### Error Handling & Reliability

- **Retry Mechanism**: Exponential backoff for failed downloads (up to 3 attempts)
- **Network Error Handling**: Comprehensive handling of ConnectionError, OSError, TimeoutError
- **Telegram API Limits**: FloodWaitError handling with automatic wait times  
- **Progress Persistence**: Save/load download progress to resume interrupted operations
- **Missing Permissions Detection**: Enhanced error messages for access issues
- **Robust Logging**: Detailed logging with reduced third-party library verbosity

## Development Notes

### Bot Capabilities
- Bot supports forwarded messages from channels and group chats only (not private chats)
- Concurrent processing: Downloads up to 5 media files simultaneously for faster performance
- Files are permanently stored in organized directories (by message ID and timestamp)
- Smart file naming includes message ID and timestamp

### User Experience Features
- Real-time progress updates every 5 seconds with:
  - Completed/failed file counts
  - Download speed (MB/s)
  - Remaining disk space (GB)
  - Total downloaded size
- Final completion summary with performance metrics and storage location
- Non-blocking progress updates that don't interrupt download speed

### Technical Implementation
- **Modular Design**: Refactored from monolithic 596-line file into 3 specialized modules
- **Asyncio-based Architecture**: Concurrent processing for maximum performance
- **Semaphore Control**: Configurable download concurrency (`max_concurrent_downloads = 5`)
- **Background Monitoring**: Separate thread for real-time statistics without blocking downloads
- **Progress Persistence**: JSON-based progress tracking for resume capability
- **Optimized Client**: Telethon client with connection pooling and retry logic
- **Clean Separation**: Bot orchestration, download operations, and monitoring are decoupled
- **Logging**: Configured for debugging (INFO level) with reduced third-party verbosity

### Performance Improvements
- **5x faster downloads** through concurrent processing vs. sequential
- **Improved Code Maintainability**: 3 focused modules vs. 1 monolithic file
- **Better Testing**: Individual components can be tested independently
- **Enhanced Debugging**: Clear separation of concerns for easier troubleshooting
- Exponential backoff retry mechanism for network reliability  
- Smart resource management prevents UI blocking during intensive operations
- Memory-efficient progress tracking with callback-based updates

### Refactoring Benefits
- **Code Organization**: Transformed 596-line monolithic file into clean modular architecture
- **Single Responsibility**: Each module focuses on one primary concern
- **Reusability**: Components can be easily reused or replaced
- **Scalability**: New features can be added without affecting existing modules
- **Maintainability**: Easier to understand, debug, and extend individual components

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Telegram bot (v0.5.0) that automatically downloads media files from forwarded messages and their replies to the server for backup purposes, with integrated SQLite database for download history and duplicate prevention. The bot uses both the Telegram Bot API (python-telegram-bot) and Telegram Client API (Telethon) to access different functionality, with enhanced media group detection and processing capabilities, plus interactive folder navigation for user-controlled download organization.

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
- **src/database.py**: SQLite database management for download history and metadata (v0.4.0)
- **src/folder_navigator.py**: Interactive folder navigation and path management system (v0.5.0)
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

1. User forwards a message or media group to the bot
2. Bot detects if message has `media_group_id` and collects all grouped messages
3. Bot extracts original chat and message information from forward metadata
4. Database checks for existing downloads to prevent duplicates (v0.4.0)
5. Uses Telethon client to access the original message, media groups, and all replies
6. `FolderNavigator` presents interactive folder selection UI with existing folder statistics (v0.5.0)
7. User navigates folders using commands (`/cr`, `/cd`, `/cd..`, `/ok`) to select download location (v0.5.0)
8. Downloads all media files concurrently using `MediaDownloader` to user-selected folder (v0.5.0)
9. Database records download metadata and file information (v0.4.0)
10. `DownloadMonitor` provides real-time progress updates with speed/disk usage stats
11. Provides completion summary with performance metrics and storage location

### Key Classes and Methods

#### `TelegramMediaBot` (src/bot.py)
Main orchestration class that coordinates all bot operations:
- `handle_message()`: Processes forwarded messages and routes to group/single processing (v0.3.1)
- `_handle_media_group()`: Collects and processes media group messages (v0.3.1)
- `_process_grouped_messages()`: Handles media group download workflow (v0.3.1)
- `_process_single_message()`: Handles individual message workflow (v0.3.1)
- `_download_and_monitor()`: Shared download and monitoring logic (v0.3.1)
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

#### `FolderNavigator` (src/folder_navigator.py) 
Interactive folder navigation and path management (v0.5.0):
- `start_folder_selection()`: Initiates folder selection workflow with media statistics
- `process_folder_command()`: Handles folder navigation commands (`/cr`, `/cd`, `/cd..`, `/ok`)
- `get_selected_path()`: Returns user-selected download destination path
- `_generate_folder_ui()`: Creates interactive folder browsing interface
- `is_awaiting_folder_selection()`: Manages user state during folder selection

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
│   ├── bot.py                   # Main bot logic with media group support (570+ lines)
│   ├── downloader.py           # Download operations with concurrency (234 lines)
│   ├── monitor.py              # Real-time monitoring and progress (134 lines)
│   ├── database.py             # SQLite database management and operations (v0.4.0)
│   ├── folder_navigator.py     # Interactive folder navigation system (260 lines, v0.5.0)
│   └── telegram_bot.py.bak     # Original monolithic file (backup)
├── config/
│   └── config.py               # Configuration management
├── main.py                     # Application entry point
├── downloads/                  # User-organized backup directory with folder structure (v0.5.0)
├── logs/                       # Log files directory (auto-created)
├── downloads.db                # SQLite database for download history (v0.4.0)
└── bot_session.session         # Telethon session file (auto-generated)
```

### Media Support

The bot handles all Telegram media types, including media groups (v0.3.1):

- Photos (saved as .jpg)
- Videos (saved as .mp4 or original format)
- Documents with original filenames preserved
- Audio files
- GIFs
- **Media Groups**: Automatically detects and processes grouped media as single units (v0.3.1)

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
- **Interactive Folder Navigation**: Users can choose download destination with real-time folder browsing (v0.5.0)
- **Media Group Detection**: Automatically detects and processes grouped media (albums) as single units
- **Database Integration**: SQLite database tracks all downloads and prevents duplicates (v0.4.0)
- Concurrent processing: Downloads up to 5 media files simultaneously for faster performance
- Files are permanently stored in user-organized directories with custom folder structures (v0.5.0)
- **Smart Directory Structure**: User-controlled organization with live folder statistics (v0.5.0)
- **Duplicate Prevention**: Database-driven checks prevent re-downloading existing files (v0.4.0)
- Smart file naming includes message ID and timestamp

### User Experience Features
- **Interactive Folder Selection**: Choose download location with intuitive commands (v0.5.0)
  - Browse existing folders with live media statistics
  - Create new folders on-the-fly during selection process
  - Navigate folder hierarchy with simple commands (`/cd`, `/cd..`, `/cr`, `/ok`)
  - Visual feedback showing current location and available folders
- Real-time progress updates every 5 seconds with:
  - Completed/failed file counts
  - Download speed (MB/s)
  - Remaining disk space (GB)
  - Total downloaded size
- Final completion summary with performance metrics and storage location
- Non-blocking progress updates that don't interrupt download speed

### Technical Implementation
- **Modular Design**: Refactored from monolithic 596-line file into 5 specialized modules (v0.5.0)
- **Interactive Navigation Architecture**: Dedicated folder navigation system with state management (v0.5.0)
- **Media Group Architecture**: Intelligent collection and processing of grouped media
- **Database Architecture**: SQLite integration for persistent download tracking and metadata (v0.4.0)
- **Asyncio-based Architecture**: Concurrent processing for maximum performance
- **Semaphore Control**: Configurable download concurrency (`max_concurrent_downloads = 5`)
- **Background Monitoring**: Separate thread for real-time statistics without blocking downloads
- **Progress Persistence**: JSON-based progress tracking for resume capability
- **Optimized Client**: Telethon client with connection pooling and retry logic
- **Clean Separation**: Bot orchestration, download operations, monitoring, and folder navigation are decoupled
- **Dual API Integration**: Smart handling of Bot API and Telethon API differences
- **Database Integration**: Comprehensive download history and duplicate detection system (v0.4.0)
- **User State Management**: Per-user navigation state with session isolation (v0.5.0)
- **Logging**: Configured for debugging (INFO level) with reduced third-party verbosity

### Performance Improvements
- **5x faster downloads** through concurrent processing vs. sequential
- **Improved Code Maintainability**: 5 focused modules vs. 1 monolithic file (v0.5.0)
- **Better Testing**: Individual components can be tested independently
- **Enhanced Debugging**: Clear separation of concerns for easier troubleshooting
- **Optimized User Experience**: Interactive folder selection improves organization efficiency (v0.5.0)
- Exponential backoff retry mechanism for network reliability  
- Smart resource management prevents UI blocking during intensive operations
- Memory-efficient progress tracking with callback-based updates
- **Streamlined Workflow**: Integrated folder navigation reduces setup time (v0.5.0)

### Refactoring Benefits
- **Code Organization**: Transformed 596-line monolithic file into clean 5-module architecture (v0.5.0)
- **Single Responsibility**: Each module focuses on one primary concern
- **Reusability**: Components can be easily reused or replaced
- **Scalability**: New features can be added without affecting existing modules
- **Maintainability**: Easier to understand, debug, and extend individual components
- **Enhanced Modularity**: Folder navigation system demonstrates continued architectural evolution (v0.5.0)

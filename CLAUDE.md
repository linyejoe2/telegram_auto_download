# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Telegram bot (v1.0.0) that automatically downloads media files from forwarded messages and their replies to the server for backup purposes, with integrated SQLite database for download history and duplicate prevention. The bot features an interactive folder navigation system for organized downloads and uses both the Telegram Bot API (python-telegram-bot) and Telegram Client API (Telethon) to access different functionality, with enhanced media group detection and processing capabilities.

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
- **src/folder_navigator.py**: Interactive folder navigation and management system (`FolderNavigator` class) (v1.0.0)
- **src/database.py**: SQLite database management for download history and metadata (v0.4.0)
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

### Data Flow (v1.0.0 Simplified Architecture)

1. **Command Check**: User forwards a message or uses folder navigation commands (`/cr`, `/cd`, `/ok`)
2. **Downloadable Check**: Bot validates forwarded messages and rejects private chats
3. **Extract All Files**: Bot collects media from original message, media groups, and all replies
4. **Folder Selection**: Interactive folder navigation system lets users choose organized storage location
5. **Download Process**: Unified download workflow handles all collected media with concurrent processing

**Detailed Flow:**

- Bot detects if message has `media_group_id` and collects all grouped messages
- Bot extracts original chat and message information from forward metadata  
- Database checks for existing downloads to prevent duplicates (v0.4.0)
- Uses Telethon client to access the original message, media groups, and all replies
- `FolderNavigator` provides interactive folder selection with visual tree display (v1.0.0)
- Downloads all media files concurrently using `MediaDownloader`
- Database records download metadata and file information (v0.4.0)
- `DownloadMonitor` provides real-time progress updates with speed/disk usage stats
- Provides completion summary with performance metrics and storage location

### Key Classes and Methods

#### `TelegramMediaBot` (src/bot.py) - v1.0.0 Simplified Architecture

Main orchestration class with streamlined linear processing flow:

- `handle_message()`: Unified entry point with simplified 5-step flow (command → downloadable → extract → folder → download)
- `_handle_commands()`: Processes folder navigation and system commands
- `_is_downloadable_message()`: Validates forwarded messages and rejects private chats
- `_process_message()`: Unified processing for both individual and grouped messages
- `_extract_all_files()`: Centralized file collection from original + media groups + replies
- `_extract_forward_info()`: Helper method for extracting forward message metadata
- `_count_media_types()`: Helper method for media type statistics
- `_process_confirmed_download()`: Unified download processing (replaces separate group/single methods)
- `get_message_and_replies()`: Retrieves original message and replies using Telethon with enhanced error handling
- `run()`: Main bot startup and event loop management

#### `FolderNavigator` (src/folder_navigator.py) - v1.0.0 New Feature

Interactive folder navigation and management system:

- `start_folder_selection()`: Initiates folder selection workflow with media preview
- `process_folder_command()`: Handles navigation commands (`/cr`, `/cd`, `/cd..`, `/ok`)
- `is_folder_command()`: Validates folder navigation command syntax
- `get_selected_path()`: Returns user's confirmed download path
- `create_folder_display()`: Generates visual folder tree with breadcrumb navigation
- `clear_user_state()`: Cleanup method for user session management

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
│   ├── bot.py                   # Main bot logic with simplified architecture (513 lines, v1.0.0)
│   ├── folder_navigator.py      # Interactive folder navigation system (v1.0.0)
│   ├── downloader.py           # Download operations with concurrency (234 lines)
│   ├── monitor.py              # Real-time monitoring and progress (134 lines)
│   ├── database.py             # SQLite database management and operations (v0.4.0)
│   └── telegram_bot.py.bak     # Original monolithic file (backup)
├── config/
│   └── config.py               # Configuration management
├── main.py                     # Application entry point
├── downloads/                  # Permanent backup directory (auto-created)
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
- **Interactive Folder Navigation**: Users can organize downloads with custom folder structures (v1.0.0)
- **Media Group Detection**: Automatically detects and processes grouped media (albums) as single units
- **Database Integration**: SQLite database tracks all downloads and prevents duplicates (v0.4.0)
- **Simplified Processing Flow**: Clean 5-step linear architecture (command → downloadable → extract → folder → download) (v1.0.0)
- Concurrent processing: Downloads up to 5 media files simultaneously for faster performance
- Files are permanently stored in organized directories (by message ID and timestamp)
- **Smart Directory Structure**: Media groups stored in `mediagroup_{id}_{timestamp}` directories
- **Duplicate Prevention**: Database-driven checks prevent re-downloading existing files (v0.4.0)
- Smart file naming includes message ID and timestamp

### User Experience Features

- **Interactive Folder Selection**: Visual folder tree with breadcrumb navigation and command-based organization (v1.0.0)
- **Media Preview**: Shows file counts (photos, videos, documents) before folder selection (v1.0.0)
- Real-time progress updates every 5 seconds with:
  - Completed/failed file counts
  - Download speed (MB/s)
  - Remaining disk space (GB)
  - Total downloaded size
- Final completion summary with performance metrics and storage location
- Non-blocking progress updates that don't interrupt download speed
- **User Session Management**: Tracks pending downloads and navigation state per user (v1.0.0)

### Technical Implementation

- **Modular Design**: Evolved from monolithic file into 4 specialized modules (bot, downloader, monitor, folder_navigator)
- **Simplified Architecture**: Linear 5-step processing flow eliminates complex branching logic (v1.0.0)
- **Interactive Navigation**: Complete folder management system with user session tracking (v1.0.0)
- **Media Group Architecture**: Intelligent collection and processing of grouped media
- **Database Architecture**: SQLite integration for persistent download tracking and metadata (v0.4.0)
- **Asyncio-based Architecture**: Concurrent processing for maximum performance
- **Semaphore Control**: Configurable download concurrency (`max_concurrent_downloads = 5`)
- **Background Monitoring**: Separate thread for real-time statistics without blocking downloads
- **Progress Persistence**: JSON-based progress tracking for resume capability
- **Optimized Client**: Telethon client with connection pooling and retry logic
- **Clean Separation**: Bot orchestration, download operations, monitoring, and navigation are decoupled
- **Dual API Integration**: Smart handling of Bot API and Telethon API differences
- **Database Integration**: Comprehensive download history and duplicate detection system (v0.4.0)
- **Logging**: Configured for debugging (INFO level) with reduced third-party verbosity

### Performance Improvements

- **5x faster downloads** through concurrent processing vs. sequential
- **Improved Code Maintainability**: 4 focused modules vs. 1 monolithic file (v1.0.0)
- **Simplified Processing Flow**: Linear 5-step architecture reduces complexity and improves debugging (v1.0.0)
- **Better Testing**: Individual components can be tested independently
- **Enhanced Debugging**: Clear separation of concerns for easier troubleshooting
- Exponential backoff retry mechanism for network reliability  
- Smart resource management prevents UI blocking during intensive operations
- Memory-efficient progress tracking with callback-based updates
- **User Experience Optimization**: Interactive folder selection improves organization efficiency (v1.0.0)

### Refactoring Benefits (v1.0.0)

- **Code Architecture**: Evolved from monolithic file into clean 4-module architecture with linear processing flow
- **Single Responsibility**: Each module and method focuses on one primary concern
- **Elimination of Duplication**: Consolidated helper methods reduce code repetition by ~200 lines
- **Reusability**: Components can be easily reused or replaced
- **Scalability**: New features can be added without affecting existing modules
- **Maintainability**: Easier to understand, debug, and extend individual components
- **Interactive Features**: New folder navigation system enhances user control and organization

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Telegram bot (v2.7.5) that automatically downloads media files from forwarded messages and their replies to the server for backup purposes. Features a professional GUI application with Windows installer, SQLite database for download history and duplicate prevention, inline-keyboard folder navigation with path history, and uses both Telegram Bot API (python-telegram-bot) and Telegram Client API (Telethon) for comprehensive functionality.

## Development Commands

### Running the Application

```bash
# GUI Mode (default on Windows)
python main.py

# CLI Mode (explicit)
python main.py --cli

# GUI Mode (explicit)
python main.py --gui
```

### Building Windows Installer

```bash
# Complete build process (requires Python 3.8+ and Inno Setup)
package_windows.bat
```

### Installing Dependencies

```bash
pip install -r requirements.txt
```

### Version Management

Use the `/update-release <version> <changes>` command (`.claude/commands/update-release.md`): it bumps the version in `app.manifest`, `installer.iss`, `package_windows.bat`, `create_version_info.py`, `src/__init__.py`, `src/ui.py`, `README.md` and this file, then updates the docs.

### Build Environment Setup

```bash
# Setup build environment for Windows packaging
setup_build_env.bat
```

## Architecture

### Core Components

### GUI Application Components
- **src/ui.py**: Main GUI application with tkinter interface and system tray integration (v1.0.0, migrated to src/ in v1.3.0)
- **src/chromium_helper.py**: Chromium check/install for screenshots (`check_chromium()`, `install_chromium()` via Playwright's bundled node driver, `ensure_browsers_path()` pins `PLAYWRIGHT_BROWSERS_PATH` to `%LOCALAPPDATA%\ms-playwright` on Windows, v2.5.0)
- **src/auth_helper.py**: GUI and console authentication helper for Telethon client (v1.0.0)

### Core Bot Components
- **main.py**: Unified entry point supporting both CLI and GUI modes with command-line arguments
- **src/bot.py**: Main bot logic and message handling (`TelegramMediaBot` class)
- **src/downloader.py**: Media download operations with concurrent processing (`MediaDownloader` class)
- **src/monitor.py**: Real-time monitoring and progress tracking (`DownloadMonitor` class)
- **src/database.py**: SQLite database management for download history and metadata
- **src/folder_navigator.py**: Interactive folder navigation and path management system
- **src/file_viewer.py**: Chat file viewer (`FileViewer`, `build_preview`, `source_link`, plus `list_videos`, `build_batch_preview`, `build_frame_preview`, `PreviewBatch` for folder video previews, v2.7.1) for `/files` (v2.7.0)
- **config/config.py**: Configuration management using environment variables from `.env` file

### URL Downloader Components (web/ package)
- **web/url_parser.py**: URL detection (`extract_url`, `detect_type`, `extract_x_username`) and dispatch (`handle_url`, `download_confirmed`); types include `youtube`, `x`, `pornhub`, `x_profile` (v2.5.0)
- **web/youtube_downloader.py**: YouTube via yt-dlp
- **web/x_downloader.py**: X/Twitter single-post video via yt-dlp with Firefox cookies
- **web/p_downloader.py**: Pornhub via yt-dlp
- **web/x_profile_downloader.py**: X account downloader (gallery-dl scan + media download + Playwright screenshots, v2.5.0)

### Windows Installer Components
- **package_windows.bat**: Complete build automation script (v1.0.0)
- **telegram_bot.spec**: PyInstaller configuration for executable creation (v1.0.0)
- **installer.iss**: Inno Setup installer configuration (v1.0.0)
- **create_version_info.py**: Version information generator for Windows executable (v1.0.0)
- **create_icon.py**: Application icon generator (v1.0.0)

### Key Architecture Patterns

1. **Dual Interface Design**: Application supports both GUI and command-line interfaces
   - **GUI Mode**: Professional Windows application with system tray integration
   - **CLI Mode**: Traditional command-line interface for advanced users and development

2. **Dual API Usage**: The bot uses both Telegram APIs:
   - **python-telegram-bot**: For bot interactions and message handling
   - **Telethon**: For accessing Telegram Client API to retrieve forwarded messages and their replies

3. **Professional Deployment**: Complete Windows installer package
   - **PyInstaller Integration**: Single executable with all dependencies bundled
   - **Inno Setup**: Professional installer with shortcuts and auto-upgrade support
   - **Build Automation**: Complete build pipeline from source to installer
   - **CI/CD Integration**: GitHub Actions for automated deployment (v1.1.0)

4. **Async/Await Pattern**: All operations are asynchronous using Python's asyncio

5. **Environment-based Configuration**: All credentials and settings loaded from `.env` file

6. **Modular Architecture**: Code organized into specialized modules:
   - **Separation of Concerns**: Each module has a single responsibility
   - **Clean Dependencies**: Clear interfaces between components
   - **Testability**: Individual modules can be tested independently

### Data Flow

1. User forwards a message or media group to the bot
2. Bot detects if message has `media_group_id` and collects all grouped messages
3. Bot extracts original chat and message information from forward metadata
4. Database checks for existing downloads to prevent duplicates (v0.4.0)
5. Uses Telethon client to access the original message, media groups, and all replies
6. `FolderNavigator` presents inline keyboard UI with subfolder buttons, up/confirm/create actions, and previous-path history (v2.1.0)
7. User navigates folders by tapping inline buttons; types a name only when creating a new folder (v2.1.0)
8. (v2.6.1) Every request goes through the per-item queue (`submit_flow`): the folder selector (step 6) appears only when it is the item's turn, so nothing downloads into a pre-chosen folder
9. Downloads all media files concurrently using `MediaDownloader` to user-selected folder (v0.5.0)
10. Database records download metadata and file information (v0.4.0)
11. `DownloadMonitor` provides real-time progress updates with speed/disk usage stats
12. Provides completion summary with performance metrics and storage location

### Key Classes and Methods

#### `TelegramMediaBot` (src/bot.py)
Main orchestration class that coordinates all bot operations:
- `start_client()`: Enhanced authentication with session validation and GUI support (v1.0.0)
- `handle_message()`: Processes forwarded messages, folder name input, and routes to group/single processing
- `handle_files_command()`: Owner-only `/files [path]` command (registered in the Telegram command menu via `set_my_commands`); `owner_id` is the Telethon session account (`get_me()`), others get "⛔ 只有 Bot 擁有者可以瀏覽檔案"; `_send_preview()` sends an image or 3 video screenshots (v2.7.0); `_send_preview_batch()` sends folder video previews as albums of 10 (1 screenshot per video, v2.7.1)
- `handle_callback_query()`: Routes inline keyboard button presses (`fn_cd`, `fn_up`, `fn_ok`, `fn_cr`, `fn_prev`) (v2.1.0); `fv_*` callbacks go to `_handle_file_viewer_callback` (owner only, v2.7.0); `xp_media` / `xp_both` / `xp_shot` (X profile mode choice) are routed to `XProfileDownloader.on_mode_chosen` before the `fn_*` guard (v2.5.0)
- `_handle_media_group()`: Collects and processes media group messages
- `_download_and_monitor()`: Shared download and monitoring logic
- `get_message_and_replies()`: Retrieves original message and replies using Telethon with enhanced error handling
- `submit_flow()` / `enqueue_flow()` / `_queue_worker()`: Serial request queue of `FlowItem`s (v2.6.1); bot keeps accepting messages during downloads, waiting items show their queue position, each item gets its own folder selector (shown only after the previous download finishes, 30-minute timeout, `❌ 取消` skips); queue is in-memory
- `_startup_scan()` / `_present_scan_unit()`: On start, checks the user's last `STARTUP_SCAN_COUNT` own messages to the bot (Telethon) against the DB and queues undownloaded channel posts/albums and X/YouTube links (X account links not scanned) (v2.6.1)
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
Inline keyboard folder navigation and path management (v2.1.0):
- `start_folder_selection()`: Initiates folder selection, returns `(text, InlineKeyboardMarkup)`
- `navigate_into(user_id, folder_index)`: Enters subfolder by button index
- `navigate_up(user_id)`: Goes up one directory level
- `navigate_to_history(user_id, history_index)`: Jumps to a previously confirmed path
- `create_folder_and_navigate(user_id, folder_name)`: Creates folder from user text input and navigates into it
- `confirm_selection(user_id)`: Confirms path, updates history (max 5 entries, most recent first)
- `get_selected_path()`: Returns absolute path of current selection
- `is_awaiting_folder_selection()` / `is_awaiting_folder_name()`: State guards for message routing
- `clear_user_state()`: Resets navigation state while preserving path history

#### `FileViewer` (src/file_viewer.py)
Inline-keyboard browser of the downloads folder for `/files` (v2.7.0):
- `start(user_id, arg)` / `handle_callback(user_id, data)`: Render list/detail/confirm views, return `ViewResult(text, markup, preview_path)`; callbacks use the `fv_` prefix: `fv_cd`, `fv_f`, `fv_up`, `fv_pv`, `fv_pva`, `fv_pn`, `fv_back`, `fv_prev`, `fv_del`, `fv_deld`, `fv_yes`, `fv_no`, `fv_close` (`fv_pg` removed in v2.7.1; `fv_f` restored in v2.7.4)
- Listing (v2.7.1, modeled on `FolderNavigator._generate_folder_ui`): no paging; all sub folders in a 2-per-row grid (names cut to 18 chars), text shows folder/video/photo/file counts + total size; empty folder offers `🗑 刪除此資料夾`; the newest `MAX_FILE_BUTTONS` (30) files of the level are listed below the folders as `fv_f:<index>` buttons (index into `state.entries` = folders + shown files) opening the detail view (also via `/files <file path>`); hidden files and `.part` hidden; all paths confined to the downloads folder (`..`, absolute paths, outside symlinks rejected)
- Folder video preview (v2.7.1): `fv_pv` (`🎞 預覽資料夾影片 (n)`, this level, shown only if it has videos) and `fv_pva` (`🎞 預覽資料夾內所有影片 (n)`, recursive, shown only if sub folders add videos); `list_videos()` collects videos, `build_batch_preview()` returns a `PreviewBatch` of up to 10, each with ONE screenshot (`build_frame_preview()`: 15s, middle frame for videos under ~16s), caption = path relative to the browsed folder + timestamp + source link; `fv_pn` (`▶️ 下一頁（剩餘 n 部）`) sends the next 10 as a new album, previous albums kept, only the control message replaced, shows `已預覽 x/y 部影片`, unreadable videos skipped and counted
- Folder photo loading (v2.7.3): `fv_ph` (`🖼 載入照片 (n)`, this level) and `fv_pha` (`🖼 載入所有照片 (n)`, recursive) reuse the `fv_pn` lazy paging; `list_photos()`/`list_media()` collect files, `build_batch_preview()` returns a thumbnail per photo (`build_image_preview()`), `ViewState.preview_kind` is `video` or `photo`
- Detail view shows size, mtime, location, video duration/resolution, download time and the source link (`source_link()`: `t.me/c/<channel>/<message>`, original YouTube/X/Pornhub URL, `x.com/i/status/<id>` for X profile downloads, "未知" if unknown); record from `DatabaseManager.find_download(file_path)` (match by path, fallback file name + size)
- `build_preview(path)` (single-file `🖼 預覽`, unchanged in v2.7.1): image -> 1 photo; video -> 3 OpenCV frames (15s, middle, 15s before end; <45s uses 10%/50%/90%), run in an executor
- Load video (v2.7.5): detail view `fv_load` -> `ViewResult.load_path` -> `TelegramMediaBot._load_video()` uploads via `upload_client` (second Telethon session `bot_upload_session` logged in with the bot token, started in `run()`; resolves the chat from updates it received) with `DocumentAttributeVideo` + thumbnail; `src/video_loader.py`: `needs_compression()` (>500 MB or >4000 kbps), `compress_video()` (ffmpeg libx265, 720p, 2000 kbps, aac 128k, progress shown in the status message), result stored as hidden `.<name>.720p_h265.mp4` (`compressed_path()`, re-used via `existing_compressed()`); needs ffmpeg in PATH or `FFMPEG_PATH` (not bundled)
- Delete with confirmation: files and empty folders only; the DB record is kept so the startup scan does not re-offer the file

#### `XProfileDownloader` (web/x_profile_downloader.py)
Downloads media and/or screenshots of a whole X account (v2.5.0):
- `start_flow(username, user_id, processing_msg)`: Scans the account with gallery-dl (in-process `gallery_dl.job.DataJob`, Firefox cookies; ~3,200 post limit; retweets excluded), replies with post/video/photo counts and the mode buttons (`xp_media`, `xp_both`, `xp_shot`)
- `on_mode_chosen(mode, user_id, message, folder_navigator)`: Stores the mode, shows the folder keyboard (`url_type = 'x_profile'`)
- `download(user_id, dest_dir, processing_msg)`: Output to `<folder>/x_<username>/` (screenshots in `screenshots/`); media concurrent (5), named `<tweetid>_<n>.<ext>`, deduped by file existence and DB id `xprofile_<tweetid>_<n>`; screenshots via Playwright Chromium (3 concurrent); posts without media are never downloaded/screenshotted
- Notes: gallery-dl must run in-process (frozen exe's `sys.executable` is the app, so `python -m gallery_dl` fails). Requires being logged in to X in Firefox. Screenshots need Chromium: use the GUI Install button (or `playwright install chromium` from source); not bundled by PyInstaller, media download works without it

#### `AuthHelper` (src/auth_helper.py)
GUI and console authentication management (v1.0.0):
- `authenticate_client()`: Main authentication function with session handling
- `check_session_exists()`: Validates existing Telethon session files
- `GUIAuthHelper`: GUI-based authentication with tkinter dialogs
- `ConsoleAuthHelper`: Fallback console authentication for development
- `get_auth_helper()`: Environment-aware authentication helper selection

### Configuration Requirements

The bot requires these environment variables in `.env`:

- `API_ID`: Telegram API ID from my.telegram.org
- `API_HASH`: Telegram API Hash from my.telegram.org  
- `PHONE_NUMBER`: Phone number for Telegram client authentication
- `BOT_TOKEN`: Bot token from @BotFather
- `STARTUP_SCAN_COUNT` (optional, v2.6.1): number of latest messages sent to the bot that are scanned at startup (default 30, 0 = off); read via `config.get_startup_scan_count()`, editable in GUI Configuration tab; `DatabaseManager.is_url_downloaded()` checks links ignoring query params
- Database (v2.7.0): `DatabaseManager.find_download(file_path)` returns the download record of a file on disk (path match, fallback file name + size so moved files are found); used by the file viewer for source links
- Security (v2.7.0): the `/files` viewer is owner-only (`TelegramMediaBot.owner_id` = Telethon session account) and confined to the downloads folder

Additional requirements for X features (v2.5.0):
- Log in to X in Firefox on the same machine (cookies are read from Firefox for X downloads and account scans)
- For X account screenshots, install Chromium once via the GUI Configuration tab > Screenshot Engine > Install (or `playwright install chromium` from source); the box shows `Chromium status` with Check/Install buttons. GUI Bot Control also has Restart Bot (Stop cancels the bot task, Start reloads `.env`)

### File Structure

```
telegram_auto_download/
├── src/
│   ├── __init__.py              # Package initialization and exports
│   ├── bot.py                   # Main bot logic with enhanced authentication (580+ lines)
│   ├── downloader.py           # Download operations with concurrency (234 lines)
│   ├── monitor.py              # Real-time monitoring and progress (134 lines)
│   ├── database.py             # SQLite database management and operations
│   ├── folder_navigator.py     # Interactive folder navigation system (260 lines)
│   ├── auth_helper.py          # GUI/console authentication helper (197 lines, v1.0.0)
│   ├── file_viewer.py          # /files chat file viewer (owner only, v2.7.0; folder video preview v2.7.1)
│   ├── chromium_helper.py      # Chromium check/install for screenshots (v2.5.0)
│   ├── ui.py                   # Main GUI application (tkinter interface, v1.3.0)
│   └── telegram_bot.py.bak     # Original monolithic file (backup)
├── web/
│   ├── __init__.py
│   ├── url_parser.py           # URL detection and dispatch
│   ├── youtube_downloader.py   # YouTube (yt-dlp)
│   ├── x_downloader.py         # X/Twitter single post (yt-dlp)
│   ├── p_downloader.py         # Pornhub (yt-dlp)
│   └── x_profile_downloader.py # X account downloader (gallery-dl + Playwright, v2.5.0)
├── config/
│   └── config.py               # Configuration management
├── main.py                     # Unified application entry point (CLI/GUI)
├── package_windows.bat         # Windows installer build script (v1.0.0)
├── setup_build_env.bat         # Build environment setup script
├── telegram_bot.spec           # PyInstaller configuration (v1.0.0)
├── installer.iss               # Inno Setup installer configuration (v1.0.0)
├── create_version_info.py      # Version info generator (v1.0.0)
├── create_icon.py              # Application icon generator (v1.0.0)
├── ChangeLog.md                # Version history and release notes
├── downloads/                  # User-organized backup directory with folder structure
├── logs/                       # Log files directory (auto-created)
├── downloads.db                # SQLite database for download history
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
- **Download Optimization**: Downloads start from smallest files for faster perceived performance (v1.2.0)
- **Optimized Telethon Client**: Connection pooling, retries, and timeout configuration
- **Real-time Monitoring**: Background thread tracking download progress, speed, and disk usage
- **Progress Callbacks**: Live download progress tracking with speed calculations
- **Smart Resource Management**: Non-blocking UI updates and memory-efficient operations
- **Skipped File Visibility**: Skipped files are now visible in the frontend (v1.1.1)

### Error Handling & Reliability

- **Enhanced Authentication**: Smart session validation and automatic cleanup of invalid sessions (v1.0.0)
- **GUI Authentication**: Robust handling of authentication in GUI environments without stdin access (v1.0.0)
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
- **Inline Keyboard Folder Selection**: Choose download location via tap-able buttons (v2.1.0)
  - Subfolder buttons displayed in a 2-per-row grid with live media statistics
  - `⬆️ 返回上級`, `✅ 確認這裡`, `📝 新建資料夾` action buttons
  - Up to 3 `🕐 /prev/path` quick-select buttons for previously used locations
  - New folder creation via a single text message — bot deletes input and updates keyboard seamlessly
- Real-time progress updates every 5 seconds with:
  - Completed/failed file counts
  - Download speed (MB/s)
  - Remaining disk space (GB)
  - Total downloaded size
- Final completion summary with performance metrics and storage location
- Non-blocking progress updates that don't interrupt download speed

### Technical Implementation
- **Professional GUI Architecture**: Complete Windows desktop application with tkinter interface (v1.0.0)
- **Windows Installer Integration**: Automated build pipeline with PyInstaller and Inno Setup (v1.0.0)
- **Dual Interface Design**: Seamless switching between GUI and command-line modes (v1.0.0)
- **Enhanced Authentication Architecture**: Robust session management with GUI/console fallback
- **Modular Design**: Refactored from monolithic 596-line file into 6 specialized modules
- **Inline Keyboard Navigation Architecture**: Button-driven folder navigation with index-based callback routing and persistent path history (v2.1.0)
- **Media Group Architecture**: Intelligent collection and processing of grouped media
- **Database Architecture**: SQLite integration for persistent download tracking and metadata
- **Asyncio-based Architecture**: Concurrent processing for maximum performance
- **Semaphore Control**: Configurable download concurrency (`max_concurrent_downloads = 5`)
- **Background Monitoring**: Separate thread for real-time statistics without blocking downloads
- **Progress Persistence**: JSON-based progress tracking for resume capability
- **Optimized Client**: Telethon client with connection pooling and retry logic
- **Clean Separation**: Bot orchestration, download operations, monitoring, authentication, and folder navigation are decoupled
- **Dual API Integration**: Smart handling of Bot API and Telethon API differences
- **Database Integration**: Comprehensive download history and duplicate detection system
- **User State Management**: Per-user navigation state with session isolation
- **Session Management**: Intelligent session validation and automatic cleanup
- **Professional Deployment**: Complete build automation and installer generation (v1.0.0)
- **Logging**: Configured for debugging (INFO level) with reduced third-party library verbosity

### Performance Improvements
- **Professional User Experience**: Complete GUI eliminates command-line complexity (v1.0.0)
- **One-Click Deployment**: Windows installer eliminates manual setup requirements (v1.0.0)
- **Faster Authentication**: Smart session validation eliminates unnecessary authentication prompts
- **5x faster downloads** through concurrent processing vs. sequential
- **Improved Code Maintainability**: 6 focused modules vs. 1 monolithic file
- **Better Testing**: Individual components can be tested independently
- **Enhanced Debugging**: Clear separation of concerns for easier troubleshooting
- **Optimized User Experience**: Interactive folder selection improves organization efficiency
- **Streamlined Authentication**: Automatic session handling reduces startup time
- **System Integration**: System tray and Start Menu integration for seamless workflow (v1.0.0)
- Exponential backoff retry mechanism for network reliability  
- Smart resource management prevents UI blocking during intensive operations
- Memory-efficient progress tracking with callback-based updates
- **Streamlined Workflow**: Integrated folder navigation reduces setup time

### Refactoring Benefits
- **Complete Application Transformation**: From command-line tool to professional Windows application (v1.0.0)
- **Code Organization**: Transformed 596-line monolithic file into clean 6-module architecture
- **Single Responsibility**: Each module focuses on one primary concern
- **GUI Integration**: Dedicated GUI application with professional desktop experience (v1.0.0)
- **Deployment Automation**: Complete build and installer pipeline for professional distribution (v1.0.0)
- **Authentication Modularity**: Dedicated authentication handling with GUI/console support
- **Reusability**: Components can be easily reused or replaced
- **Scalability**: New features can be added without affecting existing modules
- **Maintainability**: Easier to understand, debug, and extend individual components
- **Enhanced Modularity**: GUI, authentication, and folder navigation demonstrate continued architectural evolution

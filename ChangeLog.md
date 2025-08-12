# ChangeLog

## 0.5.1.0811-0155 Refactor bot.py

## 0.5.0.0811-1135 Interactive Folder Navigation

### feature

+ **Interactive Folder Navigation System** - Complete user-controlled download organization
  + Real-time folder selection with interactive commands (`/cr`, `/cd`, `/cd..`, `/ok`)
  + Dynamic folder creation and navigation during download process
  + Live media statistics display for each folder (videos, photos, documents)
  + Seamless integration with existing download workflow
  + Multi-language command support (English and Chinese aliases)

+ **Enhanced User Experience** - Intuitive folder management interface
  + Visual folder tree display with current location indicator
  + Real-time feedback for folder operations (create, navigate, confirm)
  + Smart path validation and error handling
  + User state management for concurrent sessions
  + Clear command instructions and help text

+ **Flexible Download Organization** - User-controlled file placement
  + Choose destination folder before download starts
  + Create nested folder structures on-the-fly
  + Browse existing folders with media count previews
  + Organize downloads by topic, date, or any custom structure
  + Maintain clean separation between different download sessions

### improve

+ Enhanced bot architecture with dedicated folder navigation component
+ Improved user workflow with clear separation of folder selection and download phases
+ Better error handling and user feedback for folder operations
+ More intuitive download organization compared to automatic timestamped directories
+ Cleaner code organization with `FolderNavigator` class handling all path logic

## 0.4.0.0806-2329 Database Integration and Enhanced Management

### feature

+ **SQLite Database Integration** - Persistent storage for download history and metadata
  + Track all downloads with detailed metadata (message ID, file names, sizes, dates)
  + Duplicate detection to prevent re-downloading existing files
  + Download history queries and statistics
  + Automated database initialization and schema management

+ **Enhanced Download Management** - Improved file organization and tracking
  + Smart duplicate prevention using database lookups
  + Comprehensive download statistics and reporting
  + Better error tracking and recovery mechanisms
  + Enhanced logging with database integration

### improve

+ Database-driven architecture provides better scalability and data persistence
+ Improved performance through intelligent duplicate detection
+ Enhanced reliability with persistent download history
+ Better user experience with detailed download statistics

## 0.3.1.0806-1730 Media Group Support

### feature

+ **Media Group Detection and Processing** - Intelligent handling of grouped media (albums)
  + Automatically detects messages with `media_group_id` from Bot API
  + Implements 2-second collection delay to ensure all grouped messages are captured
  + Smart collection mechanism with timer-based processing
  + Enhanced logging for media group collection progress

+ **Advanced Media Group Retrieval** - Multi-method approach for robust media group handling
  + Method 1: Direct `grouped_id` matching using Telethon API
  + Method 2: Range-based search around original message ID (±20 messages)
  + Method 3: Graceful fallback to original message processing
  + Handles Bot API and Telethon ID differences intelligently

+ **Enhanced Architecture** - Extended modular design for media group support
  + `_handle_media_group()` - Collects and manages grouped messages
  + `_process_media_group_delayed()` - Timer-based processing with async delay
  + `_process_grouped_messages()` - Dedicated media group download workflow
  + `_process_single_message()` - Refactored single message processing
  + `_download_and_monitor()` - Shared download and monitoring logic

+ **Smart Storage Organization** - Media group aware directory structure
  + Media groups stored in `mediagroup_{id}_{timestamp}` directories
  + Single messages continue using `message_{id}_{timestamp}` format
  + Preserves existing file naming conventions and organization

### improve

+ Enhanced bot architecture with clear separation of group vs single message processing
+ Improved error handling and logging for media group operations
+ Better resource management with shared download monitoring logic
+ More robust message collection with multiple detection methods

## 0.3.0.0806-1430 Major Architecture Refactoring

### refactor

+ **Complete codebase restructure** - Split monolithic telegram_bot.py (596 lines) into modular architecture
  + Create `src/bot.py` (247 lines) - Main bot logic and message handling
  + Create `src/downloader.py` (234 lines) - Download operations with concurrent processing
  + Create `src/monitor.py` (134 lines) - Real-time monitoring and progress tracking
  + Create `src/__init__.py` - Package initialization and clean exports

+ **Separation of Concerns** - Each module has single responsibility
  + `TelegramMediaBot` class focuses on bot orchestration and user interaction
  + `MediaDownloader` class handles all download operations and file management
  + `DownloadMonitor` class manages real-time progress tracking and system monitoring

+ **Improved maintainability and testability**
  + Individual components can be tested independently
  + Clear interfaces between modules
  + Easier debugging and troubleshooting
  + Better code organization for future development

### feature

+ Add total file size display throughout download process
  + Pre-download analysis shows total expected download size
  + Real-time progress shows downloaded/total MB with percentage
  + Enhanced completion summary with size comparison and completion rate
  + `get_media_size()` method for accurate file size calculation before download

+ Enhanced progress monitoring with comprehensive metrics
  + Show progress as "45.2MB / 125.3MB (36.1%)" format
  + Calculate and display completion percentage in real-time
  + Improved ETA calculations based on current download speed
  + Better disk space monitoring and warnings

### misc

+ Backup original telegram_bot.py as telegram_bot.py.bak
+ Update main.py imports to use new modular structure
+ Update CLAUDE.md documentation to reflect new architecture
+ All modules pass syntax validation and import structure tests

## 0.2.1.0806-1155 Enhanced Download Reliability

### feature

+ Add retry mechanism for media downloads
  + Implement `download_media_with_retry()` with exponential backoff
  + Support up to 3 retry attempts for failed downloads
  + Handle network errors, timeouts, and Telegram API errors gracefully
  + Add FloodWaitError handling to respect rate limits

+ Add progress tracking and persistence
  + Implement `save_progress()` and `load_progress()` for download state management
  + Save progress every 10 processed messages to prevent data loss
  + Track completed and failed files separately
  + Resume functionality for interrupted downloads

+ Enhanced error handling and logging
  + Improved error messages for better user feedback
  + Detailed logging for debugging download issues
  + Separate handling for different types of Telegram API errors
  + More informative error messages when message retrieval fails

+ Improved download reporting
  + Show count of both successful and failed downloads
  + Display detailed completion status in final message
  + Better progress updates during bulk downloads

### misc

+ Add required imports: time, json modules
+ Add error classes: FloodWaitError, RPCError from telethon.errors

## 0.2.0.0805-1015 Backup Mode Implementation

### feature

+ Convert bot to backup-only mode
  + Remove ZIP file creation functionality
  + Remove file upload/sending to users
  + Files now permanently stored on server in organized directories
  + Added backup completion summary with file count, total size, and storage location
  + Updated progress messages to reflect backup operations instead of download/upload

### docs

+ Update README.md to reflect backup-only functionality
+ Update CLAUDE.md documentation for new backup workflow

## 0.1.1.0805-1632 Documentation Fix

### fix

+ Fix README.md incorrect parts
  + Update entry point from `python src/telegram_bot.py` to `python main.py`
  + Update project structure to reflect actual files (config.py, main.py, ChangeLog.md)
  + Remove reference to non-existent .env.example file in setup instructions

## 0.1.0.0805-1200 Initial Release

### feature

+ Add src/telegram_bot.py - TelegramBot class
  + Core bot functionality for handling Telegram messages
  + Media download support for photos, videos, GIFs, audio, and documents
  + Smart file naming with timestamps and message IDs
  + Automatic ZIP packaging of downloaded files
  + Progress updates during download process
  + File size validation (50MB Telegram limit)
  + Comprehensive error handling and logging
+ Add config/config.py - environment variable management
  + BOT_TOKEN configuration
  + API_ID and API_HASH configuration
  + SESSION_NAME configuration
  + Input validation and error handling
+ Add main.py - application entry point
  + Configuration validation
  + Bot initialization and startup
  + Graceful error handling for missing environment variables
+ Add requirements.txt - Python dependencies
  + telethon for Telegram client functionality
  + python-telegram-bot for bot framework
  + python-dotenv for environment variable management
+ Add .env.example - environment variables template
  + Template for required Telegram API credentials
  + Clear documentation for each required variable
+ Add .gitignore - Git ignore rules
  + Exclude .env files and API keys
  + Exclude Telegram session files
  + Exclude downloads and logs directories
  + Standard Python ignore patterns

### docs

+ Add README.md - comprehensive project documentation
  + Setup and installation instructions
  + Environment configuration guide
  + Usage examples and bot commands
  + Feature descriptions and limitations
  + Troubleshooting section

### misc

+ Add downloads/ directory - media storage location
+ Add logs/ directory - application logging storage
+ Initialize project structure with proper directory organization

# ChangeLog

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

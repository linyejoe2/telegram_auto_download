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
- **src/telegram_bot.py**: Main bot implementation containing the `TelegramMediaBot` class
- **config/config.py**: Configuration management using environment variables from `.env` file

### Key Architecture Patterns

1. **Dual API Usage**: The bot uses both Telegram APIs:
   - **python-telegram-bot**: For bot interactions and message handling
   - **Telethon**: For accessing Telegram Client API to retrieve forwarded messages and their replies

2. **Async/Await Pattern**: All operations are asynchronous using Python's asyncio

3. **Environment-based Configuration**: All credentials and settings loaded from `.env` file

### Data Flow

1. User forwards a message to the bot
2. Bot extracts original chat and message information from forward metadata
3. Uses Telethon client to access the original message and all its replies
4. Downloads all media files from original message and replies to server storage
5. Provides confirmation with backup details (file count, size, location)

### Key Classes and Methods

- `TelegramMediaBot`: Main bot class in src/telegram_bot.py:142
  - `handle_message()`: Processes forwarded messages
  - `get_message_and_replies()`: Retrieves original message and replies using Telethon
  - `download_media_from_message()`: Downloads media files with smart naming to server

### Configuration Requirements

The bot requires these environment variables in `.env`:

- `API_ID`: Telegram API ID from my.telegram.org
- `API_HASH`: Telegram API Hash from my.telegram.org  
- `PHONE_NUMBER`: Phone number for Telegram client authentication
- `BOT_TOKEN`: Bot token from @BotFather

### File Structure

- `downloads/`: Permanent backup directory (auto-created)
- `logs/`: Log files directory (auto-created)
- `bot_session.session`: Telethon session file (auto-generated)

### Media Support

The bot handles all Telegram media types:

- Photos (saved as .jpg)
- Videos (saved as .mp4 or original format)
- Documents with original filenames preserved
- Audio files
- GIFs

### Error Handling

- Network error handling for downloads
- Missing permissions detection
- Permanent file storage with organized folder structure

## Development Notes

- Bot supports forwarded messages from channels and group chats only (not private chats)
- Files are permanently stored in organized directories (by message ID and timestamp)
- Smart file naming includes message ID and timestamp
- Progress updates shown to users during backup operations
- Users receive confirmation with backup details (file count, size, storage location)
- Logging configured for debugging (INFO level)

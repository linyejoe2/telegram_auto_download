# Telegram Auto Download Bot v0.3.1

A high-performance Telegram bot with modular architecture that automatically downloads and backs up media files from forwarded messages, media groups, and their replies to the server for permanent storage.

## 🆕 What's New in v0.3.1

- **📸 Media Group Support**: Automatically detects and processes media groups (albums) as single units
- **🔄 Smart Collection**: Intelligent 2-second delay collection ensures all grouped messages are captured
- **🎯 Enhanced Detection**: Multi-method approach handles Bot API and Telethon ID differences
- **📁 Organized Storage**: Media groups stored in dedicated `mediagroup_{id}_{timestamp}` directories
- **🔧 Robust Processing**: Graceful fallback when media groups can't be retrieved

## Previous Updates (v0.3.0)

- **🏗️ Complete Architecture Refactor**: Transformed monolithic 596-line file into clean 3-module structure
- **📊 Enhanced Progress Display**: Shows total file sizes and completion percentages in real-time
- **🔧 Better Maintainability**: Separated concerns for easier testing, debugging, and future development  
- **📈 Improved Performance**: Optimized concurrent downloads with better resource management
- **🔍 Comprehensive Monitoring**: Enhanced system stats and disk space tracking

## Features

### 🚀 Performance & Architecture
- **Modular Design**: Clean 3-module architecture for better maintainability
- **Concurrent Downloads**: Up to 5 simultaneous downloads for 5x faster performance
- **Real-time Monitoring**: Live progress tracking with speed, size, and disk usage metrics
- **Smart Progress Display**: Shows downloaded/total size with completion percentage

### 📥 Download Capabilities  
- 🤖 Telegram bot interface for easy interaction
- 📸 **Media Group Support**: Automatically processes grouped media (albums) as single operations (v0.3.1)
- 📥 Downloads media from forwarded messages and all their replies
- 💾 Permanently stores files on server for backup purposes
- 🎯 Supports photos, videos, GIFs, audio files, and documents
- 🔍 Smart file naming with timestamps and message IDs
- 📁 Organized storage in timestamped directories with media group support (v0.3.1)

### 🛡️ Reliability & Monitoring
- **Retry Mechanism**: Exponential backoff for failed downloads (up to 3 attempts)
- **Progress Persistence**: Resume interrupted downloads with JSON-based progress tracking
- **Comprehensive Logging**: Detailed error tracking and performance metrics
- **Disk Space Monitoring**: Real-time storage availability checks

## Requirements

- Python 3.8+
- Telegram API credentials (API ID and API Hash)
- Bot Token from @BotFather
- Phone number for Telegram authentication

## Installation

1. Clone the repository:

```bash
git clone <repository-url>
cd telegram_auto_download
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set up configuration:
   - Create a `.env` file in the project root
   - Fill in your Telegram API credentials

## Configuration

### Getting Telegram API Credentials

1. **API ID and API Hash:**
   - Go to <https://my.telegram.org/apps>
   - Log in with your phone number
   - Create a new application
   - Copy the `api_id` and `api_hash`

2. **Bot Token:**
   - Message @BotFather on Telegram
   - Create a new bot with `/newbot`
   - Copy the bot token

3. **Phone Number:**
   - Your Telegram account phone number (with country code)

### Environment Variables

Create a `.env` file in the project root:

```env
API_ID=your_api_id_here
API_HASH=your_api_hash_here
PHONE_NUMBER=your_phone_number_here
BOT_TOKEN=your_bot_token_here
```

## Usage

1. Start the bot:

```bash
python main.py
```

2. In Telegram:
   - Find your bot by username
   - Forward any message with media to the bot
   - Watch real-time progress updates with download speeds and completion percentage
   - Receive detailed completion summary with performance metrics and storage location

### Example Progress Updates

```
⬇️ 備份進行中...
已完成: 3/5 個文件
失敗: 0 個
進度: 45.2MB / 125.3MB (36.1%)
速度: 8.5MB/s
剩餘空間: 15.2GB
```

## Project Structure

```
telegram_auto_download/
├── src/
│   ├── __init__.py             # Package initialization and exports
│   ├── bot.py                  # Main bot logic and message handling (247 lines)
│   ├── downloader.py          # Download operations with concurrency (234 lines) 
│   ├── monitor.py             # Real-time monitoring and progress (134 lines)
│   └── telegram_bot.py.bak    # Original monolithic file (backup)
├── config/
│   └── config.py              # Configuration management
├── main.py                    # Application entry point
├── logs/                      # Log files (auto-created)
├── downloads/                 # Permanent backup directory
├── requirements.txt           # Python dependencies
├── ChangeLog.md              # Project changelog
├── CLAUDE.md                 # Development documentation
└── README.md                 # This file
```

### Architecture Overview

- **src/bot.py**: Main orchestration - handles Telegram interactions and coordinates other components
- **src/downloader.py**: Concurrent download engine with retry mechanisms and progress tracking  
- **src/monitor.py**: Real-time monitoring with background thread for progress updates and system stats
- **Modular Design**: Each component has single responsibility and clean interfaces

## Supported Media Types

- 📷 Photos (JPG format)
- 🎥 Videos (MP4 and other formats)
- 🎬 GIFs
- 🎵 Audio files (MP3 and other formats)
- 📄 Documents and files

## Error Handling

The bot includes comprehensive error handling for:

- Invalid API credentials
- Network connection issues
- File download failures
- Storage directory creation
- Telegram API rate limits

## Security Notes

- Never commit your `.env` file or API credentials
- Keep your bot token secure and private
- Files are permanently stored in organized backup directories
- All session files are ignored by git

## Troubleshooting

### Common Issues

1. **"Unable to get original message"**
   - Ensure the bot has access to the forwarded chat
   - Check if the message is from a private chat (not supported)
   - Verify bot permissions in the source channel/group

2. **"Download performance issues"**
   - Check network connectivity and speed
   - Monitor disk space - downloads pause if insufficient storage
   - Verify concurrent download settings (default: 5 simultaneous)

3. **"Authentication errors"**
   - Verify your API credentials in `.env`
   - Ensure phone number includes country code
   - Check if session file needs regeneration

4. **"Module import errors"**
   - Ensure all dependencies are installed: `pip install -r requirements.txt`
   - Verify Python version compatibility (3.8+)
   - Check if src package structure is intact

### Monitoring & Debugging

- **Real-time Monitoring**: Progress updates show download speeds, completion rates, and disk usage
- **Progress Persistence**: Check `.download_progress.json` files for resume capability  
- **Detailed Logs**: Check console output or log files in the `logs/` directory
- **Module-specific Debugging**: Each component (bot, downloader, monitor) logs separately for easier troubleshooting

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This bot (v0.3.0) is for educational and personal backup use. Ensure you comply with Telegram's Terms of Service and respect copyright when backing up media files. Only backup content you have permission to store.

**Note**: This version features a completely refactored architecture for improved performance and maintainability. The original monolithic code is preserved as `telegram_bot.py.bak` for reference.

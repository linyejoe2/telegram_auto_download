# Telegram Auto Download Bot v1.0.0

A high-performance Telegram bot with modular architecture that automatically downloads and backs up media files from forwarded messages, media groups, and their replies to the server for permanent storage. Features an interactive folder navigation system for organized downloads.

## 🆕 What's New in v1.0.0

- **📁 Interactive Folder Navigation**: Visual folder tree with command-based organization system (`/cr`, `/cd`, `/ok`)
- **🎯 Simplified Architecture**: Clean 5-step linear processing flow (command → downloadable → extract → folder → download)
- **📊 Media Preview**: Shows file counts (photos, videos, documents) before folder selection
- **🔄 Code Refactoring**: Streamlined bot logic with eliminated duplicate code and consolidated helper methods
- **🛡️ Database Protection**: Enhanced `.gitignore` to prevent tracking of user data and download history

## Previous Updates (v0.4.0)

- **🗃️ Database Integration**: SQLite database for persistent download history and metadata tracking
- **🔍 Smart Duplicates**: Intelligent duplicate detection prevents re-downloading existing files
- **📊 Download Statistics**: Comprehensive tracking and reporting of download history
- **⚡ Enhanced Performance**: Database-driven architecture improves scalability and reliability
- **🔧 Better Management**: Automated database initialization and schema management

- **🗃️ Database Integration**: SQLite database for persistent download history and metadata tracking
- **🔍 Smart Duplicates**: Intelligent duplicate detection prevents re-downloading existing files
- **📊 Download Statistics**: Comprehensive tracking and reporting of download history
- **⚡ Enhanced Performance**: Database-driven architecture improves scalability and reliability
- **🔧 Better Management**: Automated database initialization and schema management

## Previous Updates (v0.3.1)

- **📸 Media Group Support**: Automatically detects and processes media groups (albums) as single units
- **🔄 Smart Collection**: Intelligent 2-second delay collection ensures all grouped messages are captured
- **🎯 Enhanced Detection**: Multi-method approach handles Bot API and Telethon ID differences
- **📁 Organized Storage**: Media groups stored in dedicated `mediagroup_{id}_{timestamp}` directories

## Previous Updates (v0.3.0)

- **🏗️ Complete Architecture Refactor**: Transformed monolithic 596-line file into clean 3-module structure
- **📊 Enhanced Progress Display**: Shows total file sizes and completion percentages in real-time
- **🔧 Better Maintainability**: Separated concerns for easier testing, debugging, and future development  
- **📈 Improved Performance**: Optimized concurrent downloads with better resource management
- **🔍 Comprehensive Monitoring**: Enhanced system stats and disk space tracking

## Features

### 🚀 Performance & Architecture
- **Modular Design**: Clean 4-module architecture with interactive folder navigation for better maintainability
- **Simplified Processing Flow**: Linear 5-step architecture eliminates complex branching logic
- **Concurrent Downloads**: Up to 5 simultaneous downloads for 5x faster performance
- **Real-time Monitoring**: Live progress tracking with speed, size, and disk usage metrics
- **Smart Progress Display**: Shows downloaded/total size with completion percentage

### 📥 Download Capabilities  
- 🤖 Telegram bot interface for easy interaction
- 📁 **Interactive Folder Navigation**: Visual folder tree with command-based organization system (v1.0.0)
- 📊 **Media Preview**: Shows file counts before folder selection for better organization (v1.0.0)
- 📸 **Media Group Support**: Automatically processes grouped media (albums) as single operations
- 🗃️ **Database Integration**: SQLite database tracks download history and prevents duplicates (v0.4.0)
- 📥 Downloads media from forwarded messages and all their replies
- 💾 Permanently stores files on server for backup purposes
- 🎯 Supports photos, videos, GIFs, audio files, and documents
- 🔍 Smart file naming with timestamps and message IDs
- 📁 Organized storage in user-selected custom folders with timestamped directories
- 📊 Database-tracked downloads with comprehensive metadata and statistics (v0.4.0)

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
   - Use interactive folder navigation commands to organize your downloads:
     - `/cr folder_name` - Create a new folder
     - `/cd folder_name` - Navigate into a folder
     - `/cd..` - Go back to parent directory
     - `/ok` - Confirm location and start download
   - Watch real-time progress updates with download speeds and completion percentage
   - Receive detailed completion summary with performance metrics and storage location

### Example Folder Navigation

```
📂 選擇存放位置
目前位置: ./downloads/Photos/2024/

📁 可用資料夾:
├── January/
├── February/  
└── March/

📊 即將下載:
• 照片: 3 個
• 影片: 2 個  
• 文件: 0 個

使用命令:
/cr folder_name - 創建資料夾
/cd folder_name - 進入資料夾  
/cd.. - 返回上級
/ok - 確認位置
```

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
│   ├── bot.py                  # Main bot logic with simplified architecture (513 lines, v1.0.0)
│   ├── folder_navigator.py     # Interactive folder navigation system (v1.0.0)
│   ├── downloader.py          # Download operations with concurrency (234 lines) 
│   ├── monitor.py             # Real-time monitoring and progress (134 lines)
│   ├── database.py            # SQLite database management (v0.4.0)
│   └── telegram_bot.py.bak    # Original monolithic file (backup)
├── config/
│   └── config.py              # Configuration management
├── main.py                    # Application entry point
├── test_folder_navigation.py  # Folder navigation testing (v1.0.0)
├── logs/                      # Log files (auto-created)
├── downloads/                 # Permanent backup directory
├── downloads.db               # SQLite database (auto-created, gitignored)
├── requirements.txt           # Python dependencies
├── ChangeLog.md              # Project changelog
├── CLAUDE.md                 # Development documentation
└── README.md                 # This file
```

### Architecture Overview

- **src/bot.py**: Main orchestration with simplified 5-step linear processing flow (v1.0.0)
- **src/folder_navigator.py**: Interactive folder management with visual tree display and user session tracking (v1.0.0)  
- **src/downloader.py**: Concurrent download engine with retry mechanisms and progress tracking  
- **src/monitor.py**: Real-time monitoring with background thread for progress updates and system stats
- **src/database.py**: SQLite integration for download history and duplicate prevention (v0.4.0)
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

This bot (v1.0.0) is for educational and personal backup use. Ensure you comply with Telegram's Terms of Service and respect copyright when backing up media files. Only backup content you have permission to store.

**Note**: This version features interactive folder navigation and simplified architecture for enhanced user experience and maintainability. The modular design continues to evolve with clean separation of concerns for improved performance and extensibility.

# Telegram Auto Download Bot v1.0.0

A high-performance Telegram bot that automatically downloads and backs up media files from forwarded messages, media groups, and their replies. Features both command-line and GUI interfaces with interactive folder navigation and comprehensive download management.

## ✨ Key Features

- **🖥️ Professional GUI**: Windows application with system tray integration, real-time logging, and easy configuration
- **📦 Windows Installer**: One-click installation with professional setup - no Python required
- **📁 Interactive Folder Navigation**: Choose download location with intuitive commands (`/cr`, `/cd`, `/ok`)
- **🗃️ Database Integration**: SQLite database prevents duplicates and tracks download history
- **📸 Media Group Support**: Automatically processes grouped media (albums) as single units
- **⚡ High Performance**: Up to 5 concurrent downloads with real-time progress monitoring

## Quick Start

### Windows Installer

1. **Download**: Get `TelegramAutoDownload-Setup-v1.0.0.exe` from releases
2. **Install**: Run installer (no Python required)
3. **Configure**: Launch GUI, set API credentials in Configuration tab
4. **Run**: Start bot and minimize to system tray

### Build From Source

```bash
# 1. Clone and install
git clone <repository-url>
cd telegram_auto_download
pip install -r requirements.txt

# 2. Configure
# Create .env file with your credentials
API_ID=your_api_id
API_HASH=your_api_hash
PHONE_NUMBER=your_phone_number
BOT_TOKEN=your_bot_token

# 3. Run
python main.py          # Command line
python run_gui.py       # GUI (Windows)
```

## Getting API Credentials

1. **API ID/Hash**: Visit <https://my.telegram.org/apps> → Create app → Copy credentials
2. **Bot Token**: Message @BotFather → `/newbot` → Copy token
3. **Phone**: Your Telegram number with country code (e.g., +1234567890)

## Usage

Forward any media message to your bot, then:

- `/cr <name>` - Create folder
- `/cd <name>` - Enter folder  
- `/cd..` - Go back
- `/ok` - Start download

Progress updates show speed, completion, and storage location.

## Windows Installer (Recommended for End Users)

### Build Package

```batch
package_windows.bat  # Complete build process
```

**Output**: Professional Windows installer (`TelegramAutoDownload-Setup-v1.0.0.exe`) with:

- Single-click installation (no Python required)
- GUI application with system tray integration  
- Start menu shortcuts and desktop shortcut options
- Auto-upgrade capability for future versions

### Requirements for Building

- Python 3.8+
- Inno Setup 6.x (for installer creation)
- Windows 10/11

## License & Disclaimer

MIT License. For educational and personal backup use only. Respect Telegram's Terms of Service and copyright laws.

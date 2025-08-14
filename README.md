# Telegram Auto Download Bot v1.1.0

A high-performance Telegram bot that automatically downloads and backs up media from forwarded messages, media groups, and replies. Supports both CLI and GUI with interactive folder navigation, database tracking, and real-time progress.

---

## ✨ Features

- **🖥️ GUI Application**  
  Windows desktop app with system tray, real-time logs, and easy configuration.

- **📦 Windows Installer**  
  One-click setup — no Python required. Professional packaging with auto-updates.

- **📁 Folder Navigation**  
  Interactive commands (`/cr`, `/cd`, `/ok`) to choose download location.

- **🗃️ SQLite Database**  
  Tracks download history and prevents duplicates.

- **📸 Media Group Support**  
  Automatically handles albums and grouped media.

- **⚡ High Performance**  
  Concurrent downloads (up to 5), real-time metrics, and progress display.

---

## 🚀 Quick Start

### ✅ Recommended: Windows Installer

1. **Download** `TelegramAutoDownload-Setup-v1.1.0.exe` from Releases  
2. **Install** — No Python required  
3. **Launch** the app, configure API credentials in GUI  
4. **Run** the bot (minimizes to system tray)

---

### 🧰 Build From Source

```bash
# 1. Clone & Install
git clone <repository-url>
cd telegram_auto_download
pip install -r requirements.txt

# 2. Configure (.env file)
API_ID=your_api_id
API_HASH=your_api_hash
PHONE_NUMBER=+1234567890
BOT_TOKEN=your_bot_token

# 3. Run
python main.py       # CLI
python run_gui.py    # GUI (Windows)
```

### 🏗️ Building Windows Installer

You can build a standalone Windows installer (.exe) that bundles the bot and all its dependencies—no Python installation needed on the target machine.

#### ✅ Requirements

Install the following on your Windows system:

1. Python 3.8+ (64-bit recommended)
    - Download: <https://www.python.org/downloads/>
    - Make sure to check "Add Python to PATH" during installation.

2. Inno Setup 6.x
    - Download: <https://jrsoftware.org/isdl.php>
    - Install and ensure ISCC.exe is available in your system PATH.

3. PyInstaller
    - Install via pip: `pip install pyinstaller`

#### 🛠️ Build Steps

Run: `package_windows.bat`

> This script performs the following:
>
> - Runs PyInstaller using telegram_bot.spec
> - Generates a standalone EXE in /dist
> - Calls Inno Setup to generate the final installer .exe

## 🔐 API Credentials

- API ID & Hash: my.telegram.org/apps → Create App
- Bot Token: Message @BotFather → /newbot
- Phone Number: Your full number with country code (e.g., +1234567890)

## 📦 Folder Commands

Forward any media to the bot, then use:

```
/cr <name>    # Create folder
/cd <name>    # Enter folder
/cd..         # Go up
/ok           # Start download
```

## 📄 License & Disclaimer

MIT License.
For educational/personal backup use only.
You must comply with Telegram’s Terms of Service.

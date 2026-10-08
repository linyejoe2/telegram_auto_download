# Telegram Auto Download Bot v2.5.0

A high-performance Telegram bot that automatically downloads and backs up media from forwarded messages, media groups, and replies. Supports both CLI and GUI with interactive folder navigation, database tracking, and real-time progress.

---

## ✨ Features

- **🖥️ GUI Application**  
  Windows desktop app with system tray, real-time logs, and easy configuration.

- **📦 Windows Installer**  
  One-click setup — no Python required. Professional packaging with auto-updates.

- **📁 Folder Navigation**  
  Interactive inline keyboard buttons to browse and choose download location, with previous-path quick-select.

- **🗃️ SQLite Database**  
  Tracks download history and prevents duplicates.

- **⚡ High Performance**  
  Concurrent downloads (up to 5), real-time metrics, and progress display.

- **🌐 URL Video Downloader**  
  Send a YouTube, X (Twitter), or Pornhub link — the bot fetches metadata, lets you pick a folder, then downloads with live progress.

- **🐦 X Account Download**  
  Send `https://x.com/<user>` — the bot scans the account, reports post/video/photo counts, then downloads all media and/or screenshots of posts.

---

## 🚀 Quick Start

### ✅ Recommended: Windows Installer

1. **Download** `TelegramAutoDownload-Setup-v2.5.0.exe` from Releases  
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

## 📁 Folder Navigation

Forward any media to the bot. An inline keyboard appears automatically:

| Button | Action |
|---|---|
| `📁 FolderName` | Enter that subfolder |
| `⬆️ 返回上級` | Go up one level (hidden at root) |
| `✅ 確認這裡` | Confirm current location and start download |
| `📝 新建資料夾` | Prompt to type a new folder name |
| `🕐 /prev/path` | Jump to a previously used path |

Up to 5 previously confirmed paths are remembered and shown as quick-select buttons.

## 🌐 URL Video Download

Send any supported video URL directly to the bot (no forwarding needed):

| Platform | Example URL |
|---|---|
| YouTube | `https://youtu.be/...` · `https://youtube.com/watch?v=...` · `/shorts/...` |
| X / Twitter | `https://x.com/i/status/...` · `https://twitter.com/.../status/...` |
| Pornhub | `https://www.pornhub.com/view_video.php?viewkey=...` · `interstitial?viewkey=...` |

The bot fetches metadata (title, duration, size), then shows the folder selection keyboard. After confirming, it downloads the video, computes a perceptual hash for duplicate detection, and records it in the database.

> **Note:** X and Pornhub downloads use Firefox browser cookies for authentication. Make sure you are logged in to those sites in Firefox on the same machine.

## 🐦 X Account Download

Send an account URL (`https://x.com/<user>`, also `/media`, `/with_replies`, `/tweets`). The bot scans the account with gallery-dl (Firefox cookies, ~3,200 post timeline limit; large accounts can take several minutes) and replies with counts: 文章 N 篇 (含媒體 M 篇) / 影片 N 部 / 照片 N 張. Retweets are excluded.

Then choose a mode with the inline buttons:

| Button | Action |
|---|---|
| `⬇️ 下載媒體` | Download photos and videos |
| `⬇️📸 下載媒體 + 截圖` | Download media and screenshot each media post |
| `📸 只截圖` | Screenshots only |

After the mode, the usual folder keyboard appears. Output goes to `<folder>/x_<username>/` (screenshots in `screenshots/`). Media files are named `<tweetid>_<n>.<ext>` and duplicates are skipped. Posts without media are counted but never downloaded or screenshotted.

> **Note:** You must be logged in to X in Firefox on the same machine. Screenshots require a one-time Chromium install: click **Install** in the GUI Configuration tab > Screenshot Engine (or run `playwright install chromium` when running from source). Media download works without it.

## 📄 License & Disclaimer

MIT License.
For educational/personal backup use only.
You must comply with Telegram’s Terms of Service.

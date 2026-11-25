# Telegram Auto Download Bot v3.5.0

A high-performance Telegram bot that automatically downloads and backs up media from forwarded messages, media groups, and replies. Supports both CLI and GUI with interactive folder navigation, download-record tracking, and real-time progress.

---

## ✨ Features

- **🖥️ GUI Application**  
  Windows desktop app with system tray, real-time logs, and easy configuration.
  The Database tab lists recent downloads and has a **Clean Empty Files** button (v3.3.2) that deletes 0-byte files with no source link after confirmation.

- **📦 Windows Installer**  
  One-click setup — no Python required. Professional packaging with auto-updates.

- **📁 Folder Navigation**  
  Interactive inline keyboard buttons to browse and choose download location, with previous-path quick-select.

- **🗃️ Download Records**  
  Tracks download history and prevents duplicates. Each file's record is kept beside it in a hidden `.<file>.meta.json` and deleted downloads in `<DOWNLOADS_PATH>/.tad/deleted.json` (v3.3.0, no database), so history and library data travel with the folder.

- **⚡ High Performance**  
  Concurrent downloads (up to 5), real-time metrics, and progress display.

- **🌐 URL Video Downloader**  
  Send a YouTube, X (Twitter), or Pornhub link — the bot fetches metadata, lets you pick a folder, then downloads with live progress.

- **🐦 X Account Download**  
  Send `https://x.com/<user>` — the bot scans the account, reports post/video/photo counts, then downloads all media and/or screenshots of posts.

- **📚 Chat Download (v3.4.0)**  
  Send `/chats` to pick a group or channel you joined and download all its photos and videos, skipping what you already have; interrupted downloads resume after a restart.

- **🧾 Request Queue**  
  Keep sending posts and links while a download runs — items queue up and each asks for its own folder in turn.

- **🔎 Startup Scan**  
  On start, the bot queues anything you sent it recently that was not downloaded yet.

- **📂 Chat File Viewer**  
  Send `/files` to browse folders, preview folder videos, check the source link of, and delete downloaded files right from Telegram (owner only).

- **🎬 Web Video Library (v3.0.0)**  
  Watch and manage downloaded videos and photos in a browser: screenshots, search, tags, live transcoding, download history, password protected.

- **🤖 AI Recognition (v3.5.0)**  
  Select items in the web library and let AI suggest 主演 (face match) or 系列 (same person + outfit, via an Ollama vision model); you review and apply the results on the 🤖 AI 辨識 page.

---

## 🚀 Quick Start

### ✅ Recommended: Windows Installer

1. **Download** `TelegramAutoDownload-Setup-v3.5.0.exe` from Releases  
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
DOWNLOADS_PATH=downloads # optional: downloads folder (default <app dir>/downloads); download records are kept beside each file and in <DOWNLOADS_PATH>/.tad/ (v3.3.0)
STARTUP_SCAN_COUNT=30   # optional: messages checked at startup (0 = off)
WEB_ENABLED=1           # optional: start the web video library with the bot (v3.0.0)
SIMILARITY_THRESHOLD=70 # optional: % similarity at which same-length videos are grouped as versions (v3.1.0)
WEB_PORT=8765           # optional: library port (default 8765)
WEB_HOST=0.0.0.0        # optional: 0.0.0.0 = any location, 127.0.0.1 = this PC only
# STREAM_ENCODER=cpu   # optional: force CPU for the live transcode instead of NVIDIA NVENC (v3.4.1)
# OLLAMA_BASE_URL=http://localhost:11434 # optional: Ollama server for AI 辨識系列 (v3.5.0; set from the GUI "Web Library" tab)
# OLLAMA_MODEL=         # optional: Ollama vision model (empty = first model that can see pictures; set from the GUI "Web Library" tab)
# WEB_PASSWORD_HASH / WEB_SECRET are written by the GUI "Web Library" tab; set the password there

# 3. Build the web library frontend (needs Node.js 18+ and ffmpeg/ffprobe in PATH)
cd frontend && npm install && npm run build && cd ..

# 4. Run
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

4. Node.js 18+ (v3.0.0, builds the web library frontend)
    - Download: <https://nodejs.org/>

#### 🛠️ Build Steps

Run: `package_windows.bat` (reuses `build_env\` and the PyInstaller cache for faster rebuilds; `package_windows.bat fresh` rebuilds everything from scratch, e.g. after removing a package from `requirements.txt`)

> This script performs the following:
>
> - Builds the web library frontend (`npm ci && npm run build` in `frontend/`, fails if Node.js is missing)
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

The bot fetches metadata (title, duration, size), then shows the folder selection keyboard. After confirming, it downloads the video, computes a perceptual hash for duplicate detection, and records it.

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

## 🔗 t.me Link Download

Send a Telegram message link (`https://t.me/<channel>/<id>` or `https://t.me/c/<id>/<id>`, owner only) and the bot reads it with the logged-in account, so channels that block forwarding ("restrict saving content") can still be backed up, as long as that account can see the message. `?single` downloads only that message; otherwise the whole album and media replies are included. Then choose the folder as usual.

## 📚 Chat Download (/chats)

Send `/chats` (owner only; also in the Telegram command menu) to list the groups and channels the logged-in account has joined, most recent first, 10 per page (👥 group / 📢 channel, `◀` `▶` to page). `/chats <keyword>` filters by name. Tap one and the bot scans its whole history with Telegram's photo/video filter (progress shown, `✖ 停止掃描` to cancel), then shows a summary (total, photos, videos, already downloaded, and the count and size to download) above the usual folder selector. The item waits its turn in the request queue like any other.

- **Skips what you have:** items already downloaded, including deleted ones, are skipped at scan time, before downloading, so running `/chats` on the same group again only fetches what is missing.
- **Download:** files go straight into the chosen folder, 5 at a time, with progress every 5 seconds and a `⏹ 停止下載` button (the half-written file is removed). Only photos and videos (Telegram's filter) are included, not images sent as files.
- **Resume:** a started download is saved in `<DOWNLOADS_PATH>/.tad/chat_jobs.json`; if the bot stops or the PC restarts, the next start queues it again ("⏯ 繼續上次未完成的下載"), rescans and continues, skipping what is already there. Stopping or finishing removes the job.
- **Description (v3.4.0):** every Telegram download (forward, album, t.me link, startup scan / `/rescan`, `/chats`, re-download) stores the original message text as `description` in the file's hidden `.<file>.meta.json`: the message's own text, else the album caption, else the root post's text for replies. Files downloaded before v3.4.0 have none.

## 🧾 Request Queue & Startup Scan

The bot accepts forwarded posts, albums, X/YouTube links and X account links even while a download is running. Items wait in a serial queue (shown with their queue position); each gets its own folder selector, which appears only after the previous download finishes. Tap `❌ 取消` on a selector (or the X-account mode buttons) to skip an item; an unanswered selector times out after 30 minutes. The queue is kept in memory and is dropped when the bot stops.

On startup the bot checks the last `STARTUP_SCAN_COUNT` messages you sent it (default 30, `0` = off; also set in GUI Configuration > Bot Configuration > "Startup scan (messages)") against the download records and queues every forwarded channel post/album or X/YouTube link not yet downloaded, one item each. X account links are not scanned; forwards from supergroups/anonymous admins are skipped. Send `/rescan` (owner only, optional message count, e.g. `/rescan 50`) to run the same scan again at any time; items already in the queue are not added twice.

## 📂 File Viewer

Send `/files` (owner only; also in the Telegram command menu) to browse the downloads folder with inline buttons, the same way as the folder selector: all sub folders of the current level in a 2-per-row grid (no paging), followed by the newest 30 files of the level (tap one for its details, source link, preview and delete), with folder/video/photo/file counts and total size. `/files <folder-or-file>` opens that path directly; a file path opens the file details. Hidden files and unfinished `.part` downloads are not shown.

- **Folder video preview:** `🎞 預覽資料夾影片 (n)` sends one screenshot (at 15s) of every video in the current folder as albums of 10, captioned with the relative path, timestamp and source link; `🎞 預覽資料夾內所有影片 (n)` also includes sub folders (shown only when they add videos). `▶️ 下一頁（剩餘 n 部）` generates the next 10 below the previous albums and shows `已預覽 x/y 部影片`; unreadable videos are skipped.
- **Folder photo loading (v2.7.3):** `🖼 載入照片 (n)` / `🖼 載入所有照片 (n)` (with sub folders) send the folder's photos as albums of 10 (caption: relative path, size, source link) with the same lazy `▶️ 下一頁`.

- **Details & source link:** `/files <file path>` shows size, modified time, location, video duration/resolution and download time, plus its source and a `🔗 開啟來源` button (Telegram post `https://t.me/c/<channel>/<message>`, the original YouTube/X/Pornhub URL, or `https://x.com/i/status/<id>` for X account downloads; "未知" if the file has no download record).
- **Single-file preview (`🖼 預覽`):** images are sent as a photo; videos as an album of 3 screenshots (at 15s, the middle and 15s before the end; videos under 45s use 10%/50%/90%).
- **Load video (`📤 載入影片`):** uploads the video to the chat with Telethon (up to 2 GB, no Bot API 50 MB limit). Videos over 500 MB or above 4000 kbps are compressed first with ffmpeg (H.265, 720p, 2000 kbps; ffmpeg must be in PATH or set `FFMPEG_PATH`). The compressed copy is saved as a hidden `.<name>.720p_h265.mp4` in the same folder (not shown in the viewer) and re-used next time.
- **Delete (`🗑 刪除`):** asks for confirmation first. Only files and empty folders can be deleted. The download record is kept, so the startup scan will not download a deleted file again.
- **Owner only:** only the account the Telethon session is logged in as can use the viewer, and all paths are confined to the downloads folder.

## 🎬 Web Video Library

A browser app (v3.0.0) for watching and managing the videos in your downloads folder. Telegram and system settings stay in the Windows app.

- **Setup:** open the GUI **Web Library** tab, set a password (at least 8 characters, stored only as a hash), choose the port (default 8765) and access (any location `0.0.0.0` / this PC only), then click **Start** (tick **Start on launch** to run it with the app; `main.py --cli` also starts it when `WEB_ENABLED=1`). **Open in Browser** or use the URLs shown in the tab, e.g. `http://localhost:8765/library/` (v3.1.1: the library lives under `/library`; the site root `/` is an empty page). Changing the password logs out every session; 5 wrong passwords lock that client for 15 minutes.
- **Remote access:** the library speaks plain HTTP, so for access from outside put it behind an HTTPS tunnel (Cloudflare Tunnel or Tailscale are recommended) or use port forwarding at your own risk.
- **Versions (v3.1.0):** videos whose lengths differ by at most 3 s are compared on their first, middle and last screenshots (grayscale SSIM); if the mean similarity reaches the threshold (default 70 %, set under **Same-video similarity** in the Web Library tab) they are grouped as versions of one video. The library shows a group once (best quality, "N 個版本" badge); the video page has a 版本 box to switch 線路 (playback continues at the same time) and 「從群組移出」 to split a wrong match (never grouped again). 標題 / 主演 / 系列 are shared by the group. The whole library is checked when the web library starts; a new download that matches is grouped automatically and the bot sends a Telegram notice. Videos with Chinese (non-ASCII) folder or file names are compared too (v3.4.6).
- **Folder tree (v3.0.1):** the left side lists every folder with video counts; click to browse, `＋ 新增` adds a folder, drag a video or folder onto a folder to move it, right-click (or `⋯`) a folder to rename / add a sub folder / delete it (empty only) and right-click a video to open, rename, go to its folder or delete. Moved and renamed videos keep their info and screenshots.
- **Library page:** card or list view (grid / list icons, remembered per browser) of videos (clean cover = first screenshot; length or photo size, resolution and version count in one grey line under the title, v3.4.3), search, filter by 主演 / 系列, sort by 最新加入 / 標題 / 片長 / 檔案大小 / 畫質 (resolution, then bit rate; the list view shows bit rate under the resolution, v3.0.2) (filters are kept in the URL, also after a reload; the scroll position is remembered per view, so going back from a video or reloading returns to the same spot, v3.4.9), rescan, and a count of videos still being processed.
- **Video page:** cover with play button and a 3x3 screenshot grid (click a screenshot to play from there); edit 標題 / 主演 (multi-select tags) / 系列 / 來源 (auto-filled from the download record) / 描述 (v3.4.0: the original Telegram message text, editable, kept per file and not shared by versions; the library search matches it too); Video Info (size, bit rate, bit depth, codec, fps, audio, duration, playback mode, location); download the original, regenerate screenshots, delete (with confirmation).
- **Playback:** the original file is played when the browser supports it; otherwise (or if it fails) the server transcodes live with ffmpeg to H.264/AAC with seek, ±10s, volume, fullscreen and keys Space / ←/→ / F. Safari/iOS cannot play the live transcode. (v3.4.1) A 畫質 menu is in both modes: 原始 (only when playable, shows the file bit rate) and 2160p, 1080p 高 / 低, 720p 高 / 低, 480p 高 / 低 (video max 16000 / 8000 / 4500 / 4000 / 2000 / 1500 / 800 kbps); only levels that fit the video are offered, switching keeps the position; (v3.4.3) the choice applies to that video only and the default comes from the 設定 page. Transcoding uses an NVIDIA GPU (NVENC) when available, else the CPU; set `STREAM_ENCODER=cpu` to force the CPU. (v3.4.2) On phones the controls fit two rows, a tap shows / hides them and they hide by themselves after 3 s while playing; fullscreen fills the whole screen including the notch, with a 填滿 / 完整 button to crop or show the full picture. (v3.4.5) The original file now uses the same custom controls (the browser's native menu for speed / picture-in-picture / download is no longer shown), and on a touch screen swiping sideways on the player, also in fullscreen, switches to the previous / next video in the library page's current order (same folder / search / filters / sort), like Telegram's viewer: the picture follows your finger, a short flick or 60 px switches, the new video starts from the beginning and fullscreen stays on. Only works when the video was opened from the library page, not from 下載紀錄.
- **AI 辨識 (v3.5.0):** select videos / photos, then 👤 辨識主演 or 👗 辨識系列 (bottom bar, or 👤 AI 辨識主演 / 👗 AI 辨識系列 in the right-click menu of a selection); a toast links to 查看進度 and the job runs in the background, one at a time. The 🤖 AI 辨識 page (☰ menu) shows the queue (排隊中 / 執行中 / 完成 / 失敗 / 已取消, progress bar, 取消 / 刪除) and a status line (face models installed, Ollama reachable and model). **Nothing changes until you 套用 a result or 略過 it.** 主演: faces are matched with local face models (OpenCV YuNet + SFace, 12 frames per video) against items that already have 主演; you get 建議主演 (tick and 套用已選), 未知人物 cards (the same face in several items: leave out a wrong item, type a name, 設為主演) and 無法辨識 with reasons. 系列: items of the same person wearing the same outfit are grouped (outfit described and compared by an Ollama vision model; the name is pre-filled from an existing series or 「主演 + 服裝簡稱」, then 設為系列). Set the Ollama URL and model in the GUI Web Library tab (**AI Recognition (Ollama)**, Load Models lists the vision models, no restart); 辨識主演 doesn't need Ollama. Results and per-file caches (faces, outfit crops) are kept in `<downloads>/.tad/recognition.json` and the hidden `.shots` folders.
- **Side menu & settings (v3.4.3):** the ☰ button at the top right of every page opens a menu sliding in from the right with 🎬 媒體庫 / 📜 下載紀錄 / 🤖 AI 辨識 (v3.5.0) / ⚙ 設定 and 登出 (the left side stays the folder tree). The 設定 page sets the default playback quality (原始 or 2160p ... 480p 低, each with its bit rate cap and approximate data per hour) and whether fullscreen fills the screen (填滿) or shows the full picture (完整); saved per browser, so a phone and a PC can differ. The player's 畫質 menu only changes the current video.
- **Where data is stored:** next to each video as hidden files `.<file>.meta.json` (title, actors, series, source, description, cached info) and `.<file>.shots/01.jpg-09.jpg`; the chat `/files` viewer skips them. Deleting from the web also removes the video, these files and the hidden `.720p_h265` copy. The downloads folder is rescanned every 5 minutes.
- **Photos (v3.3.0):** the library also lists photos (.jpg .jpeg .png .gif .webp .bmp) with a thumbnail and Photo Info (size, format, bit depth, location); the 影片 / 圖片 / 全部 toggle on the filter row picks what is shown (remembered per browser, `?kind=` in the URL). The photo page has a large image, ‹ › (or ←/→) to the neighbors in the same folder, regenerate thumbnail, and delete, which continues with the next photo. Photos are not grouped as versions. (v3.3.3) On phones you swipe left or right to switch photos, and the neighbors are preloaded so the next photo opens at once.
- **Download history (v3.3.0):** the 📜 下載紀錄 page (☰ menu, v3.4.3) lists every download, existing and deleted, with search and status / type filters. Deleting a file keeps its record (and 標題 / 主演 / 系列 / 來源), so the startup scan and `/rescan` do not offer it again; a deleted row has ⬇ 重新下載, which queues it into its original folder. Re-download needs the bot running on that PC.
- **Re-download broken files (v3.3.1):** a video or photo that is incomplete or damaged shows a red box on its page with how its source will be found (its own record, a deleted record with the same file name, or the Telegram message id in the file name) and a ⬇ 重新下載 button; the broken copy is replaced once the source is found. Needs the bot running on that PC.
- **Multi-select delete & edit (v3.3.4):** `☑ 選取` on the filter row turns on select mode: click toggles an item, Shift+click selects a range, Ctrl/⌘+click selects even outside select mode. The bottom bar offers 全選, 🏷 編輯主演 / 系列 (add 主演 to all, remove an existing 主演, keep / set / clear 系列) and 🗑 刪除 (confirmation, deleted items stay in 下載紀錄); Esc ends, Ctrl/⌘+A selects all shown, Delete deletes; dragging a selected item to a folder moves them all, and right-click on a selected item gives the same actions. (v3.3.5) With a mouse, drag on empty space to draw a selection box (Shift adds, Ctrl toggles; the page scrolls at the top / bottom edge), and Shift / Ctrl clicks work like Windows Explorer: Shift+click selects the range from the last clicked item, Ctrl+Shift+click adds it; a click on empty space clears the selection. (v3.4.4) With 2 or more videos selected, 🔗 嘗試合併 (bottom bar, or 🔗 嘗試合併為同一部片 in the right-click menu) compares them first (same length ±3 s and screenshot similarity) and merges nothing yet; (v3.4.7) a dialog has a 相似度門檻 slider (40–99 %) that regroups live, shows 「將合併成 N 部片（共 M 部影片）」 with the groups by similarity, the videos that stay apart and those that can't be compared, and 確定合併 groups the shown result as versions (取消 merges nothing); a wrong merge can be undone with 「從群組移出」 on the video page. (v3.4.8) With exactly 2 videos selected, 🔬 加強比對 (bottom bar or right-click, by hand only) is a deeper check for copies with a cut start / end or a scaled / cropped / letterboxed picture: it aligns the two videos in time and compares matching frames, shows the score with a verdict and aligned frame pairs, and 合併為同一部片 merges them.
- **Open from another PC (v3.2.0):** the download records (stored beside each file, with deleted ones and folder history in `<downloads>/.tad/`, v3.3.0; an old `downloads.db` is imported once and renamed `downloads.db.migrated`) and paths relative to the downloads folder let you open the folder from another PC like an Obsidian vault (shared drive or synced folder, any path or drive letter) and its history and library data come with it. `.env`, Telegram sessions, logs and the web password stay per PC. Run the bot on only one PC at a time (one bot token); the web library can run on several.
- **Requirements:** ffmpeg and ffprobe in PATH or `FFMPEG_PATH` (not bundled). Building from source needs `cd frontend && npm install && npm run build` (Node.js 18+). AI 辨識 (v3.5.0): when running from source the two face models (YuNet + SFace, a few MB, from the official OpenCV Zoo with a SHA-256 check) download once on first use to `%LOCALAPPDATA%/TelegramAutoDownload/models`; the installer bundles them when `library/models` exists at build time. 辨識系列 also needs an Ollama server with a vision model.

## 📄 License & Disclaimer

MIT License.
For educational/personal backup use only.
You must comply with Telegram’s Terms of Service.

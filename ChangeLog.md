# ChangeLog

## [2.7.4] - 2026-10-28 - File Detail Button Restored
### Fixed
- `/files` list shows the newest 30 files of a level again as `fv_f` buttons (below the folders, no paging) so file details, source link, preview and delete are reachable by tapping

## [2.7.3] - 2026-10-28 - Folder Photo Loading
### Added
- `/files` folder photo loading: `🖼 載入照片 (n)` (`fv_ph`, this level) and `🖼 載入所有照片 (n)` (`fv_pha`, includes sub folders) send photos in albums of 10 with the same lazy `▶️ 下一頁` (`fv_pn`); `list_photos`/`list_media` in `file_viewer.py`

## [2.7.2] - 2026-10-28 - Installer Update
### Changed
- Installer: "Create Start Menu entry" is ticked by default; a running `TelegramAutoDownload.exe` is closed automatically before install/upgrade/uninstall; compression `lzma2/fast` (build step ~90s -> ~6s, installer 104 MB -> 132 MB)
### Removed
- `bump_version.bat`, `pyproject.toml` (bumpversion config) and `bump2version`; use `/update-release`

## [2.7.1] - 2026-10-28 - Folder Video Preview
### Added
- `/files` folder video preview (`file_viewer.py` `list_videos`, `build_batch_preview`; `bot.py` `_send_preview_batch`): `🎞 預覽資料夾影片` (`fv_pv`) and `🎞 預覽資料夾內所有影片` (`fv_pva`, includes sub folders) send one 15s screenshot per video in albums of 10 (caption: path, time, source link); lazy `▶️ 下一頁` (`fv_pn`) adds the next 10 below, earlier albums are kept
### Changed
- `/files` list view works like the folder selector: no paging, all sub folders in a 2-per-row grid with media counts; files are no longer listed (detail/preview/delete via `/files <file path>`; `fv_f`/`fv_pg` removed)

## [2.7.0] - 2026-10-27 - Chat File Viewer
### Added
- File viewer (`src/file_viewer.py` `FileViewer`, `bot.py` `handle_files_command`): owner-only `/files [folder-or-file]` (also in Telegram's command menu via `set_my_commands`) browses the downloads folder with inline buttons: folders first, files newest-first, 8 per page, item counts/sizes, hidden and `.part` files hidden, paging/up/close
- File details (size, modified time, location, video duration/resolution, download time) with source link and `🔗 開啟來源` button: `t.me/c/<channel>/<message>`, original YouTube/X/Pornhub URL, `x.com/i/status/<id>` for X account downloads, "未知" if no record; `DatabaseManager.find_download()` matches by path, falls back to file name + size
- `🖼 預覽`: images sent as a photo; videos as an album of 3 screenshots (15s, middle, 15s before end; under 45s uses 10%/50%/90%) generated with OpenCV
- `🗑 刪除` with confirmation: files and empty folders only (root/non-empty folders refused); the DB record is kept so the startup scan does not re-offer the file
### Security
- Only the Telethon session account (`TelegramMediaBot.owner_id`) can use `/files` and `fv_*` buttons; all paths are confined to the downloads folder (`..`, absolute paths, outside symlinks rejected)

## [2.6.1] - 2026-10-27 - Request Queue & Startup Scan
### Added
- Request queue (`src/bot.py` `FlowItem`, `submit_flow`, `_queue_worker`): the bot keeps accepting forwards, albums, X/YouTube links and X account links during a download; items wait serially and show their queue position
- Each queued item gets its own folder selector, shown only after the previous download finishes; new `❌ 取消` button on folder selectors and X-account mode buttons; unanswered selector times out after 30 minutes
- Startup scan: on start, the last N messages you sent the bot are checked against the downloads DB and undownloaded channel posts/albums and X/YouTube links are queued (`STARTUP_SCAN_COUNT` in `.env`, default 30, 0 = off; GUI "Startup scan (messages)"; `DatabaseManager.is_url_downloaded()`)
### Changed
- Removed the "請使用上方的按鈕選擇資料夾位置" rejection; `url_parser.download_confirmed()` takes `selected_path`/`scan`; GUI window 800x680

## [2.5.0] - 2026-10-08 - X Account Downloader
### Added
- X account downloader (`web/x_profile_downloader.py`): send `https://x.com/<user>`, scan via in-process gallery-dl (Firefox cookies), pick `xp_media`/`xp_both`/`xp_shot`, then a folder; saves to `x_<username>/` (`<tweetid>_<n>.<ext>`, deduped by file and DB), screenshots via Playwright Chromium
- GUI: "Screenshot Engine" box (Chromium Check/Install buttons, `src/chromium_helper.py`, browsers pinned to `%LOCALAPPDATA%\ms-playwright`) and a Restart Bot button
### Changed
- GUI Stop now cancels the bot task, Start reloads `.env`, Quit stops the bot; `bot.py` `run()` stops the updater first (no polling Conflict on restart)
- `package_windows.bat` rewritten: every step checked, failure prints `BUILD FAILED!` and exits 1, clean dirs verified, missing Inno Setup is an error
### Fixed
- `requirements.txt` missing line break; gallery-dl no longer run via `python -m` (broken in the frozen exe)

## [2.4.0] - 2026-10-05 - URL Video Downloader

- **URL Video Downloader** — send any supported URL directly to the bot to download:
  - YouTube (`youtube.com/watch`, `/shorts`, `youtu.be`)
  - X / Twitter (`x.com/.../status/...`, `twitter.com/.../status/...`)
  - Pornhub (`pornhub.com/view_video.php?viewkey=...`, `interstitial?viewkey=...` auto-converted)
  - Folder selection keyboard appears after metadata is fetched, same UX as Telegram media
  - Real-time download progress updates every 3 seconds (%, speed MB/s)
- **pHash Duplicate Detection for URL Downloads**:
  - `src/phasher.get_video_phash_from_path()` computes hash directly from file path (no memory load)
  - Hash used as `file_unique_id` in the database; duplicate files are rejected and removed
  - Graceful fallback to `{prefix}_{size}_{url_hash}` when cv2/ImageHash not installed
- **`web/` Package** — modular URL downloader architecture:
  - `web/url_parser.py` — URL detection (`extract_url`, `detect_type`) and dispatch (`handle_url`, `download_confirmed`)
  - `web/youtube_downloader.py` — YouTube via yt-dlp, best mp4 format
  - `web/x_downloader.py` — X/Twitter via yt-dlp with Firefox cookie passthrough
  - `web/p_downloader.py` — Pornhub via yt-dlp; `_interstitial_transfer()` normalises interstitial URLs to `view_video.php`
- **`src/folder_navigator.py`**: added `pending_url` and `url_type` fields to `NavigationState` for URL download flow
- **Dependencies**: added `yt-dlp`, `opencv-python`, `ImageHash`, `numpy`

## [2.1.0] - 2026-04-15 - Inline Keyboard Folder Navigation

- **Inline Keyboard Folder Navigation** (v2.1.0):
  - Replaced text commands (`/cr`, `/cd`, `/cd..`, `/ok`) with Telegram inline keyboard buttons
  - Subfolder buttons displayed in a grid (2 per row, truncated to 18 chars)
  - `⬆️ 返回上級` button appears only when not at root; `✅ 確認這裡` always visible
  - `📝 新建資料夾` button prompts user to type a folder name as a plain text message
  - Bot deletes the user's typed name and updates the navigation message seamlessly
- **Previous Path History** (v2.1.0):
  - Up to 5 previously confirmed paths stored per user session
  - Up to 3 `🕐 /path` quick-select buttons shown at the bottom of the keyboard
  - Only paths that still exist on disk are shown
  - History is preserved across downloads (survives `clear_user_state`)
  - Most recently confirmed path always appears first; duplicates are deduplicated
- **Bot Internals**:
  - Added `CallbackQueryHandler` in `bot.py` routing all `fn_*` callback data
  - `_start_download_with_selected_folder` now takes `user_id` + `processing_msg` directly (no `Update` dependency)
  - `FolderNavigator._generate_folder_ui` returns `(text, InlineKeyboardMarkup)` tuple throughout

## [2.0.0] - 2025-08-15 - Architecture Refactoring

- **Architecture Refactoring**:
  - Moved UI module from root to `src/ui.py` for better organization
  - Enhanced `main.py` with unified CLI/GUI entry point and argument parsing
  - Added PyInstaller stdin/stdout fixes for GUI applications
  - Removed deprecated `run_gui.py` file
- **Database Improvements**:
  - Major refactoring of `src/database.py` (224 line changes)
  - Enhanced database operations and schema management
- **Configuration Updates**:
  - Enhanced build configuration and installer settings
  - Improved config validation and error handling
- **Project Structure**:
  - Consolidated GUI components under `src/` directory
  - Updated build scripts and version management
  - Enhanced Windows installer configuration

## [1.2.0] - 2025-08-14 - Download Optimization

- **Download Optimization**: Start download from the smallest file.

## [1.1.1] - 2025-08-14 - Show Skipped Files

- **Show Skipped Files**: Skipped files are now visible in the frontend.

## [1.1.0] - 2025-08-13 - CI/CD Integration

- **CI/CD Integration**: GitHub Actions for automated deployment.

## [1.0.0] - 2025-08-13 - GUI Application Release

- **GUI Application Release**:
  - Full-featured desktop GUI with tabs (Config, Logs, Control).
  - System tray support, real-time logs, session authentication.
  - Config auto-save with validation.
- **Windows Installer**:
  - One-click installer with auto-update, no Python required.
- **Documentation Consolidation**:
  - Combined and streamlined all setup and usage guides.

## [0.5.1] - 2025-08-11 - bot.py Refactor

- **Refactor**: Improved code structure in `bot.py`.

## [0.5.0] - 2025-08-11 - Interactive Folder Navigation

- **Interactive Folder Navigation**:
  - Real-time folder selection with commands.
  - Multi-language support and visual feedback.
- **Improved UX**: Cleaner workflow and user state handling.

## [0.4.0] - 2025-08-06 - SQLite Integration

- **SQLite Integration**:
  - Persistent download history and duplicate prevention.
- **Download Management Enhancements**:
  - Smarter logging, error tracking, and statistics.

## [0.3.1] - 2025-08-06 - Media Group Support

- **Media Group Support**:
  - Detect and download grouped media (albums).
  - Intelligent fallback strategies and improved organization.

## [0.3.0] - 2025-08-06 - Modular Refactor

- **Major Code Refactor**:
  - Split monolithic bot into modular components.
  - Improved maintainability and testing.
- **Download Metrics**:
  - Show file sizes, percentages, and ETA.

## [0.2.1] - 2025-08-06 - Improved Reliability

- **Improved Reliability**:
  - Retry logic, progress persistence, and better error handling.

## [0.2.0] - 2025-08-05 - Backup Mode

- **Backup Mode**:
  - Removed upload/ZIP features, now stores files locally only.

## [0.1.1] - 2025-08-05 - Docs Fix

- **Docs Fix**: Corrected README structure and setup instructions.

## [0.1.0] - 2025-08-05 - Initial Release

- **Initial Release**:
  - Basic Telegram bot for media downloads.
  - ZIP packaging, config management, error handling, and documentation.

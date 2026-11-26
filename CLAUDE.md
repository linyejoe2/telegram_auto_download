# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Telegram bot (v3.6.3) that automatically downloads media files from forwarded messages and their replies to the server for backup purposes. Features a professional GUI application with Windows installer, per-file download records (hidden sidecars, no database, v3.3.0) for download history and duplicate prevention, inline-keyboard folder navigation with path history, and uses both Telegram Bot API (python-telegram-bot) and Telegram Client API (Telethon) for comprehensive functionality.

## Development Commands

### Running the Application

```bash
# GUI Mode (default on Windows)
python main.py

# CLI Mode (explicit)
python main.py --cli

# GUI Mode (explicit)
python main.py --gui
```

### Building Windows Installer

```bash
# Complete build process (requires Python 3.8+, Node.js 18+ and Inno Setup; step 5 runs npm ci && npm run build in frontend/)
package_windows.bat

# Full rebuild (new build_env, no PyInstaller cache), v3.0.2
package_windows.bat fresh
```

### Building the Web Library Frontend (v3.0.0)

```bash
# Outputs to library/static (gitignored); needed when running the web library from source
cd frontend && npm install && npm run build
```

### Installing Dependencies

```bash
pip install -r requirements.txt
```

### Version Management

Use the `/update-release <version> <changes>` command (`.claude/commands/update-release.md`): it bumps the version in `app.manifest`, `installer.iss`, `package_windows.bat`, `create_version_info.py`, `src/__init__.py`, `src/ui.py`, `README.md` and this file, then updates the docs.

### Build Environment Setup

```bash
# Setup build environment for Windows packaging
setup_build_env.bat
```

## Architecture

### Core Components

### GUI Application Components
- **src/ui.py**: Main GUI application with tkinter interface and system tray integration (v1.0.0, migrated to src/ in v1.3.0); has a "Web Library" tab to start/stop the web video library and set its port, access, startup and password (v3.0.0); Database tab has a "Clean Empty Files" button (`clean_empty_files()`: background scan via `DownloadRecords.empty_unsourced_files()`, shows count + first 15 paths, Yes/No confirm, background delete, reports deleted/failed, refreshes the list; v3.3.2); "Diagnostics" tab (`setup_diagnostics_tab()`, v3.6.1): live table (every 2 s only while the tab is open, Live checkbox) of CPU per app thread / child process + summary line (% of one core and of the whole machine) + status lines per component (`_diagnostic_state()`: bot / web library / AI 辨識 / people database; v3.6.2: the web library line also shows how long the last folder scan took (`Library.last_scan_seconds`) and lists the files still being written (`deferred_paths`)), thread names (v3.6.2: the asyncio default executors are named, `bot-worker` for the bot loop in `run_bot()` via `loop.set_default_executor(ThreadPoolExecutor(thread_name_prefix='bot-worker'))`, `web-library-worker` for the web library loop in `LibraryServer.start_in_thread()`; both used to be `asyncio_N` and could not be told apart), `refresh_diagnostics()`, "Profile 10 s" (`run_profile()`, background thread) and "Dump Thread Stacks" (`dump_stacks()`), reports saved as `cpu_profile_<time>.txt` / `thread_stacks_<time>.txt` in `config.LOGS_DIR` and shown by `_show_report()` with Copy
- **src/diagnostics.py** (v3.6.1): `CpuMonitor.sample()` (Windows Toolhelp32 thread / process snapshots + GetThreadTimes / GetProcessTimes via ctypes, no new dependency; kernel32 is loaded with `ctypes.PyDLL` on 64-bit so the calls keep the GIL, with `WinDLL` a busy Python thread made one sample take seconds; rows sorted by CPU, named Python threads / processes before native threads), `python_threads()`, `profile(seconds, hz, state)` (samples every Python thread's stack, 3 most common stacks per thread), `dump_stacks()`; live CPU is Windows only, the profile works everywhere
- **src/chromium_helper.py**: Chromium check/install for screenshots (`check_chromium()`, `install_chromium()` via Playwright's bundled node driver, `ensure_browsers_path()` pins `PLAYWRIGHT_BROWSERS_PATH` to `%LOCALAPPDATA%\ms-playwright` on Windows, v2.5.0)
- **src/auth_helper.py**: GUI and console authentication helper for Telethon client (v1.0.0)

### Core Bot Components
- **main.py**: Unified entry point supporting both CLI and GUI modes with command-line arguments
- **src/bot.py**: Main bot logic and message handling (`TelegramMediaBot` class)
- **src/downloader.py**: Media download operations with concurrent processing (`MediaDownloader` class)
- **src/monitor.py**: Real-time monitoring and progress tracking (`DownloadMonitor` class)
- **src/records.py**: `DownloadRecords` (singleton) download history and duplicate prevention; replaces `src/database.py` / `DatabaseManager` and the SQLite database (v3.3.0). Each file's record is the `download` key of its hidden sidecar `.<file>.meta.json` (shared with the web library; keys file_unique_id, file_id, message_id, chat_id, file_name, original_file_name, file_size, file_type, mime_type, download_date, message_date; v3.4.0 adds the optional `description` via `record_download(description=...)`, max 5000 chars, the Telegram message text, only fills an empty field so a description edited in the web library is not overwritten; `file_path` derived from the sidecar location). In-memory index built by walking the folder (`os.scandir`, sidecar reads cached by mtime), rebuilt in a background thread when older than `REFRESH_SECONDS`=120, switches when `DOWNLOADS_PATH` changes. Methods: `is_file_downloaded`, `get_downloaded_file_info` (adds `deleted`), `is_url_downloaded`, `find_download` (own sidecar, fallback a left-behind sidecar with the same name + size), `record_download`, `get_download_statistics`, `get_recent_downloads`, `cleanup_missing_files`, `forget_file(path)`, `file_moved`/`folder_moved`, `all_records`, `history(q, status, kind, offset, limit)`, `get(key)`, `refresh()`. `<downloads>/.tad/deleted.json` (`{"version":1,"records":{uid: record + file_path(rel) + deleted_date}}`): `forget_file()` moves the record there (keeping title/actors/series/source/description (`KEPT_LIBRARY_FIELDS`, v3.4.0) under `library`, removing the sidecars and the bot's compressed copy); deleted downloads count as downloaded (startup scan / `/rescan` don't offer them) and so do sidecars whose file is missing; a new download of the same id or URL removes the deleted entry and restores the kept fields. `plan_redownload(path)` -> `(record, note)` or `(None, reason)` for a broken file (v3.3.1): 1) the file's own sidecar record; 2) a deleted / left-behind record with the same file name (same size first, then same folder); 3) no record (interrupted downloads): the Telegram message id parsed from the file name (`<id>_<name>`, `photo_<id>_<date>`, `document_<id>_<date>`) plus `_candidate_chats(path)` (channels of recorded files, nearest folder first, then by frequency, max 20) as a guess record with `candidate_chats`; otherwise None ("請把原訊息重新轉傳給 Bot"). Migration on first use: `<downloads>/.tad/downloads.db` (v3.2.0) or the legacy `<app dir>/downloads.db` is imported (existing files -> sidecar `download`, others -> `deleted.json`, UTC `download_date` converted to local time) and renamed `downloads.db.migrated` (v3.3.0). `empty_unsourced_files(min_age=600)` lists 0-byte non-hidden files (hidden folders skipped, old `.part` leftovers included) with no source link (neither `source_link()` of `find_download()` nor a web-library 來源) and not modified in the last 10 minutes; `delete_files(paths)` -> (deleted count, error texts) removes each file and calls `forget_file()` (v3.3.2)
- **src/folder_navigator.py**: Interactive folder navigation and path management system
- **src/chat_scanner.py**: `/chats` helpers (v3.4.0): `list_chats(client, query)` (joined groups / channels, most recent first), `render_chat_list(chats, page, query)` (10 per page, callbacks `ch_pick:<i>`, `ch_pg:<page>`, `ch_x`; 👥 group / 📢 channel), `is_photo()`, `scan_chat()` (whole history with `InputMessagesFilterPhotoVideo`, oldest first, returns ids not downloaded yet + album captions + counts/size, `on_progress` / `should_stop`), `scan_summary()`, `load_jobs()` / `save_job()` / `remove_job()` (`<downloads>/.tad/chat_jobs.json`, `{version, jobs: {chat_id: {chat_id, title, folder (relative), user_id, started}}}`, atomic write)
- **src/file_viewer.py**: Chat file viewer (`FileViewer`, `build_preview`, `source_link`, plus `list_videos`, `build_batch_preview`, `build_frame_preview`, `PreviewBatch` for folder video previews, v2.7.1) for `/files` (v2.7.0)
- **config/config.py**: Configuration management using environment variables from `.env` file (`get_web_settings()` for the web library, v3.0.0; `get_max_threads()` (`MAX_THREADS`, default `DEFAULT_MAX_THREADS` 16, clamped to 1..cores, v3.6.3) and `apply_thread_limit()` (sets the OMP / OPENBLAS / MKL / NUMEXPR thread env vars and `cv2.setNumThreads`; `main.py` calls it before numpy / cv2 are imported); `get_ai_settings()` -> `{ollama_url (default http://localhost:11434), ollama_model ('' = first vision model)}` from `OLLAMA_BASE_URL` / `OLLAMA_MODEL`, v3.5.0; v3.2.0: `DATA_DIR_NAME = '.tad'`, `get_downloads_dir()`, `get_data_dir()`, `get_database_path()`, `get_legacy_database_path()` (v3.3.0: only used to migrate old databases), `DATABASE_PATH` removed)

### Web Library Components (v3.0.0)
- **library/**: aiohttp backend of the web video library: `media.py` (ffprobe/ffmpeg, sidecar metadata; v3.6.3 `thread_limit(share=1)` / `threads_args(share)`: every ffmpeg gets `-threads` (input and output) for its share of `MAX_THREADS`: screenshots (2 workers -> half each), live transcode, face-recognition frame grabs (`recognize._video_frames`, `min(4, limit)` in parallel -> a quarter each), deep compare `_curves` / `_frame`; with an NVIDIA GPU the live transcode runs on the GPU; pools: web library default executor and bot executor `max_workers = max(2, limit)`, screenshot pool `min(2, limit)`), `store.py` (`Library`), `auth.py` (password/session), `deep_compare.py` (enhanced compare of two videos, v3.4.8), `recognize.py` (AI 辨識 of 主演 / 系列: face models + Ollama, v3.5.0), `people.py` (人物資料庫 behind the 主演 tags, v3.6.0), `server.py` (`LibraryServer`)
- **frontend/**: React 18 + Vite 6 + Tailwind CSS 4 (react-router) UI; `npm run build` outputs to `library/static` (gitignored, bundled by `telegram_bot.spec`)

### URL Downloader Components (web/ package)
- **web/url_parser.py**: URL detection (`extract_url`, `detect_type`, `extract_x_username`) and dispatch (`handle_url`, `download_confirmed`); types include `youtube`, `x`, `pornhub`, `x_profile` (v2.5.0)
- **web/youtube_downloader.py**: YouTube via yt-dlp
- **web/x_downloader.py**: X/Twitter single-post video via yt-dlp with Firefox cookies
- **web/p_downloader.py**: Pornhub via yt-dlp
- **web/x_profile_downloader.py**: X account downloader (gallery-dl scan + media download + Playwright screenshots, v2.5.0)

### Windows Installer Components
- **package_windows.bat**: Complete build automation script (v1.0.0)
- **telegram_bot.spec**: PyInstaller configuration for executable creation (v1.0.0); v3.5.0: hiddenimport `library.recognize` and (v3.6.0) `library.people`, (v3.6.1) `src.diagnostics`, and `library/models` (face models, not in git) is added to `datas` only when it holds `.onnx` files
- **installer.iss**: Inno Setup installer configuration (v1.0.0)
- **create_version_info.py**: Version information generator for Windows executable (v1.0.0)
- **create_icon.py**: Application icon generator (v1.0.0)

### Key Architecture Patterns

1. **Dual Interface Design**: Application supports both GUI and command-line interfaces
   - **GUI Mode**: Professional Windows application with system tray integration
   - **CLI Mode**: Traditional command-line interface for advanced users and development

2. **Dual API Usage**: The bot uses both Telegram APIs:
   - **python-telegram-bot**: For bot interactions and message handling
   - **Telethon**: For accessing Telegram Client API to retrieve forwarded messages and their replies

3. **Professional Deployment**: Complete Windows installer package
   - **PyInstaller Integration**: Single executable with all dependencies bundled
   - **Inno Setup**: Professional installer with shortcuts and auto-upgrade support
   - **Build Automation**: Complete build pipeline from source to installer
   - **CI/CD Integration**: GitHub Actions for automated deployment (v1.1.0)

4. **Async/Await Pattern**: All operations are asynchronous using Python's asyncio

5. **Environment-based Configuration**: All credentials and settings loaded from `.env` file

6. **Modular Architecture**: Code organized into specialized modules:
   - **Separation of Concerns**: Each module has a single responsibility
   - **Clean Dependencies**: Clear interfaces between components
   - **Testability**: Individual modules can be tested independently

### Data Flow

1. User forwards a message or media group to the bot
2. Bot detects if message has `media_group_id` and collects all grouped messages
3. Bot extracts original chat and message information from forward metadata
4. `DownloadRecords` checks for existing downloads to prevent duplicates (v0.4.0, v3.3.0)
5. Uses Telethon client to access the original message, media groups, and all replies
6. `FolderNavigator` presents inline keyboard UI with subfolder buttons, up/confirm/create actions, and previous-path history (v2.1.0)
7. User navigates folders by tapping inline buttons; types a name only when creating a new folder (v2.1.0)
8. (v2.6.1) Every request goes through the per-item queue (`submit_flow`): the folder selector (step 6) appears only when it is the item's turn, so nothing downloads into a pre-chosen folder
9. Downloads all media files concurrently using `MediaDownloader` to user-selected folder (v0.5.0)
10. `DownloadRecords` records download metadata beside the file (v0.4.0, v3.3.0)
11. `DownloadMonitor` provides real-time progress updates with speed/disk usage stats
12. Provides completion summary with performance metrics and storage location

### Key Classes and Methods

#### `TelegramMediaBot` (src/bot.py)
Main orchestration class that coordinates all bot operations:
- `start_client()`: Enhanced authentication with session validation and GUI support (v1.0.0)
- `handle_message()`: Processes forwarded messages, folder name input, and routes to group/single processing
- `handle_files_command()`: Owner-only `/files [path]` command (registered in the Telegram command menu via `set_my_commands`); `owner_id` is the Telethon session account (`get_me()`), others get "⛔ 只有 Bot 擁有者可以瀏覽檔案"; `_send_preview()` sends an image or 3 video screenshots (v2.7.0); `_send_preview_batch()` sends folder video previews as albums of 10 (1 screenshot per video, v2.7.1)
- `handle_callback_query()`: Routes inline keyboard button presses (`fn_cd`, `fn_up`, `fn_ok`, `fn_cr`, `fn_prev`) (v2.1.0); `fv_*` callbacks go to `_handle_file_viewer_callback` (owner only, v2.7.0); `xp_media` / `xp_both` / `xp_shot` (X profile mode choice) are routed to `XProfileDownloader.on_mode_chosen` before the `fn_*` guard (v2.5.0)
- `_handle_media_group()`: Collects and processes media group messages
- `_download_and_monitor()`: Shared download and monitoring logic
- `get_message_and_replies()`: Retrieves original message and replies using Telethon with enhanced error handling
- `submit_flow()` / `enqueue_flow()` / `_queue_worker()`: Serial request queue of `FlowItem`s (v2.6.1); bot keeps accepting messages during downloads, waiting items show their queue position, each item gets its own folder selector (shown only after the previous download finishes, 30-minute timeout, `❌ 取消` skips); queue is in-memory
- `_handle_tme_link()` / `parse_tme_link()`: owner-only `t.me/<user>/<id>` and `t.me/c/<id>/<id>` links (`?single` = that message only) are read via the Telethon user session (`get_message_and_replies`, album via `_collect_media_from_original`) and queued with `submit_flow`; works for chats with "restrict saving content" (v2.7.7)
- `handle_chats_command()` / `_handle_chats_callback()` (v3.4.0): owner-only `/chats [keyword]` (registered in the command menu) lists the joined groups / channels via `chat_scanner.list_chats()` (`_chat_lists`); callbacks `ch_pick:<i>`, `ch_pg:<page>`, `ch_x`, `ch_scanstop` (✖ 停止掃描), `ch_stop:<chat_id>` (⏹ 停止下載) are handled before the `fn_*` guard
- `_scan_chat_and_queue()` / `_present_chat_job()` (v3.4.0): picking a chat scans it in a task (`_chat_scanning`, progress + stop button; already downloaded items, deleted ones too, are skipped at scan time via `_is_media_downloaded`), then `submit_flow` queues the job; on its turn the summary (`scan_summary()`) is shown above the folder selector and `NavigationState.pending_job` (`partial(_run_chat_download, job)`) runs after the folder is confirmed
- `_run_chat_download(job, folder, status)` / `_download_chat_ids()` / `_stop_chat_download()` (v3.4.0): saves the job with `chat_scanner.save_job()` (folder relative to the downloads folder), downloads the not-yet-downloaded ids straight into the folder with `max_concurrent_downloads` (5) workers; a producer fetches messages in batches of `CHAT_BATCH` = 50 (fresh file references, FloodWait waits), calls `describe(msgs, captions=...)` and re-checks each message against the records; ticker edits the progress every 5 s with the stop button; stopping (`_chat_run`) cancels the task and removes the half-written `.part`; stop / completion / failure remove the job, a bot shutdown keeps it
- `_resume_chat_jobs()` / `_present_resumed_chat_job()` (v3.4.0): called from `run()` at start; queues every job left in `chat_jobs.json` with `enqueue_flow` (folder confined to the downloads folder), sends "⏯ 繼續上次未完成的下載", rescans (`job['scan']` absent) and continues, skipping what is already there
- `_startup_scan()` / `_present_scan_unit()`: On start, checks the user's last `STARTUP_SCAN_COUNT` own messages to the bot (Telethon) against the download records and queues undownloaded channel posts/albums and X/YouTube links (X account links not scanned) (v2.6.1)
- `handle_rescan_command()` / `_scan_recent(limit, manual)`: owner-only `/rescan [count]` runs the startup scan again (registered in the command menu); `_scan_items` maps each scan unit key to its queued `FlowItem` so units still waiting are not queued twice; always reports the result in the chat (v2.7.6)
- `run()`: Main bot startup and event loop management

#### `MediaDownloader` (src/downloader.py) 
Handles all download operations with concurrent processing:
- `download_multiple_messages_concurrent()`: Manages concurrent download tasks
- `download_media_with_retry()`: Downloads with retry mechanism, exponential backoff, and progress tracking
- `download_media_from_message()`: Downloads media files with smart naming and type detection
- `describe(messages, root=None, captions=None)` / `DESCRIPTION_ATTR = 'tad_description'` (module level, v3.4.0): sets each message's description to its own text, else the album caption (`captions` {grouped_id: text} or the other messages), else the `root` post's text (replies); called by every Telegram flow (forward, album, t.me link, startup scan / `/rescan`, `/chats`, re-download); `download_media_from_message()` passes it through `_record_download_to_db` to `DownloadRecords.record_download(description=...)`; files downloaded before 3.4.0 have none
- `file_name_for(message)` (static, v3.3.1): the naming rule moved out of `download_media_from_message()` (behaviour unchanged), returns `(file name, file type, original name, mime)`; used to match a source message to a broken file
- `get_media_size()`: Calculates file sizes before download for progress tracking
- `save_progress()` / `load_progress()`: Progress persistence for resume capability

#### `DownloadMonitor` (src/monitor.py)
Real-time monitoring and progress tracking:
- `start_monitoring_thread()`: Background monitoring thread for progress and system stats
- `safe_update_message()`: Non-blocking message updates during downloads
- `calculate_speed()` / `calculate_eta()`: Performance metrics calculations
- `get_disk_usage()`: System resource monitoring

#### `FolderNavigator` (src/folder_navigator.py)
Inline keyboard folder navigation and path management (v2.1.0):
- `start_folder_selection()`: Initiates folder selection, returns `(text, InlineKeyboardMarkup)`
- `navigate_into(user_id, folder_index)`: Enters subfolder by button index
- `navigate_up(user_id)`: Goes up one directory level
- `navigate_to_history(user_id, history_index)`: Jumps to a previously confirmed path
- `create_folder_and_navigate(user_id, folder_name)`: Creates folder from user text input and navigates into it
- `confirm_selection(user_id)`: Confirms path, updates history (max 5 entries, most recent first); history is saved to `<downloads>/.tad/history.json` (`_load_history`/`_save_history`, atomic write, v3.2.0)
- `_generate_folder_ui`: skips dot entries, so `.tad` and the library's `.<file>.shots` are not listed (v3.2.0)
- `get_selected_path()`: Returns absolute path of current selection
- `is_awaiting_folder_selection()` / `is_awaiting_folder_name()`: State guards for message routing
- `NavigationState.pending_job` (v3.4.0): optional async `job(folder, message)` that `_confirm_selection()` runs after `fn_ok` confirms the folder instead of the normal download (used by `/chats`)
- `clear_user_state()`: Resets navigation state while preserving path history

#### `FileViewer` (src/file_viewer.py)
Inline-keyboard browser of the downloads folder for `/files` (v2.7.0):
- `start(user_id, arg)` / `handle_callback(user_id, data)`: Render list/detail/confirm views, return `ViewResult(text, markup, preview_path)`; callbacks use the `fv_` prefix: `fv_cd`, `fv_f`, `fv_up`, `fv_pv`, `fv_pva`, `fv_pn`, `fv_back`, `fv_prev`, `fv_del`, `fv_deld`, `fv_yes`, `fv_no`, `fv_close` (`fv_pg` removed in v2.7.1; `fv_f` restored in v2.7.4)
- Listing (v2.7.1, modeled on `FolderNavigator._generate_folder_ui`): no paging; all sub folders in a 2-per-row grid (names cut to 18 chars), text shows folder/video/photo/file counts + total size; empty folder offers `🗑 刪除此資料夾`; the newest `MAX_FILE_BUTTONS` (30) files of the level are listed below the folders as `fv_f:<index>` buttons (index into `state.entries` = folders + shown files) opening the detail view (also via `/files <file path>`); hidden files and `.part` hidden; all paths confined to the downloads folder (`..`, absolute paths, outside symlinks rejected)
- Folder video preview (v2.7.1): `fv_pv` (`🎞 預覽資料夾影片 (n)`, this level, shown only if it has videos) and `fv_pva` (`🎞 預覽資料夾內所有影片 (n)`, recursive, shown only if sub folders add videos); `list_videos()` collects videos, `build_batch_preview()` returns a `PreviewBatch` of up to 10, each with ONE screenshot (`build_frame_preview()`: 15s, middle frame for videos under ~16s), caption = path relative to the browsed folder + timestamp + source link; `fv_pn` (`▶️ 下一頁（剩餘 n 部）`) sends the next 10 as a new album, previous albums kept, only the control message replaced, shows `已預覽 x/y 部影片`, unreadable videos skipped and counted
- Folder photo loading (v2.7.3): `fv_ph` (`🖼 載入照片 (n)`, this level) and `fv_pha` (`🖼 載入所有照片 (n)`, recursive) reuse the `fv_pn` lazy paging; `list_photos()`/`list_media()` collect files, `build_batch_preview()` returns a thumbnail per photo (`build_image_preview()`), `ViewState.preview_kind` is `video` or `photo`
- Detail view shows size, mtime, location, video duration/resolution, download time and the source link (`source_link()`: `t.me/c/<channel>/<message>`, original YouTube/X/Pornhub URL, `x.com/i/status/<id>` for X profile downloads, "未知" if unknown); record from `DownloadRecords().find_download(file_path)` (match by path, fallback file name + size)
- `build_preview(path)` (single-file `🖼 預覽`, unchanged in v2.7.1): image -> 1 photo; video -> 3 OpenCV frames (15s, middle, 15s before end; <45s uses 10%/50%/90%), run in an executor
- Load video (v2.7.5): detail view `fv_load` -> `ViewResult.load_path` -> `TelegramMediaBot._load_video()` uploads via `upload_client` (second Telethon session `bot_upload_session` logged in with the bot token, started in `run()`; resolves the chat from updates it received) with `DocumentAttributeVideo` + thumbnail; `src/video_loader.py`: `needs_compression()` (>500 MB or >4000 kbps), `compress_video()` (ffmpeg libx265, 720p, 2000 kbps, aac 128k, v3.6.3: `-threads` + x265 `pools=` from `MAX_THREADS`, progress shown in the status message), result stored as hidden `.<name>.720p_h265.mp4` (`compressed_path()`, re-used via `existing_compressed()`); needs ffmpeg in PATH or `FFMPEG_PATH` (not bundled)
- Delete with confirmation: files and empty folders only; deleting calls `DownloadRecords().forget_file()` (`_forget`), which moves the record to `deleted.json` so the startup scan does not re-offer the file and the 下載紀錄 page lists it (v3.3.0)

#### `XProfileDownloader` (web/x_profile_downloader.py)
Downloads media and/or screenshots of a whole X account (v2.5.0):
- `start_flow(username, user_id, processing_msg)`: Scans the account with gallery-dl (in-process `gallery_dl.job.DataJob`, Firefox cookies; ~3,200 post limit; retweets excluded), replies with post/video/photo counts and the mode buttons (`xp_media`, `xp_both`, `xp_shot`)
- `on_mode_chosen(mode, user_id, message, folder_navigator)`: Stores the mode, shows the folder keyboard (`url_type = 'x_profile'`)
- `download(user_id, dest_dir, processing_msg)`: Output to `<folder>/x_<username>/` (screenshots in `screenshots/`); media concurrent (5), named `<tweetid>_<n>.<ext>`, deduped by file existence and record id `xprofile_<tweetid>_<n>`; screenshots via Playwright Chromium (3 concurrent); posts without media are never downloaded/screenshotted
- Notes: gallery-dl must run in-process (frozen exe's `sys.executable` is the app, so `python -m gallery_dl` fails). Requires being logged in to X in Firefox. Screenshots need Chromium: use the GUI Install button (or `playwright install chromium` from source); not bundled by PyInstaller, media download works without it

#### `LibraryServer` / `Library` (library/, v3.0.0)
Web video library (watch and manage downloaded videos in a browser; Telegram/system settings stay in the Windows app):
- `Library` (`store.py`): `scan()` walks the downloads folder (files changed in the last `SETTLE_SECONDS`=90 are deferred as still being written, `deferred` makes the next rescan come after 60 s; v3.0.2; v3.6.2: `_still_changing(mtime)` only counts modified times up to 60 s in the future / `SETTLE_SECONDS` in the past, because a file dated in the future (wrong clock, copied from another PC) used to count as still being written forever and made the library rescan the whole folder every minute instead of every 5; `scan()` records `deferred_paths` (first 5 files still being written) and `last_scan_seconds`) (video id = base64url of the relative path, `encode_id`/`decode_id`, `resolve()` confines to the folder); 2 background workers (`queue_refresh()`/`_refresh()`) fill missing info and screenshots; source auto-filled from the download record (`_lookup_source` via `find_download`/`source_link`); `list()`, `detail()`, `update()`, `delete()`, `tags()`, `processing()`; folder / file management (v3.0.1): `folders()`, `create_folder()`, `rename_folder()`, `delete_folder()` (empty only), `rename_video()` (keeps the extension), `move(video_ids, folders, dest)`; `_move_video()` carries the hidden sidecars (`_sidecars()`: meta, shots, `.720p_h265` copy), `check_name()` validates names, `_check_not_busy()` refuses videos still being processed, errors are `LibraryError(message, status)`
- `library/media.py`: `probe_info()` (ffprobe: width/height, bit rate, video bit rate, bit depth, codec/profile, fps, audio codec/channels/sample rate, duration, size), `make_screenshots()` (9 via ffmpeg), `direct_playable()`/`mime_codecs()`, `load_meta()`/`save_meta()`, `remove_sidecars()`; sidecars are hidden files next to the video: `.<file>.meta.json` (title, actors[], series, source, cached info) and `.<file>.shots/01.jpg..09.jpg` (the chat `/files` viewer skips dot files); web delete also removes the hidden `.720p_h265` copy
- `library/auth.py`: `hash_password()`/`verify_password()` (PBKDF2, `WEB_PASSWORD_HASH`), `Sessions` (HMAC-signed cookie with `WEB_SECRET`; changing the password invalidates all sessions; 5 wrong passwords -> 15 min lockout per client)
- `LibraryServer` (`server.py`, aiohttp; `start_in_thread()`/`stop_thread()` used by the GUI and CLI; v3.6.2: `start_in_thread()` names its loop's default executor `web-library-worker`). v3.1.1: every route below is under `PREFIX` = `/library` (frontend at `/library/`, `/` is a blank page, `/library` redirects (v3.4.9: `to_app` keeps the query string, because React Router writes the library page as `/library?folder=…` and a reload must keep the folder / filters / sort); session cookie path `/library`, `_session_tokens()` accepts any cookie value so a stale `/` cookie from older versions doesn't block login; `store.MEDIA_URL`; frontend `api.js` `BASE`/`API`/`MEDIA`, vite `base: '/library/'`, `BrowserRouter basename`): `/api/login|logout|session|status|videos|videos/{id}` (GET/PATCH/DELETE)`|videos/{id}/screenshots|tags|rescan`, `/api/folders` (GET/POST), `/api/folders/rename|delete`, `/api/videos/{id}/rename`, `/api/move` (v3.0.1); `/media/{id}/file` (HTTP range), `/media/{id}/stream?t=&q=<level>` (v3.4.1, was `h=480|720|1080`; live ffmpeg transcode to fragmented H.264/AAC MP4 via `media.stream_command()`; no range support so Safari/iOS cannot play it; `q` is a `STREAM_LEVELS` key, unknown -> `STREAM_DEFAULT` `720h`; `media_stream` picks `media.stream_encoder()` in an executor and, if the GPU encoder yields no output, restarts that stream on the CPU; `STREAM_HEIGHTS` removed), `/media/{id}/shots/NN.jpg`; serves `library/static` with SPA fallback; rescans every 5 min; security headers; paths confined to the downloads folder
- Frontend (`frontend/`): pages Login, Library (left `FolderTree` with drag & drop move, right-click `ContextMenu` / `PromptDialog` from `components/Dialogs.jsx`, card/list view switch stored in localStorage `tad.view`, list shows bit rate + 畫質 sort (short side, then bit rate, v3.0.2), search (v3.4.0: also matches `description`, placeholder 搜尋標題、主演、系列、描述、資料夾…), filter 主演/系列, sort (v3.6.3 `SORTS` also has 系列: series name, items without one last, then title, the list view's 系列 header toggles it like 畫質; and 隨機: random but fixed by `?seed=` in the URL, `randomKey()` = FNV-1a of seed + id (the group id for versions), so reloads, the background refresh, edits and coming back keep the order and scroll position, new items land in random places, swiping between videos follows it; a 🎲 button next to the menu picks a new seed and scrolls to the top; `setSort()` drops the seed for other sorts, a URL with sort=random but no seed gets one; unknown sort values fall back to 最新加入), filters in URL; v3.0.1; v3.4.9 scroll memory: the scroll position is saved per view (the query string = folder / search / filters / sort / kind) in sessionStorage `tad.scroll:<query>` via `api.js` `readSession()` / `writeSession()` (try/catch), a restore effect runs once after `videos` loads, the scroll listener (`useLayoutEffect`, throttled 150 ms) saves only after the restore so the short loading page can't overwrite it and flushes the last value on cleanup, `main.jsx` sets `history.scrollRestoration = 'manual'`; `VideoPage.jsx` scrolls to the top when opened, in a block-body effect because newer Chromium's `window.scrollTo` returns a Promise that React would take as the cleanup function), VideoPage (3x3 screenshots, edit title/actors/series/source/描述 (v3.4.0: `description` textarea after 來源, label "描述（Telegram 下載時為原始訊息的文字）", `formOf()` / dirty check carry it), Video Info, download, regenerate screenshots, delete); `components/Player.jsx` plays the original when `direct` and `canPlayType` allow, otherwise live transcode with custom controls (seek restarts the stream, ±10s, volume, fullscreen, Space/←/→/F); v3.4.1: 畫質 menu (`QualitySelect`) in both modes (in the control row in direct mode too since v3.4.5, replaces the old 480/720/1080 select in transcode mode): 原始 (only when `canDirect`, shows the file bit rate) + `video.qualities` [{key,label,kbps}]; switching keeps the position; v3.4.3: the start quality is the 設定 default (`initialQuality()` uses `settings.js` `defaultQuality()`: `levelAtMost()` picks the best offered level not above it; 原始 -> 原始 when playable else the best level) and a quality chosen in the menu applies to that video only (no longer saved, `tad.quality` is written only by the 設定 page); a failing original falls back to 720p 高 (not remembered); VideoPage Video Info 播放方式 says the quality is chosen in the player. v3.4.2 mobile: controls in two rows (time / seek bar / total, then play, ±10s, 畫質, fullscreen; `QualitySelect` shows only the short label over an invisible native `<select>` whose options keep the bit rates; volume slider `pointer-coarse:hidden`, 即時轉檔 label hidden under `sm`); controls auto-hide after `HIDE_AFTER` = 3 s while playing (`poke()`; mouse move shows, click toggles play; touch tap shows / hides, round middle play/pause button `pointer-fine:hidden`); seek bar commits on pointerup / pointercancel / touchend / keyup; the transcode player's box goes fullscreen (`navigationUI: 'hide'`), the video fills it with object-fit cover (填滿, default) or contain (完整) via a button shown only in fullscreen (localStorage `tad.fill`, read / written via `settings.js` `fillScreen()` / `setFillScreen()`, default set on the 設定 page), `setViewportFit()` adds `viewport-fit=cover` to the viewport meta only while fullscreen and the controls use `env(safe-area-inset-*)` padding, `screen.orientation.lock()` matches the video (unlocked on exit); original-file mode's F key fullscreens the `<video>` itself (iPhone `webkitEnterFullscreen()`; still the fallback when the box can't go fullscreen). v3.4.5 swipe between videos (`Player.jsx`, `VideoPage.jsx`, `api.js`, `Library.jsx`): original-file mode now uses the same custom controls as the transcode player (native `controls` and the bar under the video removed; label 原始檔 / 即時轉檔 in the control row, shortcut keys in button titles; Chrome's native speed / picture-in-picture / download menu is gone). New Player props `container` (the element that goes fullscreen), `nav` {prev, next, index, total}, `onSwipe(dir)`, `posterOf(dir)`; touch handlers sit on the player box (any touch except the control bar `[data-controls]`, `touch-action: pan-y pinch-zoom`): the picture follows the finger and the neighbor's first screenshot slides in beside it, release past `SWIPE_MIN` = 60 px or a flick (>= 30 px at > 0.5 px/ms) switches, else springs back (dx/4 resistance at the first / last video, touch cancel springs back); the round middle play button is hidden by opacity (not removed, so swipes starting on it work); counter `index / total · 左右滑動切換` top right with the controls. Order = the library page's order: `api.js` `saveList(back, videos)` / `listNeighbors(video, back)` keep `{back, items: [[id, group]]}` in sessionStorage `tad.list` (written by `Library.jsx` whenever `shown` changes, photos excluded), used only when `state.back` matches (pages opened from 下載紀錄 have no swipe; another version finds its place via the group). `VideoPage.jsx` keeps a stable `stage` div as the fullscreen element (stays on across videos), Player keyed `video.id`-`playFrom`, `swipeTo(dir)` navigates with `state.resume: 0` + `replace` (fetches the detail first if not cached; neighbors' details and first screenshots preloaded via `detailCache` / `preloaded`). Player: one module-level `fullscreenchange` listener resets `viewport-fit` and unlocks the orientation, orientation is locked again per video (`lockOrientation` on loadedmetadata), leaving fullscreen scrolls the player into view, `<video poster>` = first screenshot when starting at 0. v3.4.3 header / menu: `components/AppMenu.jsx` is the right side bar: a ☰ button (SVG icon) at the top right of every page (Library, VideoPage, History, Settings; `App.jsx` passes `onLogout` to every page) opens a drawer rendered with `createPortal` into `document.body` (the sticky headers use backdrop-blur, which would trap a fixed element) sliding in from the right (`--animate-slide-in-right` / `--animate-fade-in` in `index.css` `@theme`) with `PAGES` 🎬 媒體庫 `/`, 📜 下載紀錄 `/history`, 👥 人物 `/people` (v3.6.0), 🤖 AI 辨識 `/recognition` (v3.5.0), ⚙ 設定 `/settings` (current highlighted via `useLocation`) and 登出 (`api.logout()` then `onLogout()`) at the bottom; closes on the backdrop, ✕, Esc or after choosing; safe-area padding; the left side bar stays `FolderTree`. `Library.jsx` lost the 📜 下載紀錄 button (filter row) and the 登出 button (`logout()` removed), the card / list switch uses SVG grid / list icons; History and Settings have no "← 媒體庫" link (VideoPage keeps ← 返回). `pages/Settings.jsx` at `/settings`: radio cards for 預設播放畫質 (原始 + `LEVELS`, each with its cap and `perHourText()`) and 轉檔播放器全螢幕 填滿 / 完整, saved on change ("已儲存"); `settings.js` keeps the per-browser localStorage settings (`ORIGINAL` = `'orig'`, `LEVELS` / `RANK` mirror `media.STREAM_LEVELS` (keep in sync), `defaultQuality()` / `setDefaultQuality()` key `tad.quality`, default 原始, `fillScreen()` / `setFillScreen()` key `tad.fill`, `kbpsText()`, `perHourText()`). `VideoCard.jsx` (v3.4.3): nothing on the cover but the select-mode check (resolution / 🖼 / 版本 / duration / photo size badges removed); length (photo: W×H), resolution and `N 個版本` are one grey `·`-joined line under the title. Backend (v3.4.1, `library/media.py` "live transcode levels"): `STREAM_LEVELS` (key, label, short side, max video kbps, audio kbps: `2160` 16000/160, `1080h` 8000/160, `1080l` 4500/128, `720h` 4000/128, `720l` 2000/128, `480h` 1500/96, `480l` 800/96), `STREAM_DEFAULT`, `stream_level(key)`, `stream_qualities(info)` (a level is offered when the short side >= 90 % of its size or the long side >= 90 % of its 16:9 width; 480p always; sent as `qualities` in `GET /library/api/videos/{id}` by `Library.detail()`), `stream_encoder()` (tests NVIDIA `h264_nvenc` once, else libx264; `STREAM_ENCODER=cpu` forces CPU), `stream_command()` (fits the level's 16:9 box, turned for portrait, never upscales, `-maxrate` / `-bufsize` 2x, `-hwaccel cuda` with NVENC)
- Versions (v3.1.0, `library/similarity.py`): `ssim()` reproduces skimage's default SSIM with OpenCV, `similarity()` = mean over screenshots 1/5/9 (`SIG_SHOTS`), `load_signature()`/`build_signature()` cache the 320x180 grayscale frames as `sig.npy` in the shots folder (screenshots are read with `np.fromfile` + `cv2.imdecode`, not `cv2.imread`, which fails on non-ASCII paths on Windows; v3.4.6); `Library` keeps `_sigs` in memory, `threshold` (default `DEFAULT_THRESHOLD`=70), `check_all()` (full check after the first scan, sets `matching_ready`), `_match_new()` (after each refresh, calls `on_grouped(text)`), `_join()` (shared title / actors / series, merged tags), `ungroup()` (adds both `uid`s to `not_same`), `_versions()` in `detail()`; sidecar meta has `uid`, `group`, `not_same`; frontend collapses a group to its best version (`qualityKey`) and VideoPage switches 線路 with `state.resume`
- Photos (v3.3.0): `library/media.py` has `IMAGE_EXTS` (.jpg .jpeg .png .gif .webp .bmp), `is_image`/`is_media`/`kind_of`, `read_sidecar`, `set_download`, `process_image()` (OpenCV `np.fromfile` + `imdecode`: width/height/format/bit_depth/channels + thumbnail `.shots/01.jpg` max 640x1280; GIF first frame via ffprobe/ffmpeg) and `save_meta()` keeps the on-disk `download` record and, since v3.4.0, a `description` that is on disk but not loaded by the library (records own it; `_meta_lock`). `Library` scans videos and photos (entry `kind`; photos get info + thumbnail, no similarity grouping); summaries carry `kind`; a photo's `detail()` has `neighbors` {prev, next, index, total} (photos of the same folder by name) plus `preload` (v3.3.3: up to 4 ids from `_neighbors()`, nearest first: next, previous, 2nd next, 2nd previous); `list(kind)`; `folders()` returns `videos` and `photos` counts; `_sync_meta()` reloads a sidecar changed on disk (bot record, another PC), `_save()`; `delete()` calls `DownloadRecords().forget_file()`, moves call `file_moved`/`folder_moved`
- History (v3.3.0, `server.py`): `/library/api/videos?kind=video|photo`; `GET /library/api/history` (`q`, `status=exists|deleted`, `kind=video|photo|file`, `offset`, `limit`; items: key, file, rel, folder, kind, size, date, deleted_date, deleted, source, inside, `id` (library id when shown in the library), `redownload` flag); `POST /library/api/history/redownload` {key} -> 202 / 404 / 409 (file still exists) / 503 (bot not running); `LibraryServer(on_redownload=...)`, passed by GUI (`ui.py` `_redownload`) and CLI (`main.py`). Bot side (`bot.py`): `request_redownload_threadsafe(loop, record)` returns an error text or None; `_submit_redownload` sends a status message to the owner and queues with `submit_flow`; `_redownload_now` downloads into the file's original folder: `xprofile_` ids via `x_profile_downloader._fetch` + `record_download`, URL records via `url_parser.download_confirmed(selected_path=folder)`, Telegram records via `PeerChannel(chat_id)` + message id and `_start_download_with_selected_folder`. `web/youtube_downloader.py`, `x_downloader.py`, `p_downloader.py`: the fingerprint duplicate check only counts a record whose file still exists, so a deleted video can be downloaded again. Broken-file re-download (v3.3.1): `GET /library/api/videos/{id}` adds `redownload: {possible, note, bot}` for items with an error; `POST /library/api/videos/{id}/redownload` -> 202 / 404 (no source: reason text) / 503 (bot not running); `on_redownload(record, replace=None)` takes the broken file path as `replace` (`ui.py` `_redownload`, `main.py` lambda). `bot.py`: `request_redownload_threadsafe(loop, record, replace=None)`; `_find_source_message()` uses the recorded chat or, for a guess, tries each candidate channel and accepts a message only if `MediaDownloader.file_name_for(message)` equals the file name; `_discard_broken(path)` = `forget_file` then delete. Telegram: the broken file is deleted only after the source message is found (otherwise kept and the user told); YouTube/X/Pornhub: the broken copy is removed before downloading (it would count as a duplicate), the record stays in 下載紀錄 for a retry; X profile items are fetched over the file (`_fetch` writes `.part` then replaces)
- Frontend (v3.3.0): `api.js` `KINDS`, `storedKind`/`rememberKind` (localStorage `tad.kind`), `dimensions()`, `api.videos(kind)`, `api.history`, `api.redownload`; Library page has the 影片 / 圖片 / 全部 toggle on the filter row (`?kind=`), a 📜 下載紀錄 entry (a button until v3.4.2, now in the ☰ `AppMenu`, v3.4.3), per-kind folder counts (`FolderTree` `rootLabel`); `VideoCard`/`VideoRow` photo variant (W×H instead of duration; the 🖼 cover badge was removed in v3.4.3); VideoPage photo mode (large image, ‹ › and ←/→ for neighbors, Photo Info: 長寬/格式/Bit depth/大小/位置, 重新產生縮圖, 刪除圖片 continues with the next photo, `state.backPath`; v3.3.3: on touch screens (`pointer: coarse`, `pointer-coarse:hidden`) the ‹ › buttons are hidden, the counter reads 左右滑動切換 and a sideways swipe switches photo (image follows the finger via `dragX`, switches past `SWIPE_MIN` = 60 px else springs back, dx/4 resistance at the first/last photo, `touch-action: pan-y pinch-zoom`, a second finger cancels; desktop keeps buttons and ←/→); preload: module-level `detailCache` (detail JSON) and `preloaded` (Image objects) capped at `CACHE_LIMIT` = 40 (`remember()`) load `neighbors.preload` ahead, so a cached detail shows at once and refreshes in the background, `currentId` ref ignores late answers, form state carries `_id` (`formOf()`, unsaved edits kept only for the same file), delete clears the cache); `pages/History.jsx` at `/history` (status filter with counts, type filter, search, 100 per page with 載入更多; existing rows open the item page, deleted rows have ⬇ 重新下載 -> 已排入佇列); VideoPage (v3.3.1): an item with an error shows a red box with the error, `video.redownload.note` and a ⬇ 重新下載 button (disabled without a source or when the bot isn't running here), `api.redownloadVideo(id)`
- Bulk edit / delete (v3.3.4): `Library.update()` delegates to `_apply(vid, fields)` (writes title/actors/series/source to the sidecar and copies title/actors/series to the other versions of the group; v3.4.0: `description` (max 5000 chars) is written per file and NOT shared with the other versions; summaries carry `description`; caller holds the lock); `update_many(vids, add_actors, remove_actors, series=None)` removes 主演 case-insensitively, then adds new ones (deduped by `media.clean_tags`), sets 系列 when `series` is a string (`''` clears, `None` leaves it), returns `{updated, missing}`; `delete_many(vids)` calls `delete()` per id (records go to `deleted.json` like a single delete), returns `{deleted, failed: [{name, error}]}`. `server.py`: `POST /library/api/batch/update` {ids, add_actors, remove_actors, series?} and `POST /library/api/batch/delete` {ids} (400 when `ids` is empty; `_strings()` keeps only string list items). Frontend: `api.batchUpdate(ids, changes)`, `api.batchDelete(ids)`; `Library.jsx` select mode (`☑ 選取`; click toggles, Shift+click range in shown order, Ctrl/⌘+click selects and turns it on; fixed bottom action bar 已選 N 個 / 全選 / 清除選取 / 🏷 編輯主演 / 系列 / 🗑 刪除 / 完成; keys Esc, Ctrl/⌘+A, Delete; only items on screen stay selected; right-click a selected item -> 編輯已選 / 取消選取 / 刪除已選; dragging a selected item to the tree moves all selected; delete confirm lists video/photo counts, warns that grouped items lose only the shown version, reports the first 5 failures); `VideoCard`/`VideoRow` props `selecting`/`selected`/`onSelect`/`dragIds` (round ✓ at top-left, accent ring / background); `Dialogs.jsx` `BulkEditDialog` (items, actorSuggestions, seriesSuggestions, onSubmit, onCancel: 主演 on the selection with n/total counts, tap to mark for removal, TagInput to add, 系列 radio 不變更 / 設為 / 清除, 套用 disabled until something changes)
- Try merge (v3.4.4, two steps since v3.4.7): step 1 compares only: `Library.compare_many(vids)` (`store.py`) returns `{items: [{id, name, title, group, status: ok|not_ready|unreadable}], pairs: [[id, id, score]], photos, threshold}` (every pair of videos with lengths within `similarity.DURATION_TOLERANCE` +-3 s and not already in the same group, score rounded to 0.1; pairs split by hand (`not_same`) are compared too); `POST /library/api/batch/compare` {ids} (400 when fewer than 2). Step 2: `Library.join_groups(groups)` runs `_join()` per id list (clears `not_same` between the merged files; automatic grouping still respects it) and returns `{groups: [{title, versions}]}`; `POST /library/api/batch/merge` {groups: [[id, ...]]} (400 when no group has 2+ ids). Frontend: `api.batchCompare(ids)`, `api.batchMerge(groups)`; `Library.jsx` `mergeSelected()` (`comparison` state, button shows 比對中…) opens `Dialogs.jsx` `MergeDialog`, `confirmMerge(groups)` merges, toast 「已合併成 N 部片（共 M 個版本）」 and reloads; buttons `🔗 嘗試合併` in the bottom action bar and `🔗 嘗試合併為同一部片` in the right-click menu of a selection (>= 2 selected videos, photos ignored). `MergeDialog`: 相似度門檻 slider (40–99 %, starts at the library threshold, 回到預設) regroups live in the browser (`groupAt()`: union-find over pairs >= threshold plus existing groups, a match of a match joins too), shows 「將合併成 N 部片（共 M 部影片）」, groups sorted by similarity (highest first), 不合併 list by best score (or 沒有長度相近的影片), 無法比對 list (not_ready / unreadable), already-grouped and photo counts; the slider applies to this merge only (the automatic threshold stays in the Windows app); 確定合併 N 部片 sends the shown groups, 取消 / Esc / backdrop merges nothing; 「從群組移出」 on the video page undoes a wrong merge
- Enhanced compare (v3.4.8, `library/deep_compare.py`): 🔬 加強比對 for exactly two selected videos, by hand only (select-bar button and right-click item, enabled only with exactly 2 videos selected, never automatic) for copies whose start / end was cut or whose picture is scaled / cropped / letterboxed (the normal fixed 10/50/90 % screenshot check scores these low). `compare(path_a, dur_a, path_b, dur_b)`: (1) time offset: brightness of the picture's middle plus frame-to-frame change, sampled `RATE` = 4/s over the first `WINDOW` = 180 s via ffmpeg (32x18 gray), normalized cross-correlation over shifts up to `MAX_SHIFT` = 150 s (`MIN_OVERLAP` = 30 s, less for short videos); candidates best-correlation / starts aligned / ends aligned are checked with `QUICK` = 3 frame pairs; (2) verification at `SAMPLES` = 8 aligned moments: frames at `FRAME_W` = 640, black borders trimmed, ORB (1500) + ratio test + `cv2.estimateAffinePartial2D` RANSAC, warp B onto A and SSIM only inside the overlap mask (`similarity.ssim_map()`, new; `ssim()` now uses it), pairs without a transform fall back to plain SSIM; (3) score = median x100; returns offset, overlap, scale (median), aligned / pairs counts, correlation and `PREVIEWS` = 3 frame pairs as small JPEG data URLs. `Library.deep_compare(a, b)` (`store.py`): the longer video is the reference `a`; adds `regular` (normal screenshot score), `threshold`, `same_group`; `LibraryError` 400 (not two different videos) / 409 (no info yet) / 422 (no overlap, ffmpeg missing); `POST /library/api/batch/deep-compare` {ids: [a, b]} (400 unless exactly 2). Frontend: `api.deepCompare(ids)`; `Dialogs.jsx` `DeepCompareDialog` (spinner 10 s to ~1 min, score with verdict: >= threshold 很可能是同一部片, >= threshold-15 可能是, else 不像; 時間 開頭 / 結尾少了 / 多了 N 秒 + shared length, 畫面 scale difference, 對齊成功 n/8, 一般比對 score, three aligned frame pairs with times and per-pair score; 合併為同一部片 calls `Library.jsx` `confirmMerge([[a, b]])` (`join_groups`), 關閉 / 取消 does nothing); `Library.jsx` `deepCompare()` / `deepIds`; the select bar's button row wraps on phones. Measured on synthetic clips: normal 15-19 % -> enhanced 94-97 % for a trimmed + cropped and a pillarboxed copy, 1-2 % for unrelated videos, ~5 s per 1-minute pair; limits: more than ~2.5 min cut from the start isn't aligned, speed changes, mirroring and stretched aspect ratios aren't handled
- AI 辨識 (v3.5.0, `library/recognize.py`): AI suggestions for 主演 / 系列 of selected items; nothing changes in the library until a result is applied (套用) or skipped (略過). `Recognizer` (`start()` / `shutdown()` called by `LibraryServer.start/stop`): one job at a time in a background thread, queue + results in `<downloads>/.tad/recognition.json`, a job interrupted by a server stop runs again at the next start (caches make it quick); applying goes through `Library.update_many()` (主演 added, 系列 set). 主演: `FaceModel` = OpenCV YuNet detection + SFace 128-d features (`face_detection_yunet_2023mar.onnx`, `face_recognition_sface_2021dec.onnx` in `library/models`, gitignored, bundled by `telegram_bot.spec` when present with hiddenimport `library.recognize`, otherwise `model_path()` downloads them once from the official opencv_zoo with a SHA-256 check to `%LOCALAPPDATA%/TelegramAutoDownload/models`); `analyze()`: 12 frames per video (`FRAMES`, long side 1280 px, ffmpeg, 4 in parallel) or the photo (1600 px, GIF uses the thumbnail), faces >= 40 px and score >= 0.85, faces of one item grouped into persons (cosine `SAME_IN_ITEM` 0.36, passers-by dropped, max 4 persons); references = items already tagged with 主演 (`Recognizer._actor_refs`: single actor -> its main person, multi-actor items matched person by person, the last by elimination); a person whose face similarity (mean of top 3, the item's own faces and its other versions excluded) >= `FACE_MATCH` 0.40 gets that actor suggested, the others are clustered across the job as 未知人物 (`FACE_CLUSTER` 0.42, closest actor >= 0.25 as a hint). 系列 = same person (主演 tag or face match, else face cluster 人物 N) + same outfit: class `Ollama` (`/api/tags`, `/api/show` capabilities, `/api/chat` with format json, temperature 0, think false for thinking models; `models()` -> [{name, vision}]) describes each main person's outfit from the body crop (garments, colors, style, name_zh, zh); candidate pairs (all pairs for <= 8 items, else each item's 4 nearest by word overlap + HSV colour histogram) are confirmed by showing both crops side by side (same + confidence >= 60, max 400 checks per job); items of the same actor already in a 系列 (up to 3 per series) take part so an existing series name is suggested. Caches per file in the hidden shots folder (`faces.json`, `faces.npy`, `face_N.jpg`, `body_N.jpg`, `outfit_N.json` per model + file mtime; removed with the shots folder, move with the file). Server (`server.py`): `GET/POST /library/api/recognition` ({kind: actor|series, ids}), `GET /library/api/recognition/status` (face models installed, Ollama reachable + model), `GET/DELETE /library/api/recognition/{job}`, `POST .../{job}/cancel`, `POST .../{job}/apply` {entries: [{key, action apply|reject, name?, items?}]} -> {job, updated, missing}; `/library/media/{id}/ai/{face_N|body_N}.jpg`. Frontend: `api.js` `recognize`, `recognitionJobs`, `recognitionStatus`, `recognitionJob`, `cancelRecognition`, `removeRecognition`, `applyRecognition`; `Library.jsx` select bar 👤 辨識主演 / 👗 辨識系列 and right-click menu of a selection 👤 AI 辨識主演 / 👗 AI 辨識系列 (`recognizeSelected()`, `notify()` takes an optional link: toast with 查看進度 →); `pages/Recognition.jsx` at `/recognition`: queue (status 排隊中/執行中/完成/失敗/已取消, phase + done/total bar, 取消 / 刪除, polls every 2 s while active, the newest finished job with pending results opens by itself, status line) and results: 主演 -> 建議主演 list (face crop, item cover, → actor, 相似度, checkboxes, 全選 / 略過已選 / 套用已選 (n)), 未知人物 cards (tap a face to leave an item out, closest actor as hint below the line, name input with existing actors as suggestions, 設為主演 (n)), 無法辨識 list with reasons, warning when no item has 主演 yet; 系列 -> groups per person + outfit (face, outfit description, clothing crops with toggles, items already in a series as reference, name pre-filled with the existing series or "主演 + 服裝簡稱", warning when items' existing series would change, 設為系列 (n) / 略過), 沒有配對到的 list, model name and pair checks count. Tested with Qwen3.8-27B on Ollama; a 主演 job takes about 1–2 s per video for faces, v3.6.3: `Recognizer.people` (set by `LibraryServer`) -> `_actor_refs()` uses `_refs_from_people()`: `People.request_sync()` ticket (tags edited just before the job are included; served at the database's next cycle, even between items of a scan-all), waits with the progress 「等待人物資料庫建立完成」 / 「更新人物資料庫」 until `People.is_synced(ticket)`, then `People.named_refs()` (name, item uid, person index, vector), fails with 「人物資料庫錯誤：…」 when the database reports an error, so no item is re-analysed for the references (`_items()` rows include `uid`); 辨識系列 picks the existing-series references per series (max `SERIES_REFS` = 3) from items with that 主演 and analyses only those (cached); without a people database (standalone tests) the old full pass still runs and analyses every tagged item (cached afterwards); 辨識主演 doesn't need Ollama
- Drag-select & Explorer keys (v3.3.5, `Library.jsx`): `select(video, e)` follows Windows Explorer: click / Ctrl+click toggles and sets the anchor (`anchor` ref), Shift+click selects only anchor..item in shown order, Ctrl+Shift+click adds that range, Shift+click keeps the anchor. Drag-select (mouse only, `pointerType === 'mouse'`; touch still scrolls): `onPointerDown` on `<main>` starts on empty space (not header / links / buttons / inputs / `[data-id]`), the `marquee` ref holds the start in page coordinates, the mode (none = replace, Shift = add, Ctrl/⌘ = toggle against the selection at the start) and item rects read once from `[data-select-root] [data-id]` after 6 px; the box (`boxEl`, fixed div) is moved by style changes, `setSelected` only runs when the hit set changes, the first hit becomes the anchor, a `requestAnimationFrame` loop scrolls within 60 px of the top / bottom edge and follows wheel scrolling; a plain click on empty space clears the selection; `<main>` gets `select-none` in select mode. `VideoCard`/`VideoRow` carry `data-id` and prevent text selection on Shift+mousedown
- 人物資料庫 (v3.6.0, `library/people.py`, `frontend/src/pages/People.jsx`): a face database behind the 主演 tags; tags stay the source of truth. `People` (v3.6.3: `synced` = built at least once, also for an empty library; `request_sync()` / `is_synced(ticket)` / `named_refs()` with `_want` / `_done` tickets serve AI 辨識; created by `LibraryServer` as `self.people`, `library.on_change = people.wake`, `start()` / `shutdown()` called by `LibraryServer.start/stop`): own background thread, polls every `POLL_SECONDS` = 60 s and wakes on library changes, status {phase `sync` 建立人物資料庫 / `scan` 辨識中, done/total, error} shown on the page. A person = id + name (`''` = 未命名人物 #`next_num`; `People.label()`) + face references (SFace vectors from `recognize.analyze()`). Named people come from the tags (`_sync` / `_derive`): each tagged item's matching face becomes a reference (single actor: the face closest to that actor's other references, else the main face; multi-actor items matched person by person, the last by elimination), re-derived only when the item's tags or file change (`tagged` keys); people nobody is tagged with and without faces are dropped. New items (meta `added` >= `since`, i.e. seen by the library after the database was created) are recognised as soon as info / screenshots are ready (`_recognize`): every face matching a named person (>= `recognize.FACE_MATCH` 0.40, mean of the 3 closest references, the item's own faces and other versions excluded, people in the item's `not_people` skipped) adds that 主演 tag (recorded in `auto_actors`), a face matching an unnamed person joins it, any other face starts a new 未命名人物. Existing items only after `scan_all` (「🔍 掃描全部未掃描的項目（n）」, saved, survives restarts, ⏹ 停止掃描; `set_scan_all(on)`). Methods `overview()` (v3.6.2: built in one pass over the items and one over the references, holding the lock only while copying; it used to loop over every item and reference once per person, ~5.8 s for 5,000 items / 2,300 people, and the 人物 page polls `GET /library/api/people` every 2.5 s while the database is busy, so the web library worker never rested; now ~13 ms), `detail(pid)`, `rename(pid, name)` (renames the 主演 tag on every item via `Library.replace_actor()`; naming an unnamed person adds the tag to its items; an existing name merges), `merge(pid, into)` (keeps a name if either had one), `delete(pid)` (named: removes the tag from all items), `remove_items(pid, vids)` (不是這個人: removes the tag, drops the face, adds the person to the item's `not_people`; a hand-removed auto tag is remembered as `not_people` too). Files `<downloads>/.tad/people.json` (people, references, `since`, `scan_all`, `next_num`, `tagged`) + `people.npy` (one vector row per reference); sidecar keys `people_scan` (file mtime recognised), `auto_actors`, `not_people`. Library hooks (`store.py`): `Library.on_change` (called after an item's info / screenshots are made and when 主演 change), `set_fields(vid, fields)` (extra sidecar keys, not shared with versions), `replace_actor(old, new)` (`''` removes; also updates `auto_actors`). `recognize.py`: `analyze()` is serialised by a module lock `_analyze_lock` (AI 辨識 jobs and the people database share the cache files); `FaceModel` raises `RuntimeError` 「人臉模型無法載入」 on a damaged model file (and deletes a damaged downloaded copy so the next try downloads it again) instead of every item being skipped. Routes (`server.py`): `GET /library/api/people` (people with label, count, auto count, cover face, faces count, plus status, `scan_all`, `unscanned`, items), `POST /library/api/people/scan` {on}, `GET|DELETE /library/api/people/{pid}`, `POST /library/api/people/{pid}/rename` {name}, `/merge` {into}, `/remove` {items}. Frontend: `api.js` `people`, `person`, `peopleScan`, `renamePerson`, `mergePerson`, `removeFromPerson`, `deletePerson`; `pages/People.jsx` at `/people` (已命名 / 未命名 tabs with counts, `?tab=`, search, face-card grid with item / auto counts, unnamed seen only once hidden behind 「顯示只出現一次的」, scan button + status line, polls every 2.5 s while busy) and `/people/:id` (`PersonPage`: face, name input with existing names (命名 / 改名 / 合併), 🎬 在媒體庫查看 -> `/?actor=name&kind=all`, 合併到… select, 🗑 刪除人物 with confirmation, items grid with cover + face crop + 自動 badge, tap to pick wrong items then 「不是這個人（n）」, item name opens the item page with `backPath`); `AppMenu.jsx` `PAGES` 👥 人物 `/people` before 🤖 AI 辨識; `App.jsx` routes.
- GUI: "Web Library" tab in `src/ui.py` (`setup_web_tab`, `start_web`, `stop_web`, `save_web_settings_clicked`, `auto_start_web`); v3.5.0 "AI Recognition (Ollama)" section (Ollama URL, `load_ollama_models()` lists the server's vision models in a background thread via `library.recognize.Ollama.models()`, model combobox (empty = first vision model), `save_ai_settings()` writes `OLLAMA_BASE_URL` / `OLLAMA_MODEL` to `.env` + `os.environ`, used from the next job, no restart); `main.py --cli` also starts the library when `WEB_ENABLED=1`

#### `AuthHelper` (src/auth_helper.py)
GUI and console authentication management (v1.0.0):
- `authenticate_client()`: Main authentication function with session handling
- `check_session_exists()`: Validates existing Telethon session files
- `GUIAuthHelper`: GUI-based authentication with tkinter dialogs
- `ConsoleAuthHelper`: Fallback console authentication for development
- `get_auth_helper()`: Environment-aware authentication helper selection

### Configuration Requirements

The bot requires these environment variables in `.env`:

- `API_ID`: Telegram API ID from my.telegram.org
- `API_HASH`: Telegram API Hash from my.telegram.org  
- `PHONE_NUMBER`: Phone number for Telegram client authentication
- `BOT_TOKEN`: Bot token from @BotFather
- `STARTUP_SCAN_COUNT` (optional, v2.6.1): number of latest messages sent to the bot that are scanned at startup (default 30, 0 = off); read via `config.get_startup_scan_count()`, editable in GUI Configuration tab; `DownloadRecords.is_url_downloaded()` checks links ignoring query params
- `DOWNLOADS_PATH` (optional, v3.2.0): downloads folder, read live via `config.get_downloads_dir()` (default `<app dir>/downloads`); data folder `<downloads>/.tad/` (hidden on Windows) holds `deleted.json` (deleted downloads, v3.3.0), `history.json` and `chat_jobs.json` (unfinished `/chats` downloads, resumed at the next start, v3.4.0) (no `downloads.db` since v3.3.0; records live beside the files), so the folder can be opened from another PC (paths relative). Per device: `.env`, Telethon sessions, logs; run the bot on one PC at a time, the web library may run on several
- Records (v2.7.0, `DownloadRecords` since v3.3.0): `find_download(file_path)` returns the download record of a file on disk (path match, fallback file name + size so moved files are found); used by the file viewer for source links
- Security (v2.7.0): the `/files` viewer is owner-only (`TelegramMediaBot.owner_id` = Telethon session account) and confined to the downloads folder
- Web library (v3.0.0, all optional, read via `config.get_web_settings()`): `WEB_ENABLED` (1 = start with the bot, default 0), `WEB_PORT` (default 8765), `WEB_HOST` (`0.0.0.0` any location / `127.0.0.1` this PC only), `WEB_PASSWORD_HASH` (PBKDF2, set from the GUI Web Library tab, never plain text), `WEB_SECRET` (cookie signing key), `SIMILARITY_THRESHOLD` (percent, default 70, GUI "Same-video similarity", v3.1.0), `STREAM_ENCODER` (`cpu` forces the CPU for live transcoding instead of NVIDIA NVENC, v3.4.1), `OLLAMA_BASE_URL` (default `http://localhost:11434`) and `OLLAMA_MODEL` (empty = first vision model) for AI 辨識系列 (v3.5.0, read via `config.get_ai_settings()`, set from the GUI Web Library tab), `MAX_THREADS` (optional, default 16, at most the core count; GUI Configuration > Performance; limits the threads of ffmpeg / OpenCV / numpy / the worker pools, not a hard cap on the process total, v3.6.3); needs ffmpeg/ffprobe in PATH or `FFMPEG_PATH`, `aiohttp`, and a built `library/static` (Node.js 18+)

Additional requirements for X features (v2.5.0):
- Log in to X in Firefox on the same machine (cookies are read from Firefox for X downloads and account scans)
- For X account screenshots, install Chromium once via the GUI Configuration tab > Screenshot Engine > Install (or `playwright install chromium` from source); the box shows `Chromium status` with Check/Install buttons. GUI Bot Control also has Restart Bot (Stop cancels the bot task, Start reloads `.env`). v3.6.3 Configuration tab "Performance" section: "Max CPU threads" Spinbox (1..cores) + Save (`save_max_threads()` writes `MAX_THREADS` to `.env` + `os.environ`, calls `config.apply_thread_limit()`); ffmpeg / OpenCV use the new value at once, numpy and the worker pools after restarting the app

### File Structure

```
telegram_auto_download/
├── src/
│   ├── __init__.py              # Package initialization and exports
│   ├── bot.py                   # Main bot logic with enhanced authentication (580+ lines)
│   ├── downloader.py           # Download operations with concurrency (234 lines)
│   ├── monitor.py              # Real-time monitoring and progress (134 lines)
│   ├── records.py              # DownloadRecords: per-file download records in sidecars + .tad/deleted.json (v3.3.0)
│   ├── folder_navigator.py     # Interactive folder navigation system (260 lines)
│   ├── chat_scanner.py         # /chats: chat list, photo/video scan, chat_jobs.json (v3.4.0)
│   ├── auth_helper.py          # GUI/console authentication helper (197 lines, v1.0.0)
│   ├── file_viewer.py          # /files chat file viewer (owner only, v2.7.0; folder video preview v2.7.1)
│   ├── chromium_helper.py      # Chromium check/install for screenshots (v2.5.0)
│   ├── ui.py                   # Main GUI application (tkinter interface, v1.3.0; Diagnostics tab v3.6.1)
│   ├── diagnostics.py          # CPU per thread / child process, 10 s stack profile, thread dump for the Diagnostics tab (v3.6.1)
│   └── telegram_bot.py.bak     # Original monolithic file (backup)
├── web/
│   ├── __init__.py
│   ├── url_parser.py           # URL detection and dispatch
│   ├── youtube_downloader.py   # YouTube (yt-dlp)
│   ├── x_downloader.py         # X/Twitter single post (yt-dlp)
│   ├── p_downloader.py         # Pornhub (yt-dlp)
│   └── x_profile_downloader.py # X account downloader (gallery-dl + Playwright, v2.5.0)
├── library/                    # Web video library backend (v3.0.0)
│   ├── __init__.py
│   ├── media.py                # ffprobe info, ffmpeg screenshots, sidecar metadata
│   ├── store.py                # Library: scan, background workers, tags
│   ├── auth.py                 # Password hash, signed sessions, lockout
│   ├── deep_compare.py         # Enhanced compare of two videos: time offset + aligned frames (v3.4.8)
│   ├── people.py               # 人物資料庫: face references behind the 主演 tags, auto-tagging of new items, 未命名人物 (v3.6.0)
│   ├── recognize.py            # AI 辨識: YuNet/SFace face match for 主演, Ollama outfit match for 系列, job queue (v3.5.0)
│   ├── models/                 # YuNet + SFace .onnx face models (gitignored, bundled by the spec when present, v3.5.0)
│   ├── server.py               # aiohttp LibraryServer (API, media streaming, React build)
│   └── static/                 # Built frontend (npm run build, gitignored)
├── frontend/                   # Web library UI (React 18 + Vite 6 + Tailwind CSS 4, v3.0.0)
│   ├── package.json
│   ├── vite.config.js
│   └── src/                    # App.jsx, api.js, settings.js, pages/ (Login, Library, VideoPage, History, Recognition, People, Settings), components/ (Player, TagInput, VideoCard, AppMenu)
├── config/
│   └── config.py               # Configuration management
├── main.py                     # Unified application entry point (CLI/GUI)
├── package_windows.bat         # Windows installer build script (v1.0.0)
├── setup_build_env.bat         # Build environment setup script
├── telegram_bot.spec           # PyInstaller configuration (v1.0.0; v3.5.0 bundles library/models when present; v3.6.0 hiddenimport library.people; v3.6.1 hiddenimport src.diagnostics)
├── installer.iss               # Inno Setup installer configuration (v1.0.0)
├── create_version_info.py      # Version info generator (v1.0.0)
├── create_icon.py              # Application icon generator (v1.0.0)
├── ChangeLog.md                # Version history and release notes
├── downloads/                  # User-organized backup directory with folder structure (DOWNLOADS_PATH)
│   └── .tad/                   # Data folder (v3.2.0): deleted.json (deleted download records, v3.3.0), history.json (folder path history), chat_jobs.json (unfinished /chats downloads, v3.4.0)
├── logs/                       # Log files directory (auto-created)
└── bot_session.session         # Telethon session file (auto-generated)
```

### Media Support

The bot handles all Telegram media types, including media groups (v0.3.1):

- Photos (saved as .jpg)
- Videos (saved as .mp4 or original format)
- Documents with original filenames preserved
- Audio files
- GIFs
- **Media Groups**: Automatically detects and processes grouped media as single units (v0.3.1)

### Performance & Optimization Features

- **Concurrent Downloads**: Up to 5 simultaneous downloads using asyncio.Semaphore
- **Download Optimization**: Downloads start from smallest files for faster perceived performance (v1.2.0)
- **Optimized Telethon Client**: Connection pooling, retries, and timeout configuration
- **Real-time Monitoring**: Background thread tracking download progress, speed, and disk usage
- **Progress Callbacks**: Live download progress tracking with speed calculations
- **Smart Resource Management**: Non-blocking UI updates and memory-efficient operations
- **Skipped File Visibility**: Skipped files are now visible in the frontend (v1.1.1)

### Error Handling & Reliability

- **Enhanced Authentication**: Smart session validation and automatic cleanup of invalid sessions (v1.0.0)
- **GUI Authentication**: Robust handling of authentication in GUI environments without stdin access (v1.0.0)
- **Retry Mechanism**: Exponential backoff for failed downloads (up to 3 attempts)
- **Network Error Handling**: Comprehensive handling of ConnectionError, OSError, TimeoutError
- **Telegram API Limits**: FloodWaitError handling with automatic wait times  
- **Progress Persistence**: Save/load download progress to resume interrupted operations
- **Missing Permissions Detection**: Enhanced error messages for access issues
- **Robust Logging**: Detailed logging with reduced third-party library verbosity

## Development Notes

### Bot Capabilities
- Bot supports forwarded messages from channels and group chats only (not private chats)
- **Interactive Folder Navigation**: Users can choose download destination with real-time folder browsing (v0.5.0)
- **Media Group Detection**: Automatically detects and processes grouped media (albums) as single units
- **Download Records**: sidecar-based records track all downloads and prevent duplicates (v0.4.0 SQLite, v3.3.0 records beside files)
- Concurrent processing: Downloads up to 5 media files simultaneously for faster performance
- Files are permanently stored in user-organized directories with custom folder structures (v0.5.0)
- **Smart Directory Structure**: User-controlled organization with live folder statistics (v0.5.0)
- **Duplicate Prevention**: Record-driven checks prevent re-downloading existing files (v0.4.0)
- Smart file naming includes message ID and timestamp

### User Experience Features
- **Inline Keyboard Folder Selection**: Choose download location via tap-able buttons (v2.1.0)
  - Subfolder buttons displayed in a 2-per-row grid with live media statistics
  - `⬆️ 返回上級`, `✅ 確認這裡`, `📝 新建資料夾` action buttons
  - Up to 3 `🕐 /prev/path` quick-select buttons for previously used locations
  - New folder creation via a single text message — bot deletes input and updates keyboard seamlessly
- Real-time progress updates every 5 seconds with:
  - Completed/failed file counts
  - Download speed (MB/s)
  - Remaining disk space (GB)
  - Total downloaded size
- Final completion summary with performance metrics and storage location
- Non-blocking progress updates that don't interrupt download speed

### Technical Implementation
- **Professional GUI Architecture**: Complete Windows desktop application with tkinter interface (v1.0.0)
- **Windows Installer Integration**: Automated build pipeline with PyInstaller and Inno Setup (v1.0.0)
- **Dual Interface Design**: Seamless switching between GUI and command-line modes (v1.0.0)
- **Enhanced Authentication Architecture**: Robust session management with GUI/console fallback
- **Modular Design**: Refactored from monolithic 596-line file into 6 specialized modules
- **Inline Keyboard Navigation Architecture**: Button-driven folder navigation with index-based callback routing and persistent path history (v2.1.0)
- **Media Group Architecture**: Intelligent collection and processing of grouped media
- **Records Architecture**: per-file sidecar records (`DownloadRecords`) for persistent download tracking and metadata (v3.3.0, was SQLite)
- **Asyncio-based Architecture**: Concurrent processing for maximum performance
- **Semaphore Control**: Configurable download concurrency (`max_concurrent_downloads = 5`)
- **Background Monitoring**: Separate thread for real-time statistics without blocking downloads
- **Progress Persistence**: JSON-based progress tracking for resume capability
- **Optimized Client**: Telethon client with connection pooling and retry logic
- **Clean Separation**: Bot orchestration, download operations, monitoring, authentication, and folder navigation are decoupled
- **Dual API Integration**: Smart handling of Bot API and Telethon API differences
- **Records Integration**: Comprehensive download history and duplicate detection system
- **User State Management**: Per-user navigation state with session isolation
- **Session Management**: Intelligent session validation and automatic cleanup
- **Professional Deployment**: Complete build automation and installer generation (v1.0.0)
- **Logging**: Configured for debugging (INFO level) with reduced third-party library verbosity

### Performance Improvements
- **Professional User Experience**: Complete GUI eliminates command-line complexity (v1.0.0)
- **One-Click Deployment**: Windows installer eliminates manual setup requirements (v1.0.0)
- **Faster Authentication**: Smart session validation eliminates unnecessary authentication prompts
- **5x faster downloads** through concurrent processing vs. sequential
- **Improved Code Maintainability**: 6 focused modules vs. 1 monolithic file
- **Better Testing**: Individual components can be tested independently
- **Enhanced Debugging**: Clear separation of concerns for easier troubleshooting
- **Optimized User Experience**: Interactive folder selection improves organization efficiency
- **Streamlined Authentication**: Automatic session handling reduces startup time
- **System Integration**: System tray and Start Menu integration for seamless workflow (v1.0.0)
- Exponential backoff retry mechanism for network reliability  
- Smart resource management prevents UI blocking during intensive operations
- Memory-efficient progress tracking with callback-based updates
- **Streamlined Workflow**: Integrated folder navigation reduces setup time

### Refactoring Benefits
- **Complete Application Transformation**: From command-line tool to professional Windows application (v1.0.0)
- **Code Organization**: Transformed 596-line monolithic file into clean 6-module architecture
- **Single Responsibility**: Each module focuses on one primary concern
- **GUI Integration**: Dedicated GUI application with professional desktop experience (v1.0.0)
- **Deployment Automation**: Complete build and installer pipeline for professional distribution (v1.0.0)
- **Authentication Modularity**: Dedicated authentication handling with GUI/console support
- **Reusability**: Components can be easily reused or replaced
- **Scalability**: New features can be added without affecting existing modules
- **Maintainability**: Easier to understand, debug, and extend individual components
- **Enhanced Modularity**: GUI, authentication, and folder navigation demonstrate continued architectural evolution

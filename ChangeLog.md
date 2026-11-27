# ChangeLog

## [3.9.0] - 2026-11-26 - Download Tags & Whole t.me Posts
### Added
- Bot asks for 主演 / 系列 after 「✅ 確認這裡」: answer with one message (line 1 主演 separated by `,` `，` `、` `/` `;` `&`, line 2 系列 optional, 「-」 = empty, labelled `主演：` / `系列：` lines also work), tap one of the 3 latest 🕐 combinations (`tag_history` in `history.json`, max 5 per user), ⏭ 跳過 or ❌ 取消; no answer in 10 min (`TAG_TIMEOUT`) downloads without tags (`bot.py` `_ask_tags_then()` / `_answer_tags()` / `_handle_tag_callback()`, `FolderNavigator.get_tag_history()` / `remember_tags()`)
- Applies to every flow with the folder selector (forward, album, t.me link, YouTube / X / Pornhub, X account, `/chats`, startup scan / `/rescan`): the tags travel in a context variable (new `src/download_tags.py` `parse()` / `describe()` / `use()` / `current()`) and `DownloadRecords.record_download()` -> `media.set_download(..., tags)` writes them into each file's sidecar, so the library / 人物資料庫 see them; `/chats` jobs keep `tags` in `chat_jobs.json` for a resume; already-downloaded skips and 下載紀錄 re-downloads are not tagged; the completion message shows the tags
### Changed
- t.me links download the whole post: `?single` is ignored so every photo / video of the album is fetched, and replies under the album's other items are included (`bot.py` `_replies()`, `parse_tme_link()` no longer returns `single`)
### Fixed
- A t.me link to a post that isn't an album picked the largest album nearby, i.e. another post's media; now only the post itself is downloaded (`_handle_tme_link()`)

## [3.8.0] - 2026-11-26 - Classifier Canvas
### Added
- 分類器's 未分類 section is a canvas (`ClassifierCanvas.jsx`): each item shows its whole picture (object-contain, portrait videos stay recognisable) in justified rows, title under it, accent ring + ✓ when selected; the shape follows the loaded cover when it differs from the recorded size by > 8 % (rotated phone videos)
- Drag items freely, or onto a series card / 「＋ 新系列」 (pointer events, `Classifier.jsx` `dragAt()` / `dropItems()`); drag on empty space = selection box; wheel pans, Shift + wheel / pinch zooms 10 %-400 % at the pointer (`tad.canvasZoom`), Space / middle button / touch drag pans; only items near the view are rendered; hover previews play on the canvas too (`useHoverPreview` / `PreviewVideo` exported from `VideoCard.jsx`)
- Toolbar: zoom slider with percentage, order 最新加入 / 依標題 (`?order=title`) and 「排列」 button; the canvas is arranged on open and when the filters or order change, hand placement is kept until 排列
### Removed
- The classifier's card-size zoom (`tad.classifyZoom`, `VideoCard` `compact`) and the HTML5 drag & drop on series cards

## [3.7.3] - 2026-11-26 - Portrait Preview Fix
### Fixed
- Hover preview clips failed (404) for every portrait video: `scale=-2:360:force_original_aspect_ratio=decrease` rounded the height to 359 and libx264 refuses odd sizes; now the short side is 360 and the other side even (portrait 720x1280 -> 360x640), and the pieces are spread over the picture's own length (a longer audio track gave a 3 s clip) (`media.make_preview()`)
- A video whose clip can't be made is remembered by path + modified time, so hovering it again doesn't rerun ffmpeg; the failure is logged as a warning with ffmpeg's first error line (`server.py` `media_preview`)

## [3.7.2] - 2026-11-26 - Swipe Before Playing & Stream Fixes
### Added
- Video page: before pressing ▶, swipe sideways on the cover (touch), the new ‹ › buttons or ←/→ switch to the previous / next video in the library's order and stay on its screenshots (`VideoPage.jsx` `swipeTo(dir, play=false)`, `swipeNav()`)
- Fix: switching videos (esp. live-transcoded ones) hung the page: a dropped `<video>` kept downloading and used up the browser's 6 connections (new `api.js` `releaseVideo()`, run when the Player's `<video>` is dropped); `media_stream` now always stops ffmpeg and drains its output after kill (`proc.communicate()`, `proc.wait()` never returned), and `_register_stream()` stops a viewer's oldest streams beyond `STREAMS_PER_VIEWER` = 2 (`STREAMS_TOTAL` = 4) (`library/server.py`)

## [3.7.1] - 2026-11-26 - Hover Preview & Resizable Classifier
### Added
- Hover preview: resting the mouse 1 s on a video card (library card / list, 分類器) plays a muted clip of 6 x 1.5 s pieces at 360p, made on the first request and cached as `preview.mp4` in the shots folder (`VideoCard.jsx` `useHoverPreview()` / `PreviewVideo`, `media.make_preview()`, `GET /library/media/{id}/preview.mp4`, `Library.preview_source()`)
- 分類器 draggable divider between the 系列 strip and the 未分類 list (drag, double-click = 1/4, ↑/↓ keys; 15-80 %, kept in `tad.classifySplit`); series albums grow with the strip and show more covers (2x2 / 3x3 / 4x4) (`Classifier.jsx`)

## [3.7.0] - 2026-11-26 - Series Classifier
### Added
- New 🗂 分類器 page `/classify` in the ☰ menu (`Classifier.jsx`, `App.jsx`, `AppMenu.jsx`): top 1/4 = 系列 as folder-style cards (2x2 covers, name, count; one row scrolled with the mouse wheel; 主演 filter `?actor=`, series search `?sq=`, 「＋ 新系列」), bottom 3/4 = items without a 系列 (影片 / 圖片 / 全部, search, 「只顯示「X」的項目」; Shift + wheel or the slider resizes the cards, small ones show only the title)
- Drag one item, a selection or a drag-select box onto a series card (or click the card with items selected, or 「＋ 新系列」 / 加入新系列 to name a new one) to set its 系列 via `api.batchUpdate`; the toast has 復原; ✎ / right-click renames a series (an existing name merges); click a card or double-click an item opens it in the library / item page
- Rename a series on the library page: 「✎ 改名」 beside the 系列 filter (`Library.rename_series()` in `store.py`, `POST /library/api/series/rename`, `api.renameSeries()`); the filter follows the new name
### Fixed
- Library routes answered 200 with `null` instead of the error when a request was refused (e.g. a bad folder name showed 「已重新命名」): aiohttp's `Response` is falsy, so `error or web.json_response(...)` always returned the success response; now `error if error is not None else ...` in every `_run` route (`server.py`)
- Windows build stopped at Inno Setup "EndUpdateResource failed (110)": with Pillow 13 `create_icon.py` wrote an icon with only a 16x16 image; it now saves from the 256x256 image so all 6 sizes are written

## [3.6.3] - 2026-11-25 - Thread Limit & New Sorts
### Added
- Windows app Configuration tab "Performance" > "Max CPU threads" (`MAX_THREADS`, default 16, at most the PC's cores): ffmpeg (screenshots, live transcode, face-recognition frames, deep compare, 載入影片 compression), OpenCV, numpy and the worker pools use at most that many threads (`config.get_max_threads()` / `apply_thread_limit()`, `media.thread_limit()` / `threads_args()`, `src/ui.py`, `main.py`)
- Library page 排序 options 系列 (also the list view's 系列 header) and 隨機 (order fixed by `?seed=`, 🎲 picks a new one) (`Library.jsx`)
### Changed
- AI 辨識 takes the 主演 references from the people database (`People.request_sync()` / `named_refs()`) instead of re-analysing every tagged item on each job, and picks 系列 references per series (`library/recognize.py`, `library/people.py`)

## [3.6.2] - 2026-11-25 - Idle CPU Fixes
### Fixed
- 人物 page list (`People.overview()`, `GET /library/api/people`) looped over every item and face reference once per person, so one request took seconds with many 未命名人物 (~5.8 s for 5,000 items / 2,300 people) and the page's 2.5 s polling could keep the web library's worker thread busy all the time (the likely cause of the 90 % CPU seen while idle); now built in one pass (~13 ms) with the database lock held only while copying (`library/people.py`)
- A file whose modified time is in the future (wrong clock, copied from another PC) counted as "still being written" forever, so the library rescanned the whole downloads folder every minute instead of every 5; `Library._still_changing()` now only counts times up to 60 s ahead (`library/store.py`)
### Changed
- The asyncio thread pools are named `web-library-worker` / `bot-worker` (both were `asyncio_N`); the Diagnostics web library line shows the last folder scan time and the files still being written (`library/server.py`, `src/ui.py`)

## [3.6.1] - 2026-11-25 - Diagnostics Tab
### Added
- Windows app Diagnostics tab to find what uses the CPU when the app seems idle: live table (2 s, only while the tab is open) of CPU per thread (Python threads by name, native threads as "native thread <id>") and per child process (ffmpeg, node …), a machine-wide summary, and status lines for bot / web library / AI 辨識 / people database (`src/ui.py` `setup_diagnostics_tab()`, `_diagnostic_state()`)
- "Profile 10 s" (stack sampling at 100 Hz + CPU by thread / process) and "Dump Thread Stacks", saved as `cpu_profile_<time>.txt` / `thread_stacks_<time>.txt` in the logs folder and shown with Copy; new `src/diagnostics.py` (`CpuMonitor`, `profile()`, `dump_stacks()`; Windows API via ctypes, no new dependency); `telegram_bot.spec` hiddenimport `src.diagnostics`

## [3.6.0] - 2026-11-25 - People Database
### Added
- Web library 人物資料庫 behind the 主演 tags (`library/people.py` `People`, background thread): named people are built from the tags (the tagged item's matching face becomes a reference); new items are recognised once their screenshots are ready, a face matching a named person gets that 主演 tag automatically (`auto_actors`), unknown faces are collected as 未命名人物; existing items only after 「🔍 掃描全部未掃描的項目」; stored in `<downloads>/.tad/people.json` + `people.npy`
- New 👥 人物 page `/people` and `/people/:id` in the ☰ menu (`People.jsx`, `AppMenu.jsx`, `App.jsx`, `api.js`, `/library/api/people*`): 已命名 / 未命名 tabs, search, 命名 / 改名 / 合併 / 刪除人物, 🎬 在媒體庫查看, 「不是這個人」 (never added again, `not_people`; a hand-removed auto tag is remembered too), scan status; tags stay in sync
### Changed
- `Library.on_change`, `set_fields()`, `replace_actor()` (`store.py`); `recognize.analyze()` is serialised by a lock; a damaged face model now raises 「人臉模型無法載入」 and is re-downloaded instead of skipping every item; `telegram_bot.spec` hiddenimport `library.people`

## [3.5.0] - 2026-11-25 - AI Recognition
### Added
- Web library AI 辨識: select items, then 👤 辨識主演 (OpenCV YuNet + SFace face match against items already tagged, unknown faces clustered as 未知人物) or 👗 辨識系列 (same person + same outfit, outfits described and compared by an Ollama vision model) from the bottom bar or right-click menu; runs as a background queue (`library/recognize.py` `Recognizer`, `/library/api/recognition*`, `/library/media/{id}/ai/*.jpg`, `Library.jsx` `recognizeSelected()`)
- New 🤖 AI 辨識 page `/recognition` in the ☰ menu (`Recognition.jsx`, `AppMenu.jsx`, `api.js`): job queue with progress, 取消 / 刪除, and results to review; nothing changes until 套用 (主演 added / 系列 set via `Library.update_many()`) or 略過; jobs and caches are kept in `<downloads>/.tad/recognition.json` and the hidden shots folder
- Windows app Web Library tab: "AI Recognition (Ollama)" section (Ollama URL, Load Models, model, Save → `OLLAMA_BASE_URL` / `OLLAMA_MODEL`; `config.get_ai_settings()`); `telegram_bot.spec` bundles `library/models` when present, otherwise the face models download once on first use
### Changed
- `AppMenu.jsx` `PAGES` lists 🤖 AI 辨識 between 下載紀錄 and 設定

## [3.4.9] - 2026-11-25 - Remember Library Position
### Added
- Web library page remembers its scroll position per view (folder / search / filters / sort / kind) in this tab: going back from a video or reloading the page returns to where you were once the list has loaded; the video page now opens at the top (`Library.jsx`, `VideoPage.jsx`, `main.jsx`, `api.js` `readSession()` / `writeSession()`)
### Fixed
- Reloading the library page lost the folder, filters and sort: the server's `/library` redirect to `/library/` dropped the query string (`library/server.py` `LibraryServer.to_app`), it now keeps it

## [3.4.8] - 2026-11-25 - Enhanced Compare
### Added
- Web library 🔬 加強比對 for exactly two selected videos (bottom bar button and right-click item, enabled only when 2 videos are selected, started by hand only): for copies with a cut start / end or a scaled / cropped / letterboxed picture that the normal screenshot check scores low (`library/deep_compare.py` `compare()`, `Library.deep_compare()`, `POST /library/api/batch/deep-compare`, `similarity.ssim_map()`)
- It finds the time offset (brightness + frame change sampled 4/s over the first 180 s, cross-correlation up to 150 s), then checks 8 aligned moments (ORB + RANSAC warp, SSIM inside the overlap) and `DeepCompareDialog` shows the score with a verdict, time / scale difference, 對齊成功 n/8, the 一般比對 score and 3 aligned frame pairs; 合併為同一部片 merges the two (`Dialogs.jsx`, `Library.jsx`, `api.js`)

## [3.4.7] - 2026-11-25 - Merge Threshold Slider
### Changed
- 🔗 嘗試合併 no longer merges at once: it compares first (`Library.compare_many()` replaces `merge_many()`, `POST /library/api/batch/compare`) and the new `MergeDialog` (replaces `MergeResultDialog`) has a 相似度門檻 slider (40–99 %, 回到預設) that regroups live and shows 「將合併成 N 部片（共 M 部影片）」, groups and 不合併 / 無法比對 lists sorted by similarity; 確定合併 sends the shown groups (`Library.join_groups()`, `POST /library/api/batch/merge` now takes `{groups}`), 取消 merges nothing; the slider applies to this merge only (`store.py`, `server.py`, `api.js`, `Dialogs.jsx`, `Library.jsx`)

## [3.4.6] - 2026-11-25 - Similarity Fix for Chinese Paths
### Fixed
- Videos in folders or with file names containing Chinese (non-ASCII) characters never got a similarity signature on Windows (`cv2.imread` can't open such paths), so automatic grouping never compared them and 🔗 嘗試合併 said 「還沒有截圖或影片資訊」; screenshots are now read with `np.fromfile` + `cv2.imdecode` (`library/similarity.py` `build_signature()`). The next startup full check compares these videos for the first time, so it may group some automatically and take longer once
### Changed
- 🔗 嘗試合併 reports a new reason `unreadable` (screenshots exist but can't be read) shown as 「截圖無法讀取（可在影片頁按「重新產生截圖」）」 (`store.py` `merge_many()`, `Dialogs.jsx` `MergeResultDialog`)

## [3.4.5] - 2026-11-25 - Swipe Between Videos
### Added
- Web library video page: on touch screens, swiping sideways on the player (fullscreen too) switches to the previous / next video like Telegram's viewer: the picture follows the finger with the neighbor's first screenshot beside it, 60 px or a quick flick switches, otherwise it springs back; the new video starts from 0 and fullscreen stays on; order = the library page's current folder / search / filters / sort (`api.js` `saveList()` / `listNeighbors()`, `Library.jsx`, `VideoPage.jsx` `swipeTo()`, `Player.jsx`)
### Changed
- Original-file playback uses the same custom controls as the transcode player (native controls removed, so Chrome's speed / picture-in-picture / download menu is gone); fullscreen and orientation lock now follow the video across switches (`Player.jsx`)

## [3.4.4] - 2026-11-25 - Try Merge Selected Videos
### Added
- Web library multi-select: 🔗 嘗試合併 in the bottom bar (and 🔗 嘗試合併為同一部片 in the right-click menu of a selection) compares the selected videos (2 or more, photos ignored) with the automatic grouping check (length within ±3 s, screenshot similarity >= the threshold; a match of a match joins too) and puts matches into one group; pairs split with 「從群組移出」 are compared too and, when merged, lose that mark (`not_same`) for each other (`library/store.py` `merge_many()`, `POST /library/api/batch/merge`, `Library.jsx` `mergeSelected()`)
- Result dialog (`Dialogs.jsx` `MergeResultDialog`): merged groups with version count and similarity range, unmerged videos with the reason (best score vs threshold / no video of similar length / screenshots not made yet), already-grouped and photo counts; a wrong merge is undone with 「從群組移出」 on the video page

## [3.4.3] - 2026-11-24 - Settings Page & Side Menu
### Added
- Web library ☰ side menu at the top right of every page (`AppMenu.jsx`): 🎬 媒體庫 / 📜 下載紀錄 / ⚙ 設定 and 登出; new 設定 page `/settings` (`Settings.jsx`, `settings.js`) with the default playback quality (原始 or a transcode level with its cap and data per hour) and fullscreen 填滿 / 完整, saved per browser (`tad.quality`, `tad.fill`)
### Changed
- Player starts at the 設定 default; a quality picked in the player now applies to that video only; 原始 on a file the browser can't play uses the best transcode level (`Player.jsx`); library cards keep the cover clean, length / resolution / version count sit on one grey line under the title (`VideoCard.jsx`); 📜 下載紀錄 and 登出 buttons moved into the menu

## [3.4.2] - 2026-11-24 - Mobile Player
### Fixed
- Web library player on phones: controls no longer overflow (two rows: time / seek bar / total, then play, ±10s, 畫質, fullscreen; volume slider and 即時轉檔 label hidden on narrow / touch screens); 畫質 shows only the short label; controls auto-hide after 3 s while playing, a tap shows / hides them and a round middle button plays / pauses (`Player.jsx`)
- Fullscreen fits the phone screen: video fills it (no black bars) with a 完整 / 填滿 toggle (`tad.fill`), reaches under the notch with safe-area padding, turns to the video's orientation; original-file mode's F key fullscreens the video itself (iPhone `webkitEnterFullscreen()`)

## [3.4.1] - 2026-11-24 - Player Quality Levels
### Changed
- Web library player: 畫質 menu for every video (direct and transcode mode; position kept when switching): 原始 (only when the browser can play the file; shows its bit rate) and 2160p, 1080p 高 / 低, 720p 高 / 低, 480p 高 / 低 with capped bit rates; only levels that fit the video are offered, the choice is remembered per browser (`tad.quality`) (`Player.jsx`, `library/media.py` `STREAM_LEVELS`, `stream_qualities()`, `store.py` `detail()` `qualities`)
- Live transcode `/library/media/{id}/stream?t=&q=<level>` (was `h=`) fits the level's box, never upscales and caps the bit rate (`stream_command()`); uses NVIDIA NVENC when available (falls back to the CPU per stream), `STREAM_ENCODER=cpu` in `.env` forces the CPU (`stream_encoder()`)

## [3.4.0] - 2026-11-24 - Chat Download & Message Description
### Added
- Owner-only `/chats [關鍵字]` (also in the command menu): lists the joined groups / channels (10 per page, name filter), scans the whole history for photos and videos with Telegram's filter (`src/chat_scanner.py`, ✖ 停止掃描), skips what is already downloaded (deleted ones too) before downloading, shows a summary above the usual folder selector and queues with `submit_flow` (`bot.py` `_run_chat_download()`, `_download_chat_ids()`, `NavigationState.pending_job`)
- Downloads run 5 at a time, messages fetched in batches of 50 (`CHAT_BATCH`) and re-checked first, progress every 5 s with ⏹ 停止下載 (removes the half-written `.part`); a running job is saved in `<downloads>/.tad/chat_jobs.json` and `_resume_chat_jobs()` continues it after a restart (rescan, skip what exists)
- Message description: every Telegram download stores the original text (its own, else the album caption, else the root post for replies) as `description` in the sidecar (`downloader.py` `describe()`, `records.py` `KEPT_LIBRARY_FIELDS`, so it survives delete + re-download); the web library item page has an editable 描述 box and the search matches it (`store.py` `_apply()`, `VideoPage.jsx`, `Library.jsx`)

## [3.3.5] - 2026-11-23 - Drag-select
### Added
- Web library drag-select (mouse): drag on empty space draws a box and selects every item it touches; no key replaces the selection, Shift adds, Ctrl/⌘ toggles; the page scrolls near the top / bottom edge; a click on empty space clears the selection (`Library.jsx`)
### Changed
- Shift / Ctrl clicks follow Windows Explorer: Shift+click selects only the range from the anchor (the last clicked item) instead of adding it, Ctrl+Shift+click adds the range, Ctrl+click toggles and moves the anchor; Shift+click no longer selects page text (`Library.jsx` `select()`, `VideoCard.jsx`)

## [3.3.4] - 2026-11-23 - Multi-select Delete & Edit
### Added
- Web library multi-select: `☑ 選取` button on the filter row, click / Shift+click range / Ctrl(⌘)+click to select videos and photos; bottom action bar with 全選, 清除選取, 🏷 編輯主演 / 系列, 🗑 刪除, 完成 (keys: Esc, Ctrl/⌘+A, Delete); dragging a selected item to a folder moves all selected items (`Library.jsx`, `VideoCard.jsx`)
- Bulk edit dialog (`Dialogs.jsx` `BulkEditDialog`): add 主演 to all selected items, tap an existing 主演 to remove it, keep / set / clear 系列; bulk delete asks for confirmation and reports failures
- `POST /library/api/batch/update` and `POST /library/api/batch/delete` (`library/store.py` `update_many()`, `delete_many()`, `_apply()` shared with `update()`); deleted items keep their download record in `.tad/deleted.json` like a single delete

## [3.3.3] - 2026-11-23 - Photo Swipe & Preload
### Added
- Photo page on touch screens: swipe left / right to switch photo (image follows the finger, springs back under 60 px; ‹ › buttons hidden, desktop keeps buttons and ←/→) (`VideoPage.jsx`)
### Changed
- Photo page preloads the details and images of the 2 next and 2 previous photos (`library/store.py` `_neighbors()` returns `preload`), so switching shows the photo at once instead of "載入中…"

## [3.3.2] - 2026-11-23 - Clean Empty Files
### Added
- Windows app Database tab: "Clean Empty Files" button (`src/ui.py` `clean_empty_files()`) scans for 0-byte files with no source link, shows the count and first 15 paths, asks for confirmation (cannot be undone), deletes them and reports the result
- `src/records.py` `DownloadRecords.empty_unsourced_files()` (skips files modified in the last 10 minutes and hidden folders) and `delete_files()` (removes the hidden sidecars; a record without a source link moves to `deleted.json`)

## [3.3.1] - 2026-11-23 - Re-download Broken Files
### Added
- Item page of a broken video / photo (e.g. 檔案不完整或已損毀) shows how its source will be found and a ⬇ 重新下載 button (`POST /library/api/videos/{id}/redownload`, `src/records.py` `plan_redownload()`: own record, a deleted record with the same file name, or the Telegram message id parsed from the file name searched in the channels of recorded files)
### Changed
- Re-download keeps the broken file until the source is found (Telegram) or removes it first (YouTube / X / Pornhub); `MediaDownloader.file_name_for()` split out of `download_media_from_message()`

## [3.3.0] - 2026-11-23 - Records Beside Files, Photos & Download History
### Added
- Web library shows photos too (`library/media.py` `process_image()`, `store.py` entry `kind`): thumbnail and image info, 影片 / 圖片 / 全部 toggle (`?kind=`), photo page with ‹ › / ←/→ to neighbors
- 下載紀錄 page (`/history`, `GET /api/history`): search and filter downloaded and deleted items; `POST /api/history/redownload` queues a deleted item again into its original folder (the bot must be running on that PC; `bot.py` `request_redownload_threadsafe`)
### Changed
- The SQLite database is gone: `src/records.py` `DownloadRecords` replaces `src/database.py`; each file's record is the `download` key of its hidden `.<file>.meta.json`, deleted downloads move to `<downloads>/.tad/deleted.json` (still counted as downloaded, so scans do not re-offer them); `downloads.db` (v3.2.0 or legacy) is imported once and renamed `downloads.db.migrated`
### Fixed
- Re-downloading a deleted YouTube / X / Pornhub video is no longer dropped as a duplicate

## [3.2.0] - 2026-11-23 - Library Data in Downloads Folder
### Changed
- The download database now lives at `<DOWNLOADS_PATH>/.tad/downloads.db` (`config.get_database_path()`); the old `<app dir>/downloads.db` is copied there on first start and renamed `downloads.db.migrated`; `DatabaseManager` reopens the database when `DOWNLOADS_PATH` changes
- `file_path` is stored relative to the downloads folder, so another PC that opens the same folder (different path or drive letter) reuses the history; the SQLite journal is not WAL, so network shares work
- Folder path history (`🕐` buttons) is saved in `<downloads>/.tad/history.json` instead of memory only; GUI downloads path field uses `get_downloads_dir()` and tells you to restart the bot after saving
### Fixed
- The folder picker no longer lists hidden (dot) folders such as `.tad` and the library's `.<file>.shots`

## [3.1.1] - 2026-11-20 - Library Moved to /library
### Changed
- The web library (frontend, `/library/api`, `/library/media`) now lives under `/library` (`server.PREFIX`, vite `base`, router `basename`); `/` returns an empty page, `/library` redirects to `/library/`; GUI / CLI links point to `/library/`
### Fixed
- Login no longer fails when the browser still holds the old session cookie stored for `/`: every session cookie value is checked, and login / logout expire the old one

## [3.1.0] - 2026-11-20 - Similar Video Versions
### Added
- Similar-video detection (`library/similarity.py`): videos whose lengths differ by at most 3 s are compared on screenshots 1, 5 and 9 (10 / 50 / 90 %) with grayscale SSIM (skimage-identical, OpenCV only); mean >= threshold (default 70 %, GUI "Same-video similarity", `SIMILARITY_THRESHOLD`) groups them as versions of one video
- Decoded grayscale frames (320x180) are cached as `sig.npy` in the hidden shots folder and in memory, so comparisons need no image decoding
- Full check of the whole library when the web library starts (`Library.check_all`); afterwards every new video is matched when its screenshots are ready (`_match_new`) and the bot sends a Telegram notice (`notify_owner_threadsafe`)
- Web: a group shows once (best quality) with a "N 個版本" badge; video page 版本 box switches 線路 and keeps the playback time; 「從群組移出」 splits a file out and the pair is never grouped again (`/api/videos/{id}/ungroup`, `not_same`)
### Changed
- 標題 / 主演 / 系列 are shared within a group (tags merged when grouping); sidecar meta gains `uid`, `group`, `not_same`

## [3.0.2] - 2026-11-20 - Quality Sort & Partial Download Fix
### Added
- Library list view shows bit rate under the resolution; new 畫質 sort (resolution, then bit rate) in the sort menu and on the list column header
### Fixed
- Telegram media downloads to `<name>.part` and is renamed when complete (`downloader.py`), so the web library no longer probes half-written videos ("moov atom not found"); the library waits for files changed in the last 90 s, shows "檔案不完整或已損毀" for broken files
- `package_windows.bat` reuses `build_env\` and the PyInstaller cache (`package_windows.bat fresh` rebuilds from scratch); an empty locked output folder no longer stops the build

## [3.0.1] - 2026-11-20 - Library Folder Tree
### Added
- Web library folder tree (`FolderTree.jsx`): browse folders, `＋ 新增` folder, drag videos / folders onto a folder to move them, right-click (or `⋯`) to rename / add sub folder / delete empty folder; right-click a video to open, rename, go to its folder or delete
- Card / list view switch on the library page (remembered per browser)
- API `/api/folders` (list / create / rename / delete), `/api/videos/{id}/rename`, `/api/move` (`Library.folders`, `create_folder`, `rename_folder`, `delete_folder`, `rename_video`, `move`); moved / renamed videos keep their hidden info, screenshots and `.720p_h265` copy; names are validated and videos still being processed can't be moved

## [3.0.0] - 2026-11-20 - Web Video Library
### Added
- Web video library for watching and managing downloaded videos in a browser (Telegram and system settings stay in the Windows app): `library/` backend (aiohttp `LibraryServer` in `server.py`, `Library` scanner with 2 background workers in `store.py`, ffprobe info and 9 ffmpeg screenshots in `media.py`) and `frontend/` (React 18 + Vite 6 + Tailwind CSS 4; `npm run build` outputs to the gitignored `library/static`)
- Pages: Login; library grid (cover, resolution/duration badges, search, filter by 主演/系列/資料夾, sort, rescan); video page (3x3 screenshot grid, edit title/actors/series/source, Video Info panel, download original, regenerate screenshots, delete with confirm)
- Player plays the original file when the browser supports the codec, otherwise (or on failure) a live ffmpeg transcode to fragmented H.264/AAC MP4 with custom controls (seek, ±10s, volume, 480/720/1080p, fullscreen, Space/←/→/F); Safari/iOS cannot play the live transcode (no range support)
- Metadata is kept beside each video as hidden `.<file>.meta.json` and `.<file>.shots/01-09.jpg`; the source is auto-filled from the bot database (`find_download`/`source_link`); deleting from the web also removes the sidecars and the hidden `.720p_h265` copy
- Windows app "Web Library" tab (`src/ui.py` `setup_web_tab`): Start/Stop/Open in Browser, Start on launch (`WEB_ENABLED`), Port (`WEB_PORT`, default 8765), Access any location / this PC only (`WEB_HOST`), new password; CLI `main.py --cli` also starts the library when `WEB_ENABLED=1` (`config.get_web_settings()`)
### Changed
- `package_windows.bat` step 5 runs `npm ci && npm run build` in `frontend/` (needs Node.js 18+, build fails without it); `telegram_bot.spec` bundles `library/static`, aiohttp and the library modules; `aiohttp` added to `requirements.txt`; ffmpeg/ffprobe must be in PATH or `FFMPEG_PATH`
### Security
- Password stored only as a PBKDF2 hash (`WEB_PASSWORD_HASH`); HMAC-signed session cookie (`WEB_SECRET`), changing the password logs out all sessions; 5 wrong passwords lock the client for 15 minutes; security headers and all paths confined to the downloads folder

## [2.7.7] - 2026-11-20 - t.me Link Download
### Added
- Owner-only `t.me/<channel>/<id>` and `t.me/c/<id>/<id>` link download (`bot.py` `parse_tme_link`, `_handle_tme_link`): media is read through the logged-in Telethon account, so "restrict saving content" chats work; `?single` downloads only that message, otherwise the whole album and media replies, then the usual folder selector

## [2.7.6] - 2026-11-04 - Rescan Command
### Added
- Owner-only `/rescan [count]` (also in the command menu; `bot.py` `handle_rescan_command`, `_scan_recent`): runs the startup scan on demand over the last `STARTUP_SCAN_COUNT` (or `count`) messages and queues what is not downloaded; items already waiting in the queue are not queued twice, and the result is always reported in the chat

## [2.7.5] - 2026-10-28 - Load Video
### Added
- File detail `📤 載入影片` (`fv_load`): sends the video to the chat through Telethon (second session logged in as the bot, `src/bot.py` `_load_video`) instead of the Bot API, so the 50 MB limit does not apply (up to 2 GB)
- Videos over 500 MB or above 4000 kbps are first compressed with ffmpeg to H.265 / 720p / 2000 kbps (`src/video_loader.py`, needs ffmpeg in PATH or `FFMPEG_PATH`); the result is kept as hidden `.<name>.720p_h265.mp4` next to the original (not listed by the viewer) and re-used next time

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

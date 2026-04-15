# ChangeLog

## 2.1.0

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

## 2.0.0.0815-1127

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

## 1.2.0.0814-1118

- **Download Optimization**: Start download from the smallest file.

## 1.1.1.0814-1019

- **Show Skipped Files**: Skipped files are now visible in the frontend.

## 1.1.0.0813-1403

- **CI/CD Integration**: GitHub Actions for automated deployment.

## 1.0.0.0813

- **GUI Application Release**:
  - Full-featured desktop GUI with tabs (Config, Logs, Control).
  - System tray support, real-time logs, session authentication.
  - Config auto-save with validation.
- **Windows Installer**:
  - One-click installer with auto-update, no Python required.
- **Documentation Consolidation**:
  - Combined and streamlined all setup and usage guides.

## 0.5.1.0811-0155

- **Refactor**: Improved code structure in `bot.py`.

## 0.5.0.0811-1135

- **Interactive Folder Navigation**:
  - Real-time folder selection with commands.
  - Multi-language support and visual feedback.
- **Improved UX**: Cleaner workflow and user state handling.

## 0.4.0.0806-2329

- **SQLite Integration**:
  - Persistent download history and duplicate prevention.
- **Download Management Enhancements**:
  - Smarter logging, error tracking, and statistics.

## 0.3.1.0806-1730

- **Media Group Support**:
  - Detect and download grouped media (albums).
  - Intelligent fallback strategies and improved organization.

## 0.3.0.0806-1430

- **Major Code Refactor**:
  - Split monolithic bot into modular components.
  - Improved maintainability and testing.
- **Download Metrics**:
  - Show file sizes, percentages, and ETA.

## 0.2.1.0806-1155

- **Improved Reliability**:
  - Retry logic, progress persistence, and better error handling.

## 0.2.0.0805-1015

- **Backup Mode**:
  - Removed upload/ZIP features, now stores files locally only.

## 0.1.1.0805-1632

- **Docs Fix**: Corrected README structure and setup instructions.

## 0.1.0.0805-1200

- **Initial Release**:
  - Basic Telegram bot for media downloads.
  - ZIP packaging, config management, error handling, and documentation.

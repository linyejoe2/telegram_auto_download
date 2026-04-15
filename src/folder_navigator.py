import os
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

MAX_PATH_HISTORY = 5
FOLDERS_PER_ROW = 2


@dataclass
class NavigationState:
    """用戶資料夾導航狀態"""
    user_id: int
    current_path: str = ""          # 相對於 base_path 的路徑
    pending_messages: List = None   # 等待下載的消息
    media_counts: Dict[str, int] = None
    awaiting_folder_selection: bool = False
    awaiting_folder_name: bool = False  # 等待用戶輸入新資料夾名稱
    current_folders: List = None    # 目前目錄的資料夾列表（供索引回調使用）
    path_history: List = None       # 已確認過的路徑歷史（最近在前）
    nav_message: object = None      # 導航訊息對象（用於編輯）
    pending_url: str = None         # 待下載的 URL（非 Telegram 媒體）
    url_type: str = None            # URL 類型，例如 'youtube'

    def __post_init__(self):
        if self.pending_messages is None:
            self.pending_messages = []
        if self.media_counts is None:
            self.media_counts = {'video': 0, 'photo': 0, 'document': 0}
        if self.current_folders is None:
            self.current_folders = []
        if self.path_history is None:
            self.path_history = []


class FolderNavigator:
    """資料夾導航管理器 — 使用 Inline Keyboard Buttons"""

    def __init__(self, base_path: str = "./downloads"):
        self.base_path = os.path.abspath(base_path)
        self.user_states: Dict[int, NavigationState] = {}
        os.makedirs(self.base_path, exist_ok=True)

    # ─── state helpers ───────────────────────────────────────────────────────

    def get_user_state(self, user_id: int) -> NavigationState:
        if user_id not in self.user_states:
            self.user_states[user_id] = NavigationState(user_id=user_id)
        return self.user_states[user_id]

    def is_awaiting_folder_selection(self, user_id: int) -> bool:
        return self.get_user_state(user_id).awaiting_folder_selection

    def is_awaiting_folder_name(self, user_id: int) -> bool:
        state = self.get_user_state(user_id)
        return state.awaiting_folder_selection and state.awaiting_folder_name

    def set_awaiting_folder_name(self, user_id: int, value: bool):
        self.get_user_state(user_id).awaiting_folder_name = value

    def get_selected_path(self, user_id: int) -> str:
        state = self.get_user_state(user_id)
        if state.current_path:
            return os.path.join(self.base_path, state.current_path)
        return self.base_path

    def get_pending_messages(self, user_id: int) -> List:
        return self.get_user_state(user_id).pending_messages

    def clear_user_state(self, user_id: int):
        """清除導航狀態，但保留路徑歷史以便下次使用"""
        if user_id not in self.user_states:
            return
        history = self.user_states[user_id].path_history
        self.user_states[user_id] = NavigationState(user_id=user_id)
        self.user_states[user_id].path_history = history
        logger.info(f"已清除用戶 {user_id} 的導航狀態（保留路徑歷史）")

    # ─── navigation actions ──────────────────────────────────────────────────

    def start_folder_selection(
        self, user_id: int, messages: List, media_counts: Dict[str, int]
    ) -> Tuple[str, InlineKeyboardMarkup]:
        state = self.get_user_state(user_id)
        state.pending_messages = messages
        state.media_counts = media_counts
        state.awaiting_folder_selection = True
        state.awaiting_folder_name = False
        state.current_path = ""
        state.nav_message = None
        return self._generate_folder_ui(state)

    def navigate_into(self, user_id: int, folder_index: int) -> Tuple[str, InlineKeyboardMarkup]:
        state = self.get_user_state(user_id)
        if folder_index < 0 or folder_index >= len(state.current_folders):
            return self._generate_folder_ui(state)

        folder_name = state.current_folders[folder_index]
        target_path = f"{state.current_path}/{folder_name}" if state.current_path else folder_name
        target_full = os.path.join(self.base_path, target_path)

        if os.path.isdir(target_full):
            state.current_path = target_path
            logger.info(f"用戶 {user_id} 進入資料夾: {state.current_path}")

        return self._generate_folder_ui(state)

    def navigate_up(self, user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
        state = self.get_user_state(user_id)
        if state.current_path:
            parts = state.current_path.split('/')
            state.current_path = '/'.join(parts[:-1]) if len(parts) > 1 else ""
            logger.info(f"用戶 {user_id} 返回上級: {state.current_path or '/'}")
        return self._generate_folder_ui(state)

    def navigate_to_history(self, user_id: int, history_index: int) -> Tuple[str, InlineKeyboardMarkup]:
        state = self.get_user_state(user_id)
        if history_index < 0 or history_index >= len(state.path_history):
            return self._generate_folder_ui(state)

        hist_path = state.path_history[history_index]
        full_path = os.path.join(self.base_path, hist_path) if hist_path else self.base_path
        if os.path.isdir(full_path):
            state.current_path = hist_path
            logger.info(f"用戶 {user_id} 選擇歷史路徑: {hist_path or '/'}")

        return self._generate_folder_ui(state)

    def create_folder_and_navigate(self, user_id: int, folder_name: str) -> Tuple[str, InlineKeyboardMarkup]:
        state = self.get_user_state(user_id)
        state.awaiting_folder_name = False

        invalid_chars = set(r'/\:*?"<>|')
        if not folder_name or any(c in invalid_chars for c in folder_name):
            return self._generate_folder_ui(state)

        current_full = os.path.join(self.base_path, state.current_path) if state.current_path else self.base_path
        new_folder_full = os.path.join(current_full, folder_name)

        try:
            os.makedirs(new_folder_full, exist_ok=True)
            state.current_path = f"{state.current_path}/{folder_name}" if state.current_path else folder_name
            logger.info(f"用戶 {user_id} 創建並進入資料夾: {state.current_path}")
        except Exception as e:
            logger.error(f"創建資料夾失敗: {e}")

        return self._generate_folder_ui(state)

    def confirm_selection(self, user_id: int) -> Tuple[str, bool]:
        """確認選擇，更新路徑歷史，返回 (display_path, True)"""
        state = self.get_user_state(user_id)
        display_path = f"/{state.current_path}" if state.current_path else "/"

        # Update history (deduplicate, most recent first)
        rel = state.current_path
        if rel in state.path_history:
            state.path_history.remove(rel)
        state.path_history.insert(0, rel)
        state.path_history = state.path_history[:MAX_PATH_HISTORY]

        state.awaiting_folder_selection = False
        logger.info(f"用戶 {user_id} 確認存放位置: {display_path}")
        return display_path, True

    # ─── UI generation ───────────────────────────────────────────────────────

    def _generate_folder_ui(self, state: NavigationState) -> Tuple[str, InlineKeyboardMarkup]:
        display_path = f"/{state.current_path}" if state.current_path else "/"
        current_full = os.path.join(self.base_path, state.current_path) if state.current_path else self.base_path

        folders = []
        media_counts = {'video': 0, 'photo': 0, 'document': 0}

        try:
            if os.path.exists(current_full):
                for item in os.listdir(current_full):
                    item_path = os.path.join(current_full, item)
                    if os.path.isdir(item_path):
                        folders.append(item)
                    elif os.path.isfile(item_path):
                        lower = item.lower()
                        if any(lower.endswith(e) for e in ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm']):
                            media_counts['video'] += 1
                        elif any(lower.endswith(e) for e in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']):
                            media_counts['photo'] += 1
                        elif any(lower.endswith(e) for e in ['.pdf', '.doc', '.docx', '.txt', '.zip', '.rar', '.7z']):
                            media_counts['document'] += 1
                folders.sort()
        except Exception as e:
            logger.warning(f"讀取資料夾列表失敗: {e}")

        state.current_folders = folders

        # ── Text ──
        text = (
            f"📂 請選擇存放位置\n"
            f"目前在: {display_path}\n"
            f"影片 {media_counts['video']} 個 | 照片 {media_counts['photo']} 個 | 檔案 {media_counts['document']} 個"
        )

        # ── Keyboard ──
        keyboard = []

        # Subfolder buttons (FOLDERS_PER_ROW per row)
        for i in range(0, len(folders), FOLDERS_PER_ROW):
            row = []
            for j in range(FOLDERS_PER_ROW):
                idx = i + j
                if idx < len(folders):
                    name = folders[idx]
                    label = f"📁 {name[:18]}{'…' if len(name) > 18 else ''}"
                    row.append(InlineKeyboardButton(label, callback_data=f"fn_cd:{idx}"))
            keyboard.append(row)

        # Navigation row
        nav_row = []
        if state.current_path:
            nav_row.append(InlineKeyboardButton("⬆️ 返回上級", callback_data="fn_up"))
        nav_row.append(InlineKeyboardButton("✅ 確認這裡", callback_data="fn_ok"))
        keyboard.append(nav_row)

        # Create folder button
        keyboard.append([InlineKeyboardButton("📝 新建資料夾", callback_data="fn_cr")])

        # Previous paths (at most 3 in one row)
        valid_history = [
            (idx, p) for idx, p in enumerate(state.path_history)
            if os.path.isdir(os.path.join(self.base_path, p) if p else self.base_path)
        ]
        if valid_history:
            history_row = []
            for idx, hist_path in valid_history[:3]:
                label = f"🕐 /{hist_path}" if hist_path else "🕐 /"
                if len(label) > 20:
                    label = label[:19] + "…"
                history_row.append(InlineKeyboardButton(label, callback_data=f"fn_prev:{idx}"))
            keyboard.append(history_row)

        return text, InlineKeyboardMarkup(keyboard)

import os
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class NavigationState:
    """用戶資料夾導航狀態"""
    user_id: int
    current_path: str = ""  # 相對於 ./downloads/ 的路徑
    pending_messages: List = None  # 等待下載的消息
    media_counts: Dict[str, int] = None  # 媒體統計
    awaiting_folder_selection: bool = False
    
    def __post_init__(self):
        if self.pending_messages is None:
            self.pending_messages = []
        if self.media_counts is None:
            self.media_counts = {'video': 0, 'photo': 0, 'document': 0}


class FolderNavigator:
    """資料夾導航管理器"""
    
    def __init__(self, base_path: str = "./downloads"):
        self.base_path = os.path.abspath(base_path)
        self.user_states: Dict[int, NavigationState] = {}
        
        # 資料夾命令映射
        self.folder_commands = {
            '/cr': 'create_folder',
            '/cd': 'change_directory', 
            '/cd..': 'parent_directory',
            '/ok': 'confirm_folder',
            '/創建': 'create_folder',
            '/進入': 'change_directory',
            '/退出': 'parent_directory',
            '/確定': 'confirm_folder'
        }
        
        # 確保基礎目錄存在
        os.makedirs(self.base_path, exist_ok=True)
    
    def get_user_state(self, user_id: int) -> NavigationState:
        """獲取或創建用戶狀態"""
        if user_id not in self.user_states:
            self.user_states[user_id] = NavigationState(user_id=user_id)
        return self.user_states[user_id]
    
    def start_folder_selection(self, user_id: int, messages: List, media_counts: Dict[str, int]) -> str:
        """開始資料夾選擇流程"""
        state = self.get_user_state(user_id)
        state.pending_messages = messages
        state.media_counts = media_counts
        state.awaiting_folder_selection = True
        state.current_path = ""  # 重置到根目錄
        
        return self._generate_folder_ui(state)
    
    def is_folder_command(self, text: str) -> bool:
        """檢查是否為資料夾命令"""
        if not text:
            return False
        
        # 檢查完整命令匹配
        command_parts = text.split(' ', 1)
        command = command_parts[0]
        return command in self.folder_commands
    
    def process_folder_command(self, user_id: int, text: str) -> Tuple[str, bool]:
        """
        處理資料夾命令
        Returns: (response_message, is_confirmed)
        """
        state = self.get_user_state(user_id)
        
        if not state.awaiting_folder_selection:
            return "請先發送媒體文件開始下載流程", False
        
        command_parts = text.split(' ', 1)
        command = command_parts[0]
        
        if command not in self.folder_commands:
            return "未知命令，請使用 /cr, /cd, /cd.., /ok 或中文別名", False
        
        action = self.folder_commands[command]
        
        try:
            if action == 'create_folder':
                return self._handle_create_folder(state, command_parts)
            elif action == 'change_directory':
                return self._handle_change_directory(state, command_parts)
            elif action == 'parent_directory':
                return self._handle_parent_directory(state)
            elif action == 'confirm_folder':
                return self._handle_confirm_folder(state)
                
        except Exception as e:
            logger.error(f"處理資料夾命令時出錯: {e}")
            return f"命令執行出錯: {str(e)}", False
        
        return "未知錯誤", False
    
    def _handle_create_folder(self, state: NavigationState, command_parts: List[str]) -> Tuple[str, bool]:
        """處理創建資料夾命令"""
        if len(command_parts) < 2:
            return "請提供資料夾名稱，例如: /cr 我的資料夾", False
        
        folder_name = command_parts[1].strip()
        if not folder_name:
            return "資料夾名稱不能為空", False
        
        # 檢查資料夾名稱是否有效
        if any(char in folder_name for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']):
            return "資料夾名稱包含無效字符", False
        
        # 建立完整路徑
        current_full_path = os.path.join(self.base_path, state.current_path)
        new_folder_path = os.path.join(current_full_path, folder_name)
        
        try:
            os.makedirs(new_folder_path, exist_ok=True)
            # 切換到新建的資料夾
            if state.current_path:
                state.current_path = f"{state.current_path}/{folder_name}"
            else:
                state.current_path = folder_name
                
            logger.info(f"用戶 {state.user_id} 創建並進入資料夾: {state.current_path}")
            
        except Exception as e:
            logger.error(f"創建資料夾失敗: {e}")
            return f"創建資料夾失敗: {str(e)}", False
        
        return self._generate_folder_ui(state), False
    
    def _handle_change_directory(self, state: NavigationState, command_parts: List[str]) -> Tuple[str, bool]:
        """處理切換目錄命令"""
        if len(command_parts) < 2:
            return "請提供資料夾名稱，例如: /cd 我的資料夾", False
        
        folder_name = command_parts[1].strip()
        if not folder_name:
            return "資料夾名稱不能為空", False
        
        # 建立目標路徑
        if state.current_path:
            target_path = f"{state.current_path}/{folder_name}"
        else:
            target_path = folder_name
            
        target_full_path = os.path.join(self.base_path, target_path)
        
        if not os.path.exists(target_full_path):
            return f"資料夾 '{folder_name}' 不存在", False
        
        if not os.path.isdir(target_full_path):
            return f"'{folder_name}' 不是一個資料夾", False
        
        state.current_path = target_path
        logger.info(f"用戶 {state.user_id} 切換到資料夾: {state.current_path}")
        
        return self._generate_folder_ui(state), False
    
    def _handle_parent_directory(self, state: NavigationState) -> Tuple[str, bool]:
        """處理返回上級目錄命令"""
        if not state.current_path:
            return "已經在根目錄了", False
        
        # 移除最後一個資料夾
        path_parts = state.current_path.split('/')
        if len(path_parts) > 1:
            state.current_path = '/'.join(path_parts[:-1])
        else:
            state.current_path = ""
            
        logger.info(f"用戶 {state.user_id} 返回上級目錄: {state.current_path}")
        
        return self._generate_folder_ui(state), False
    
    def _handle_confirm_folder(self, state: NavigationState) -> Tuple[str, bool]:
        """處理確認資料夾命令"""
        display_path = f"/{state.current_path}" if state.current_path else "/"
        
        # 標記為已確認
        state.awaiting_folder_selection = False
        
        logger.info(f"用戶 {state.user_id} 確認存放位置: {display_path}")
        
        return f"📁 已確認存放位置: {display_path}", True
    
    def _generate_folder_ui(self, state: NavigationState) -> str:
        """生成資料夾選擇界面"""
        display_path = f"/{state.current_path}" if state.current_path else "/"
        
        # 獲取當前目錄下的資料夾和文件列表
        current_full_path = os.path.join(self.base_path, state.current_path) if state.current_path else self.base_path
        folders = []
        current_folder_media_counts = {'video': 0, 'photo': 0, 'document': 0}
        
        try:
            if os.path.exists(current_full_path):
                for item in os.listdir(current_full_path):
                    item_path = os.path.join(current_full_path, item)
                    if os.path.isdir(item_path):
                        folders.append(item)
                    elif os.path.isfile(item_path):
                        # 統計當前資料夾中的媒體文件
                        item_lower = item.lower()
                        if any(item_lower.endswith(ext) for ext in ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm']):
                            current_folder_media_counts['video'] += 1
                        elif any(item_lower.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']):
                            current_folder_media_counts['photo'] += 1
                        elif any(item_lower.endswith(ext) for ext in ['.pdf', '.doc', '.docx', '.txt', '.zip', '.rar', '.7z']):
                            current_folder_media_counts['document'] += 1
                folders.sort()
        except Exception as e:
            logger.warning(f"讀取資料夾列表失敗: {e}")
        
        # 構建界面文字
        ui_text = f"📂 請選擇存放位置\n目前在: {display_path}\n"
        
        if folders:
            ui_text += f"資料夾: {', '.join(folders)}\n"
        else:
            ui_text += "資料夾: (無)\n"
        
        # 添加當前資料夾媒體文件統計
        ui_text += f"影片 {current_folder_media_counts['video']} 個\n"
        ui_text += f"照片 {current_folder_media_counts['photo']} 個\n"
        ui_text += f"檔案 {current_folder_media_counts['document']} 個"
        
        return ui_text
    
    def get_selected_path(self, user_id: int) -> str:
        """獲取用戶選擇的路徑"""
        state = self.get_user_state(user_id)
        if state.current_path:
            return os.path.join(self.base_path, state.current_path)
        return self.base_path
    
    def get_pending_messages(self, user_id: int) -> List:
        """獲取待處理的消息"""
        state = self.get_user_state(user_id)
        return state.pending_messages
    
    def clear_user_state(self, user_id: int):
        """清除用戶狀態"""
        if user_id in self.user_states:
            del self.user_states[user_id]
            logger.info(f"已清除用戶 {user_id} 的導航狀態")
    
    def is_awaiting_folder_selection(self, user_id: int) -> bool:
        """檢查用戶是否正在選擇資料夾"""
        state = self.get_user_state(user_id)
        return state.awaiting_folder_selection
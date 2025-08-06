import sqlite3
import os
import logging
from datetime import datetime
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)


class DatabaseManager:
    """SQLite 資料庫管理類，用於防止重複下載文件"""
    
    def __init__(self, db_path: str = "downloads.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """初始化資料庫和表格"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS downloads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        
                        file_unique_id TEXT NOT NULL,           -- Telegram 的全局唯一 ID
                        file_id TEXT NOT NULL,                  -- Telegram 的文件 ID
                        message_id INTEGER NOT NULL,            -- 訊息 ID
                        chat_id INTEGER NOT NULL,               -- 聊天室 ID
                        
                        -- 檔案資訊
                        file_name TEXT NOT NULL,                -- 檔案名稱
                        original_file_name TEXT,                -- 原始檔案名 (如果有)
                        file_path TEXT NOT NULL,                -- 本地檔案路徑
                        file_size INTEGER,                      -- 檔案大小 (bytes)
                        file_type TEXT,                         -- 檔案類型 (photo/video/document/etc)
                        mime_type TEXT,                         -- MIME 類型
                        
                        -- 時間記錄
                        download_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                        message_date DATETIME,                  -- 原始訊息時間
                        
                        -- 主要唯一約束：防止同一檔案重複下載
                        UNIQUE(file_unique_id)
                    )
                """)
                conn.commit()
                logger.info("資料庫初始化完成")
        except Exception as e:
            logger.error(f"資料庫初始化失敗: {e}")
            raise
    
    def is_file_downloaded(self, file_unique_id: str) -> bool:
        """檢查文件是否已經下載過"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT 1 FROM downloads WHERE file_unique_id = ? LIMIT 1",
                    (file_unique_id,)
                )
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"檢查文件是否下載過時出錯: {e}")
            return False
    
    def get_downloaded_file_info(self, file_unique_id: str) -> Optional[dict]:
        """獲取已下載文件的詳細信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row  # 讓結果可以像字典一樣訪問
                cursor = conn.execute("""
                    SELECT * FROM downloads WHERE file_unique_id = ? LIMIT 1
                """, (file_unique_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"獲取文件信息時出錯: {e}")
            return None
    
    def record_download(self, file_unique_id: str, file_id: str, message_id: int, 
                       chat_id: int, file_name: str, file_path: str, 
                       original_file_name: str = None, file_size: int = None, 
                       file_type: str = None, mime_type: str = None, 
                       message_date: datetime = None) -> bool:
        """記錄下載的文件信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO downloads 
                    (file_unique_id, file_id, message_id, chat_id, file_name, 
                     original_file_name, file_path, file_size, file_type, 
                     mime_type, message_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (file_unique_id, file_id, message_id, chat_id, file_name,
                      original_file_name, file_path, file_size, file_type,
                      mime_type, message_date))
                conn.commit()
                logger.debug(f"記錄文件下載: {file_name}")
                return True
        except Exception as e:
            logger.error(f"記錄下載信息時出錯: {e}")
            return False
    
    def get_download_statistics(self) -> dict:
        """獲取下載統計信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_files,
                        SUM(file_size) as total_size,
                        COUNT(DISTINCT chat_id) as unique_chats,
                        file_type,
                        COUNT(*) as count_by_type
                    FROM downloads
                    GROUP BY file_type
                """)
                
                stats_by_type = {}
                total_files = 0
                total_size = 0
                unique_chats = 0
                
                for row in cursor.fetchall():
                    if row[3]:  # file_type
                        stats_by_type[row[3]] = row[4]
                    if not total_files:  # 只取第一行的總計數據
                        total_files = row[0]
                        total_size = row[1] or 0
                        unique_chats = row[2]
                
                return {
                    'total_files': total_files,
                    'total_size_bytes': total_size,
                    'total_size_mb': round((total_size or 0) / (1024 * 1024), 2),
                    'unique_chats': unique_chats,
                    'files_by_type': stats_by_type
                }
        except Exception as e:
            logger.error(f"獲取統計信息時出錯: {e}")
            return {'total_files': 0, 'total_size_bytes': 0, 'total_size_mb': 0, 'unique_chats': 0, 'files_by_type': {}}
    
    def cleanup_missing_files(self) -> Tuple[int, int]:
        """清理資料庫中指向不存在文件的記錄"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT id, file_path FROM downloads")
                records = cursor.fetchall()
                
                missing_count = 0
                total_count = len(records)
                
                for record_id, file_path in records:
                    if not os.path.exists(file_path):
                        conn.execute("DELETE FROM downloads WHERE id = ?", (record_id,))
                        missing_count += 1
                        logger.debug(f"刪除不存在文件的記錄: {file_path}")
                
                conn.commit()
                logger.info(f"清理完成: 刪除了 {missing_count} 個不存在文件的記錄")
                return missing_count, total_count
        except Exception as e:
            logger.error(f"清理資料庫時出錯: {e}")
            return 0, 0
    
    def get_recent_downloads(self, limit: int = 10) -> List[dict]:
        """獲取最近下載的文件列表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM downloads 
                    ORDER BY download_date DESC 
                    LIMIT ?
                """, (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"獲取最近下載列表時出錯: {e}")
            return []
    
    def close(self):
        """關閉資料庫連接（在這個實現中是 no-op，因為我們使用 context manager）"""
        pass
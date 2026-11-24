import asyncio
import os
import logging
import time
import json
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from telethon.errors import FloodWaitError, RPCError
from telethon import TelegramClient
from .records import DownloadRecords

logger = logging.getLogger(__name__)

# The Telegram message text stored as the file's `description` (sidecar, editable in the web library)
DESCRIPTION_ATTR = 'tad_description'


def describe(messages, root=None, captions=None):
    """Set each message's description: its own text, else its album's caption (from `captions`
    {grouped_id: text} or the other messages of the list), else the text of `root` (the original
    post when these are its replies). Messages that already have one are left alone."""
    captions = dict(captions or {})
    for m in messages:
        text = (getattr(m, 'message', '') or '').strip()
        if getattr(m, 'grouped_id', None) and text:
            captions.setdefault(m.grouped_id, text)
    root_text = (getattr(root, 'message', '') or '').strip() if root is not None else ''
    for m in messages:
        if getattr(m, DESCRIPTION_ATTR, None) is None:
            text = (getattr(m, 'message', '') or '').strip()
            setattr(m, DESCRIPTION_ATTR, text or captions.get(getattr(m, 'grouped_id', None), '') or root_text)
    return messages


class MediaDownloader:
    """處理媒體文件下載的類"""
    
    def __init__(self, client: TelegramClient, max_concurrent_downloads=5):
        self.client = client
        self.max_concurrent_downloads = max_concurrent_downloads
        self.download_semaphore = asyncio.Semaphore(max_concurrent_downloads)
        self.monitor = None
        self.db = DownloadRecords()   # records live next to the files (src/records.py)
        self.message_callback = None
    
    def set_monitor(self, monitor):
        """設定監控器"""
        self.monitor = monitor
    
    def set_message_callback(self, callback):
        """設定訊息回調函數，用於發送訊息給用戶"""
        self.message_callback = callback
    
    def get_media_size(self, message):
        """獲取媒體文件大小"""
        try:
            if not message.media:
                return 0

            if hasattr(message, 'file') and message.file and hasattr(message.file, 'size'):
                return message.file.size
            
            if isinstance(message.media, MessageMediaPhoto):
                # 照片大小通常較小，使用預估值
                return message.media.photo.sizes[-1].size if hasattr(message.media.photo, 'sizes') else 500000  # 預估500KB
            
            elif isinstance(message.media, MessageMediaDocument):
                return message.media.document.size if hasattr(message.media.document, 'size') else 0
                
        except Exception as e:
            logger.debug(f"獲取媒體大小時出錯: {e}")
            return 0
        
        return 0

    @staticmethod
    def _remove_partial(tmp_path):
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    async def download_media_with_retry(self, message, file_path, max_retries=3):
        """下載媒體文件，包含重試機制和進度追蹤

        先下載到 "<檔名>.part"，完成後才改成正式檔名：下載中或中斷的檔案不會被當成完整影片
        （網頁影片庫、/files 都會略過 .part）。
        """
        tmp_path = file_path + '.part'
        async with self.download_semaphore:  # 控制併發數量
            for attempt in range(max_retries):
                try:
                    # 初始化進度統計
                    if self.monitor:
                        stats = self.monitor.get_stats()
                        stats['start_time'] = time.time()
                        stats['_last_progress'] = 0  # 用於追蹤進度差
                        self.monitor.update_stats(stats)
                        
                    # 使用進度回調來追蹤下載進度
                    def progress_callback(current, total):
                        if self.monitor:
                            stats = self.monitor.get_stats()
                            # 更新已下載大小（粗略估算）
                            downloaded = current - stats.get('_last_progress', 0)
                            stats['downloaded_size'] += max(downloaded, 0)
                            stats['_last_progress'] = current
                            self.monitor.update_stats(stats)
                    
                    await self.client.download_media(
                        message, 
                        tmp_path,
                        progress_callback=progress_callback
                    )
                    if not os.path.exists(tmp_path):
                        logger.error(f"下載沒有產生檔案: {file_path}")
                        return False
                    os.replace(tmp_path, file_path)

                    # 更新統計
                    if os.path.exists(file_path) and self.monitor:
                        file_size = os.path.getsize(file_path)
                        stats = self.monitor.get_stats()
                        stats['completed_files'] += 1
                        self.monitor.update_stats(stats)
                    
                    return True
                    
                except (ConnectionError, OSError, asyncio.TimeoutError, RPCError) as e:
                    if attempt == max_retries - 1:
                        logger.error(f"下載失敗，已嘗試 {max_retries} 次: {e}")
                        self._remove_partial(tmp_path)
                        if self.monitor:
                            stats = self.monitor.get_stats()
                            stats['failed_files'] += 1
                            self.monitor.update_stats(stats)
                        return False
                    
                    wait_time = (2 ** attempt) + 1  # 指數退避：2, 3, 5 秒
                    logger.warning(f"下載失敗 (嘗試 {attempt + 1}/{max_retries})，{wait_time} 秒後重試: {e}")
                    await asyncio.sleep(wait_time)
                    
                except FloodWaitError as e:
                    logger.warning(f"觸發限流，等待 {e.seconds} 秒")
                    await asyncio.sleep(e.seconds)
                    
                except Exception as e:
                    logger.error(f"下載時發生未知錯誤: {e}")
                    self._remove_partial(tmp_path)
                    if self.monitor:
                        stats = self.monitor.get_stats()
                        stats['failed_files'] += 1
                        self.monitor.update_stats(stats)
                    return False
        
        return False

    @staticmethod
    def file_name_for(message):
        """(file name, file type, original name, mime type) a message's media is saved as, or None.

        Photos: photo_<msg id>_<date>.jpg; documents (videos, GIFs...): <msg id>_<original name>, or
        document_<msg id>_<date><ext> without one. Also used to recognise a file's source message
        when it has no download record (re-download of a broken video).
        """
        if isinstance(message.media, MessageMediaPhoto):
            return f"photo_{message.id}_{message.date.strftime('%Y%m%d_%H%M%S')}.jpg", "photo", "", None
        if not isinstance(message.media, MessageMediaDocument):
            return None
        document = message.media.document
        original_name, file_extension = "", ""
        for attr in document.attributes:
            if hasattr(attr, 'file_name') and attr.file_name:
                original_name = attr.file_name
                file_extension = os.path.splitext(attr.file_name)[1]
                break
        mime_type = document.mime_type or ''
        if not file_extension:                     # 沒有副檔名：根據 MIME 類型推斷
            if mime_type.startswith('video/'):
                file_extension = '.mp4'
            elif mime_type.startswith('image/'):
                file_extension = '.gif' if 'gif' in mime_type else '.jpg'
            elif mime_type.startswith('audio/'):
                file_extension = '.mp3'
            else:
                file_extension = '.bin'
        if original_name:
            file_name = f"{message.id}_{original_name}"
        else:
            file_name = f"document_{message.id}_{message.date.strftime('%Y%m%d_%H%M%S')}{file_extension}"
        return file_name, "document", original_name, mime_type or None

    async def download_media_from_message(self, message, download_dir):
        """從訊息中下載媒體文件"""
        if not message.media:
            return []
        
        # 檢查是否已經下載過這個文件
        file_unique_id = self._get_file_unique_id(message)
        if file_unique_id and self.db.is_file_downloaded(file_unique_id):
            existing_info = self.db.get_downloaded_file_info(file_unique_id)
            if existing_info and os.path.exists(existing_info['file_path']):
                logger.info(f"文件已存在，跳過下載: {existing_info['file_name']}")
                # 更新統計信息 - 標記為跳過
                if self.monitor:
                    stats = self.monitor.get_stats()
                    stats['completed_files'] += 1
                    self.monitor.update_stats(stats)
                return [existing_info['file_name']]
            else:
                logger.debug(f"檔案記錄存在但實體檔案不存在，將重新下載: {file_unique_id}")
        
        try:
            os.makedirs(download_dir, exist_ok=True)
            downloaded_files = []
            named = self.file_name_for(message)
            if named:
                file_name, file_type, original_name, mime_type = named
                file_path = os.path.join(download_dir, file_name)
                label = "照片" if file_type == "photo" else "文檔"
                if await self.download_media_with_retry(message, file_path):
                    downloaded_files.append(file_name)
                    logger.info(f"下載{label}: {file_name}")
                    self._record_download_to_db(message, file_name, file_path, file_type, download_dir,
                                                original_name or None, mime_type,
                                                description=getattr(message, DESCRIPTION_ATTR, None))
                else:
                    logger.error(f"{label}下載失敗: {file_name}")
            return downloaded_files
            
        except Exception as e:
            logger.error(f"下載媒體時出錯: {e}")
            return []

    async def download_multiple_messages_concurrent(self, messages, download_dir):
        """並發下載多個消息的媒體文件"""
        if not messages:
            return []
        describe(messages)   # album captions for the files that have no text of their own

        # 過濾已下載的文件
        messages_to_download = []
        skipped_count = 0
        
        for message in messages:
            if not message.media:
                continue
                
            file_unique_id = self._get_file_unique_id(message)
            if file_unique_id and self.db.is_file_downloaded(file_unique_id):
                existing_info = self.db.get_downloaded_file_info(file_unique_id)
                if existing_info and os.path.exists(existing_info['file_path']):
                    logger.debug(f"跳過已下載的文件: {existing_info['file_name']}")
                    skipped_count += 1
                    continue
            
            messages_to_download.append(message)
        
        if skipped_count > 0:
            logger.info(f"跳過 {skipped_count} 個已下載的文件")
            # 發送訊息到 Telegram
            if self.message_callback:
                try:
                    await self.message_callback(f"⏭️ 跳過 {skipped_count} 個已下載的文件")
                except Exception as e:
                    logger.warning(f"發送跳過文件訊息失敗: {e}")
        
        # 統計總文件數和總大小
        total_media_count = len(messages_to_download)
        
        # 計算總文件大小
        total_size = 0
        for message in messages_to_download:
            if message.media:
                size = self.get_media_size(message)
                total_size += size
                
        messages_to_download = sorted(messages_to_download, key=self.get_media_size)
        
        # 更新監控器統計
        if self.monitor:
            stats = self.monitor.get_stats()
            stats.update({
                'total_files': total_media_count,
                'total_size': total_size,
                'start_time': time.time(),
                'completed_files': stats.get('completed_files', 0) + skipped_count  # 將跳過的文件算作已完成
            })
            self.monitor.update_stats(stats)
        
        if total_media_count == 0:
            return []
        
        logger.info(f"開始並發下載 {total_media_count} 個媒體文件，總大小: {total_size/(1024**2):.1f}MB")
        
        # 創建下載任務
        download_tasks = []
        for message in messages_to_download:
            if message.media:
                task = self.download_media_from_message(message, download_dir)
                download_tasks.append(task)
        
        # 並發執行所有下載任務
        try:
            results = await asyncio.gather(*download_tasks, return_exceptions=True)
            
            # 合併結果
            all_files = []
            for result in results:
                if isinstance(result, list):
                    all_files.extend(result)
                elif isinstance(result, Exception):
                    logger.error(f"下載任務異常: {result}")
                    if self.monitor:
                        stats = self.monitor.get_stats()
                        stats['failed_files'] += 1
                        self.monitor.update_stats(stats)
            
            return all_files
            
        except Exception as e:
            logger.error(f"下載出錯: {e}")
            return []

    def save_progress(self, download_dir, progress_data):
        """保存下載進度"""
        progress_file = os.path.join(download_dir, '.download_progress.json')
        try:
            with open(progress_file, 'w', encoding='utf-8') as f:
                json.dump(progress_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"無法保存進度: {e}")

    def load_progress(self, download_dir):
        """載入下載進度"""
        progress_file = os.path.join(download_dir, '.download_progress.json')
        try:
            if os.path.exists(progress_file):
                with open(progress_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"無法載入進度: {e}")
        return {"completed_files": [], "failed_files": []}
    
    def _get_file_unique_id(self, message):
        """獲取文件的唯一 ID"""
        try:
            if not message.media:
                return None
                
            if isinstance(message.media, MessageMediaPhoto):
                return message.media.photo.id
            elif isinstance(message.media, MessageMediaDocument):
                return message.media.document.id
        except Exception as e:
            logger.debug(f"獲取文件唯一 ID 時出錯: {e}")
        return None
    
    def _record_download_to_db(self, message, file_name, file_path, file_type, download_dir, original_file_name=None,
                               mime_type=None, description=None):
        """記錄下載信息（檔案旁的 sidecar）；description 預設為訊息文字"""
        try:
            file_unique_id = self._get_file_unique_id(message)
            if not file_unique_id:
                return False
            
            file_id = ""
            if isinstance(message.media, MessageMediaPhoto):
                file_id = message.media.photo.access_hash
            elif isinstance(message.media, MessageMediaDocument):
                file_id = message.media.document.access_hash
            
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else None
            
            success = self.db.record_download(
                file_unique_id=str(file_unique_id),
                file_id=str(file_id),
                message_id=message.id,
                chat_id=message.peer_id.channel_id if hasattr(message.peer_id, 'channel_id') else 0,
                file_name=file_name,
                file_path=file_path,
                original_file_name=original_file_name,
                file_size=file_size,
                file_type=file_type,
                mime_type=mime_type,
                message_date=message.date,
                description=(getattr(message, 'message', '') or '').strip() if description is None else description,
            )
            
            if success:
                logger.debug(f"成功記錄下載信息到資料庫: {file_name}")
            else:
                logger.warning(f"記錄下載信息失敗: {file_name}")
                
            return success
        except Exception as e:
            logger.error(f"記錄下載信息到資料庫時出錯: {e}")
            return False
    
    def get_download_statistics(self):
        """獲取下載統計信息"""
        return self.db.get_download_statistics()
    
    def cleanup_missing_files(self):
        """清理資料庫中指向不存在文件的記錄"""
        return self.db.cleanup_missing_files()
    
    def get_recent_downloads(self, limit=10):
        """獲取最近下載的文件列表"""
        return self.db.get_recent_downloads(limit)
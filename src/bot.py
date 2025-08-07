import asyncio
import os
import logging
import time
import json
import shutil
from telethon import TelegramClient
from telethon.errors import RPCError
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from datetime import datetime

from .monitor import DownloadMonitor
from .downloader import MediaDownloader
from .folder_navigator import FolderNavigator

# 設定日誌
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 減少第三方庫的詳細日誌
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telethon.client.updates').setLevel(logging.WARNING)


class TelegramMediaBot:
    """Telegram媒體下載機器人主類"""
    
    def __init__(self, api_id, api_hash, phone_number, bot_token):
        # Media group tracking
        self.media_groups = {}
        self.group_timers = {}
        
        # Telegram Client (用於訪問 API) - 優化連接設定
        self.client = TelegramClient(
            'bot_session', 
            api_id, 
            api_hash,
            connection_retries=3,
            retry_delay=1,
            auto_reconnect=True,
            timeout=30
        )
        
        # Save main event loop
        self.loop = asyncio.get_event_loop()
        
        # 初始化組件
        self.monitor = DownloadMonitor(self.loop)
        # 設定資料庫路徑在專案根目錄
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "downloads.db")
        self.downloader = MediaDownloader(self.client, max_concurrent_downloads=5, db_path=db_path)
        self.downloader.set_monitor(self.monitor)
        # 初始化資料夾導航器
        downloads_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "downloads")
        self.folder_navigator = FolderNavigator(downloads_path)
        
        self.phone_number = phone_number
        self.bot_token = bot_token
        
        # Bot Application
        self.app = Application.builder().token(bot_token).build()
        
        # 設定處理器
        self.app.add_handler(MessageHandler(filters.ALL, self.handle_message))
    
    async def start_client(self):
        """啟動 Telegram Client"""
        await self.client.start(phone=self.phone_number)
        logger.info("Telegram Client 已啟動")
    
    async def get_message_and_replies(self, chat_id, message_id):
        """獲取指定訊息及其所有回覆"""
        try:
            logger.info(f"正在獲取 chat_id={chat_id}, message_id={message_id} 的訊息")
            
            # 獲取聊天實體
            try:
                chat = await self.client.get_entity(chat_id)
                logger.info(f"成功獲取聊天實體: {chat.title if hasattr(chat, 'title') else chat}")
            except Exception as entity_error:
                logger.error(f"無法獲取聊天實體 {chat_id}: {entity_error}")
                return None, []
            
            # 獲取原始訊息
            try:
                original_message = await self.client.get_messages(chat, ids=message_id)
                if not original_message:
                    logger.warning(f"未找到訊息 ID {message_id}")
                    return None, []
                logger.info(f"成功獲取原始訊息 ID {message_id}")
            except Exception as msg_error:
                logger.error(f"無法獲取訊息 {message_id}: {msg_error}")
                return None, []
            
            # 獲取所有回覆 - 使用更安全的方法
            replies = []
            try:
                async for reply in self.client.iter_messages(chat, reply_to=message_id):
                    replies.append(reply)
                logger.info(f"成功獲取 {len(replies)} 則回覆")
            except Exception as reply_error:
                logger.warning(f"獲取回覆時出錯，但會繼續處理原訊息: {reply_error}")
                # 即使獲取回覆失敗，也返回原訊息
            
            logger.info(f"找到原訊息和 {len(replies)} 則回覆")
            return original_message, replies
            
        except RPCError as rpc_error:
            logger.error(f"Telegram API 錯誤: {rpc_error}")
            return None, []
        except Exception as e:
            logger.error(f"獲取訊息時發生未預期錯誤: {e}")
            return None, []
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理收到的訊息 - 簡化流程"""
        message = update.message
        user_id = message.from_user.id
        
        # 1. 檢查是否為命令
        if await self._handle_commands(message, user_id):
            return
        
        # 2. 檢查是否為可下載的訊息（拒絕私人群組/聊天）
        if not await self._is_downloadable_message(message):
            return
        
        # 3. 處理媒體組收集或直接處理單個訊息
        if message.media_group_id:
            await self._handle_media_group(update, context)
        else:
            await self._process_message(message)
    
    async def _handle_commands(self, message, user_id):
        """處理命令，返回True表示已處理"""
        # 檢查是否為資料夾導航命令
        if message.text and self.folder_navigator.is_folder_command(message.text):
            response, is_confirmed = self.folder_navigator.process_folder_command(user_id, message.text)
            await message.reply_text(response)
            
            if is_confirmed:
                # 開始下載流程
                await asyncio.sleep(2)  # 等待2秒如用戶需求
                await self._start_download_process(user_id, message)
            return True
        
        # 檢查用戶是否正在選擇資料夾
        if self.folder_navigator.is_awaiting_folder_selection(user_id):
            await message.reply_text("請使用資料夾命令選擇存放位置：\n/cr 資料夾名 - 創建資料夾\n/cd 資料夾名 - 進入資料夾\n/cd.. - 返回上級\n/ok - 確認位置")
            return True
        
        return False
    
    async def _is_downloadable_message(self, message):
        """檢查是否為可下載的訊息（拒絕私人群組/聊天）"""
        if not message.forward_origin:
            await message.reply_text(
                "請轉發一則訊息給我，我會備份該訊息及其所有回覆中的媒體文件到伺服器！\n\n"
                "支援的媒體類型：照片、影片、GIF、音訊等"
            )
            return False
        
        # 檢查是否來自私人聊天或隱藏用戶
        from telegram import MessageOriginChannel, MessageOriginChat
        if not isinstance(message.forward_origin, (MessageOriginChannel, MessageOriginChat)):
            await message.reply_text("❌ 暫不支援來自私人聊天或隱藏用戶的轉發訊息")
            return False
        
        return True
    
    async def _handle_media_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理媒體組消息"""
        message = update.message
        media_group_id = message.media_group_id
        
        # 將消息添加到媒體組
        if media_group_id not in self.media_groups:
            self.media_groups[media_group_id] = []
        
        self.media_groups[media_group_id].append(message)
        logger.info(f"收集媒體組 {media_group_id} 中的消息，目前有 {len(self.media_groups[media_group_id])} 個")
        
        # 取消之前的計時器（如果存在）
        if media_group_id in self.group_timers:
            self.group_timers[media_group_id].cancel()
        
        # 設定新的計時器，2秒後處理媒體組
        self.group_timers[media_group_id] = asyncio.create_task(
            self._process_media_group_delayed(media_group_id, 2.0)
        )
    
    async def _process_media_group_delayed(self, media_group_id: str, delay: float):
        """延遲處理媒體組，確保收集所有相關消息"""
        await asyncio.sleep(delay)
        
        if media_group_id in self.media_groups:
            messages = self.media_groups[media_group_id]
            logger.info(f"開始處理媒體組 {media_group_id}，包含 {len(messages)} 個消息")
            
            # 使用第一個消息作為主消息進行處理
            if messages:
                primary_message = messages[0]
                await self._process_message(primary_message, messages)
            
            # 清理
            del self.media_groups[media_group_id]
            if media_group_id in self.group_timers:
                del self.group_timers[media_group_id]
    
    async def _process_message(self, message, group_messages=None):
        """統一處理訊息 - 提取所有文件到下載列表"""
        user_id = message.from_user.id
        is_group = group_messages is not None
        
        # 發送處理中訊息
        processing_msg = await message.reply_text(
            f"📡 正在獲取來自{'媒體組' if is_group else ''}的訊息..."
        )
        
        try:
            # 提取原訊息資訊
            chat_id, original_message_id, chat_name = self._extract_forward_info(message)
            if not chat_id:
                await processing_msg.edit_text("❌ 暫不支援來自私人聊天或隱藏用戶的轉發訊息")
                return
            
            await processing_msg.edit_text(f"📡 正在獲取來自 {chat_name} 的訊息...")
            
            # 獲取原訊息和回覆
            original_message, replies = await self.get_message_and_replies(chat_id, original_message_id)
            if not original_message:
                await processing_msg.edit_text(self._get_error_message())
                return
            
            # 3. 提取所有文件到下載列表（原始+回覆+媒體組）
            messages_to_download = await self._extract_all_files(
                original_message, replies, chat_id, original_message_id, is_group
            )
            
            if not messages_to_download:
                await processing_msg.edit_text("ℹ️ 該訊息及其回覆中沒有找到任何媒體文件")
                return
            
            # 統計媒體類型
            media_counts = self._count_media_types(messages_to_download)
            
            # 4. 資料夾選擇
            folder_ui = self.folder_navigator.start_folder_selection(
                user_id, group_messages or [message], media_counts
            )
            await processing_msg.edit_text(folder_ui)
            
        except Exception as e:
            logger.error(f"處理訊息時出錯: {e}")
            await processing_msg.edit_text(f"❌ 處理時出錯: {str(e)}")
    
    def _extract_forward_info(self, message):
        """提取轉發訊息資訊"""
        from telegram import MessageOriginChannel, MessageOriginChat
        
        if isinstance(message.forward_origin, MessageOriginChannel):
            return (
                message.forward_origin.chat.id,
                message.forward_origin.message_id,
                message.forward_origin.chat.title or message.forward_origin.chat.username
            )
        elif isinstance(message.forward_origin, MessageOriginChat):
            return (
                message.forward_origin.sender_chat.id,
                message.forward_origin.message_id,
                message.forward_origin.sender_chat.title or message.forward_origin.sender_chat.username
            )
        else:
            return None, None, None
    
    def _get_error_message(self):
        """獲取標準錯誤訊息"""
        return (
            "❌ 無法獲取原訊息\n\n"
            "可能的原因：\n"
            "• Bot 沒有權限訪問該頻道/群組\n"
            "• 訊息已被刪除\n"
            "• 訊息 ID 無效\n\n"
            "請確認 Bot 是該頻道/群組的成員"
        )
    
    async def _extract_all_files(self, original_message, replies, chat_id, original_message_id, is_group):
        """提取所有文件（原始+回覆+媒體組）到下載列表"""
        messages_to_download = []
        
        # 添加原始消息文件
        if original_message.media:
            messages_to_download.append(original_message)
        
        # 如果是媒體組，嘗試獲取所有相關媒體
        if is_group and hasattr(original_message, 'grouped_id') and original_message.grouped_id:
            try:
                telethon_group_id = original_message.grouped_id
                # 搜索媒體組中的所有消息
                async for msg in self.client.iter_messages(chat_id, limit=100):
                    if (hasattr(msg, 'grouped_id') and 
                        msg.grouped_id == telethon_group_id and 
                        msg.media and 
                        msg.id != original_message.id):  # 避免重複
                        messages_to_download.append(msg)
                logger.info(f"從媒體組找到 {len(messages_to_download)} 個媒體文件")
            except Exception as e:
                logger.warning(f"無法獲取媒體組文件: {e}")
        
        # 添加回覆中的媒體
        for reply in replies:
            if reply.media:
                messages_to_download.append(reply)
        
        return messages_to_download
    
    def _count_media_types(self, messages):
        """統計媒體類型"""
        media_counts = {'video': 0, 'photo': 0, 'document': 0}
        for msg in messages:
            if msg.video or (hasattr(msg, 'document') and msg.document and 
                           msg.document.mime_type and msg.document.mime_type.startswith('video/')):
                media_counts['video'] += 1
            elif msg.photo:
                media_counts['photo'] += 1 
            elif hasattr(msg, 'document') and msg.document:
                media_counts['document'] += 1
        return media_counts
    
    async def _start_download_process(self, user_id: int, message):
        """開始下載流程，處理已確認的資料夾選擇"""
        try:
            # 獲取待處理的消息
            pending_messages = self.folder_navigator.get_pending_messages(user_id)
            if not pending_messages:
                await message.reply_text("❌ 沒有找到待處理的消息")
                return
            
            # 獲取選定的下載路徑
            selected_path = self.folder_navigator.get_selected_path(user_id)
            
            # 發送分析中的消息
            processing_msg = await message.reply_text("📊 正在分析媒體文件...")
            
            # 5. 統一處理已確認的下載
            await self._process_confirmed_download(processing_msg, pending_messages, selected_path, user_id)
                
            # 清除用戶狀態
            self.folder_navigator.clear_user_state(user_id)
            
        except Exception as e:
            logger.error(f"開始下載流程時出錯: {e}")
            await message.reply_text(f"❌ 開始下載時出錯: {str(e)}")
    
    async def _process_confirmed_download(self, processing_msg, pending_messages, selected_path, user_id):
        """處理已確認資料夾的下載 - 統一流程"""
        try:
            first_message = pending_messages[0]
            
            # 提取來源資訊
            chat_id, original_message_id, chat_name = self._extract_forward_info(first_message)
            if not chat_id:
                await processing_msg.edit_text("❌ 無法處理此類型的轉發訊息")
                return
            
            # 獲取原始消息和回覆
            original_message, replies = await self.get_message_and_replies(chat_id, original_message_id)
            if not original_message:
                await processing_msg.edit_text("❌ 無法訪問原始訊息")
                return
            
            # 提取所有文件到下載列表
            is_group = len(pending_messages) > 1
            messages_to_download = await self._extract_all_files(
                original_message, replies, chat_id, original_message_id, is_group
            )
            
            if not messages_to_download:
                await processing_msg.edit_text("ℹ️ 該訊息及其回覆中沒有找到任何媒體文件")
                return
            
            # 創建下載目錄
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dir_prefix = "mediagroup" if is_group else "message"
            download_dir = os.path.join(selected_path, f"{dir_prefix}_{original_message_id}_{timestamp}")
            
            # 開始下載
            await self._download_and_monitor(processing_msg, messages_to_download, download_dir, original_message_id, chat_name)
            
        except Exception as e:
            logger.error(f"處理已確認下載時出錯: {e}")
            await processing_msg.edit_text(f"❌ 處理時出錯: {str(e)}")
    
    async def _download_and_monitor(self, processing_msg, messages_to_download, download_dir, original_message_id, chat_name):
        """共用的下載和監控邏輯"""
        # 初始化下載統計
        self.monitor.update_stats({
            'total_files': 0,
            'completed_files': 0,
            'failed_files': 0,
            'total_size': 0,
            'downloaded_size': 0,
            'start_time': time.time()
        })
        
        # 啟動監控線程
        self.monitor.start_monitoring_thread(download_dir, processing_msg)
        
        try:
            await processing_msg.edit_text("📊 正在分析媒體文件...")
            
            # 預先計算總文件大小
            total_size = 0
            for message in messages_to_download:
                if message.media:
                    size = await self.downloader.get_media_size(message)
                    total_size += size
            
            total_size_mb = total_size / (1024**2)
            await processing_msg.edit_text(f"🚀 開始下載 {len(messages_to_download)} 個媒體文件，總大小: {total_size_mb:.1f}MB...")
            
            # 使用並發下載
            all_downloaded_files = await self.downloader.download_multiple_messages_concurrent(
                messages_to_download, download_dir
            )
            
        finally:
            # 停止監控線程
            self.monitor.stop_monitoring()
        
        # 獲取最終統計
        final_stats = self.monitor.get_stats()
        
        # 計算下載時間和速度
        elapsed_time = time.time() - final_stats['start_time']
        avg_speed = (final_stats['downloaded_size'] / (1024**2)) / max(elapsed_time, 1)
        
        # 獲取最終磁碟空間
        disk_usage = self.monitor.get_disk_usage(download_dir)
        
        # 建立結果訊息
        result_msg = f"✅ 下載完成！\n"
        result_msg += f"原訊息 ID: {original_message_id}\n"
        result_msg += f"來源: {chat_name}\n"
        result_msg += f"成功下載: {final_stats['completed_files']} 個媒體文件\n"
        
        if final_stats['failed_files'] > 0:
            result_msg += f"失敗: {final_stats['failed_files']} 個文件\n"
        
        # 顯示下載大小和預期大小的對比
        if final_stats['total_size'] > 0:
            completion_rate = (final_stats['downloaded_size'] / final_stats['total_size']) * 100
            result_msg += f"下載大小: {final_stats['downloaded_size']/(1024**2):.1f}MB / {final_stats['total_size']/(1024**2):.1f}MB ({completion_rate:.1f}%)\n"
        else:
            result_msg += f"下載大小: {final_stats['downloaded_size']/(1024**2):.1f}MB\n"
        
        result_msg += f"平均速度: {avg_speed:.1f}MB/s\n"
        result_msg += f"耗時: {elapsed_time:.1f}秒\n"
        result_msg += f"剩餘空間: {disk_usage['free_gb']:.1f}GB\n"
        result_msg += f"儲存位置: {download_dir}"
        
        await processing_msg.edit_text(result_msg)
        
        # 記錄完成日誌
        logger.info(
            f"下載完成 - 成功: {final_stats['completed_files']}, "
            f"失敗: {final_stats['failed_files']}, "
            f"總大小: {final_stats['downloaded_size']/(1024**2):.1f}MB, "
            f"速度: {avg_speed:.1f}MB/s"
        )
    
    def get_download_statistics(self):
        """獲取下載統計信息"""
        return self.downloader.get_download_statistics()
    
    def cleanup_missing_files(self):
        """清理資料庫中指向不存在文件的記錄"""
        return self.downloader.cleanup_missing_files()
    
    def get_recent_downloads(self, limit=10):
        """獲取最近下載的文件列表"""
        return self.downloader.get_recent_downloads(limit)
    
    async def run(self):
        """啟動 Bot"""
        try:
            # 啟動 Telegram Client
            await self.start_client()
            
            # 啟動 Bot
            logger.info("正在啟動 Telegram Bot...")
            await self.app.initialize()
            await self.app.start()
            
            logger.info("Bot 已啟動！可以開始轉發訊息了")
            
            # 保持運行
            await self.app.updater.start_polling()
            
            # 等待直到被停止
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Bot 運行出錯: {e}")
        finally:
            # 清理
            await self.app.stop()
            await self.app.shutdown()
            await self.client.disconnect()
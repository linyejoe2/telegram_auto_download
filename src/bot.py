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
        self.folder_navigator = FolderNavigator(base_path=downloads_path)
        
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
        """處理收到的訊息"""
        message = update.message
        user_id = message.from_user.id
        
        # 檢查是否為資料夾命令
        if message.text and self.folder_navigator.is_folder_command(message.text):
            response, is_confirmed = self.folder_navigator.process_folder_command(user_id, message.text)
            await message.reply_text(response)
            
            # 如果確認了資料夾選擇，開始下載
            if is_confirmed:
                pending_messages = self.folder_navigator.get_pending_messages(user_id)
                if pending_messages:
                    await self._start_download_with_selected_folder(update, context, pending_messages)
                    # 清除用戶狀態
                    self.folder_navigator.clear_user_state(user_id)
            return
        
        # 檢查用戶是否正在選擇資料夾，如果是則忽略非命令消息
        if self.folder_navigator.is_awaiting_folder_selection(user_id):
            await message.reply_text("請使用資料夾命令: /cr 創建資料夾, /cd 進入資料夾, /cd.. 返回上級, /ok 確認位置")
            return
        
        # 檢查是否為轉發訊息
        if not message.forward_origin:
            await message.reply_text(
                "請轉發一則訊息給我，我會備份該訊息及其所有回覆中的媒體文件到伺服器！\n\n"
                "支援的媒體類型：照片、影片、GIF、音訊等\n\n"
                "資料夾命令:\n"
                "• /cr <名稱> - 創建資料夾\n"
                "• /cd <名稱> - 進入資料夾\n" 
                "• /cd.. - 返回上級目錄\n"
                "• /ok - 確認當前位置並開始下載"
            )
            return
        
        # 檢查是否為媒體組
        media_group_id = message.media_group_id
        if media_group_id:
            await self._handle_media_group(update, context)
        else:
            await self._process_single_message(update, context)
    
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
                # 創建一個更新對象來處理
                from telegram import Update, Message
                fake_update = Update(
                    update_id=0,
                    message=primary_message
                )
                
                # 將所有媒體組消息合併處理
                await self._process_grouped_messages(fake_update, messages)
            
            # 清理
            del self.media_groups[media_group_id]
            if media_group_id in self.group_timers:
                del self.group_timers[media_group_id]
    
    async def _process_grouped_messages(self, update: Update, group_messages: list):
        """處理合併的媒體組消息"""
        primary_message = update.message
        user_id = primary_message.from_user.id
        
        # 發送處理中訊息 - 只對第一個消息回復
        processing_msg = await primary_message.reply_text(f"🔄 正在分析媒體組 ({len(group_messages)} 個文件)，請稍候...")
        
        try:
            # 提取原訊息資訊
            from telegram import MessageOriginChannel, MessageOriginUser, MessageOriginHiddenUser, MessageOriginChat
            
            if isinstance(primary_message.forward_origin, MessageOriginChannel):
                # 來自頻道
                chat_id = primary_message.forward_origin.chat.id
                original_message_id = primary_message.forward_origin.message_id
                chat_name = primary_message.forward_origin.chat.title or primary_message.forward_origin.chat.username
            elif isinstance(primary_message.forward_origin, MessageOriginChat):
                # 來自群組
                chat_id = primary_message.forward_origin.sender_chat.id
                original_message_id = primary_message.forward_origin.message_id
                chat_name = primary_message.forward_origin.sender_chat.title or primary_message.forward_origin.sender_chat.username
            else:
                # 來自私人聊天或隱藏用戶
                await processing_msg.edit_text("❌ 暫不支援來自私人聊天或隱藏用戶的轉發訊息")
                return
            
            await processing_msg.edit_text(f"📡 正在獲取來自 {chat_name} 的媒體組訊息...")
            
            # 獲取原訊息和回覆
            original_message, replies = await self.get_message_and_replies(chat_id, original_message_id)
            
            if not original_message:
                error_msg = (
                    "❌ 無法獲取原訊息\n\n"
                    "可能的原因：\n"
                    "• Bot 沒有權限訪問該頻道/群組\n"
                    "• 訊息已被刪除\n"
                    "• 訊息 ID 無效\n\n"
                    "請確認 Bot 是該頻道/群組的成員"
                )
                await processing_msg.edit_text(error_msg)
                return
            
            # 準備所有需要下載的消息（包含媒體組中的所有消息）
            messages_to_download = []
            
            # 對於媒體組，我們需要從原始頻道獲取相關的所有消息
            media_group_id = primary_message.media_group_id
            if media_group_id:
                # 獲取原始頻道中的媒體組消息
                try:
                    # 方法1: 如果原始消息有grouped_id，使用它來查找所有相關消息
                    if hasattr(original_message, 'grouped_id') and original_message.grouped_id:
                        telethon_group_id = original_message.grouped_id
                        async for msg in self.client.iter_messages(chat_id, limit=100):
                            if hasattr(msg, 'grouped_id') and msg.grouped_id == telethon_group_id and msg.media:
                                messages_to_download.append(msg)
                        logger.info(f"從原始頻道找到媒體組 {telethon_group_id} 的 {len(messages_to_download)} 個媒體文件")
                    
                    # 方法2: 如果方法1沒找到文件，嘗試搜索原始消息周圍的消息
                    if not messages_to_download:
                        # 獲取原始消息前後的消息來尋找媒體組
                        base_id = original_message_id
                        search_range = 20  # 搜索前後20個消息
                        
                        async for msg in self.client.iter_messages(
                            chat_id, 
                            min_id=max(1, base_id - search_range),
                            max_id=base_id + search_range
                        ):
                            if msg.media and hasattr(msg, 'grouped_id') and msg.grouped_id:
                                messages_to_download.append(msg)
                        
                        # 如果找到多個有grouped_id的消息，按grouped_id分組
                        if messages_to_download:
                            grouped_messages = {}
                            for msg in messages_to_download:
                                group_id = msg.grouped_id
                                if group_id not in grouped_messages:
                                    grouped_messages[group_id] = []
                                grouped_messages[group_id].append(msg)
                            
                            # 選擇最大的組（最可能是我們想要的媒體組）
                            largest_group = max(grouped_messages.values(), key=len)
                            messages_to_download = largest_group
                            logger.info(f"在原始消息周圍找到最大媒體組，包含 {len(messages_to_download)} 個媒體文件")
                    
                    # 方法3: 如果還是沒找到，至少處理原始消息
                    if not messages_to_download and original_message.media:
                        messages_to_download.append(original_message)
                        logger.info("無法找到媒體組，只處理原始消息")
                        
                except Exception as e:
                    logger.warning(f"無法從原始頻道獲取媒體組: {e}")
                    # 如果無法獲取媒體組，至少處理原始消息
                    if original_message.media:
                        messages_to_download.append(original_message)
            else:
                # 添加原始消息（如果有媒體）
                if original_message.media:
                    messages_to_download.append(original_message)
            
            # 添加回覆（如果有媒體）
            for reply in replies:
                if reply.media:
                    messages_to_download.append(reply)
            
            if not messages_to_download:
                await processing_msg.edit_text("ℹ️ 該媒體組及相關回覆中沒有找到任何媒體文件")
                return
            
            # 統計即將下載的媒體類型（用於顯示）
            download_media_counts = {'video': 0, 'photo': 0, 'document': 0}
            for msg in messages_to_download:
                if hasattr(msg, 'video') and msg.video:
                    download_media_counts['video'] += 1
                elif hasattr(msg, 'photo') and msg.photo:
                    download_media_counts['photo'] += 1
                elif hasattr(msg, 'document') and msg.document:
                    download_media_counts['document'] += 1
            
            # 觸發資料夾選擇（不傳遞media_counts，讓FolderNavigator自己計算當前資料夾的媒體統計）
            folder_ui_text = self.folder_navigator.start_folder_selection(user_id, messages_to_download, {'video': 0, 'photo': 0, 'document': 0})
            
            # 添加下載資訊到文字
            info_text = f"📊 找到 {len(messages_to_download)} 個媒體文件\n"
            info_text += f"影片: {download_media_counts['video']} 個, 照片: {download_media_counts['photo']} 個, 檔案: {download_media_counts['document']} 個\n\n"
            info_text += folder_ui_text + "\n\n"
            info_text += "命令說明:\n• /cr <名稱> - 創建資料夾\n• /cd <名稱> - 進入資料夾\n• /cd.. - 返回上級\n• /ok - 確認位置並開始下載"
            
            await processing_msg.edit_text(info_text)
            
        except Exception as e:
            logger.error(f"處理媒體組時出錯: {e}")
            await processing_msg.edit_text(f"❌ 處理時出錯: {str(e)}")
    
    async def _process_single_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理單個消息"""
        message = update.message
        
        # 發送處理中訊息
        processing_msg = await message.reply_text("🔄 正在備份中，請稍候...")
        
        try:
            # 提取原訊息資訊
            from telegram import MessageOriginChannel, MessageOriginUser, MessageOriginHiddenUser, MessageOriginChat
            
            if isinstance(message.forward_origin, MessageOriginChannel):
                # 來自頻道
                chat_id = message.forward_origin.chat.id
                original_message_id = message.forward_origin.message_id
                chat_name = message.forward_origin.chat.title or message.forward_origin.chat.username
            elif isinstance(message.forward_origin, MessageOriginChat):
                # 來自群組
                chat_id = message.forward_origin.sender_chat.id
                original_message_id = message.forward_origin.message_id
                chat_name = message.forward_origin.sender_chat.title or message.forward_origin.sender_chat.username
            else:
                # 來自私人聊天或隱藏用戶
                await processing_msg.edit_text("❌ 暫不支援來自私人聊天或隱藏用戶的轉發訊息")
                return
            
            await processing_msg.edit_text(f"📡 正在獲取來自 {chat_name} 的訊息...")
            
            # 獲取原訊息和回覆
            original_message, replies = await self.get_message_and_replies(chat_id, original_message_id)
            
            if not original_message:
                error_msg = (
                    "❌ 無法獲取原訊息\n\n"
                    "可能的原因：\n"
                    "• Bot 沒有權限訪問該頻道/群組\n"
                    "• 訊息已被刪除\n"
                    "• 訊息 ID 無效\n\n"
                    "請確認 Bot 是該頻道/群組的成員"
                )
                await processing_msg.edit_text(error_msg)
                return
            
            # 準備所有需要下載的消息
            messages_to_download = []
            if original_message.media:
                messages_to_download.append(original_message)
            
            for reply in replies:
                if reply.media:
                    messages_to_download.append(reply)
            
            if not messages_to_download:
                await processing_msg.edit_text("ℹ️ 該訊息及其回覆中沒有找到任何媒體文件")
                return
            
            # 統計即將下載的媒體類型（用於顯示）
            download_media_counts = {'video': 0, 'photo': 0, 'document': 0}
            for msg in messages_to_download:
                if hasattr(msg, 'video') and msg.video:
                    download_media_counts['video'] += 1
                elif hasattr(msg, 'photo') and msg.photo:
                    download_media_counts['photo'] += 1
                elif hasattr(msg, 'document') and msg.document:
                    download_media_counts['document'] += 1
            
            # 獲取用戶ID
            user_id = message.from_user.id
            
            # 觸發資料夾選擇（不傳遞media_counts，讓FolderNavigator自己計算當前資料夾的媒體統計）
            folder_ui_text = self.folder_navigator.start_folder_selection(user_id, messages_to_download, {'video': 0, 'photo': 0, 'document': 0})
            
            # 添加下載資訊到文字
            info_text = f"📊 找到 {len(messages_to_download)} 個媒體文件\n"
            info_text += f"影片: {download_media_counts['video']} 個, 照片: {download_media_counts['photo']} 個, 檔案: {download_media_counts['document']} 個\n\n"
            info_text += folder_ui_text + "\n\n"
            info_text += "命令說明:\n• /cr <名稱> - 創建資料夾\n• /cd <名稱> - 進入資料夾\n• /cd.. - 返回上級\n• /ok - 確認位置並開始下載"
            
            await processing_msg.edit_text(info_text)
            
        except Exception as e:
            logger.error(f"處理訊息時出錯: {e}")
            await processing_msg.edit_text(f"❌ 處理時出錯: {str(e)}")
    
    async def _start_download_with_selected_folder(self, update: Update, context: ContextTypes.DEFAULT_TYPE, messages_to_download: list):
        """使用選定的資料夾開始下載"""
        message = update.message
        user_id = message.from_user.id
        
        # 獲取用戶選擇的資料夾路徑
        selected_folder = self.folder_navigator.get_selected_path(user_id)
        
        # 發送開始下載訊息
        processing_msg = await message.reply_text("🚀 開始下載到選定的資料夾...")
        
        try:
            os.makedirs(selected_folder, exist_ok=True)
            
            # 從第一個消息獲取原始訊息資訊（用於顯示）
            original_message_id = messages_to_download[0].id
            chat_name = "Telegram"  # 預設名稱，因為這些已經是從Telethon獲取的消息
            
            # 開始下載和監控
            await self._download_and_monitor(processing_msg, messages_to_download, selected_folder, original_message_id, chat_name)
            
        except Exception as e:
            logger.error(f"開始下載時出錯: {e}")
            await processing_msg.edit_text(f"❌ 開始下載時出錯: {str(e)}")
    
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
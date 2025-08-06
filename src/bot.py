import asyncio
import os
import logging
import time
import shutil
from telethon import TelegramClient
from telethon.errors import RPCError
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from datetime import datetime

from .monitor import DownloadMonitor
from .downloader import MediaDownloader

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
        self.downloader = MediaDownloader(self.client, max_concurrent_downloads=5)
        self.downloader.set_monitor(self.monitor)
        
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
        
        # 檢查是否為轉發訊息
        if not message.forward_origin:
            await message.reply_text(
                "請轉發一則訊息給我，我會備份該訊息及其所有回覆中的媒體文件到伺服器！\n\n"
                "支援的媒體類型：照片、影片、GIF、音訊等"
            )
            return
        
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
            
            # 創建下載目錄
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            download_dir = os.path.join('downloads', f"message_{original_message_id}_{timestamp}")
            os.makedirs(download_dir, exist_ok=True)
            
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
            
        except Exception as e:
            logger.error(f"處理訊息時出錯: {e}")
            await processing_msg.edit_text(f"❌ 處理時出錯: {str(e)}")
    
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
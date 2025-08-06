import asyncio
import os
import logging
import time
import json
from telethon import TelegramClient
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from telethon.errors import FloodWaitError, RPCError
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from datetime import datetime

# 設定日誌
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration will be passed from main.py or config module

class TelegramMediaBot:
    def __init__(self, api_id, api_hash, phone_number, bot_token):
        # Telegram Client (用於訪問 API)
        self.client = TelegramClient('bot_session', api_id, api_hash)
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
    
    async def download_media_with_retry(self, message, file_path, max_retries=3):
        """下載媒體文件，包含重試機制"""
        for attempt in range(max_retries):
            try:
                await self.client.download_media(message, file_path)
                return True
                
            except (ConnectionError, OSError, asyncio.TimeoutError, RPCError) as e:
                if attempt == max_retries - 1:
                    logger.error(f"下載失敗，已嘗試 {max_retries} 次: {e}")
                    return False
                
                wait_time = (2 ** attempt) + 1  # 指數退避：2, 3, 5 秒
                logger.warning(f"下載失敗 (嘗試 {attempt + 1}/{max_retries})，{wait_time} 秒後重試: {e}")
                await asyncio.sleep(wait_time)
                
            except FloodWaitError as e:
                logger.warning(f"觸發限流，等待 {e.seconds} 秒")
                await asyncio.sleep(e.seconds)
                
            except Exception as e:
                logger.error(f"下載時發生未知錯誤: {e}")
                return False
        
        return False

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

    async def download_media_from_message(self, message, download_dir):
        """從訊息中下載媒體文件"""
        if not message.media:
            return []
        
        try:
            os.makedirs(download_dir, exist_ok=True)
            downloaded_files = []
            
            # 處理照片
            if isinstance(message.media, MessageMediaPhoto):
                file_name = f"photo_{message.id}_{message.date.strftime('%Y%m%d_%H%M%S')}.jpg"
                file_path = os.path.join(download_dir, file_name)
                
                if await self.download_media_with_retry(message, file_path):
                    downloaded_files.append(file_name)
                    logger.info(f"下載照片: {file_name}")
                else:
                    logger.error(f"照片下載失敗: {file_name}")
                
            # 處理文檔（影片、GIF等）
            elif isinstance(message.media, MessageMediaDocument):
                document = message.media.document
                
                # 獲取文件副檔名
                file_extension = ""
                original_name = ""
                
                for attr in document.attributes:
                    if hasattr(attr, 'file_name') and attr.file_name:
                        original_name = attr.file_name
                        file_extension = os.path.splitext(attr.file_name)[1]
                        break
                
                # 如果沒有副檔名，根據 MIME 類型推斷
                if not file_extension:
                    mime_type = document.mime_type
                    if mime_type.startswith('video/'):
                        file_extension = '.mp4'
                    elif mime_type.startswith('image/'):
                        file_extension = '.gif' if 'gif' in mime_type else '.jpg'
                    elif mime_type.startswith('audio/'):
                        file_extension = '.mp3'
                    else:
                        file_extension = '.bin'
                
                # 使用原檔名或生成新檔名
                if original_name:
                    file_name = f"{message.id}_{original_name}"
                else:
                    file_name = f"document_{message.id}_{message.date.strftime('%Y%m%d_%H%M%S')}{file_extension}"
                
                file_path = os.path.join(download_dir, file_name)
                
                if await self.download_media_with_retry(message, file_path):
                    downloaded_files.append(file_name)
                    logger.info(f"下載文檔: {file_name}")
                else:
                    logger.error(f"文檔下載失敗: {file_name}")
            
            return downloaded_files
            
        except Exception as e:
            logger.error(f"下載媒體時出錯: {e}")
            return []
    
    
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
            
            await processing_msg.edit_text("⬇️ 正在備份媒體文件...")
            
            all_downloaded_files = []
            
            # 下載原訊息的媒體
            if original_message.media:
                files = await self.download_media_from_message(original_message, download_dir)
                all_downloaded_files.extend(files)
            
            # 載入進度（如果存在）
            progress = self.load_progress(download_dir)
            completed_files = set(progress.get("completed_files", []))
            failed_files = set(progress.get("failed_files", []))
            
            # 下載所有回覆的媒體
            for i, reply in enumerate(replies):
                if reply.media:
                    try:
                        files = await self.download_media_from_message(reply, download_dir)
                        all_downloaded_files.extend(files)
                        
                        # 更新進度
                        for file_name in files:
                            completed_files.add(file_name)
                        
                        # 每10個訊息保存一次進度
                        if (i + 1) % 10 == 0:
                            progress_data = {
                                "completed_files": list(completed_files),
                                "failed_files": list(failed_files),
                                "processed_replies": i + 1,
                                "total_replies": len(replies)
                            }
                            self.save_progress(download_dir, progress_data)
                            
                    except Exception as e:
                        logger.error(f"處理回覆 {reply.id} 時出錯: {e}")
                        failed_files.add(f"reply_{reply.id}")
                
                # 更新進度顯示
                if (i + 1) % 5 == 0:
                    await processing_msg.edit_text(f"⬇️ 正在備份媒體文件... ({i + 1}/{len(replies)} 回覆已處理)")
            
            # 保存最終進度
            final_progress = {
                "completed_files": list(completed_files),
                "failed_files": list(failed_files),
                "processed_replies": len(replies),
                "total_replies": len(replies),
                "completed": True
            }
            self.save_progress(download_dir, final_progress)
            
            if not all_downloaded_files:
                await processing_msg.edit_text("ℹ️ 該訊息及其回覆中沒有找到任何媒體文件")
                return
            
            # 計算總文件大小
            total_size = 0
            for file_name in all_downloaded_files:
                file_path = os.path.join(download_dir, file_name)
                if os.path.exists(file_path):
                    total_size += os.path.getsize(file_path)
            
            # 建立結果訊息
            result_msg = f"✅ 備份完成！\n"
            result_msg += f"原訊息 ID: {original_message_id}\n"
            result_msg += f"來源: {chat_name}\n"
            result_msg += f"成功下載: {len(all_downloaded_files)} 個媒體文件\n"
            
            if failed_files:
                result_msg += f"失敗: {len(failed_files)} 個文件\n"
            
            result_msg += f"總大小: {total_size / 1024 / 1024:.1f}MB\n"
            result_msg += f"儲存位置: {download_dir}"
            
            await processing_msg.edit_text(result_msg)
            
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

# 創建 Bot 實例並運行
async def main():
    bot = TelegramMediaBot(API_ID, API_HASH, PHONE_NUMBER, BOT_TOKEN)
    await bot.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot 已停止")
    except Exception as e:
        logger.error(f"程式出錯: {e}")
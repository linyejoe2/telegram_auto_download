import asyncio
import os
import logging
from telethon import TelegramClient
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import zipfile
import tempfile
import shutil
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
            # 獲取聊天實體
            chat = await self.client.get_entity(chat_id)
            
            # 獲取原始訊息
            original_message = await self.client.get_messages(chat, ids=message_id)
            if not original_message:
                return None, []
            
            # 獲取所有回覆
            replies = []
            async for reply in self.client.iter_messages(chat, reply_to=message_id):
                replies.append(reply)
            
            logger.info(f"找到原訊息和 {len(replies)} 則回覆")
            return original_message, replies
            
        except Exception as e:
            logger.error(f"獲取訊息時出錯: {e}")
            return None, []
    
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
                
                await self.client.download_media(message, file_path)
                downloaded_files.append(file_name)
                logger.info(f"下載照片: {file_name}")
                
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
                
                await self.client.download_media(message, file_path)
                downloaded_files.append(file_name)
                logger.info(f"下載文檔: {file_name}")
            
            return downloaded_files
            
        except Exception as e:
            logger.error(f"下載媒體時出錯: {e}")
            return []
    
    async def create_zip_file(self, download_dir, zip_name):
        """將下載的文件打包成 ZIP"""
        try:
            zip_path = os.path.join(os.path.dirname(download_dir), f"{zip_name}.zip")
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(download_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, download_dir)
                        zipf.write(file_path, arcname)
            
            return zip_path
        except Exception as e:
            logger.error(f"創建 ZIP 文件時出錯: {e}")
            return None
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理收到的訊息"""
        message = update.message
        
        # 檢查是否為轉發訊息
        if not message.forward_from_chat and not message.forward_from:
            await message.reply_text(
                "請轉發一則訊息給我，我會下載該訊息及其所有回覆中的媒體文件！\n\n"
                "支援的媒體類型：照片、影片、GIF、音訊等"
            )
            return
        
        # 發送處理中訊息
        processing_msg = await message.reply_text("🔄 正在處理中，請稍候...")
        
        try:
            # 提取原訊息資訊
            if message.forward_from_chat:
                # 來自頻道或群組
                chat_id = message.forward_from_chat.id
                original_message_id = message.forward_from_message_id
                chat_name = message.forward_from_chat.title or message.forward_from_chat.username
            else:
                # 來自私人聊天
                await processing_msg.edit_text("❌ 暫不支援來自私人聊天的轉發訊息")
                return
            
            await processing_msg.edit_text(f"📡 正在獲取來自 {chat_name} 的訊息...")
            
            # 獲取原訊息和回覆
            original_message, replies = await self.get_message_and_replies(chat_id, original_message_id)
            
            if not original_message:
                await processing_msg.edit_text("❌ 無法獲取原訊息，請確認 Bot 有權限訪問該聊天")
                return
            
            # 創建臨時下載目錄
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            temp_dir = tempfile.mkdtemp()
            download_dir = os.path.join(temp_dir, f"message_{original_message_id}_{timestamp}")
            
            await processing_msg.edit_text("⬇️ 正在下載媒體文件...")
            
            all_downloaded_files = []
            
            # 下載原訊息的媒體
            if original_message.media:
                files = await self.download_media_from_message(original_message, download_dir)
                all_downloaded_files.extend(files)
            
            # 下載所有回覆的媒體
            for i, reply in enumerate(replies):
                if reply.media:
                    files = await self.download_media_from_message(reply, download_dir)
                    all_downloaded_files.extend(files)
                
                # 更新進度
                if (i + 1) % 5 == 0:
                    await processing_msg.edit_text(f"⬇️ 正在下載媒體文件... ({i + 1}/{len(replies)} 回覆已處理)")
            
            if not all_downloaded_files:
                await processing_msg.edit_text("ℹ️ 該訊息及其回覆中沒有找到任何媒體文件")
                shutil.rmtree(temp_dir)
                return
            
            await processing_msg.edit_text("📦 正在打包文件...")
            
            # 創建 ZIP 文件
            zip_name = f"telegram_media_{original_message_id}_{timestamp}"
            zip_path = await self.create_zip_file(download_dir, zip_name)
            
            if zip_path and os.path.exists(zip_path):
                # 檢查文件大小（Telegram Bot 限制 50MB）
                file_size = os.path.getsize(zip_path)
                if file_size > 50 * 1024 * 1024:  # 50MB
                    await processing_msg.edit_text(
                        f"⚠️ 文件太大 ({file_size / 1024 / 1024:.1f}MB)，超過 Telegram 限制 (50MB)\n"
                        f"共下載了 {len(all_downloaded_files)} 個媒體文件"
                    )
                else:
                    # 發送 ZIP 文件
                    await processing_msg.edit_text("📤 正在上傳文件...")
                    
                    with open(zip_path, 'rb') as zip_file:
                        await context.bot.send_document(
                            chat_id=message.chat_id,
                            document=zip_file,
                            filename=f"{zip_name}.zip",
                            caption=f"✅ 下載完成！\n"
                                   f"原訊息 ID: {original_message_id}\n"
                                   f"來源: {chat_name}\n"
                                   f"共 {len(all_downloaded_files)} 個媒體文件\n"
                                   f"文件大小: {file_size / 1024 / 1024:.1f}MB"
                        )
                    
                    await processing_msg.delete()
            else:
                await processing_msg.edit_text("❌ 創建打包文件時出錯")
            
            # 清理臨時文件
            shutil.rmtree(temp_dir)
            
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
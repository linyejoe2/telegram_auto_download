import asyncio
import os
import logging
import time
from telethon import TelegramClient
from telethon.errors import RPCError
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

from .monitor import DownloadMonitor
from .downloader import MediaDownloader
from .folder_navigator import FolderNavigator

# 設定日誌
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telethon.client.updates').setLevel(logging.WARNING)


class TelegramMediaBot:
    """精簡重構版：合併重複邏輯並抽出共用方法"""

    def __init__(self, api_id, api_hash, phone_number, bot_token):
        # media group handling
        self.media_groups = {}
        self.group_timers = {}

        # Telethon client
        self.client = TelegramClient(
            'bot_session',
            api_id,
            api_hash,
            connection_retries=3,
            retry_delay=1,
            auto_reconnect=True,
            timeout=30,
        )

        # event loop
        self.loop = asyncio.get_event_loop()

        # components
        base_dir = os.path.dirname(os.path.dirname(__file__))
        db_path = os.path.join(base_dir, 'downloads.db')
        downloads_path = os.path.join(base_dir, 'downloads')

        self.monitor = DownloadMonitor(self.loop)
        self.downloader = MediaDownloader(self.client, max_concurrent_downloads=5, db_path=db_path)
        self.downloader.set_monitor(self.monitor)
        self.folder_navigator = FolderNavigator(base_path=downloads_path)

        self.phone_number = phone_number
        self.bot_token = bot_token

        # Bot Application (python-telegram-bot)
        self.app = Application.builder().token(bot_token).build()
        self.app.add_handler(MessageHandler(filters.ALL, self.handle_message))

    # ---------------------- startup ----------------------
    async def start_client(self):
        await self.client.start(phone=self.phone_number)
        logger.info('Telegram Client 已啟動')

    # ---------------------- helpers ----------------------
    async def get_message_and_replies(self, chat_id, message_id):
        """獲取原始訊息與回覆，統一錯誤處理
        Returns (original_message or None, list_of_replies)
        """
        try:
            chat = await self.client.get_entity(chat_id)
        except Exception as e:
            logger.error(f'無法獲取聊天實體 {chat_id}: {e}')
            return None, []

        try:
            original = await self.client.get_messages(chat, ids=message_id)
            if not original:
                logger.warning(f'未找到訊息 ID {message_id} in {chat_id}')
                return None, []
        except Exception as e:
            logger.error(f'無法獲取訊息 {message_id}: {e}')
            return None, []

        replies = []
        try:
            async for r in self.client.iter_messages(chat, reply_to=message_id):
                replies.append(r)
        except Exception as e:
            logger.warning(f'獲取回覆失敗，但繼續處理: {e}')

        return original, replies

    async def _collect_media_from_original(self, chat_id, original_message, expected_size: int = None, search_range: int = 50):
        """
        精準收集與 original_message 屬於同一 media group 的 messages（優先使用 grouped_id）。
        - 只在 original_message 附近範圍內搜尋 (default search_range=50) 以提高準確度與效能。
        - 如果提供 expected_size，會優先回傳長度等於 expected_size 的組（若有）。
        Returns: list of messages (sorted by id asc). 若沒有 media，回傳 []。
        """
        try:
            # 如果 original 沒有 media，直接返回空
            if not getattr(original_message, "media", None):
                return []

            # 優先使用 grouped_id（最準確）
            gid = getattr(original_message, "grouped_id", None)

            # 定義搜尋區間（保守、靠近原訊息）
            base = original_message.id
            min_id = max(1, base - search_range)
            max_id = base + search_range

            found = []

            # 若有 grouped_id，直接在附近搜尋並過濾相同 grouped_id
            if gid:
                async for m in self.client.iter_messages(chat_id, min_id=min_id, max_id=max_id):
                    if getattr(m, "grouped_id", None) == gid and getattr(m, "media", None):
                        found.append(m)

                # 排序（由小到大，保證順序）
                if found:
                    found.sort(key=lambda x: x.id)
                    # 如果有 expected_size 且完全匹配則直接回傳
                    if expected_size is not None and len(found) == expected_size:
                        logger.info(f"找到完全匹配的 media group grouped_id={gid}, size={len(found)}")
                        return found
                    # 否則回傳目前找到的（應該就是正確的組）
                    logger.info(f"於附近找到 grouped_id={gid} 的 {len(found)} 則消息")
                    return found

                # 如果在附近沒找到（理論上很少遇到），做小範圍擴展搜尋（limit）
                async for m in self.client.iter_messages(chat_id, limit=200):
                    if getattr(m, "grouped_id", None) == gid and getattr(m, "media", None):
                        found.append(m)
                if found:
                    found.sort(key=lambda x: x.id)
                    logger.info(f"附近未找到，擴展搜尋後找到 grouped_id={gid} 的 {len(found)} 則消息")
                    return found

            # 若 original 沒有 grouped_id 或上述策略未找到任何結果：
            # 在附近收集所有有 grouped_id 的消息，分組後選擇最可能的一組
            candidates = {}
            async for m in self.client.iter_messages(chat_id, min_id=min_id, max_id=max_id):
                mgid = getattr(m, "grouped_id", None)
                if mgid and getattr(m, "media", None):
                    candidates.setdefault(mgid, []).append(m)

            if candidates:
                # 對每組排序
                for mgid, lst in candidates.items():
                    lst.sort(key=lambda x: x.id)

                # 若有 expected_size，優先選剛好相等的組
                if expected_size is not None:
                    for mgid, lst in candidates.items():
                        if len(lst) == expected_size:
                            logger.info(f"在附近找到與期望大小相符的 grouped_id={mgid}, size={len(lst)}")
                            return lst
                    # 否則挑選與期望差距最小的組
                    best_mgid, best_lst = min(candidates.items(), key=lambda kv: abs(len(kv[1]) - expected_size))
                    logger.info(f"選擇最接近期望大小的 grouped_id={best_mgid}, size={len(best_lst)}")
                    return best_lst

                # 沒有 expected_size 時，回傳最大組（最可能為完整 media group）
                largest_mgid, largest_lst = max(candidates.items(), key=lambda kv: len(kv[1]))
                logger.info(f"回傳附近最大的媒體組 grouped_id={largest_mgid}, size={len(largest_lst)}")
                return largest_lst

            # 最後 fallback：若 original 本身有 media，就回傳它
            logger.info("未找到任何 grouped_id 組合，fallback 回傳 original_message（若有 media）")
            return [original_message] if getattr(original_message, "media", None) else []

        except Exception as e:
            logger.warning(f"_collect_media_from_original 發生例外: {e}")
            # fallback 保守處理
            return [original_message] if getattr(original_message, "media", None) else []

    def _count_media_types(self, messages):
        counts = {'video': 0, 'photo': 0, 'document': 0}
        for m in messages:
            if getattr(m, 'video', None):
                counts['video'] += 1
            elif getattr(m, 'photo', None):
                counts['photo'] += 1
            elif getattr(m, 'document', None):
                counts['document'] += 1
        return counts

    async def _prepare_folder_selection(self, user_id, messages_to_download, processing_msg):
        """共用的：觸發 FolderNavigator 並編輯 processing_msg 顯示資訊"""
        counts = self._count_media_types(messages_to_download)
        ui_text = self.folder_navigator.start_folder_selection(user_id, messages_to_download, {'video': 0, 'photo': 0, 'document': 0})

        info_text = f"📊 找到 {len(messages_to_download)} 個媒體文件\n"
        info_text += f"影片: {counts['video']} 個, 照片: {counts['photo']} 個, 檔案: {counts['document']} 個\n\n"
        info_text += ui_text + "\n\n"
        info_text += (
            "命令說明:\n"
            "• /cr <名稱> - 創建資料夾\n"
            "• /cd <名稱> - 進入資料夾\n"
            "• /cd.. - 返回上級\n"
            "• /ok - 確認位置並開始下載"
        )

        await processing_msg.edit_text(info_text)

    # ---------------------- message handling ----------------------
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.message
        user_id = msg.from_user.id

        # folder commands
        if msg.text and self.folder_navigator.is_folder_command(msg.text):
            response, confirmed = self.folder_navigator.process_folder_command(user_id, msg.text)
            await msg.reply_text(response)
            if confirmed:
                pending = self.folder_navigator.get_pending_messages(user_id)
                if pending:
                    await self._start_download_with_selected_folder(update, context, pending)
                self.folder_navigator.clear_user_state(user_id)
            return

        if self.folder_navigator.is_awaiting_folder_selection(user_id):
            await msg.reply_text('請使用資料夾命令: /cr 創建資料夾, /cd 進入資料夾, /cd.. 返回上級, /ok 確認位置')
            return

        # require forwarded message
        if not msg.forward_origin:
            await msg.reply_text(
                '請轉發一則訊息給我，我會備份該訊息及其所有回覆中的媒體文件到伺服器！\n\n'
                '支援的媒體類型：照片、影片、GIF、音訊等\n\n'
                '資料夾命令:\n'
                '• /cr <名稱> - 創建資料夾\n'
                '• /cd <名稱> - 進入資料夾\n'
                '• /cd.. - 返回上級目錄\n'
                '• /ok - 確認當前位置並開始下載'
            )
            return

        # media group aggregator
        if msg.media_group_id:
            await self._handle_media_group(update, context)
        else:
            await self._handle_forwarded_single(update, context)

    async def _handle_media_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.message
        mgid = msg.media_group_id
        self.media_groups.setdefault(mgid, []).append(msg)
        logger.info(f'收集媒體組 {mgid}: 現在 {len(self.media_groups[mgid])} 則')

        # reset timer
        if mgid in self.group_timers:
            self.group_timers[mgid].cancel()
        self.group_timers[mgid] = asyncio.create_task(self._process_media_group_delayed(mgid, 2.0))

    async def _process_media_group_delayed(self, media_group_id: str, delay: float):
        await asyncio.sleep(delay)
        if media_group_id not in self.media_groups:
            return
        msgs = self.media_groups.pop(media_group_id)
        logger.info(f'開始處理媒體組 {media_group_id}，包含 {len(msgs)} 個消息')

        primary = msgs[0]
        processing_msg = await primary.reply_text(f'🔄 正在分析媒體組 ({len(msgs)} 個文件)，請稍候...')

        # extract forward info
        from telegram import MessageOriginChannel, MessageOriginChat
        try:
            if isinstance(primary.forward_origin, MessageOriginChannel):
                chat_id = primary.forward_origin.chat.id
                original_message_id = primary.forward_origin.message_id
                chat_name = primary.forward_origin.chat.title or primary.forward_origin.chat.username
            elif isinstance(primary.forward_origin, MessageOriginChat):
                chat_id = primary.forward_origin.sender_chat.id
                original_message_id = primary.forward_origin.message_id
                chat_name = primary.forward_origin.sender_chat.title or primary.forward_origin.sender_chat.username
            else:
                await processing_msg.edit_text('❌ 暫不支援來自私人聊天或隱藏用戶的轉發訊息')
                return

            await processing_msg.edit_text(f'📡 正在獲取來自 {chat_name} 的媒體組訊息...')
            original_message, replies = await self.get_message_and_replies(chat_id, original_message_id)
            if not original_message:
                await processing_msg.edit_text('❌ 無法獲取原訊息，請確認 Bot 權限或訊息是否存在')
                return

            # collect all messages to download: prefer collecting media group from origin
            messages_to_download = await self._collect_media_from_original(chat_id, original_message)
            # also include replies with media
            for r in replies:
                if getattr(r, 'media', None):
                    messages_to_download.append(r)

            if not messages_to_download:
                await processing_msg.edit_text('ℹ️ 該媒體組及相關回覆中沒有找到任何媒體文件')
                return

            await self._prepare_folder_selection(primary.from_user.id, messages_to_download, processing_msg)

        except Exception as e:
            logger.error(f'處理媒體組錯誤: {e}')
            await processing_msg.edit_text(f'❌ 處理媒體組時出錯: {e}')

    async def _handle_forwarded_single(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message
        processing_msg = await message.reply_text('🔄 正在備份中，請稍候...')

        from telegram import MessageOriginChannel, MessageOriginChat
        try:
            if isinstance(message.forward_origin, MessageOriginChannel):
                chat_id = message.forward_origin.chat.id
                original_message_id = message.forward_origin.message_id
                chat_name = message.forward_origin.chat.title or message.forward_origin.chat.username
            elif isinstance(message.forward_origin, MessageOriginChat):
                chat_id = message.forward_origin.sender_chat.id
                original_message_id = message.forward_origin.message_id
                chat_name = message.forward_origin.sender_chat.title or message.forward_origin.sender_chat.username
            else:
                await processing_msg.edit_text('❌ 暫不支援來自私人聊天或隱藏用戶的轉發訊息')
                return

            await processing_msg.edit_text(f'📡 正在獲取來自 {chat_name} 的訊息...')
            original_message, replies = await self.get_message_and_replies(chat_id, original_message_id)
            if not original_message:
                await processing_msg.edit_text('❌ 無法獲取原訊息，請確認 Bot 權限或訊息是否存在')
                return

            messages_to_download = []
            if getattr(original_message, 'media', None):
                messages_to_download.append(original_message)
            for r in replies:
                if getattr(r, 'media', None):
                    messages_to_download.append(r)

            if not messages_to_download:
                await processing_msg.edit_text('ℹ️ 該訊息及其回覆中沒有找到任何媒體文件')
                return

            await self._prepare_folder_selection(message.from_user.id, messages_to_download, processing_msg)

        except Exception as e:
            logger.error(f'處理訊息時出錯: {e}')
            await processing_msg.edit_text(f'❌ 處理時出錯: {e}')

    # ---------------------- download flow ----------------------
    async def _start_download_with_selected_folder(self, update: Update, context: ContextTypes.DEFAULT_TYPE, messages_to_download: list):
        message = update.message
        user_id = message.from_user.id
        selected_folder = self.folder_navigator.get_selected_path(user_id)
        processing_msg = await message.reply_text('🚀 開始下載到選定的資料夾...')

        try:
            os.makedirs(selected_folder, exist_ok=True)
            original_message_id = messages_to_download[0].id if messages_to_download else 0
            chat_name = 'Telegram'
            await self._download_and_monitor(processing_msg, messages_to_download, selected_folder, original_message_id, chat_name)
        except Exception as e:
            logger.error(f'開始下載時出錯: {e}')
            await processing_msg.edit_text(f'❌ 開始下載時出錯: {e}')

    async def _download_and_monitor(self, processing_msg, messages_to_download, download_dir, original_message_id, chat_name):
        # init stats
        self.monitor.update_stats({
            'total_files': 0,
            'completed_files': 0,
            'failed_files': 0,
            'total_size': 0,
            'downloaded_size': 0,
            'start_time': time.time()
        })

        self.monitor.start_monitoring_thread(download_dir, processing_msg)

        try:
            await processing_msg.edit_text('📊 正在分析媒體文件...')
            total_size = 0
            for m in messages_to_download:
                if getattr(m, 'media', None):
                    total_size += await self.downloader.get_media_size(m)

            total_size_mb = total_size / (1024**2)
            await processing_msg.edit_text(f'🚀 開始下載 {len(messages_to_download)} 個媒體文件，總大小: {total_size_mb:.1f}MB...')

            all_files = await self.downloader.download_multiple_messages_concurrent(messages_to_download, download_dir)

        finally:
            self.monitor.stop_monitoring()

        stats = self.monitor.get_stats()
        elapsed = time.time() - stats['start_time']
        avg_speed = (stats['downloaded_size'] / (1024**2)) / max(elapsed, 1)
        disk = self.monitor.get_disk_usage(download_dir)

        result = (
            f"✅ 下載完成！\n原訊息 ID: {original_message_id}\n來源: {chat_name}\n"
            f"成功下載: {stats['completed_files']} 個媒體文件\n"
        )
        if stats['failed_files'] > 0:
            result += f"失敗: {stats['failed_files']} 個文件\n"

        if stats['total_size'] > 0:
            completion_rate = (stats['downloaded_size'] / stats['total_size']) * 100
            result += f"下載大小: {stats['downloaded_size']/(1024**2):.1f}MB / {stats['total_size']/(1024**2):.1f}MB ({completion_rate:.1f}%)\n"
        else:
            result += f"下載大小: {stats['downloaded_size']/(1024**2):.1f}MB\n"

        result += f"平均速度: {avg_speed:.1f}MB/s\n耗時: {elapsed:.1f}秒\n剩餘空間: {disk['free_gb']:.1f}GB\n儲存位置: {download_dir}"

        await processing_msg.edit_text(result)
        logger.info(f"下載完成 - 成功: {stats['completed_files']}, 失敗: {stats['failed_files']}, 大小: {stats['downloaded_size']/(1024**2):.1f}MB, 速度: {avg_speed:.1f}MB/s")

    # ---------------------- utilities ----------------------
    def get_download_statistics(self):
        return self.downloader.get_download_statistics()

    def cleanup_missing_files(self):
        return self.downloader.cleanup_missing_files()

    def get_recent_downloads(self, limit=10):
        return self.downloader.get_recent_downloads(limit)

    async def run(self):
        try:
            await self.start_client()
            logger.info('正在啟動 Telegram Bot...')
            await self.app.initialize()
            await self.app.start()
            logger.info('Bot 已啟動！可以開始轉發訊息了')
            await self.app.updater.start_polling()

            while True:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f'Bot 運行出錯: {e}')
        finally:
            await self.app.stop()
            await self.app.shutdown()
            await self.client.disconnect()

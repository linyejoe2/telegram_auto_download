import asyncio
import os
import sys
import logging
import time
import queue
from telethon import TelegramClient
from telethon.errors import RPCError
from telegram import Update
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from .monitor import DownloadMonitor
from .downloader import MediaDownloader
from .folder_navigator import FolderNavigator
from web import url_parser

# 設定日誌
log_queue = queue.Queue()
class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
    
    def emit(self, record):
        self.log_queue.put(self.format(record))
# Create logs directory
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)

# Configure file logging
log_file = os.path.join(log_dir, 'bot.log')

# Configure root logger with GUI-friendly settings
try:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            QueueHandler(log_queue)
        ],
        force=True  # Force reconfiguration if already configured
    )
except Exception as e:
    # Fallback logging configuration for GUI environments
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        filename=log_file,
        filemode='a',
        encoding='utf-8'
    )
    # Add queue handler separately
    root_logger = logging.getLogger()
    root_logger.addHandler(QueueHandler(log_queue))
logger = logging.getLogger(__name__)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telethon.client.updates').setLevel(logging.WARNING)


class TelegramMediaBot:
    """精簡重構版：合併重複邏輯並抽出共用方法"""

    def __init__(self, api_id, api_hash, phone_number, bot_token):
        # media group handling
        self.media_groups = {}
        self.group_timers = {}

        # Telethon client with GUI-friendly settings
        self.client = TelegramClient(
            'bot_session',
            api_id,
            api_hash,
            connection_retries=3,
            retry_delay=1,
            auto_reconnect=True,
            timeout=30,
            # system_version="4.16.30-vxCUSTOM",  # Custom version to avoid issues
            device_model="Desktop",
            # app_version="0.5.1",
            lang_code="en",
            system_lang_code="en"
        )

        # event loop
        self.loop = asyncio.get_event_loop()

        # components
        base_dir = os.path.dirname(os.path.dirname(__file__))
        db_path = os.path.join(base_dir, 'downloads.db')
        
        # Get downloads path from environment or use default
        from dotenv import load_dotenv
        load_dotenv()
        downloads_path = os.getenv('DOWNLOADS_PATH', os.path.join(base_dir, 'downloads'))
        self.downloads_path = downloads_path

        self.monitor = DownloadMonitor(self.loop)
        self.downloader = MediaDownloader(self.client, max_concurrent_downloads=5, db_path=db_path)
        self.downloader.set_monitor(self.monitor)
        self.folder_navigator = FolderNavigator(base_path=downloads_path)

        self.phone_number = phone_number
        self.bot_token = bot_token

        # Bot Application (python-telegram-bot)
        self.app = Application.builder().token(bot_token).build()
        self.app.add_handler(CallbackQueryHandler(self.handle_callback_query))
        self.app.add_handler(MessageHandler(filters.ALL, self.handle_message))

    # ---------------------- startup ----------------------
    async def start_client(self, gui_root=None):
        try:
            # Check if client is already connected
            if self.client.is_connected():
                logger.info('Telegram Client 已經連接')
                return
            
            # Check if session file exists
            session_file = 'bot_session.session'
            session_exists = os.path.exists(session_file)
            
            if session_exists:
                logger.info('發現現有會話文件，嘗試自動登入...')
                try:
                    # Import auth helper to get proper handlers
                    from .auth_helper import get_auth_helper
                    auth_helper = get_auth_helper(gui_root)
                    
                    # Try to start with existing session but with proper handlers for fallback
                    await self.client.start(
                        phone=self.phone_number,
                        code_callback=auth_helper.phone_code_callback,
                        password=auth_helper.password_callback
                    )
                    logger.info('Telegram Client 已啟動（使用現有會話）')
                    return
                except EOFError as e:
                    logger.warning(f'會話需要額外驗證但GUI不可用: {e}')
                    logger.warning('將刪除會話文件並重新認證')
                    # Remove session file that needs interactive input
                    try:
                        os.remove(session_file)
                        logger.info('已刪除需要互動認證的會話文件')
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning(f'使用現有會話失敗，將重新認證: {e}')
                    # Remove invalid session file
                    try:
                        os.remove(session_file)
                        logger.info('已刪除無效的會話文件')
                    except Exception:
                        pass
            
            # Need authentication - import auth helper
            logger.info('需要進行認證...')
            from .auth_helper import authenticate_client, get_auth_helper
            
            # Get appropriate auth helper for environment
            auth_helper = get_auth_helper(gui_root)
            
            # Handle authentication based on environment
            if hasattr(sys, 'frozen'):  # Running in PyInstaller GUI
                logger.info('GUI模式：使用圖形界面進行認證')
                success = await authenticate_client(self.client, self.phone_number, auth_helper)
                if not success:
                    raise Exception("GUI authentication failed")
            else:
                # Development mode - try GUI first, fallback to console
                try:
                    success = await authenticate_client(self.client, self.phone_number, auth_helper)
                    if not success:
                        raise Exception("Authentication failed")
                except Exception as e:
                    logger.warning(f"GUI authentication failed, trying direct method: {e}")
                    await self.client.start(phone=self.phone_number)
            
            logger.info('Telegram Client 已啟動（新認證）')
            
        except EOFError as e:
            logger.error(f'認證失敗 - 輸入錯誤: {e}')
            logger.error('這通常表示需要重新認證或在控制台模式下首次設定')
            raise Exception("Authentication requires interactive input. Please run in console mode first or check session file.")
        except Exception as e:
            logger.error(f'Telegram Client 啟動失敗: {e}')
            # Check if it's an authentication issue
            if "phone" in str(e).lower() or "auth" in str(e).lower() or "eof" in str(e).lower():
                logger.error('認證問題：請檢查手機號碼和API憑證，或刪除 bot_session.session 文件重新認證')
            raise

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
        """觸發 FolderNavigator 並編輯 processing_msg 顯示 Inline Keyboard"""
        counts = self._count_media_types(messages_to_download)
        nav_text, markup = self.folder_navigator.start_folder_selection(
            user_id, messages_to_download, {'video': 0, 'photo': 0, 'document': 0}
        )

        info_text = (
            f"📊 找到 {len(messages_to_download)} 個媒體文件\n"
            f"影片: {counts['video']} 個, 照片: {counts['photo']} 個, 檔案: {counts['document']} 個\n\n"
            f"{nav_text}"
        )

        await processing_msg.edit_text(info_text, reply_markup=markup)

    # ---------------------- callback query handling ----------------------
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = query.from_user.id
        data = query.data or ""

        await query.answer()

        if not data.startswith("fn_"):
            return

        if not self.folder_navigator.is_awaiting_folder_selection(user_id):
            await query.answer("此操作已過期，請重新發送媒體文件", show_alert=True)
            return

        try:
            if data == "fn_up":
                text, markup = self.folder_navigator.navigate_up(user_id)
                await query.message.edit_text(text, reply_markup=markup)

            elif data == "fn_ok":
                state = self.folder_navigator.get_user_state(user_id)
                pending_url = state.pending_url
                url_type = state.url_type

                display_path, _ = self.folder_navigator.confirm_selection(user_id)
                pending = self.folder_navigator.get_pending_messages(user_id)

                await query.message.edit_text(f"📁 已確認存放位置: {display_path}\n🚀 開始下載...")

                if pending:
                    await self._start_download_with_selected_folder(user_id, query.message, pending)
                elif pending_url and url_type:
                    await url_parser.download_confirmed(
                        user_id, pending_url, url_type, query.message, self.folder_navigator
                    )

                self.folder_navigator.clear_user_state(user_id)

            elif data.startswith("fn_cd:"):
                index = int(data[6:])
                text, markup = self.folder_navigator.navigate_into(user_id, index)
                await query.message.edit_text(text, reply_markup=markup)

            elif data.startswith("fn_prev:"):
                index = int(data[8:])
                text, markup = self.folder_navigator.navigate_to_history(user_id, index)
                await query.message.edit_text(text, reply_markup=markup)

            elif data == "fn_cr":
                state = self.folder_navigator.get_user_state(user_id)
                state.nav_message = query.message
                self.folder_navigator.set_awaiting_folder_name(user_id, True)
                await query.message.edit_text(
                    "📝 請輸入新資料夾名稱：\n直接發送一則文字訊息即可",
                    reply_markup=None
                )

        except Exception as e:
            logger.error(f"處理資料夾按鈕回調時出錯: {e}")

    # ---------------------- message handling ----------------------
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.message
        user_id = msg.from_user.id

        # Handle new folder name input
        if self.folder_navigator.is_awaiting_folder_name(user_id) and msg.text:
            folder_name = msg.text.strip()
            state = self.folder_navigator.get_user_state(user_id)
            text, markup = self.folder_navigator.create_folder_and_navigate(user_id, folder_name)
            try:
                await msg.delete()
            except Exception:
                pass
            nav_msg = state.nav_message
            if nav_msg:
                await nav_msg.edit_text(text, reply_markup=markup)
            else:
                await msg.reply_text(text, reply_markup=markup)
            return

        if self.folder_navigator.is_awaiting_folder_selection(user_id):
            await msg.reply_text('請使用上方的按鈕選擇資料夾位置')
            return

        # Detect URL (e.g. YouTube link)
        if msg.text:
            detected_url = url_parser.extract_url(msg.text)
            if detected_url:
                url_type = url_parser.detect_type(detected_url)
                if url_type:
                    processing_msg = await msg.reply_text("🔍 正在解析連結...")
                    await url_parser.handle_url(
                        detected_url, url_type, user_id, processing_msg, self.folder_navigator
                    )
                else:
                    await msg.reply_text("❌ 不支援的連結類型，目前支援 YouTube 及 X (Twitter) 網址")
                return

        # require forwarded message
        if not msg.forward_origin:
            await msg.reply_text(
                '請轉發一則訊息給我，我會備份該訊息及其所有回覆中的媒體文件到伺服器！\n\n'
                '支援的媒體類型：照片、影片、GIF、音訊等\n\n'
                '也可以直接發送 YouTube 網址進行下載'
            )
            return
        
        logger.info(f'收到新請求')

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
    async def _start_download_with_selected_folder(self, user_id: int, processing_msg, messages_to_download: list):
        selected_folder = self.folder_navigator.get_selected_path(user_id)
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
                    total_size += self.downloader.get_media_size(m)

            total_size_mb = total_size / (1024**2)
            await processing_msg.edit_text(f'🚀 開始下載 {len(messages_to_download)} 個媒體文件，總大小: {total_size_mb:.1f}MB...')

            # 設定訊息回調函數，讓下載器可以發送新訊息
            async def send_message_to_user(text):
                try:
                    await processing_msg.reply_text(text)
                except Exception as e:
                    logger.warning(f"發送訊息失敗: {e}")
            
            self.downloader.set_message_callback(send_message_to_user)
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
    
    def update_downloads_path(self, new_path):
        """Update the downloads path and reinitialize folder navigator"""
        self.downloads_path = new_path
        self.folder_navigator = FolderNavigator(base_path=new_path)
        os.makedirs(new_path, exist_ok=True)

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

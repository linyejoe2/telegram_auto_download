import asyncio
import logging
import time
import threading
import shutil
import os

logger = logging.getLogger(__name__)


class DownloadMonitor:
    """監控下載進度和系統資源的類"""
    
    def __init__(self, loop):
        self.loop = loop
        self.monitoring_active = False
        self.current_download_dir = None
        self.download_stats = {
            'total_files': 0,
            'completed_files': 0,
            'failed_files': 0,
            'total_size': 0,
            'downloaded_size': 0,
            'start_time': None
        }
    
    def update_stats(self, stats_dict):
        """更新下載統計資料"""
        self.download_stats.update(stats_dict)
    
    def get_stats(self):
        """獲取當前統計資料"""
        return self.download_stats.copy()
    
    def start_monitoring_thread(self, download_dir, processing_msg):
        """啟動監控線程"""
        self.current_download_dir = download_dir
        self.monitoring_active = True
        
        def monitor_downloads():
            """監控下載進度和磁碟空間"""
            last_update = time.time()
            
            while self.monitoring_active:
                try:
                    current_time = time.time()
                    
                    # 每5秒更新一次
                    if current_time - last_update >= 5:
                        # 獲取磁碟空間資訊
                        if self.current_download_dir and os.path.exists(self.current_download_dir):
                            total, used, free = shutil.disk_usage(self.current_download_dir)
                            free_gb = free / (1024**3)
                            
                            # 計算下載速度
                            elapsed = current_time - (self.download_stats.get('start_time', current_time))
                            if elapsed > 0:
                                speed_mbps = (self.download_stats['downloaded_size'] / (1024**2)) / elapsed
                            else:
                                speed_mbps = 0
                            
                            # 計算下載進度百分比
                            if self.download_stats['total_size'] > 0:
                                progress_percent = (self.download_stats['downloaded_size'] / self.download_stats['total_size']) * 100
                            else:
                                progress_percent = 0
                            
                            # 構建狀態訊息
                            status_msg = (
                                f"⬇️ 備份進行中...\n"
                                f"已完成: {self.download_stats['completed_files']}/{self.download_stats['total_files']} 個文件\n"
                                f"失敗: {self.download_stats['failed_files']} 個\n"
                                f"進度: {self.download_stats['downloaded_size']/(1024**2):.1f}MB / {self.download_stats['total_size']/(1024**2):.1f}MB ({progress_percent:.1f}%)\n"
                                f"速度: {speed_mbps:.1f}MB/s\n"
                                f"剩餘空間: {free_gb:.1f}GB"
                            )
                            
                            # 異步更新消息
                            asyncio.run_coroutine_threadsafe(
                                self.safe_update_message(processing_msg, status_msg),
                                self.loop
                            )
                            
                            # 記錄詳細日誌
                            logger.info(
                                f"下載狀態 - 完成: {self.download_stats['completed_files']}, "
                                f"失敗: {self.download_stats['failed_files']}, "
                                f"速度: {speed_mbps:.1f}MB/s, "
                                f"剩餘空間: {free_gb:.1f}GB"
                            )
                            
                            last_update = current_time
                    
                    time.sleep(1)  # 每秒檢查一次
                    
                except Exception as e:
                    logger.error(f"監控線程錯誤: {e}")
                    time.sleep(5)
        
        # 在後台線程中運行監控
        monitor_thread = threading.Thread(target=monitor_downloads, daemon=True)
        monitor_thread.start()
        logger.info("監控線程已啟動")

    async def safe_update_message(self, processing_msg, text):
        """安全地更新消息，避免阻塞"""
        try:
            await processing_msg.edit_text(text)
        except Exception as e:
            # 特別處理「消息未修改」錯誤，這是正常情況
            if "Message is not modified" in str(e):
                logger.debug("消息內容相同，跳過更新")
            else:
                # 忽略其他消息更新錯誤，不影響下載進程
                logger.debug(f"消息更新失敗: {e}")

    def stop_monitoring(self):
        """停止監控線程"""
        self.monitoring_active = False
        logger.info("監控線程已停止")
    
    def get_disk_usage(self, path):
        """獲取指定路徑的磁碟使用情況"""
        try:
            if os.path.exists(path):
                total, used, free = shutil.disk_usage(path)
                return {
                    'total_gb': total / (1024**3),
                    'used_gb': used / (1024**3),
                    'free_gb': free / (1024**3)
                }
        except Exception as e:
            logger.error(f"獲取磁碟使用情況失敗: {e}")
        
        return {'total_gb': 0, 'used_gb': 0, 'free_gb': 0}
    
    def calculate_speed(self):
        """計算當前下載速度"""
        if not self.download_stats.get('start_time'):
            return 0
        
        elapsed = time.time() - self.download_stats['start_time']
        if elapsed > 0:
            return (self.download_stats['downloaded_size'] / (1024**2)) / elapsed
        return 0
    
    def calculate_eta(self):
        """計算預估剩餘時間"""
        speed = self.calculate_speed()
        if speed > 0 and self.download_stats['total_size'] > 0:
            remaining_size = self.download_stats['total_size'] - self.download_stats['downloaded_size']
            remaining_mb = remaining_size / (1024**2)
            return remaining_mb / speed
        return 0
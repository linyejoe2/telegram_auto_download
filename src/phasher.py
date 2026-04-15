import cv2
import imagehash
from PIL import Image
import tempfile
import os

def get_video_phash_fast(video_buffer, points=[0.1, 0.5, 0.9]):
    """
    從影片的指定百分比位置選取影格並計算 pHash。
    :param video_buffer: 影片的 bytes 數據
    :param points: 要抽樣的比例清單，預設 10%, 50%, 90%
    :return: 串接後的 Hash 字串
    """
    hashes = []
    
    # 創建暫存檔，讓 OpenCV 可以讀取
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_video:
        temp_video.write(video_buffer)
        temp_path = temp_video.name

    try:
        cap = cv2.VideoCapture(temp_path)
        if not cap.isOpened():
            return None
            
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        for p in points:
            # 計算目標幀數位置
            target_frame = int(total_frames * p)
            
            # 跳轉到該幀
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = cap.read()
            
            if ret:
                # 轉色並計算 pHash
                img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(img_rgb)
                h = imagehash.phash(pil_img)
                hashes.append(str(h))
            else:
                # 如果該點讀取失敗（例如影片毀損），放入一個佔位符
                hashes.append("0000000000000000")
                
        cap.release()
    finally:
        # 確保刪除暫存檔
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return "-".join(hashes) if hashes else None

def get_video_phash_from_path(video_path, points=[0.1, 0.5, 0.9]):
    """
    從影片檔案路徑計算 pHash，不需要讀取整個檔案到記憶體。
    :param video_path: 影片檔案的本地路徑
    :param points: 要抽樣的比例清單，預設 10%, 50%, 90%
    :return: 串接後的 Hash 字串，失敗時回傳 None
    """
    hashes = []
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        return None

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        for p in points:
            target_frame = int(total_frames * p)
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = cap.read()

            if ret:
                img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(img_rgb)
                h = imagehash.phash(pil_img)
                hashes.append(str(h))
            else:
                hashes.append("0000000000000000")
    finally:
        cap.release()

    return "-".join(hashes) if hashes else None


# 使用範例
# with open("/content/C0050.MP4", "rb") as f:
#     video_data = f.read()
#     v_hash = get_video_phash_fast(video_data)
#     print(f"Video Hash: {v_hash}")
#
# v_hash = get_video_phash_from_path("/content/C0050.MP4")
# print(f"Video Hash: {v_hash}")
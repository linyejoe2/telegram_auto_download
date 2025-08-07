#!/usr/bin/env python3
"""
測試資料夾導航功能的簡單腳本
"""

from src.folder_navigator import FolderNavigator
import os

def test_folder_navigation():
    """測試資料夾導航功能"""
    print("開始測試資料夾導航功能...")
    
    # 創建測試目錄
    test_base_path = "./test_downloads"
    navigator = FolderNavigator(test_base_path)
    
    print(f"創建 FolderNavigator，基礎路徑: {test_base_path}")
    
    # 測試用戶ID
    test_user_id = 12345
    
    # 模擬媒體統計
    test_media_counts = {'video': 3, 'photo': 5, 'document': 2}
    test_messages = ['test_message_1', 'test_message_2']
    
    # 開始資料夾選擇
    print("\n開始資料夾選擇流程...")
    folder_ui = navigator.start_folder_selection(test_user_id, test_messages, test_media_counts)
    print(f"資料夾UI輸出:\n{folder_ui}")
    
    # 測試創建資料夾命令
    print("\n測試 /cr 影片存放區 命令...")
    response, confirmed = navigator.process_folder_command(test_user_id, "/cr 影片存放區")
    print(f"回應: {response}")
    print(f"是否確認: {confirmed}")
    
    # 測試創建子資料夾
    print("\n測試 /創建 暫存 命令...")
    response, confirmed = navigator.process_folder_command(test_user_id, "/創建 暫存")
    print(f"回應: {response}")
    print(f"是否確認: {confirmed}")
    
    # 測試返回上級目錄
    print("\n測試 /cd.. 命令...")
    response, confirmed = navigator.process_folder_command(test_user_id, "/cd..")
    print(f"回應: {response}")
    print(f"是否確認: {confirmed}")
    
    # 測試確認位置
    print("\n測試 /ok 命令...")
    response, confirmed = navigator.process_folder_command(test_user_id, "/ok")
    print(f"回應: {response}")
    print(f"是否確認: {confirmed}")
    
    # 檢查選定的路徑
    if confirmed:
        selected_path = navigator.get_selected_path(test_user_id)
        print(f"選定的路徑: {selected_path}")
        
        # 檢查資料夾是否真的存在
        if os.path.exists(selected_path):
            print(f"資料夾存在: {selected_path}")
        else:
            print(f"資料夾不存在: {selected_path}")
    
    print("\n清理用戶狀態...")
    navigator.clear_user_state(test_user_id)
    
    print("測試完成!")

def test_folder_commands():
    """測試資料夾命令識別"""
    print("\n測試資料夾命令識別...")
    
    navigator = FolderNavigator("./test_downloads")
    
    test_commands = [
        "/cr 測試資料夾",
        "/cd 影片",
        "/cd..",
        "/ok",
        "/創建 中文資料夾",
        "/進入 測試",
        "/退出",
        "/確定",
        "普通文字",
        "",
        None
    ]
    
    for cmd in test_commands:
        is_folder_cmd = navigator.is_folder_command(cmd)
        print(f"命令: '{cmd}' -> 是資料夾命令: {is_folder_cmd}")

if __name__ == "__main__":
    try:
        test_folder_commands()
        test_folder_navigation()
        print("\n所有測試完成!")
    except Exception as e:
        print(f"測試失敗: {e}")
        import traceback
        traceback.print_exc()
#!/usr/bin/env python3
"""
Create version information file for Windows executable
"""

import os

# ===== Version constant =====
APP_VERSION = "2.0.0"
APP_VERSION_TUPLE = tuple(map(int, APP_VERSION.split("."))) + (0,)
# ============================

version_info = f"""
# UTF-8
#
# For more details about fixed file info 'ffi' see:
# http://msdn.microsoft.com/en-us/library/ms646997.aspx

VSVersionInfo(
  ffi=FixedFileInfo(
    # filevers and prodvers should be always a tuple with four items: (1, 2, 3, 4)
    filevers={APP_VERSION_TUPLE},
    prodvers={APP_VERSION_TUPLE},
    mask=0x3f,
    flags=0x0,
    OS=0x4,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'Telegram Auto Download Bot'),
        StringStruct(u'FileDescription', u'Telegram Auto Download Bot - Media Backup Tool'),
        StringStruct(u'FileVersion', u'{APP_VERSION}.0'),
        StringStruct(u'InternalName', u'TelegramAutoDownload'),
        StringStruct(u'LegalCopyright', u'© 2024 Telegram Auto Download Bot'),
        StringStruct(u'OriginalFilename', u'TelegramAutoDownload.exe'),
        StringStruct(u'ProductName', u'Telegram Auto Download Bot'),
        StringStruct(u'ProductVersion', u'{APP_VERSION}.0')])
      ]), 
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""

def create_version_info():
    """Create version_info.txt file for PyInstaller"""
    try:
        with open('version_info.txt', 'w', encoding='utf-8') as f:
            f.write(version_info.strip())
        print(f"Version info file created successfully (version {APP_VERSION})")
        return True
    except Exception as e:
        print(f"Failed to create version info: {e}")
        return False

if __name__ == "__main__":
    create_version_info()

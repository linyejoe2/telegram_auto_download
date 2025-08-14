#!/usr/bin/env python3
"""
Create version information file for Windows executable
"""

import os

version_info = """
# UTF-8
#
# For more details about fixed file info 'ffi' see:
# http://msdn.microsoft.com/en-us/library/ms646997.aspx

VSVersionInfo(
  ffi=FixedFileInfo(
    # filevers and prodvers should be always a tuple with four items: (1, 2, 3, 4)
    # Set not needed items to zero 0.
    filevers=(1, 2, 0, 0),
    prodvers=(1, 2, 0, 0),
    # Contains a bitmask that specifies the valid bits 'flags'r
    mask=0x3f,
    # Contains a bitmask that specifies the Boolean attributes of the file.
    flags=0x0,
    # The operating system for which this file was designed.
    # 0x4 - NT and there is no need to change it.
    OS=0x4,
    # The general type of file.
    # 0x1 - the file is an application.
    fileType=0x1,
    # The function of the file.
    # 0x0 - the function is not defined for this fileType
    subtype=0x0,
    # Creation date and time stamp.
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'Telegram Auto Download Bot'),
        StringStruct(u'FileDescription', u'Telegram Auto Download Bot - Media Backup Tool'),
        StringStruct(u'FileVersion', u'1.2.0.0'),
        StringStruct(u'InternalName', u'TelegramAutoDownload'),
        StringStruct(u'LegalCopyright', u'© 2024 Telegram Auto Download Bot'),
        StringStruct(u'OriginalFilename', u'TelegramAutoDownload.exe'),
        StringStruct(u'ProductName', u'Telegram Auto Download Bot'),
        StringStruct(u'ProductVersion', u'1.2.0.0')])
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
        print("Version info file created successfully")
        return True
    except Exception as e:
        print(f"Failed to create version info: {e}")
        return False

if __name__ == "__main__":
    create_version_info()
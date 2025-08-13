# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Get the project root directory
project_root = os.path.dirname(os.path.abspath(SPEC))

# Collect hidden imports - all modules that might not be detected automatically
hiddenimports = [
    # Core application modules
    'src',
    'src.bot',
    'src.downloader', 
    'src.monitor',
    'src.folder_navigator',
    'src.database',
    'config',
    'config.config',
    
    # Telegram libraries
    'telegram',
    'telegram.ext',
    'telegram.ext.filters',
    'telegram.ext.handlers',
    'telegram.ext.updater',
    'telegram.ext.application',
    'telegram.ext.messagehandler',
    'telegram.ext.contexttypes',
    'telethon',
    'telethon.client',
    'telethon.errors',
    'telethon.tl',
    'telethon.tl.types',
    'telethon.sessions',
    
    # GUI and system tray
    'tkinter',
    'tkinter.ttk',
    'tkinter.filedialog',
    'tkinter.messagebox',
    'tkinter.scrolledtext',
    'pystray',
    'pystray._win32',
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageTk',
    
    # Environment and configuration
    'dotenv',
    'python_dotenv',
    
    # System libraries
    'asyncio',
    'queue',
    'threading',
    'sqlite3',
    'logging',
    'logging.handlers',
    'json',
    'os',
    'sys',
    'time',
    'datetime',
    'shutil',
    'pathlib',
    'urllib',
    'urllib.parse',
    'urllib.request',
    'ssl',
    'socket',
    'hashlib',
    'base64',
    'uuid',
    'tempfile',
    'glob',
    'fnmatch',
    're',
    'collections',
    'functools',
    'itertools',
    'weakref',
    'copy',
    'pickle',
    'platform',
    'subprocess',
    'signal',
    'atexit',
    
    # HTTP and network
    'httpx',
    'httpcore',
    'certifi',
    'anyio',
    'sniffio',
    'h11',
    'idna',
    
    # Cryptography (for Telegram)
    'cryptography',
    'cryptography.fernet',
    'cryptography.hazmat',
    'cryptography.hazmat.primitives',
    'cryptography.hazmat.backends',
    'rsa',
    'pyaes',
]

# Collect data files
datas = [
    # Include config directory
    (os.path.join(project_root, 'config'), 'config'),
    
    # Include any template or resource files
    # (os.path.join(project_root, 'resources'), 'resources'),  # If you have resources
]

# Additional data files from packages
try:
    datas += collect_data_files('telegram')
except Exception:
    pass

try:
    datas += collect_data_files('telethon')
except Exception:
    pass

try:
    datas += collect_data_files('certifi')
except Exception:
    pass

# Analysis configuration
a = Analysis(
    ['run_gui.py'],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude large packages we don't need
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'jupyter',
        'IPython',
        'notebook',
        'zmq',
        'tornado',
        'django',
        'flask',
        'fastapi',
        'pytest',
        'setuptools',
        'pip',
        'wheel',
        'distutils',
        'test',
        'tests',
        'testing',
        'unittest',
        'doctest',
        
        # Development tools
        'pdb',
        'pydoc',
        'debugpy',
        'pydevd',
        
        # Large optional libraries
        'opencv',
        'cv2',
        'tensorflow',
        'torch',
        'sklearn',
        'networkx',
        'plotly',
        'bokeh',
        'seaborn',
        
        # Documentation generators
        'sphinx',
        'jinja2',
        'markupsafe',
        
        # Build tools
        'pkg_resources',
        'setuptools',
        'distutils',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Remove duplicate entries
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Executable configuration
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TelegramAutoDownload',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,  # Remove debug symbols to reduce false positives
    upx=False,   # Disable UPX compression (often triggers antivirus)
    console=False,  # GUI application
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_root, 'assets', 'icon.ico'),
    version=os.path.join(project_root, 'version_info.txt'),
    manifest=os.path.join(project_root, 'app.manifest'),  # Add Windows manifest
    uac_admin=False,  # Don't require admin privileges
    uac_uiaccess=False,
)

# Collection configuration
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TelegramAutoDownload',
)

# Optional: Create a single file executable (uncomment if desired)
# Note: This creates a larger single file but may be slower to start
"""
exe_onefile = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='TelegramAutoDownload-Standalone',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_root, 'assets', 'icon.ico'),
    version=os.path.join(project_root, 'version_info.txt'),
)
"""
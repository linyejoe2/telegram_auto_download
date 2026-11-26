import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Telegram API Configuration
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
PHONE_NUMBER = os.getenv('PHONE_NUMBER')
BOT_TOKEN = os.getenv('BOT_TOKEN')
DOWNLOADS_PATH = os.getenv('DOWNLOADS_PATH')

# Validate required environment variables
def validate_config():
    """Validate that all required environment variables are set."""
    required_vars = {
        'API_ID': API_ID,
        'API_HASH': API_HASH,
        'PHONE_NUMBER': PHONE_NUMBER,
        'BOT_TOKEN': BOT_TOKEN
    }
    
    missing_vars = []
    for var_name, var_value in required_vars.items():
        if not var_value:
            missing_vars.append(var_name)
    
    if missing_vars:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing_vars)}\n"
            "Please check your .env file and ensure all variables are set."
        )
    
    return True

def get_startup_scan_count(default: int = 30) -> int:
    """How many of the user's latest messages to the bot are checked at startup (0 = off)."""
    try:
        return max(0, int(os.getenv('STARTUP_SCAN_COUNT', default)))
    except (TypeError, ValueError):
        return default

def get_web_settings() -> dict:
    """Web video library settings (WEB_* in .env); the password is stored only as a hash."""
    try:
        port = int(os.getenv('WEB_PORT', '8765'))
    except ValueError:
        port = 8765
    return {
        'enabled': os.getenv('WEB_ENABLED', '0') == '1',
        'host': os.getenv('WEB_HOST', '0.0.0.0'),
        'port': port,
        'password_hash': os.getenv('WEB_PASSWORD_HASH', ''),
        'secret': os.getenv('WEB_SECRET', ''),
        'similarity': similarity_threshold(),
    }


DEFAULT_MAX_THREADS = 16


def get_max_threads() -> int:
    """MAX_THREADS: the most CPU threads the heavy work may use (ffmpeg, OpenCV, numpy, worker pools);
    default 16, never more than the PC's cores (Windows app Configuration > Performance, v3.6.3)."""
    try:
        value = int(os.getenv('MAX_THREADS', DEFAULT_MAX_THREADS))
    except ValueError:
        value = DEFAULT_MAX_THREADS
    return max(1, min(value, os.cpu_count() or value))


def apply_thread_limit(limit: int = None) -> int:
    """Apply MAX_THREADS to OpenCV (at once) and numpy's math libraries (they read it when first loaded,
    so call this before numpy / cv2 are imported: main.py does)."""
    limit = limit or get_max_threads()
    for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_MAX_THREADS'):
        os.environ[name] = str(limit)
    try:
        import cv2
        cv2.setNumThreads(limit)
    except Exception:
        pass
    return limit


def get_ai_settings() -> dict:
    """AI 辨識 (web library): the Ollama server and vision model used to describe / compare outfits.
    An empty model means the first installed model that can see pictures (library/recognize.py)."""
    return {
        'ollama_url': os.getenv('OLLAMA_BASE_URL', '').strip() or 'http://localhost:11434',
        'ollama_model': os.getenv('OLLAMA_MODEL', '').strip(),
    }


def similarity_threshold(default: float = 70) -> float:
    """Percent at which two videos of the same length count as versions of one video (SIMILARITY_THRESHOLD)."""
    try:
        return min(100.0, max(1.0, float(os.getenv('SIMILARITY_THRESHOLD', default))))
    except ValueError:
        return default

# File and Directory Configuration
def get_app_dir():
    """Get the application directory that works for both development and packaged app"""
    if hasattr(sys, '_MEIPASS'):
        # Running as packaged executable
        return os.path.dirname(sys.executable)
    else:
        # Running in development
        return os.path.dirname(os.path.dirname(__file__))

DATA_DIR_NAME = '.tad'          # library data folder inside DOWNLOADS_PATH (like Obsidian's .obsidian)


def get_downloads_dir() -> str:
    """The current downloads folder (DOWNLOADS_PATH, read live so a reloaded .env takes effect)."""
    return os.path.abspath(os.getenv('DOWNLOADS_PATH') or os.path.join(get_app_dir(), 'downloads'))


def get_data_dir(downloads_dir: str = None) -> str:
    """Hidden folder inside the downloads folder holding the database and history, so the whole
    library (media + data) can be opened from any device that mounts the same folder."""
    path = os.path.join(downloads_dir or get_downloads_dir(), DATA_DIR_NAME)
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)
        if os.name == 'nt':
            try:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(path, 0x02)
            except Exception:
                pass
    return path


def get_database_path(downloads_dir: str = None):
    """downloads.db lives in <DOWNLOADS_PATH>/.tad/ (v3.2.0; before that it was next to the app)."""
    return os.path.join(get_data_dir(downloads_dir), 'downloads.db')


def get_legacy_database_path():
    """Where downloads.db was kept before v3.2.0 (migrated into the downloads folder on first open)."""
    return os.path.join(get_app_dir(), 'downloads.db')


DOWNLOADS_DIR = get_downloads_dir()
LOGS_DIR = os.path.join(get_app_dir(), 'logs')

# Bot Configuration
MAX_FILE_SIZE_MB = 50  # Telegram bot file upload limit
SESSION_NAME = 'bot_session'

# Create directories if they don't exist
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
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

# File and Directory Configuration
def get_app_dir():
    """Get the application directory that works for both development and packaged app"""
    if hasattr(sys, '_MEIPASS'):
        # Running as packaged executable
        return os.path.dirname(sys.executable)
    else:
        # Running in development
        return os.path.dirname(os.path.dirname(__file__))

def get_database_path():
    """Get the database path that works for both development and packaged app"""
    return os.path.join(get_app_dir(), 'downloads.db')

DOWNLOADS_DIR = DOWNLOADS_PATH or os.path.join(get_app_dir(), 'downloads')
LOGS_DIR = os.path.join(get_app_dir(), 'logs')
DATABASE_PATH = get_database_path()

# Bot Configuration
MAX_FILE_SIZE_MB = 50  # Telegram bot file upload limit
SESSION_NAME = 'bot_session'

# Create directories if they don't exist
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
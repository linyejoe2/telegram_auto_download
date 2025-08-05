#!/usr/bin/env python3
"""
Telegram Auto Download Bot - Main Entry Point

This is an improved version of the telegram bot that uses environment variables
for configuration and better project structure.
"""

import asyncio
import sys
import os

# Add the project root and config directories to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config'))

from config.config import validate_config, API_ID, API_HASH, PHONE_NUMBER, BOT_TOKEN
from src.telegram_bot import TelegramMediaBot

async def main():
    """Main function to run the Telegram bot."""
    try:
        # Validate configuration
        validate_config()
        print("✅ Configuration validated successfully")
        
        # Create and run the bot
        bot = TelegramMediaBot(API_ID, API_HASH, PHONE_NUMBER, BOT_TOKEN)
        await bot.run()
        
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
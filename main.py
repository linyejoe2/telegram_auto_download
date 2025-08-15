#!/usr/bin/env python3
"""
Telegram Auto Download Bot - Main Entry Point

Unified entry point supporting both CLI and GUI modes.
"""

import asyncio
import sys
import os
import argparse
import io

def fix_stdin_stdout():
    """Fix stdin/stdout for PyInstaller GUI applications"""
    if getattr(sys, 'frozen', False):  # Running in PyInstaller bundle
        # Redirect stdin to prevent "lost sys.stdin" errors
        if sys.stdin is None or not hasattr(sys.stdin, 'fileno'):
            sys.stdin = io.StringIO('')
        
        # Ensure stdout and stderr exist
        if sys.stdout is None:
            sys.stdout = io.StringIO()
        if sys.stderr is None:
            sys.stderr = io.StringIO()

# Apply the fix before importing anything else
fix_stdin_stdout()

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.config import validate_config, API_ID, API_HASH, PHONE_NUMBER, BOT_TOKEN
from src.bot import TelegramMediaBot

async def main():
    """Main function to run the Telegram bot in CLI mode."""
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

def run_gui():
    """Run the GUI application."""
    try:
        from src.ui import TelegramBotGUI
        app = TelegramBotGUI()
        app.run()
    except KeyboardInterrupt:
        print("\nGUI application stopped by user")
    except Exception as e:
        # In GUI mode, we might not have console output
        try:
            import tkinter.messagebox as mb
            mb.showerror("Error", f"Error starting GUI: {e}")
        except:
            # Fallback to file logging if GUI fails
            with open("error.log", "w") as f:
                f.write(f"Error starting GUI: {e}\n")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telegram Auto Download Bot")
    parser.add_argument("--gui", action="store_true", help="Run in GUI mode")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode (default)")
    
    args = parser.parse_args()
    
    # Default to GUI if no arguments provided and we're in a Windows environment
    # or if explicitly requested
    if args.gui or (not args.cli and not sys.argv[1:] and os.name == 'nt'):
        run_gui()
    else:
        asyncio.run(main())
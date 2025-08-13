#!/usr/bin/env python3
"""
Telegram Auto Download Bot GUI Launcher
"""

import sys
import os
import io

# Fix for PyInstaller stdin/stdout issues
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
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from ui import TelegramBotGUI

if __name__ == "__main__":
    try:
        app = TelegramBotGUI()
        app.run()
    except KeyboardInterrupt:
        print("\nGUI application stopped by user")
    except Exception as e:
        # In GUI mode, we might not have console output
        import tkinter.messagebox as mb
        try:
            mb.showerror("Error", f"Error starting GUI: {e}")
        except:
            # Fallback to file logging if GUI fails
            with open("error.log", "w") as f:
                f.write(f"Error starting GUI: {e}\n")
        sys.exit(1)
#!/usr/bin/env python3
"""
Authentication helper for GUI mode Telethon client
Handles authentication without requiring stdin input
"""

import asyncio
import logging
import tkinter as tk
from tkinter import simpledialog, messagebox
import sys

logger = logging.getLogger(__name__)

class GUIAuthHelper:
    """GUI-based authentication helper for Telethon"""
    
    def __init__(self, root=None):
        self.root = root
        self.auth_window = None
    
    def phone_code_callback(self):
        """Handle phone code input via GUI"""
        try:
            if self.root:
                # Use existing root window
                code = simpledialog.askstring(
                    "Telegram Authentication",
                    "Please enter the verification code sent to your phone:",
                    parent=self.root
                )
            else:
                # Create temporary window
                temp_root = tk.Tk()
                temp_root.withdraw()  # Hide the main window
                code = simpledialog.askstring(
                    "Telegram Authentication", 
                    "Please enter the verification code sent to your phone:",
                    parent=temp_root
                )
                temp_root.destroy()
            
            return code
        except Exception as e:
            logger.error(f"Phone code input failed: {e}")
            return None
    
    def password_callback(self):
        """Handle 2FA password input via GUI"""
        try:
            if self.root:
                password = simpledialog.askstring(
                    "Two-Factor Authentication",
                    "Please enter your 2FA password:",
                    parent=self.root,
                    show='*'
                )
            else:
                temp_root = tk.Tk()
                temp_root.withdraw()
                password = simpledialog.askstring(
                    "Two-Factor Authentication",
                    "Please enter your 2FA password:",
                    parent=temp_root,
                    show='*'
                )
                temp_root.destroy()
            
            return password
        except Exception as e:
            logger.error(f"Password input failed: {e}")
            return None
    
    def show_auth_info(self, phone_number):
        """Show authentication information to user"""
        try:
            message = f"""Telegram Authentication Required

Phone number: {phone_number}

A verification code will be sent to your phone.
Please check your Telegram app or SMS.

Click OK when ready to continue."""
            
            if self.root:
                messagebox.showinfo("Authentication", message, parent=self.root)
            else:
                temp_root = tk.Tk()
                temp_root.withdraw()
                messagebox.showinfo("Authentication", message, parent=temp_root)
                temp_root.destroy()
        except Exception as e:
            logger.error(f"Failed to show auth info: {e}")

class ConsoleAuthHelper:
    """Fallback console-based authentication for development"""
    
    def phone_code_callback(self):
        """Handle phone code input via console"""
        try:
            return input("Please enter the verification code: ")
        except EOFError:
            logger.error("EOF when reading phone code")
            return None
    
    def password_callback(self):
        """Handle 2FA password input via console"""
        try:
            import getpass
            return getpass.getpass("Please enter your 2FA password: ")
        except EOFError:
            logger.error("EOF when reading password")
            return None
        except ImportError:
            try:
                return input("Please enter your 2FA password: ")
            except EOFError:
                return None
    
    def show_auth_info(self, phone_number):
        """Show authentication information to console"""
        print(f"\nTelegram Authentication Required")
        print(f"Phone number: {phone_number}")
        print("A verification code will be sent to your phone.")
        print("Please check your Telegram app or SMS.\n")

def get_auth_helper(gui_root=None):
    """Get appropriate authentication helper based on environment"""
    is_frozen = getattr(sys, 'frozen', False)
    has_gui = gui_root is not None
    
    # Always try GUI first if available
    if has_gui or is_frozen:
        try:
            # Test if tkinter is available
            import tkinter
            return GUIAuthHelper(gui_root)
        except ImportError:
            logger.warning("tkinter not available, falling back to console auth")
    
    # Fallback to console
    return ConsoleAuthHelper()

def check_session_exists(session_name='bot_session'):
    """Check if a Telethon session file exists"""
    import os
    session_file = f"{session_name}.session"
    return os.path.exists(session_file)

async def authenticate_client(client, phone_number, auth_helper=None):
    """Authenticate Telethon client with proper error handling - for new authentication only"""
    if auth_helper is None:
        auth_helper = get_auth_helper()
    
    try:
        logger.info(f"Starting fresh authentication for {phone_number}")
        
        # Show authentication info for interactive auth
        auth_helper.show_auth_info(phone_number)
        
        # Start client with custom handlers for new authentication
        await client.start(
            phone=phone_number,
            code_callback=auth_helper.phone_code_callback,
            password=auth_helper.password_callback
        )
        
        logger.info("Fresh authentication successful")
        return True
        
    except EOFError as e:
        logger.error(f"Authentication failed - EOF error: {e}")
        logger.error("This usually means GUI authentication is not available")
        return False
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        return False

# Monkey patch for Telethon to prevent stdin access
def patch_telethon_input():
    """Patch Telethon to avoid direct stdin access"""
    try:
        from telethon import client
        
        # Store original input method if it exists
        if hasattr(client, '_input'):
            client._original_input = client._input
        
        # Replace with our safe input
        def safe_input(prompt=""):
            logger.warning(f"Telethon tried to access stdin with prompt: {prompt}")
            raise EOFError("stdin not available in GUI mode")
        
        client._input = safe_input
        logger.info("Telethon input patched for GUI mode")
        
    except ImportError:
        logger.warning("Could not patch Telethon - not installed")
    except Exception as e:
        logger.error(f"Failed to patch Telethon: {e}")

# Apply patch on import
patch_telethon_input()
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import queue
import os
import sys
import logging
from dotenv import load_dotenv, set_key
import pystray
from PIL import Image, ImageDraw
import asyncio
from main import main as bot_main
from src.bot import log_queue
from config.config import validate_config

class TelegramBotGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Telegram Auto Download Bot")
        self.root.geometry("800x600")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Set window icon using the same tray image
        try:
            icon_image = self.create_tray_image()
            # Convert PIL image to PhotoImage for tkinter
            from PIL import ImageTk
            photo = ImageTk.PhotoImage(icon_image)
            self.root.iconphoto(True, photo)
        except Exception as e:
            # If icon setting fails, continue without it
            pass
        
        # Load environment variables
        load_dotenv()
        
        # Bot control
        self.bot_running = False
        self.bot_thread = None
        self.log_queue = queue.Queue()
        
        # Auto-start preference
        self.auto_start_var = tk.BooleanVar(value=True)
        
        # System tray
        self.tray_icon = None
        self.is_minimized_to_tray = False
        
        # Setup GUI
        self.setup_gui()
        self.setup_logging()
        self.load_current_settings()
        
        # Start log monitoring
        self.monitor_logs()
        
        # Auto-start bot if configuration is valid
        self.auto_start_bot()

    def create_tray_image(self):
        """Create a simple icon for system tray"""
        # Create a simple icon image
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), color='blue')
        draw = ImageDraw.Draw(image)
        
        # Draw a simple "T" for Telegram
        draw.rectangle([20, 10, 30, 50], fill='white')
        draw.rectangle([10, 10, 50, 20], fill='white')
        
        return image

    def setup_gui(self):
        """Setup the main GUI interface"""
        # Create main notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Configuration
        config_frame = ttk.Frame(notebook)
        notebook.add(config_frame, text="Configuration")
        self.setup_config_tab(config_frame)
        
        # Logs tab
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text="Logs")
        self.setup_log_tab(log_frame)

    def setup_config_tab(self, parent):
        """Setup configuration tab with bot control at top"""
        # Bot Control section (at top)
        control_frame = ttk.LabelFrame(parent, text="Bot Control", padding="10")
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Status
        status_frame = ttk.Frame(control_frame)
        status_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(status_frame, text="Bot Status:").pack(side=tk.LEFT)
        self.status_label = ttk.Label(status_frame, text="Stopped", foreground="red")
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # Control buttons
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        self.start_button = ttk.Button(button_frame, text="Start Bot", command=self.start_bot)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="Stop Bot", command=self.stop_bot, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        # Auto-start checkbox
        ttk.Checkbutton(button_frame, text="Auto-start on launch", variable=self.auto_start_var).pack(side=tk.LEFT, padx=20)
        
        # Downloads path configuration
        path_frame = ttk.LabelFrame(parent, text="Download Path Configuration", padding="10")
        path_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(path_frame, text="Downloads Directory:").pack(anchor=tk.W)
        
        self.downloads_path_var = tk.StringVar()
        self.downloads_path_entry = ttk.Entry(path_frame, textvariable=self.downloads_path_var, width=60)
        self.downloads_path_entry.pack(fill=tk.X, expand=True)
        
        path_input_button_frame = ttk.Frame(path_frame)
        path_input_button_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(path_input_button_frame, text="Browse", command=self.browse_downloads_path).pack(side=tk.LEFT, pady=5)
        
        ttk.Button(path_input_button_frame, text="Save Downloads Path", command=self.save_downloads_path).pack(side=tk.LEFT, pady=5)
        
        # Bot configuration
        bot_config_frame = ttk.LabelFrame(parent, text="Bot Configuration", padding="10")
        bot_config_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # API ID
        ttk.Label(bot_config_frame, text="API ID:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.api_id_var = tk.StringVar()
        ttk.Entry(bot_config_frame, textvariable=self.api_id_var, width=30).grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
        
        # API Hash
        ttk.Label(bot_config_frame, text="API Hash:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.api_hash_var = tk.StringVar()
        ttk.Entry(bot_config_frame, textvariable=self.api_hash_var, width=30, show="*").grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)
        
        # Phone Number
        ttk.Label(bot_config_frame, text="Phone Number:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.phone_var = tk.StringVar()
        ttk.Entry(bot_config_frame, textvariable=self.phone_var, width=30).grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)
        
        # Bot Token
        ttk.Label(bot_config_frame, text="Bot Token:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.bot_token_var = tk.StringVar()
        ttk.Entry(bot_config_frame, textvariable=self.bot_token_var, width=30, show="*").grid(row=3, column=1, sticky=tk.W, padx=5, pady=2)
        
        ttk.Button(bot_config_frame, text="Save Bot Configuration", command=self.save_bot_config).grid(row=4, column=0, columnspan=2, pady=10, sticky=tk.W)

    def setup_log_tab(self, parent):
        """Setup logs tab"""
        log_frame = ttk.LabelFrame(parent, text="Application Logs", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Log text area
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=20)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Log controls
        log_controls = ttk.Frame(log_frame)
        log_controls.pack(fill=tk.X, pady=5)
        
        ttk.Button(log_controls, text="Clear Logs", command=self.clear_logs).pack(side=tk.LEFT)
        ttk.Button(log_controls, text="Save Logs", command=self.save_logs).pack(side=tk.LEFT, padx=5)

    def auto_start_bot(self):
        """Auto-start bot if configuration is valid and auto-start is enabled"""
        if not self.auto_start_var.get():
            return
            
        try:
            # Check if configuration is valid
            load_dotenv()
            validate_config()
            
            # Auto-start the bot after GUI is fully loaded
            self.root.after(1000, self.start_bot)  # Delay start by 1 second
            logging.info("Auto-starting bot...")
            
        except Exception as e:
            logging.info(f"Auto-start skipped: {e}")
            # Don't show error popup for auto-start failures

    def setup_logging(self):
        """Setup logging to capture bot logs"""
        # Create logs directory
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        # Configure file logging
        log_file = os.path.join(log_dir, 'bot.log')
        
        # Setup logging handler that also sends to queue
        class QueueHandler(logging.Handler):
            def __init__(self, log_queue):
                super().__init__()
                self.log_queue = log_queue
            
            def emit(self, record):
                self.log_queue.put(self.format(record))
        
        # Configure root logger
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                QueueHandler(log_queue)
            ]
        )

    def monitor_logs(self):
        """Monitor log queue and update GUI"""
        try:
            while True:
                log_message = log_queue.get_nowait()
                self.log_text.insert(tk.END, log_message + '\n')
                self.log_text.see(tk.END)
        except queue.Empty:
            pass
        
        # Schedule next check
        self.root.after(100, self.monitor_logs)

    def load_current_settings(self):
        """Load current settings from .env file"""
        self.downloads_path_var.set(os.getenv('DOWNLOADS_PATH', os.path.join(os.path.dirname(__file__), 'downloads')))
        self.api_id_var.set(os.getenv('API_ID', ''))
        self.api_hash_var.set(os.getenv('API_HASH', ''))
        self.phone_var.set(os.getenv('PHONE_NUMBER', ''))
        self.bot_token_var.set(os.getenv('BOT_TOKEN', ''))

    def browse_downloads_path(self):
        """Browse for downloads directory"""
        directory = filedialog.askdirectory(
            title="Select Downloads Directory",
            initialdir=self.downloads_path_var.get()
        )
        if directory:
            self.downloads_path_var.set(directory)

    def save_downloads_path(self):
        """Save downloads path to .env file"""
        try:
            downloads_path = self.downloads_path_var.get()
            if not downloads_path:
                messagebox.showerror("Error", "Please enter a downloads path")
                return
            
            # Create directory if it doesn't exist
            os.makedirs(downloads_path, exist_ok=True)
            
            # Save to .env file
            env_file = '.env'
            set_key(env_file, 'DOWNLOADS_PATH', downloads_path)
            
            messagebox.showinfo("Success", "Downloads path saved successfully!")
            logging.info(f"Downloads path updated to: {downloads_path}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save downloads path: {str(e)}")
            logging.error(f"Failed to save downloads path: {e}")

    def save_bot_config(self):
        """Save bot configuration to .env file"""
        try:
            env_file = '.env'
            
            # Save all configuration values
            set_key(env_file, 'API_ID', self.api_id_var.get())
            set_key(env_file, 'API_HASH', self.api_hash_var.get())
            set_key(env_file, 'PHONE_NUMBER', self.phone_var.get())
            set_key(env_file, 'BOT_TOKEN', self.bot_token_var.get())
            
            messagebox.showinfo("Success", "Bot configuration saved successfully!")
            logging.info("Bot configuration updated")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save bot configuration: {str(e)}")
            logging.error(f"Failed to save bot configuration: {e}")

    def start_bot(self):
        """Start the Telegram bot"""
        try:
            # Validate configuration
            load_dotenv()  # Reload environment variables
            validate_config()
            
            if self.bot_running:
                messagebox.showwarning("Warning", "Bot is already running!")
                return
            
            # Start bot in separate thread
            self.bot_thread = threading.Thread(target=self.run_bot, daemon=True)
            self.bot_thread.start()
            
            # Update UI
            self.bot_running = True
            self.status_label.config(text="Running", foreground="green")
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            
            logging.info("Bot started successfully")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start bot: {str(e)}")
            logging.error(f"Failed to start bot: {e}")

    def stop_bot(self):
        """Stop the Telegram bot"""
        try:
            if not self.bot_running:
                messagebox.showwarning("Warning", "Bot is not running!")
                return
            
            # Update UI
            self.bot_running = False
            self.status_label.config(text="Stopped", foreground="red")
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            
            logging.info("Bot stopped")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to stop bot: {str(e)}")
            logging.error(f"Failed to stop bot: {e}")

    def run_bot(self):
        """Run the bot in a separate thread"""
        try:
            asyncio.run(bot_main())
            # Import bot directly and run with GUI root
            # from config.config import validate_config, API_ID, API_HASH, PHONE_NUMBER, BOT_TOKEN
            # from src.bot import TelegramMediaBot
            
            # # Create bot instance
            # bot = TelegramMediaBot(API_ID, API_HASH, PHONE_NUMBER, BOT_TOKEN)
            
            # # Run bot with GUI root for authentication
            # asyncio.run(bot.run(self.root))
            
        except Exception as e:
            logging.error(f"Bot error: {e}")
            self.root.after(0, self.stop_bot)

    def clear_logs(self):
        """Clear the log text area"""
        self.log_text.delete(1.0, tk.END)

    def save_logs(self):
        """Save logs to file"""
        try:
            log_content = self.log_text.get(1.0, tk.END)
            if not log_content.strip():
                messagebox.showwarning("Warning", "No logs to save!")
                return
            
            file_path = filedialog.asksaveasfilename(
                title="Save Logs",
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
            )
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(log_content)
                messagebox.showinfo("Success", f"Logs saved to {file_path}")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save logs: {str(e)}")

    def setup_system_tray(self):
        """Setup system tray functionality"""
        try:
            # Create tray icon
            icon_image = self.create_tray_image()
            
            # Create menu
            menu = pystray.Menu(
                pystray.MenuItem("Show", self.show_window),
                pystray.MenuItem("Hide", self.hide_window),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", self.quit_application)
            )
            
            self.tray_icon = pystray.Icon("TelegramBot", icon_image, "Telegram Auto Download Bot", menu)
            
        except Exception as e:
            logging.error(f"Failed to setup system tray: {e}")

    def show_window(self, icon=None, item=None):
        """Show the main window"""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.is_minimized_to_tray = False

    def hide_window(self, icon=None, item=None):
        """Hide window to system tray"""
        self.root.withdraw()
        self.is_minimized_to_tray = True

    def on_closing(self):
        """Handle window closing event"""
        if self.tray_icon:
            # Minimize to tray instead of closing
            self.hide_window()
        else:
            self.quit_application()

    def quit_application(self, icon=None, item=None):
        """Quit the application completely"""
        try:
            if self.bot_running:
                self.stop_bot()
            
            if self.tray_icon:
                self.tray_icon.stop()
            
            self.root.quit()
            self.root.destroy()
            
        except Exception as e:
            logging.error(f"Error during quit: {e}")

    def run_tray_in_thread(self):
        """Run system tray in separate thread"""
        if self.tray_icon:
            self.tray_icon.run()

    def run(self):
        """Run the GUI application"""
        try:
            # Setup system tray
            self.setup_system_tray()
            
            # Start system tray in separate thread
            if self.tray_icon:
                tray_thread = threading.Thread(target=self.run_tray_in_thread, daemon=True)
                tray_thread.start()
            
            # Start main GUI loop
            self.root.mainloop()
            
        except Exception as e:
            logging.error(f"GUI error: {e}")
            messagebox.showerror("Error", f"GUI error: {str(e)}")

if __name__ == "__main__":
    app = TelegramBotGUI()
    app.run()
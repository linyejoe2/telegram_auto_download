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
import subprocess
import platform
from main import main as bot_main
from src.bot import log_queue
from src.database import DatabaseManager
from config.config import validate_config

class TelegramBotGUI:
    def __init__(self):
        self.version = "v1.2.0"
        self.root = tk.Tk()
        self.root.title("Telegram Auto Download Bot " + self.version)
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
        
        # Initialize database displays
        self.root.after(500, self.init_database_displays)
        
        # Auto-start bot if configuration is valid
        # self.auto_start_bot()

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
        
        # Database tab
        database_frame = ttk.Frame(notebook)
        notebook.add(database_frame, text="Database")
        self.setup_database_tab(database_frame)

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

    def setup_database_tab(self, parent):
        """Setup database tab"""
        # Statistics section
        stats_frame = ttk.LabelFrame(parent, text="Download Statistics", padding="10")
        stats_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Main statistics display
        main_stats_frame = ttk.Frame(stats_frame)
        main_stats_frame.pack(fill=tk.X, pady=5)
        
        # Total files
        ttk.Label(main_stats_frame, text="Total Files:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.total_files_label = ttk.Label(main_stats_frame, text="0", font=("Arial", 10, "bold"))
        self.total_files_label.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        # Total size
        ttk.Label(main_stats_frame, text="Total Size:").grid(row=0, column=2, sticky=tk.W, padx=5)
        self.total_size_label = ttk.Label(main_stats_frame, text="0 MB", font=("Arial", 10, "bold"))
        self.total_size_label.grid(row=0, column=3, sticky=tk.W, padx=5)
        
        # Unique chats
        ttk.Label(main_stats_frame, text="Unique Chats:").grid(row=0, column=4, sticky=tk.W, padx=5)
        self.unique_chats_label = ttk.Label(main_stats_frame, text="0", font=("Arial", 10, "bold"))
        self.unique_chats_label.grid(row=0, column=5, sticky=tk.W, padx=5)
        
        # File types section
        file_types_frame = ttk.Frame(stats_frame)
        file_types_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(file_types_frame, text="File Types:", font=("Arial", 9, "bold")).pack(anchor=tk.W)
        self.file_types_frame = ttk.Frame(file_types_frame)
        self.file_types_frame.pack(fill=tk.X, pady=5)
        
        # Refresh stats button
        ttk.Button(stats_frame, text="Refresh Statistics", command=self.refresh_statistics).pack(side=tk.LEFT, pady=5)
        
        # Recent downloads section
        downloads_frame = ttk.LabelFrame(parent, text="Recent Downloads", padding="10")
        downloads_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        tree_frame = tk.Frame(downloads_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        
        # Create treeview for downloads list
        self.columns = ("File Name", "Type", "Size", "Download Date", "Path")
        self.downloads_tree = ttk.Treeview(tree_frame, columns=self.columns, show="headings")
        
        self.sort_order = {col: False for col in self.columns}
        
        # Configure column headings and widths
        # self.downloads_tree.heading("File Name", text="File Name")
        # self.downloads_tree.heading("Type", text="Type")
        # self.downloads_tree.heading("Size", text="Size")
        # self.downloads_tree.heading("Download Date", text="Download Date")
        # self.downloads_tree.heading("Path", text="Path")
        for col in self.columns:
            self.downloads_tree.heading(col, text=col, command=lambda c=col: self.sort_by_column(c))
        
        self.downloads_tree.column("File Name", width=200)
        self.downloads_tree.column("Type", width=80)
        self.downloads_tree.column("Size", width=70)
        self.downloads_tree.column("Download Date", width=120)
        self.downloads_tree.column("Path", width=250)
        
        # Add scrollbar for treeview
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.downloads_tree.yview)
        self.downloads_tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack treeview and scrollbar
        self.downloads_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Controls for downloads list
        downloads_controls = ttk.Frame(downloads_frame)
        downloads_controls.pack(fill=tk.X, pady=5)
        
        ttk.Button(downloads_controls, text="Refresh Downloads", command=self.refresh_downloads).pack(side=tk.LEFT)
        ttk.Button(downloads_controls, text="Open File Location", command=self.open_file_location).pack(side=tk.LEFT, padx=5)
        
    def sort_by_column(self, col):
        # Get all rows
        data = [(self.downloads_tree.set(child, col), child) for child in self.downloads_tree.get_children('')]

        # Try to convert to float/int for size/date sorting, fallback to string
        def try_cast(val):
            try:
                # Size handling for "1.5 MB", "230 KB", etc.
                if col == "Size":
                    num, unit = val.split()
                    num = float(num)
                    multiplier = {"B": 1, "KB": 1_000, "MB": 1_000_000, "GB": 1_000_000_000}
                    return num * multiplier[unit]
                elif col == "Download Date":
                    return val  # Could use datetime.strptime if needed
                return float(val)
            except:
                return val.lower()

        # Sort data
        data.sort(key=lambda x: try_cast(x[0]), reverse=self.sort_order[col])
        self.sort_order[col] = not self.sort_order[col]

        # Rearrange items in tree
        for index, (_, iid) in enumerate(data):
            self.downloads_tree.move(iid, '', index)

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

    def refresh_statistics(self):
        """Refresh download statistics"""
        try:
            db = DatabaseManager()
            stats = db.get_download_statistics()
            
            # Update main statistics labels
            self.total_files_label.config(text=str(stats.get('total_files', 0)))
            total_size_mb = stats.get('total_size_mb', 0)
            self.total_size_label.config(text=f"{total_size_mb:.1f} MB")
            self.unique_chats_label.config(text=str(stats.get('unique_chats', 0)))
            
            # Clear existing file type labels
            for widget in self.file_types_frame.winfo_children():
                widget.destroy()
            
            # Add file type breakdown
            type_stats = stats.get('files_by_type', {})
            if type_stats:
                row = 0
                for file_type, count in type_stats.items():
                    type_name = file_type or 'unknown'
                    ttk.Label(self.file_types_frame, text=f"{type_name}:").grid(row=row, column=0, sticky=tk.W, padx=5)
                    ttk.Label(self.file_types_frame, text=f"{count} files", font=("Arial", 9, "bold")).grid(row=row, column=1, sticky=tk.W, padx=5)
                    row += 1
            else:
                ttk.Label(self.file_types_frame, text="No files downloaded yet", style="TLabel").pack(anchor=tk.W)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refresh statistics: {str(e)}")

    def refresh_downloads(self):
        """Refresh recent downloads list"""
        try:
            # Clear existing items
            for item in self.downloads_tree.get_children():
                self.downloads_tree.delete(item)
            
            # Get recent downloads
            db = DatabaseManager()
            downloads = db.get_recent_downloads(limit=100)  # Show last 100 downloads
            
            # Populate treeview
            for download in downloads:
                file_name = download.get('file_name', 'Unknown')
                file_type = download.get('file_type', 'Unknown')
                file_size = download.get('file_size', 0)
                download_date = download.get('download_date', '')
                file_path = download.get('file_path', '')
                
                # Format file size
                if file_size:
                    if file_size > 1024**2:
                        size_str = f"{file_size/(1024**2):.1f} MB"
                    elif file_size > 1024:
                        size_str = f"{file_size/1024:.1f} KB"
                    else:
                        size_str = f"{file_size} B"
                else:
                    size_str = "Unknown"
                
                # Format date
                if download_date:
                    try:
                        # Parse ISO format date
                        from datetime import datetime
                        dt = datetime.fromisoformat(download_date.replace('Z', '+00:00'))
                        date_str = dt.strftime("%Y-%m-%d %H:%M")
                    except:
                        date_str = str(download_date)[:16]  # Truncate if parsing fails
                else:
                    date_str = "Unknown"
                
                # Insert into treeview
                self.downloads_tree.insert("", "end", values=(
                    file_name, file_type, size_str, date_str, file_path
                ))
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refresh downloads: {str(e)}")

    def open_file_location(self):
        """Open file location of selected download"""
        try:
            selection = self.downloads_tree.selection()
            if not selection:
                messagebox.showwarning("Warning", "Please select a file from the list.")
                return
            
            # Get file path from selected item
            item = self.downloads_tree.item(selection[0])
            file_path = item['values'][4]  # Path is the 5th column (index 4)
            
            if not file_path or not os.path.exists(file_path):
                messagebox.showerror("Error", "File not found or path is invalid.")
                return
            
            # Open file location in file explorer
            if platform.system() == "Windows":
                subprocess.run(f'explorer /select,"{file_path}"')
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", "-R", file_path])
            else:  # Linux
                subprocess.run(["xdg-open", os.path.dirname(file_path)])
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open file location: {str(e)}")

    def init_database_displays(self):
        """Initialize database displays on startup"""
        try:
            self.refresh_statistics()
            self.refresh_downloads()
        except Exception as e:
            # Don't show error dialog on startup, just log it
            logging.error(f"Failed to initialize database displays: {e}")

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
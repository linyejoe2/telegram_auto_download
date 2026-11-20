import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import queue
import os
import sys
import logging
from dotenv import load_dotenv, set_key
import pystray
from PIL import Image, ImageDraw, ImageTk
import asyncio
import importlib
import subprocess
import platform
import sys
import os
import time
# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .bot import log_queue, TelegramMediaBot
import config.config as bot_config
from .database import DatabaseManager
from config.config import validate_config, get_web_settings

class TelegramBotGUI:
    def __init__(self):
        self.version = "v3.0.2"
        self.root = tk.Tk()
        self.root.title("Telegram Auto Download Bot " + self.version)
        self.root.geometry("800x680")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Set window icon using the same tray image
        try:
            icon_image = Image.open("assets/icon.ico")
            # Convert PIL image to PhotoImage for tkinter
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
        self.bot_loop = None
        self.bot_task = None
        self.log_queue = queue.Queue()
        
        # Auto-start preference
        self.auto_start_var = tk.BooleanVar(value=True)
        
        # Web video library (library/server.py), runs in its own thread
        self.web_server = None

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
        self.root.after(1000, self.check_chromium_status)
        
        self.database_update_thread = threading.Thread(target=self.refresh_database, daemon=True)
        
        # Auto-start bot if configuration is valid
        self.auto_start_bot()
        self.root.after(1500, self.auto_start_web)

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

        # Web video library tab
        web_frame = ttk.Frame(notebook)
        notebook.add(web_frame, text="Web Library")
        self.setup_web_tab(web_frame)

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

        self.restart_button = ttk.Button(button_frame, text="Restart Bot", command=self.restart_bot)
        self.restart_button.pack(side=tk.LEFT, padx=5)

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
        
        # Startup scan: how many of my latest messages to the bot are checked at startup
        ttk.Label(bot_config_frame, text="Startup scan (messages):").grid(row=4, column=0, sticky=tk.W, pady=2)
        scan_frame = ttk.Frame(bot_config_frame)
        scan_frame.grid(row=4, column=1, sticky=tk.W, padx=5, pady=2)
        self.startup_scan_var = tk.StringVar()
        ttk.Entry(scan_frame, textvariable=self.startup_scan_var, width=6).pack(side=tk.LEFT)
        ttk.Label(scan_frame, text="0 = off. Checks your last N messages to the bot when it starts").pack(side=tk.LEFT, padx=8)

        ttk.Button(bot_config_frame, text="Save Bot Configuration", command=self.save_bot_config).grid(row=5, column=0, columnspan=2, pady=10, sticky=tk.W)

        # Chromium (used for X post screenshots)
        chromium_frame = ttk.LabelFrame(parent, text="Screenshot Engine", padding="10")
        chromium_frame.pack(fill=tk.X, padx=10, pady=5)

        self.chromium_status_label = ttk.Label(chromium_frame, text="Chromium status: Not checked")
        self.chromium_status_label.pack(side=tk.LEFT)

        self.chromium_check_button = ttk.Button(chromium_frame, text="Check", command=self.check_chromium_status)
        self.chromium_check_button.pack(side=tk.RIGHT, padx=5)
        self.chromium_install_button = ttk.Button(chromium_frame, text="Install", command=self.install_chromium)
        self.chromium_install_button.pack(side=tk.RIGHT, padx=5)

    # ---------------------- web video library ----------------------
    def setup_web_tab(self, parent):
        """Web video library: watch & manage downloaded videos in a browser (password protected)"""
        settings = get_web_settings()

        control = ttk.LabelFrame(parent, text="Web Library Server", padding="10")
        control.pack(fill=tk.X, padx=10, pady=5)
        status_row = ttk.Frame(control)
        status_row.pack(fill=tk.X, pady=5)
        ttk.Label(status_row, text="Status:").pack(side=tk.LEFT)
        self.web_status_label = ttk.Label(status_row, text="Stopped", foreground="red")
        self.web_status_label.pack(side=tk.LEFT, padx=10)

        buttons = ttk.Frame(control)
        buttons.pack(fill=tk.X, pady=5)
        self.web_start_button = ttk.Button(buttons, text="Start", command=self.start_web)
        self.web_start_button.pack(side=tk.LEFT, padx=5)
        self.web_stop_button = ttk.Button(buttons, text="Stop", command=self.stop_web, state=tk.DISABLED)
        self.web_stop_button.pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons, text="Open in Browser", command=self.open_web).pack(side=tk.LEFT, padx=5)
        self.web_enabled_var = tk.BooleanVar(value=settings['enabled'])
        ttk.Checkbutton(buttons, text="Start on launch", variable=self.web_enabled_var,
                        command=self.save_web_settings).pack(side=tk.LEFT, padx=20)

        settings_frame = ttk.LabelFrame(parent, text="Settings", padding="10")
        settings_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(settings_frame, text="Port:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.web_port_var = tk.StringVar(value=str(settings['port']))
        ttk.Entry(settings_frame, textvariable=self.web_port_var, width=8).grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Label(settings_frame, text="Access:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.web_host_var = tk.StringVar(value=settings['host'])
        access = ttk.Frame(settings_frame)
        access.grid(row=1, column=1, sticky=tk.W, padx=5)
        ttk.Radiobutton(access, text="Any location (0.0.0.0)", value="0.0.0.0", variable=self.web_host_var).pack(side=tk.LEFT)
        ttk.Radiobutton(access, text="This PC only", value="127.0.0.1", variable=self.web_host_var).pack(side=tk.LEFT, padx=10)

        ttk.Label(settings_frame, text="New password:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.web_password_var = tk.StringVar()
        ttk.Entry(settings_frame, textvariable=self.web_password_var, width=30, show="*").grid(row=2, column=1, sticky=tk.W, padx=5)
        self.web_password_label = ttk.Label(
            settings_frame, text="Password: set" if settings['password_hash'] else "Password: not set (required)",
            foreground="green" if settings['password_hash'] else "red")
        self.web_password_label.grid(row=3, column=1, sticky=tk.W, padx=5)

        ttk.Button(settings_frame, text="Save Web Settings", command=self.save_web_settings_clicked).grid(
            row=4, column=0, columnspan=2, sticky=tk.W, pady=10)

        notes = ttk.LabelFrame(parent, text="Notes", padding="10")
        notes.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(notes, justify=tk.LEFT, wraplength=720, text=(
            "• Shows every video in the downloads folder: player, screenshots, actors / series / source, video info.\n"
            "• Info and screenshots are stored next to each video as hidden files (.<name>.meta.json, .<name>.shots).\n"
            "• Needs ffmpeg / ffprobe in PATH (or FFMPEG_PATH). Videos the browser can't play are transcoded live.\n"
            "• From outside your network: forward the port on your router, or better use an HTTPS tunnel "
            "(e.g. Cloudflare Tunnel / Tailscale), so the password isn't sent unencrypted. Use a strong password.\n"
            "• Telegram and system settings stay in this Windows app.")).pack(anchor=tk.W)
        self.web_urls_label = ttk.Label(notes, text="", foreground="blue")
        self.web_urls_label.pack(anchor=tk.W, pady=(8, 0))

    def _web_urls(self):
        port = self.web_port_var.get().strip() or '8765'
        urls = [f"http://localhost:{port}"]
        if self.web_host_var.get() == '0.0.0.0':
            try:
                import socket
                for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                    ip = info[4][0]
                    if not ip.startswith('127.') and f"http://{ip}:{port}" not in urls:
                        urls.append(f"http://{ip}:{port}")
            except Exception:
                pass
        return urls

    def save_web_settings(self):
        """Persist port / access / start-on-launch to .env (returns False if invalid)"""
        port = self.web_port_var.get().strip()
        if not port.isdigit() or not 1 <= int(port) <= 65535:
            messagebox.showerror("Error", "Port must be a number between 1 and 65535")
            return False
        set_key('.env', 'WEB_PORT', port)
        set_key('.env', 'WEB_HOST', self.web_host_var.get())
        set_key('.env', 'WEB_ENABLED', '1' if self.web_enabled_var.get() else '0')
        os.environ.update({'WEB_PORT': port, 'WEB_HOST': self.web_host_var.get(),
                           'WEB_ENABLED': '1' if self.web_enabled_var.get() else '0'})
        return True

    def save_web_settings_clicked(self):
        if not self.save_web_settings():
            return
        password = self.web_password_var.get()
        if password:
            if len(password) < 8:
                messagebox.showerror("Error", "Use a password of at least 8 characters (the library can be reached from the internet)")
                return
            from library.auth import hash_password, new_secret
            password_hash = hash_password(password)
            set_key('.env', 'WEB_PASSWORD_HASH', password_hash)
            os.environ['WEB_PASSWORD_HASH'] = password_hash
            if not os.getenv('WEB_SECRET'):
                secret = new_secret()
                set_key('.env', 'WEB_SECRET', secret)
                os.environ['WEB_SECRET'] = secret
            self.web_password_var.set('')
            self.web_password_label.config(text="Password: set", foreground="green")
            logging.info("Web library password updated (all web sessions logged out)")
        if self.web_server:
            self.stop_web()
            self.start_web()
        messagebox.showinfo("Success", "Web settings saved" + (" and the server restarted" if self.web_server else ""))

    def auto_start_web(self):
        settings = get_web_settings()
        if settings['enabled'] and settings['password_hash']:
            self.start_web(quiet=True)

    def start_web(self, quiet=False):
        if self.web_server:
            return
        settings = get_web_settings()
        if not settings['password_hash']:
            if not quiet:
                messagebox.showerror("Error", "Set a password for the web library first")
            return
        if not settings['secret']:
            from library.auth import new_secret
            settings['secret'] = new_secret()
            set_key('.env', 'WEB_SECRET', settings['secret'])
            os.environ['WEB_SECRET'] = settings['secret']
        try:
            from library.server import LibraryServer
            server = LibraryServer(
                lambda: os.getenv('DOWNLOADS_PATH') or bot_config.DOWNLOADS_DIR,
                settings['password_hash'], settings['secret'], port=settings['port'], host=settings['host'])
            server.start_in_thread()
        except Exception as e:
            logging.error(f"Web library failed to start: {e}")
            if not quiet:
                messagebox.showerror("Error", f"Failed to start web library: {e}")
            return
        self.web_server = server
        self.web_status_label.config(text=f"Running on port {settings['port']}", foreground="green")
        self.web_start_button.config(state=tk.DISABLED)
        self.web_stop_button.config(state=tk.NORMAL)
        self.web_urls_label.config(text="Open: " + "   ".join(self._web_urls()))

    def stop_web(self):
        if self.web_server:
            self.web_server.stop_thread()
            self.web_server = None
        self.web_status_label.config(text="Stopped", foreground="red")
        self.web_start_button.config(state=tk.NORMAL)
        self.web_stop_button.config(state=tk.DISABLED)
        self.web_urls_label.config(text="")

    def open_web(self):
        import webbrowser
        webbrowser.open(self._web_urls()[0])

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
        # ttk.Button(stats_frame, text="Refresh Statistics", command=self.refresh_statistics).pack(side=tk.LEFT, pady=5)
        
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
        self.startup_scan_var.set(os.getenv('STARTUP_SCAN_COUNT', '30'))

    def _set_chromium_status(self, status, busy=False):
        """Update the Chromium status label and buttons (call on the Tk thread)."""
        self.chromium_status_label.config(text=f"Chromium status: {status}")
        state = tk.DISABLED if busy else tk.NORMAL
        self.chromium_check_button.config(state=state)
        self.chromium_install_button.config(state=state)

    def check_chromium_status(self):
        """Check in the background whether Chromium can be launched"""
        from .chromium_helper import check_chromium
        self._set_chromium_status("Checking...", busy=True)

        def work():
            _, status = check_chromium()
            self.root.after(0, lambda: self._set_chromium_status(status))

        threading.Thread(target=work, daemon=True).start()

    def install_chromium(self):
        """Download Chromium in the background, then re-check"""
        from .chromium_helper import install_chromium, check_chromium
        self._set_chromium_status("Installing... (this may take a few minutes)", busy=True)

        def work():
            ok, message = install_chromium(
                lambda line: self.root.after(
                    0, lambda l=line: self._set_chromium_status(f"Installing... {l[:60]}", busy=True)
                )
            )
            if ok:
                _, status = check_chromium()
            else:
                status = message
                logging.error(f"Chromium install failed: {message}")
            self.root.after(0, lambda: self._set_chromium_status(status))

        threading.Thread(target=work, daemon=True).start()

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

            scan_count = self.startup_scan_var.get().strip() or '30'
            if not scan_count.isdigit():
                messagebox.showerror("Error", "Startup scan must be a whole number (0 = off)")
                return
            set_key(env_file, 'STARTUP_SCAN_COUNT', str(int(scan_count)))

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
            if self.bot_running:
                messagebox.showwarning("Warning", "Bot is already running!")
                return

            # Reload .env so credentials saved since launch are used
            load_dotenv(override=True)
            importlib.reload(bot_config)
            validate_config()

            # Start bot in separate thread
            self.bot_thread = threading.Thread(target=self.run_bot, daemon=True)
            self.bot_thread.start()

            # Update UI
            self.bot_running = True
            self.status_label.config(text="Running", foreground="green")
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.restart_button.config(state=tk.NORMAL)

            logging.info("Bot started successfully")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to start bot: {str(e)}")
            logging.error(f"Failed to start bot: {e}")

    def _cancel_bot(self, join_timeout=20):
        """Cancel the running bot task and wait for its cleanup to finish (blocking)"""
        loop, task, thread = self.bot_loop, self.bot_task, self.bot_thread
        if loop is not None and task is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass  # loop already closed
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(join_timeout)

    def stop_bot(self, on_stopped=None):
        """Stop the Telegram bot; on_stopped is called on the Tk thread once it has fully stopped"""
        if not self.bot_running:
            messagebox.showwarning("Warning", "Bot is not running!")
            return

        self.bot_running = False
        self.status_label.config(text="Stopping...", foreground="orange")
        for button in (self.start_button, self.stop_button, self.restart_button):
            button.config(state=tk.DISABLED)

        def work():
            self._cancel_bot()

            def done():
                self.status_label.config(text="Stopped", foreground="red")
                self.start_button.config(state=tk.NORMAL)
                self.restart_button.config(state=tk.NORMAL)
                logging.info("Bot stopped")
                if on_stopped:
                    on_stopped()

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def restart_bot(self):
        """Stop the bot (if running) and start it again with the current configuration"""
        if self.bot_running:
            self.stop_bot(on_stopped=self.start_bot)
        else:
            self.start_bot()

    def run_bot(self):
        """Run the bot in a separate thread on its own cancellable event loop"""
        loop = asyncio.new_event_loop()
        self.bot_loop = loop
        try:
            asyncio.set_event_loop(loop)
            bot = TelegramMediaBot(
                bot_config.API_ID, bot_config.API_HASH, bot_config.PHONE_NUMBER, bot_config.BOT_TOKEN
            )
            self.bot_task = loop.create_task(bot.run())
            loop.run_until_complete(self.bot_task)
        except asyncio.CancelledError:
            pass  # stopped from the GUI
        except Exception as e:
            logging.error(f"Bot error: {e}")
            if self.bot_running:
                self.root.after(0, self.stop_bot)
        finally:
            self.bot_task = None
            loop.close()

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
            
    def refresh_database(self):
        self.refresh_statistics()
        self.refresh_downloads()
        time.sleep(1)
        self.refresh_database()

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
            icon_image = Image.open("assets/icon.ico")
            
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
                self.bot_running = False
                self._cancel_bot(join_timeout=5)

            if self.web_server:
                self.web_server.stop_thread(timeout=5)
                self.web_server = None
            
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
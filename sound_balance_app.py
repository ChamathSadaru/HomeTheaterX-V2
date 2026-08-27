import os
import sys
import time
import threading
import tkinter as tk
# pyrefly: ignore [missing-import]
import customtkinter as ctk
from PIL import Image, ImageDraw
from audio_backend import AudioBackend

class SoundBalanceApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Define Premium Samsung Gold/Nature Palette
        self.COLOR_GOLD = "#D4AF37"    # Rich Gold for Master / Highlights
        self.COLOR_MOSS = "#8FA382"    # Moss Green for Front Stage Speakers
        self.COLOR_SAND = "#C5A880"    # Sand Gold for Rear Stage Speakers
        self.COLOR_RED = "#FF5E5B"     # Warm Red/Coral for Subwoofer
        self.COLOR_BG_MAIN = "#111418" # Deep Charcoal Canvas
        self.COLOR_BG_CARD = "#1C2025" # Slate Card Backgrounds
        self.COLOR_BORDER = "#2C3138"  # Subtle Border Divider

        # Initialize separated Audio Backend
        self.backend = AudioBackend()

        # Configure Main window (hidden during splash screen)
        self.title("Samsung HT-F4B3 Audioscape Controller")
        self.center_window(950, 700)
        self.resizable(False, False)

        # Set theme and styling
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # Hide main window initially
        self.withdraw()

        # UI state helpers
        self.channel_count = 0
        self.is_updating_ui = False  # Flag to prevent feedback loops

        # System tray references
        self.tray_icon = None
        self.tray_thread = None

        # Create GUI Components
        self.create_widgets()

        # Initial load of audio devices
        self.refresh_devices()

        # Start background polling to sync with external changes
        self.poll_volume_changes()

        # Configure system tray
        self.setup_system_tray()
        self.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)

        # Show borderless splash screen
        self.show_splash()

    def center_window(self, width, height):
        """Centers the window on the active screen."""
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def show_splash(self):
        """Displays a borderless splash screen centered on screen for 3 seconds."""
        self.splash = ctk.CTkToplevel(self)
        self.splash.overrideredirect(True)
        
        # Dimensions of splash image (matching 16:9 ratio of uploaded graphic)
        width = 640
        height = 360
        
        # Center splash screen
        screen_width = self.splash.winfo_screenwidth()
        screen_height = self.splash.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.splash.geometry(f"{width}x{height}+{x}+{y}")
        
        # Force splash window on top
        self.splash.attributes("-topmost", True)
        
        try:
            from PIL import ImageTk
            script_dir = os.path.dirname(os.path.abspath(__file__))
            image_path = os.path.join(script_dir, "samsung_splash.jpg")
            
            if os.path.exists(image_path):
                img = Image.open(image_path)
                img = img.resize((width, height), Image.Resampling.LANCZOS)
                self.splash_img = ImageTk.PhotoImage(img)
                
                # Image Label
                img_label = tk.Label(self.splash, image=self.splash_img, borderwidth=0, highlightthickness=0)
                img_label.pack(fill="both", expand=True)
                
                # Overlay loading text
                loading_lbl = tk.Label(
                    self.splash, 
                    text="SAMSUNG | Integrated Audioscape Calibration Engine...", 
                    font=("Segoe UI", 11, "bold"),
                    bg="#0E1114",
                    fg=self.COLOR_SAND,
                    bd=0
                )
                loading_lbl.place(relx=0.5, rely=0.9, anchor="center")
            else:
                self.create_splash_fallback(width, height)
        except Exception as e:
            print(f"Error loading splash image: {e}")
            self.create_splash_fallback(width, height)
            
        # Close splash and show main window after 3000ms
        self.after(3000, self.close_splash)

    def create_splash_fallback(self, width, height):
        """Displays a clean themed screen if splash image fails to load."""
        self.splash.configure(fg_color=self.COLOR_BG_MAIN)
        lbl = ctk.CTkLabel(
            self.splash, 
            text="SAMSUNG\n\nINTEGRATED AUDIOSCAPE\nA NATURE'S SYMPHONY\n\n[ HT-F4B3 ]", 
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=self.COLOR_GOLD
        )
        lbl.pack(expand=True)

    def close_splash(self):
        """Closes the splash window and reveals the main dashboard."""
        if hasattr(self, 'splash') and self.splash:
            self.splash.destroy()
        self.deiconify()

    def generate_tray_icon_image(self):
        """Generates a custom gold-themed speaker icon in-memory for the system tray."""
        try:
            img = Image.new('RGBA', (64, 64), color=(0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            # Gold circle background
            draw.ellipse([6, 6, 58, 58], fill=(212, 175, 55, 255), outline=(255, 255, 255, 255), width=2)
            # Speaker shape
            draw.polygon([(18, 24), (26, 24), (38, 14), (38, 50), (26, 40), (18, 40)], fill=(17, 20, 24, 255))
            # Sound waves
            draw.arc([22, 14, 48, 48], start=315, end=45, fill=(255, 255, 255, 255), width=3)
            return img
        except Exception as e:
            print(f"Error generating tray icon image: {e}")
            return Image.new('RGB', (64, 64), color=(212, 175, 55))

    def setup_system_tray(self):
        """Initializes and runs the Windows System Tray icon thread."""
        try:
            import pystray
            icon_img = self.generate_tray_icon_image()
            
            menu = pystray.Menu(
                pystray.MenuItem("Open Dashboard", self.restore_from_tray, default=True),
                pystray.MenuItem("Mute / Unmute", lambda: self.toggle_mute()),
                pystray.MenuItem("Reset Balance", lambda: self.reset_balance()),
                pystray.MenuItem("Exit", self.quit_application)
            )
            
            self.tray_icon = pystray.Icon(
                "HT-F4B3 Controller",
                icon_img,
                "Samsung HT-F4B3 Audioscape Controller",
                menu
            )
            
            self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
            self.tray_thread.start()
        except Exception as e:
            print(f"Error setting up system tray: {e}")

    def minimize_to_tray(self):
        """Hides the UI window, leaving the app running in the system tray."""
        self.withdraw()

    def restore_from_tray(self, icon=None, item=None):
        """Restores the UI window from the system tray."""
        self.deiconify()
        self.show_main_restored()

    def show_main_restored(self):
        self.lift()
        self.focus_force()

    def quit_application(self, icon=None, item=None):
        """Fully stops the system tray icon, closes the window, and exits."""
        if self.tray_icon:
            self.tray_icon.stop()
        self.destroy()
        sys.exit(0)

    def create_widgets(self):
        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)  # Main content area gets maximum space

        # ---------------- Title Header ----------------
        self.title_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.title_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        
        self.title_label = ctk.CTkLabel(
            self.title_frame, 
            text="SAMSUNG | HT-F4B3 Audioscape Controller", 
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=self.COLOR_GOLD
        )
        self.title_label.pack(side="left")

        self.refresh_btn = ctk.CTkButton(
            self.title_frame, 
            text="Refresh Devices", 
            width=120,
            command=self.refresh_devices,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=self.COLOR_GOLD,
            text_color="#111418",
            hover_color=self.COLOR_SAND
        )
        self.refresh_btn.pack(side="right")

        # ---------------- Device Selection ----------------
        self.device_frame = ctk.CTkFrame(self, fg_color=self.COLOR_BG_CARD, border_color=self.COLOR_BORDER, border_width=1)
        self.device_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.device_frame.grid_columnconfigure(1, weight=1)

        self.device_label = ctk.CTkLabel(
            self.device_frame, 
            text="Audio Device:", 
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        )
        self.device_label.grid(row=0, column=0, padx=15, pady=15, sticky="w")

        self.device_dropdown = ctk.CTkOptionMenu(
            self.device_frame, 
            values=[], 
            command=self.on_device_changed,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=self.COLOR_BG_MAIN,
            button_color=self.COLOR_GOLD,
            button_hover_color=self.COLOR_SAND,
            text_color="#ffffff",
            dropdown_hover_color=self.COLOR_GOLD
        )
        self.device_dropdown.grid(row=0, column=1, padx=(0, 15), pady=15, sticky="ew")

        # ---------------- Main Content Frame ----------------
        self.main_content = ctk.CTkFrame(self, fg_color=self.COLOR_BG_MAIN, border_width=1, border_color=self.COLOR_BORDER)
        self.main_content.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")

        # ---------------- Footer Control Buttons ----------------
        self.footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.footer_frame.grid(row=3, column=0, padx=20, pady=(10, 20), sticky="ew")

        self.mute_btn = ctk.CTkButton(
            self.footer_frame, 
            text="Mute", 
            fg_color="#D90429", 
            hover_color="#EF233C",
            command=self.toggle_mute,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            width=120
        )
        self.mute_btn.pack(side="left", padx=(0, 10))

        self.reset_balance_btn = ctk.CTkButton(
            self.footer_frame, 
            text="Reset Balance (All 100%)", 
            fg_color="#4A4E69", 
            hover_color="#22223B",
            command=self.reset_balance,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        )
        self.reset_balance_btn.pack(side="left")

        self.status_lbl = ctk.CTkLabel(
            self.footer_frame,
            text="SAMSUNG | Detecting System configuration...",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#888F96"
        )
        self.status_lbl.pack(side="right", padx=10)

        # Local Shortcuts
        self.bind("<Control-m>", lambda e: self.toggle_mute())
        self.bind("<Control-r>", lambda e: self.reset_balance())
        self.bind("<Escape>", lambda e: self.minimize_to_tray())

        # Dynamic Sliders references
        self.channel_sliders = []
        self.channel_labels = []
        self.channel_val_labels = []

    def refresh_devices(self):
        """Loads and lists active output audio devices in the dropdown."""
        try:
            device_names = self.backend.refresh_devices()
            default_name = self.backend.get_default_device_name()

            if device_names:
                default_index = 0
                if default_name in device_names:
                    default_index = device_names.index(default_name)

                self.device_dropdown.configure(values=device_names)
                self.device_dropdown.set(device_names[default_index])
                self.on_device_changed(device_names[default_index])
            else:
                self.device_dropdown.configure(values=["No Active Devices Found"])
                self.device_dropdown.set("No Active Devices Found")
                self.clear_main_content()
        except Exception as e:
            print(f"Error refreshing devices: {e}")

    def on_device_changed(self, device_name):
        """Called when a different audio device is selected in the dropdown."""
        try:
            if self.backend.activate_device(device_name):
                self.channel_count = self.backend.channel_count
                self.build_channel_sliders()
                self.update_gui_from_hardware()
            else:
                self.clear_main_content()
        except Exception as e:
            print(f"Error changing device to {device_name}: {e}")
            self.clear_main_content()

    def clear_main_content(self):
        """Clears all widgets inside the main content frame."""
        for widget in self.main_content.winfo_children():
            widget.destroy()
        self.channel_sliders.clear()
        self.channel_labels.clear()
        self.channel_val_labels.clear()

    def get_channel_label(self, idx, count):
        """Returns standard speaker channel names based on layout and index."""
        if count == 6:
            mapping = {
                0: "Left (L)",
                1: "Right (R)",
                2: "Center (C)",
                3: "Subwoofer (Sub)",
                4: "Rear Left (RL)",
                5: "Rear Right (RR)"
            }
            return mapping.get(idx, f"Channel {idx+1}")
        
        if count == 2:
            mapping = {
                0: "Left (L)",
                1: "Right (R)"
            }
            return mapping.get(idx, f"Channel {idx+1}")

        return f"Channel {idx+1}"

    def build_channel_sliders(self):
        """Dynamically creates sliders based on channel count."""
        if self.channel_count == 6:
            self.build_51_layout()
            self.status_lbl.configure(text="System: Samsung 5.1 Surround Sound")
        elif self.channel_count == 2:
            self.build_stereo_layout()
            self.status_lbl.configure(text="System: Stereo (2.0)")
        else:
            self.build_fallback_layout()
            self.status_lbl.configure(text=f"System: Multi-Channel ({self.channel_count} ch)")

    def create_speaker_module(self, parent, channel_idx, name, color="#D4AF37", locked=False):
        """Helper to create a unified speaker control frame with vertical slider & Test button."""
        frame = ctk.CTkFrame(parent, fg_color=self.COLOR_BG_CARD, border_color=self.COLOR_BORDER, border_width=1)
        frame.grid_columnconfigure(0, weight=1)
        
        # Label
        lbl = ctk.CTkLabel(
            frame, 
            text=name, 
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=color
        )
        lbl.pack(pady=(12, 4))
        self.channel_labels.append(lbl)

        # 🔊 Test Button
        test_btn = ctk.CTkButton(
            frame,
            text="🔊 Test",
            width=60,
            height=22,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color="transparent",
            border_color=color,
            border_width=1,
            text_color=color,
            hover_color=color,
            command=lambda idx=channel_idx: self.play_channel_test(idx)
        )
        test_btn.pack(pady=4)
        
        # Slider
        slider = ctk.CTkSlider(
            frame,
            from_=0,
            to=100,
            orientation="vertical",
            number_of_steps=100,
            command=lambda val, idx=channel_idx: self.on_channel_slider_changed(idx, val),
            progress_color=color,
            button_color=color,
            button_hover_color=self.COLOR_GOLD if color != self.COLOR_GOLD else self.COLOR_SAND
        )
        
        if locked:
            slider.set(100)
            slider.configure(state="disabled")
            
        slider.pack(pady=6, fill="y", expand=True)
        # Grow the list if needed (fallback layout uses append, not pre-sized None lists)
        while len(self.channel_sliders) <= channel_idx:
            self.channel_sliders.append(None)
        self.channel_sliders[channel_idx] = slider
        
        # Value Label
        val_text = "100% [LOCKED]" if locked else "100%"
        val_lbl = ctk.CTkLabel(
            frame,
            text=val_text,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
        )
        val_lbl.pack(pady=(6, 4))
        # Grow the list if needed (fallback layout uses append, not pre-sized None lists)
        while len(self.channel_val_labels) <= channel_idx:
            self.channel_val_labels.append(None)
        self.channel_val_labels[channel_idx] = val_lbl
        
        # Add remote control adjustment notice
        if locked:
            notice_lbl = ctk.CTkLabel(
                frame,
                text="Use HT remote\nto adjust level",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color="#888F96"
            )
            notice_lbl.pack(pady=(0, 8))
        else:
            empty_lbl = ctk.CTkLabel(
                frame,
                text="",
                font=ctk.CTkFont(size=10)
            )
            empty_lbl.pack(pady=(0, 8))
        
        return frame

    def create_master_module(self, parent):
        """Helper to create the master control module."""
        frame = ctk.CTkFrame(parent, fg_color=self.COLOR_BG_CARD, border_color=self.COLOR_BORDER, border_width=1)
        frame.grid_columnconfigure(0, weight=1)
        
        lbl = ctk.CTkLabel(
            frame, 
            text="MASTER", 
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=self.COLOR_GOLD
        )
        lbl.pack(pady=(12, 6))
        
        self.master_slider = ctk.CTkSlider(
            frame,
            from_=0,
            to=100,
            orientation="vertical",
            number_of_steps=100,
            command=self.on_master_slider_changed,
            progress_color=self.COLOR_GOLD,
            button_color=self.COLOR_GOLD,
            button_hover_color=self.COLOR_SAND
        )
        self.master_slider.pack(pady=6, fill="y", expand=True)
        
        self.master_value_label = ctk.CTkLabel(
            frame,
            text="100%",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
        )
        self.master_value_label.pack(pady=(6, 12))
        
        return frame

    def create_profiles_module(self, parent):
        """Creates the sound profile selection panel with standard acoustic modes."""
        frame = ctk.CTkFrame(parent, fg_color=self.COLOR_BG_CARD, border_color=self.COLOR_BORDER, border_width=1)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_rowconfigure(0, weight=1) # Title
        frame.grid_rowconfigure(1, weight=2) # Buttons Row 1
        frame.grid_rowconfigure(2, weight=2) # Buttons Row 2
        
        lbl = ctk.CTkLabel(
            frame, 
            text="SOUND PROFILES", 
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=self.COLOR_GOLD
        )
        lbl.grid(row=0, column=0, columnspan=2, pady=(10, 5))
        
        # Profile buttons
        btn_movie = ctk.CTkButton(
            frame,
            text="🎬 Movie",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="transparent",
            border_color=self.COLOR_GOLD,
            border_width=1,
            text_color=self.COLOR_GOLD,
            hover_color=self.COLOR_GOLD,
            command=lambda: self.apply_profile("Movie")
        )
        btn_movie.grid(row=1, column=0, padx=8, pady=6, sticky="nsew")
        
        btn_music = ctk.CTkButton(
            frame,
            text="🎵 Music",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="transparent",
            border_color=self.COLOR_MOSS,
            border_width=1,
            text_color=self.COLOR_MOSS,
            hover_color=self.COLOR_MOSS,
            command=lambda: self.apply_profile("Music")
        )
        btn_music.grid(row=1, column=1, padx=8, pady=6, sticky="nsew")
        
        btn_game = ctk.CTkButton(
            frame,
            text="🎮 Game",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="transparent",
            border_color=self.COLOR_SAND,
            border_width=1,
            text_color=self.COLOR_SAND,
            hover_color=self.COLOR_SAND,
            command=lambda: self.apply_profile("Game")
        )
        btn_game.grid(row=2, column=0, padx=8, pady=(4, 12), sticky="nsew")
        
        btn_night = ctk.CTkButton(
            frame,
            text="🌙 Night",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="transparent",
            border_color=self.COLOR_RED,
            border_width=1,
            text_color=self.COLOR_RED,
            hover_color=self.COLOR_RED,
            command=lambda: self.apply_profile("Night")
        )
        btn_night.grid(row=2, column=1, padx=8, pady=(4, 12), sticky="nsew")
        
        return frame

    def create_right_sidebar(self, parent):
        """Creates the unified master sidebar hosting Master Volume & EQ Presets."""
        sidebar_frame = ctk.CTkFrame(parent, fg_color="transparent")
        sidebar_frame.grid_columnconfigure(0, weight=1)
        sidebar_frame.grid_rowconfigure(0, weight=3) # Master Volume gets more height
        sidebar_frame.grid_rowconfigure(1, weight=2) # Presets get less height
        
        master = self.create_master_module(sidebar_frame)
        master.grid(row=0, column=0, padx=5, pady=(0, 10), sticky="nsew")
        
        profiles = self.create_profiles_module(sidebar_frame)
        profiles.grid(row=1, column=0, padx=5, pady=0, sticky="nsew")
        
        return sidebar_frame

    def build_51_layout(self):
        """Builds a beautiful 5.1 surround sound physical placement mixer layout (No Tabs)."""
        self.clear_main_content()
        
        # Configure columns: Column 0 gets Speaker Grid, Column 1 gets Sidebar
        self.main_content.grid_columnconfigure(0, weight=4)
        self.main_content.grid_columnconfigure(1, weight=1)
        self.main_content.grid_rowconfigure(0, weight=1)
        
        # Left Pane: Mixer Grid Container
        mixer_pane = ctk.CTkFrame(self.main_content, fg_color="transparent")
        mixer_pane.grid(row=0, column=0, padx=15, pady=10, sticky="nsew")
        
        # 2 rows, 3 columns inside Left Mixer Pane
        mixer_pane.grid_columnconfigure(0, weight=1, uniform="cols")
        mixer_pane.grid_columnconfigure(1, weight=1, uniform="cols")
        mixer_pane.grid_columnconfigure(2, weight=1, uniform="cols")
        mixer_pane.grid_rowconfigure(0, weight=1, uniform="rows")
        mixer_pane.grid_rowconfigure(1, weight=1, uniform="rows")
        
        self.channel_sliders = [None] * self.channel_count
        self.channel_labels = [None] * self.channel_count
        self.channel_val_labels = [None] * self.channel_count
        
        # Row 0: FL, C, FR
        self.create_speaker_module(mixer_pane, 0, "Front Left (FL)", self.COLOR_MOSS).grid(row=0, column=0, padx=10, pady=5, sticky="nsew")
        self.create_speaker_module(mixer_pane, 2, "Center (C)", self.COLOR_MOSS).grid(row=0, column=1, padx=10, pady=5, sticky="nsew")
        self.create_speaker_module(mixer_pane, 1, "Front Right (FR)", self.COLOR_MOSS).grid(row=0, column=2, padx=10, pady=5, sticky="nsew")
        
        # Row 1: Sub, RL, RR
        self.create_speaker_module(mixer_pane, 3, "Subwoofer (Sub)", self.COLOR_RED, locked=True).grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        self.create_speaker_module(mixer_pane, 4, "Rear Left (RL)", self.COLOR_SAND).grid(row=1, column=1, padx=10, pady=5, sticky="nsew")
        self.create_speaker_module(mixer_pane, 5, "Rear Right (RR)", self.COLOR_SAND).grid(row=1, column=2, padx=10, pady=5, sticky="nsew")
        
        # Right Pane: Master Sidebar module in Column 1
        self.create_right_sidebar(self.main_content).grid(row=0, column=1, padx=15, pady=15, sticky="nsew")

    def build_stereo_layout(self):
        """Builds a beautiful stereo layout (No Tabs)."""
        self.clear_main_content()
        
        # Configure columns: Column 0 gets Stereo Mixer, Column 1 gets Sidebar
        self.main_content.grid_columnconfigure(0, weight=4)
        self.main_content.grid_columnconfigure(1, weight=1)
        self.main_content.grid_rowconfigure(0, weight=1)
        
        # Left Pane: Stereo Mixer Frame
        mixer_pane = ctk.CTkFrame(self.main_content, fg_color="transparent")
        mixer_pane.grid(row=0, column=0, padx=15, pady=10, sticky="nsew")
        
        mixer_pane.grid_columnconfigure(0, weight=1, uniform="cols")
        mixer_pane.grid_columnconfigure(1, weight=1, uniform="cols")
        mixer_pane.grid_rowconfigure(0, weight=1)
        
        self.channel_sliders = [None] * self.channel_count
        self.channel_labels = [None] * self.channel_count
        self.channel_val_labels = [None] * self.channel_count
        
        self.create_speaker_module(mixer_pane, 0, "Left Speaker (L)", self.COLOR_MOSS).grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        self.create_speaker_module(mixer_pane, 1, "Right Speaker (R)", self.COLOR_MOSS).grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        
        # Right Pane: Master Sidebar module in Column 1
        self.create_right_sidebar(self.main_content).grid(row=0, column=1, padx=15, pady=15, sticky="nsew")

    def build_fallback_layout(self):
        """Fallback scrollable layout for multi-channel systems other than 5.1/Stereo (No Tabs)."""
        self.clear_main_content()
        
        # Configure columns: Column 0 gets Scroll Mixer, Column 1 gets Sidebar
        self.main_content.grid_columnconfigure(0, weight=4)
        self.main_content.grid_columnconfigure(1, weight=1)
        self.main_content.grid_rowconfigure(0, weight=1)
        
        # Left Pane: Scroll Frame
        scroll_frame = ctk.CTkScrollableFrame(self.main_content, fg_color="transparent")
        scroll_frame.grid(row=0, column=0, padx=15, pady=10, sticky="nsew")
        
        # Channels list
        self.channel_sliders = []
        self.channel_labels = []
        self.channel_val_labels = []
        
        for i in range(self.channel_count):
            label_text = self.get_channel_label(i, self.channel_count)
            
            row_frame = ctk.CTkFrame(scroll_frame, fg_color=self.COLOR_BG_CARD, border_color=self.COLOR_BORDER, border_width=1)
            row_frame.pack(fill="x", pady=5, padx=10)
            
            lbl = ctk.CTkLabel(
                row_frame, 
                text=label_text, 
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                width=150,
                anchor="w"
            )
            lbl.pack(side="left", padx=15, pady=10)
            self.channel_labels.append(lbl)
            
            slider = ctk.CTkSlider(
                row_frame,
                from_=0,
                to=100,
                number_of_steps=100,
                command=lambda val, index=i: self.on_channel_slider_changed(index, val),
                progress_color=self.COLOR_GOLD,
                button_color=self.COLOR_GOLD,
                button_hover_color=self.COLOR_SAND
            )
            slider.pack(side="left", fill="x", expand=True, padx=10, pady=10)
            self.channel_sliders.append(slider)
            
            val_lbl = ctk.CTkLabel(
                row_frame,
                text="100%",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                width=50
            )
            val_lbl.pack(side="right", padx=15, pady=10)
            self.channel_val_labels.append(val_lbl)
            
        # Right Pane: Master Sidebar module in Column 1
        self.create_right_sidebar(self.main_content).grid(row=0, column=1, padx=15, pady=15, sticky="nsew")

    def on_master_slider_changed(self, val):
        """Event when Master Volume Slider is adjusted."""
        if self.is_updating_ui:
            return
        val_int = int(val)  # CTkSlider emits float
        self.backend.set_master_volume(val_int)
        if self.master_value_label:
            self.master_value_label.configure(text=f"{val_int}%")

    def on_channel_slider_changed(self, channel_idx, val):
        """Event when a Channel Slider is adjusted."""
        if self.is_updating_ui:
            return
        val_int = int(val)  # CTkSlider emits float; backend expects int percentage
        self.backend.set_channel_volume(channel_idx, val_int)
        if self.channel_val_labels[channel_idx]:
            self.channel_val_labels[channel_idx].configure(text=f"{val_int}%")

    def play_channel_test(self, channel_idx):
        """Requests backend to play a short test tone on specific channel."""
        self.backend.play_channel_test(channel_idx)

    def apply_profile(self, profile):
        """Applies acoustic preset profiles (Movie, Music, Game, Night) using backend configuration."""
        try:
            self.is_updating_ui = True
            
            profile_data = self.backend.get_profile_values(profile)
            channels = profile_data["channels"]
            master_val = profile_data["master"]
            
            # Apply Master Volume if preset specifies it
            if master_val is not None:
                self.backend.set_master_volume(master_val)
                if hasattr(self, 'master_slider') and self.master_slider:
                    self.master_slider.set(master_val)
                if hasattr(self, 'master_value_label') and self.master_value_label:
                    self.master_value_label.configure(text=f"{master_val}%")
            
            # Apply individual channel volumes
            for idx, val in channels.items():
                if idx < self.channel_count:
                    self.backend.set_channel_volume(idx, val)
                    if self.channel_sliders[idx]:
                        self.channel_sliders[idx].set(val)
                    if self.channel_val_labels[idx]:
                        self.channel_val_labels[idx].configure(text=f"{val}%")
            
            self.is_updating_ui = False
        except Exception as e:
            print(f"Error applying profile {profile}: {e}")
            self.is_updating_ui = False

    def toggle_mute(self):
        """Toggles mute state using backend."""
        new_mute = self.backend.toggle_mute()
        self.update_mute_button_state(new_mute)

    def update_mute_button_state(self, is_muted):
        """Updates Mute button appearance based on current state."""
        if is_muted:
            self.mute_btn.configure(text="Unmute", fg_color="#38B000", hover_color="#70E000")
        else:
            self.mute_btn.configure(text="Mute", fg_color="#D90429", hover_color="#EF233C")

    def reset_balance(self):
        """Resets all channel volumes to 100% using backend."""
        try:
            self.is_updating_ui = True
            self.backend.reset_balance()
            for i in range(self.channel_count):
                if i < len(self.channel_sliders) and self.channel_sliders[i]:
                    self.channel_sliders[i].set(100)
                if i < len(self.channel_val_labels) and self.channel_val_labels[i]:
                    if self.channel_count == 6 and i == 3:
                        self.channel_val_labels[i].configure(text="100% [LOCKED]")
                    else:
                        self.channel_val_labels[i].configure(text="100%")
            self.is_updating_ui = False
        except Exception as e:
            print(f"Error resetting balance: {e}")
            self.is_updating_ui = False

    def update_gui_from_hardware(self):
        """Reads volume states from backend and updates UI elements."""
        if self.is_updating_ui:
            return

        try:
            self.is_updating_ui = True

            # 1. Master Volume & Mute State
            master_percent, is_muted = self.backend.get_master_volume()
            if hasattr(self, 'master_slider') and self.master_slider:
                self.master_slider.set(master_percent)
            if hasattr(self, 'master_value_label') and self.master_value_label:
                self.master_value_label.configure(text=f"{master_percent}%")

            self.update_mute_button_state(is_muted)

            # 2. Channel Volumes
            channel_vols = self.backend.get_channel_volumes()
            for i in range(min(self.channel_count, len(self.channel_sliders), len(channel_vols))):
                if self.channel_sliders[i]:
                    self.channel_sliders[i].set(channel_vols[i])
                    if self.channel_val_labels[i]:
                        if self.channel_count == 6 and i == 3:
                            self.channel_val_labels[i].configure(text="100% [LOCKED]")
                        else:
                            self.channel_val_labels[i].configure(text=f"{channel_vols[i]}%")

            self.is_updating_ui = False
        except Exception as e:
            print(f"Error reading hardware state: {e}")
            self.is_updating_ui = False

    def poll_volume_changes(self):
        """Periodically polls the audio system for changes made externally."""
        self.update_gui_from_hardware()
        self.after(1000, self.poll_volume_changes)


if __name__ == "__main__":
    app = SoundBalanceApp()
    app.mainloop()

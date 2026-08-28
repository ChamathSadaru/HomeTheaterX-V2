import os
import sys
import threading
import tkinter as tk
from PIL import Image, ImageTk, ImageDraw
import pystray
import webview

class UIManager:
    def __init__(self, backend, config_manager, startup_manager, notify_fn):
        self.backend = backend
        self.config_manager = config_manager
        self.startup_manager = startup_manager
        self.notify_fn = notify_fn
        
        self.window = None
        self.tray_icon = None
        self.splash_root = None
        self._is_fullscreen = False
        self._orig_w = 1152
        self._orig_h = 870
        self._orig_x = None
        self._orig_y = None

    def generate_tray_icon_image(self, muted=False):
        try:
            img = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            ring_color = (220, 60, 60, 255) if muted else (212, 175, 55, 255)
            draw.ellipse([6, 6, 58, 58], fill=ring_color, outline=(255, 255, 255, 255), width=2)
            draw.polygon([(18, 24), (26, 24), (38, 14), (38, 50), (26, 40), (18, 40)], fill=(17, 20, 24, 255))
            if muted:
                draw.line([(40, 22), (52, 34)], fill=(17, 20, 24, 255), width=3)
                draw.line([(40, 34), (52, 22)], fill=(17, 20, 24, 255), width=3)
            else:
                draw.arc([22, 14, 48, 48], start=315, end=45, fill=(255, 255, 255, 255), width=3)
            return img
        except Exception as e:
            print(f"Error generating tray icon image: {e}")
            return Image.new("RGB", (64, 64), color=(212, 175, 55))

    def refresh_tray_icon(self):
        """Swaps the tray icon glyph so it visibly reflects mute state."""
        if not self.tray_icon:
            return
        try:
            _, muted = self.backend.get_master_volume()
            self.tray_icon.icon = self.generate_tray_icon_image(muted=muted)
        except Exception:
            pass

    def start_tray_icon(self):
        try:
            def on_open_dashboard(icon, item):
                if self.window:
                    threading.Thread(target=lambda: self.window.show(), daemon=True).start()

            def on_toggle_mute(icon, item):
                new_mute = self.backend.toggle_mute()
                self.notify_fn(
                    "System Muted" if new_mute else "System Unmuted",
                    "Hardware master output silenced." if new_mute else "Acoustic channels active again.",
                    dedupe_key="mute_toggle",
                )
                self.refresh_tray_icon()

            def on_reset_balance(icon, item):
                self.backend.reset_balance()
                self.notify_fn("Balance Reset", "All speaker channels reset to 100% gain.", dedupe_key="reset_balance")

            def on_toggle_startup(icon, item):
                new_state = not self.startup_manager.is_startup_enabled()
                if self.startup_manager.set_startup(new_state):
                    self.config_manager.set("launch_on_startup", new_state)
                    self.notify_fn(
                        "Startup Setting Updated",
                        "App will now launch automatically with Windows." if new_state
                        else "App will no longer launch automatically with Windows.",
                        dedupe_key="startup_toggle",
                    )

            def startup_checked(item):
                return self.startup_manager.is_startup_enabled()

            def mute_label(item):
                _, muted = self.backend.get_master_volume()
                return "Unmute" if muted else "Mute"

            def on_exit(icon, item):
                icon.stop()
                if self.window:
                    try:
                        self.window.events.closing -= self.on_window_closing
                    except Exception:
                        pass
                    self.window.destroy()
                os._exit(0)

            icon_img = self.generate_tray_icon_image()
            menu = pystray.Menu(
                pystray.MenuItem("Open Dashboard", on_open_dashboard, default=True),
                pystray.MenuItem(mute_label, on_toggle_mute),
                pystray.MenuItem("Reset Balance", on_reset_balance),
                pystray.MenuItem("Start with Windows", on_toggle_startup, checked=startup_checked),
                pystray.MenuItem("Exit", on_exit)
            )

            self.tray_icon = pystray.Icon(
                "HomeTheaterX",
                icon_img,
                "HomeTheaterX Controller",
                menu
            )
            self.tray_icon.run()
        except Exception as e:
            print(f"Failed to initialize background system tray: {e}")

    def on_window_closing(self):
        if self.window:
            self.window.hide()
            if self.config_manager.get("minimize_to_tray_on_close", True):
                self.notify_fn(
                    "Still Running",
                    "HomeTheaterX is minimized to the system tray.",
                    dedupe_key="minimize_to_tray",
                )
        return False

    def run_splash_screen_thread(self, base_dir):
        try:
            self.splash_root = tk.Tk()
            self.splash_root.overrideredirect(True)
            self.splash_root.attributes("-topmost", True)
            
            img_path = os.path.join(base_dir, "Splash.jpg")
            if os.path.exists(img_path):
                img = Image.open(img_path)
                original_width, original_height = img.size
                target_width = 600
                target_height = int((target_width / original_width) * original_height)
                
                try:
                    resample_filter = Image.Resampling.LANCZOS
                except AttributeError:
                    try:
                        resample_filter = Image.ANTIALIAS
                    except AttributeError:
                        resample_filter = Image.BICUBIC
                
                img = img.resize((target_width, target_height), resample_filter)
                photo = ImageTk.PhotoImage(img)
                
                width, height = target_width, target_height
                screen_width = self.splash_root.winfo_screenwidth()
                screen_height = self.splash_root.winfo_screenheight()
                x = (screen_width - width) // 2
                y = (screen_height - height) // 2
                self.splash_root.geometry(f"{width}x{height}+{x}+{y}")
                
                label = tk.Label(self.splash_root, image=photo, borderwidth=0, highlightthickness=0)
                label.pack()
                label.image = photo
                
                self.splash_root.mainloop()
            else:
                self.splash_root = None
        except Exception as splash_err:
            print(f"Failed to display native splash screen: {splash_err}")
            self.splash_root = None

    def destroy_splash(self):
        if self.splash_root:
            try:
                self.splash_root.after(0, self.splash_root.destroy)
            except Exception:
                pass

    def create_gui_window(self, port):
        win_w = 1152
        win_h = 840
        x = None
        y = None
        try:
            screens = webview.screens
            if screens:
                primary = next((s for s in screens if s.x == 0 and s.y == 0), screens[0])
                if primary.height < 880:
                    win_h = max(600, int(primary.height * 0.92))
                    win_w = min(1152, max(960, int(primary.width * 0.92)))
                x = int(primary.x + (primary.width - win_w) / 2)
                y = int(primary.y + (primary.height - win_h) / 2)
        except Exception as scr_err:
            print(f"Failed to query monitor coordinates: {scr_err}")

        self.window = webview.create_window(
            title="HomeTheaterX",
            url=f"http://localhost:{port}",
            width=win_w,
            height=win_h,
            min_size=(960, 600),
            resizable=True,
            frameless=True,
            easy_drag=False,
            x=x,
            y=y,
            hidden=True,
            background_color='#050508'
        )
        self.backend.window = self.window
        # Capture close requests
        try:
            self.window.events.closing += self.on_window_closing
        except Exception:
            pass
            
        return self.window

    def get_screen_count(self):
        try:
            screens = webview.screens
            return len(screens) if screens else 1
        except Exception:
            return 1

    def move_to_next_screen(self):
        """Moves the window to the center of the next monitor in circular sequence."""
        if not self.window:
            return {"status": "error", "message": "No active window"}

        try:
            screens = webview.screens
            if not screens or len(screens) <= 1:
                return {"status": "error", "message": "Single screen configuration"}

            # Get current window position and size
            win_x = getattr(self.window, "x", 0) or 0
            win_y = getattr(self.window, "y", 0) or 0
            win_w = getattr(self.window, "width", 1152) or 1152
            win_h = getattr(self.window, "height", 870) or 870

            # Determine which screen the window center is currently on
            center_x = win_x + win_w / 2
            center_y = win_y + win_h / 2

            current_screen_idx = 0
            for idx, scr in enumerate(screens):
                if scr.x <= center_x < scr.x + scr.width and scr.y <= center_y < scr.y + scr.height:
                    current_screen_idx = idx
                    break

            next_screen_idx = (current_screen_idx + 1) % len(screens)
            target_screen = screens[next_screen_idx]

            new_x = int(target_screen.x + (target_screen.width - win_w) / 2)
            new_y = int(target_screen.y + (target_screen.height - win_h) / 2)

            self.window.move(new_x, new_y)
            return {
                "status": "success",
                "screen_index": next_screen_idx,
                "total_screens": len(screens)
            }
        except Exception as e:
            print(f"[UIManager] Failed to move window between screens: {e}")
            return {"status": "error", "message": str(e)}

    def toggle_fullscreen(self):
        """Toggles fullscreen / maximize state of the pywebview application window."""
        if not self.window:
            return {"status": "error", "message": "No active window"}

        try:
            if self._is_fullscreen:
                # Restore windowed bounds
                try:
                    self.window.restore()
                except Exception:
                    pass
                try:
                    if hasattr(self.window, "toggle_fullscreen") and getattr(self.window, "fullscreen", False):
                        self.window.toggle_fullscreen()
                except Exception:
                    pass
                try:
                    self.window.resize(self._orig_w, self._orig_h)
                    if self._orig_x is not None and self._orig_y is not None:
                        self.window.move(self._orig_x, self._orig_y)
                except Exception:
                    pass
                self._is_fullscreen = False
            else:
                # Save previous bounds
                self._orig_w = getattr(self.window, "width", 1152) or 1152
                self._orig_h = getattr(self.window, "height", 870) or 870
                self._orig_x = getattr(self.window, "x", 0) or 0
                self._orig_y = getattr(self.window, "y", 0) or 0

                # Maximize / Fullscreen
                try:
                    self.window.maximize()
                except Exception:
                    pass
                try:
                    if hasattr(self.window, "toggle_fullscreen"):
                        self.window.toggle_fullscreen()
                except Exception:
                    pass
                self._is_fullscreen = True

            return {
                "status": "success",
                "fullscreen": self._is_fullscreen
            }
        except Exception as e:
            print(f"[UIManager] Failed to toggle fullscreen: {e}")
            return {"status": "error", "message": str(e)}

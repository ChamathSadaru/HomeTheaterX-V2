import os
import sys
import threading
import time
from http.server import ThreadingHTTPServer

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Chamathz.HomeTheaterX.AudioEngine.2.0")
except Exception:
    pass

from audio_backend import AudioBackend
import config_manager
import notifier
import startup_manager
from services import dolby_service, ui_service, apo_service
from services.api_handler import AudioControlHandler
from services.websocket_service import WebSocketManager

# Initialize shared backend instance
backend = AudioBackend()

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")

# Load initial devices and select default (or last-used) output device
device_names = backend.refresh_devices()
default_name = backend.get_default_device_name()
preferred_name = config_manager.get("last_device") or default_name
if device_names:
    if preferred_name in device_names:
        backend.activate_device(preferred_name)
    elif default_name in device_names:
        backend.activate_device(default_name)
    else:
        backend.activate_device(device_names[0])

# Global configuration
PORT = 5000
server_instance = None
cached_ddl_state = False
ui_manager = None
ws_manager = None


def notify_if_enabled(title, message, dedupe_key=None):
    """Central choke-point for Windows toast notifications."""
    if config_manager.get("notifications_enabled", True):
        notifier.notify(title, message, dedupe_key=dedupe_key)


def update_ddl_callback(state):
    global cached_ddl_state
    cached_ddl_state = state


def set_ddl_state(state):
    global cached_ddl_state
    cached_ddl_state = state


def get_local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def init_server():
    global PORT, server_instance, ws_manager
    
    # Initialize and start WebSocket server on PORT + 10 (e.g. 5010)
    ws_manager = WebSocketManager(backend, config_manager, host="0.0.0.0", port=PORT + 10)
    ws_manager.start()

    # Inject dependencies into the API Handler
    AudioControlHandler.backend = backend
    AudioControlHandler.get_ddl_state = staticmethod(lambda: cached_ddl_state)
    AudioControlHandler.set_ddl_state = staticmethod(set_ddl_state)
    AudioControlHandler.notify_fn = staticmethod(notify_if_enabled)
    AudioControlHandler.ws_manager = ws_manager

    for attempt in range(5):
        try:
            server_instance = ThreadingHTTPServer(("0.0.0.0", PORT), AudioControlHandler)
            local_ip = get_local_ip()
            print(f"Bound HTTP server successfully to port {PORT} (listening on all interfaces)")
            print(f"  [Local Access]   http://localhost:{PORT}")
            print(f"  [Network Access] http://{local_ip}:{PORT}")
            return True
        except OSError:
            print(f"Port {PORT} is busy. Trying next port...")
            PORT += 1
    return False


def main():
    global ui_manager, cached_ddl_state

    # Explicitly set AppUserModelID to make Windows display the custom taskbar icon
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("HomeTheaterX.Controller.1.0")
    except Exception:
        pass

    # Initialize UI Service manager
    ui_manager = ui_service.UIManager(backend, config_manager, startup_manager, notify_if_enabled)
    AudioControlHandler.ui_manager = ui_manager

    # 1. Bind HTTP server in main thread to ensure port is selected before creating webview
    if not init_server():
        print("Error: Could not bind server to any port from 5000 to 5004.")
        sys.exit(1)

    # 2. Run HTTP server thread as a background daemon
    server_thread = threading.Thread(target=server_instance.serve_forever, daemon=True)
    server_thread.start()

    # 3. Run System Tray thread
    tray_thread = threading.Thread(target=ui_manager.start_tray_icon, daemon=True)
    tray_thread.start()

    # 4. Sync "launch on startup" registry state with the saved preference
    if config_manager.get("launch_on_startup", False):
        startup_manager.enable_startup()

    notify_if_enabled(
        "HomeTheaterX",
        "Controller started and running in the system tray.",
        dedupe_key="app_started",
    )

    # 5. Check Dolby state silently first, then show 2-second splash screen and reveal GUI
    window_loaded_event = threading.Event()

    def on_dolby_ready(is_on):
        global cached_ddl_state
        cached_ddl_state = is_on
        print(f"[Startup] Dolby verification complete (DDL: {'ON' if is_on else 'OFF'}). Displaying splash screen...")
        
        # Display splash screen
        splash_thread = threading.Thread(target=ui_manager.run_splash_screen_thread, args=(BASE_DIR,), daemon=True)
        splash_thread.start()

        # Hold splash screen for ~2 seconds for a sleek introduction, then reveal GUI
        def smooth_reveal():
            time.sleep(2.0)
            window_loaded_event.wait(timeout=5.0)
            try:
                if ui_manager.window:
                    ui_manager.window.show()
            except Exception:
                pass
            ui_manager.destroy_splash()

        threading.Thread(target=smooth_reveal, daemon=True).start()

    # Launch background silent Dolby check on currently selected device
    dolby_service.async_check_dolby(on_dolby_ready, target_device_name=backend.current_device_name)

    # 6. Initialize and run PyWebview GUI on the main thread (hidden until splash completes)
    try:
        window = ui_manager.create_gui_window(PORT)

        def on_window_loaded():
            window_loaded_event.set()

        window.events.loaded += on_window_loaded
        
        icon_path = os.path.join(BASE_DIR, "Icon.ico")
        if not os.path.exists(icon_path):
            icon_path = None

        import webview
        webview.start(icon=icon_path)
    except Exception as gui_err:
        print(f"GUI window initialization failed (running in headless mode): {gui_err}")
        print("Falling back to console-only mode. HTTP server remains active.")
        try:
            server_instance.serve_forever()
        except KeyboardInterrupt:
            print("Stopping server...")


if __name__ == "__main__":
    main()

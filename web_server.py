import os
import sys
import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from audio_backend import AudioBackend
import config_manager
import notifier
import startup_manager
import webview

# Initialize shared backend instance
backend = AudioBackend()

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
window = None
tray_icon_ref = None


def notify_if_enabled(title, message, dedupe_key=None):
    """Central choke-point for every native Windows notification the app
    sends, so the user's notification preference (Settings tab) is always
    respected in one place."""
    if config_manager.get("notifications_enabled", True):
        notifier.notify(title, message, dedupe_key=dedupe_key)


async def get_windows_media_status():
    import winrt.windows.media.control as wmc
    import winrt.windows.storage.streams as wss
    import base64
    try:
        manager = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
        session = manager.get_current_session()
        if not session:
            return {"status": "no_session"}
        
        props = await session.try_get_media_properties_async()
        pb = session.get_playback_info()
        timeline = session.get_timeline_properties()
        
        status_val = int(pb.playback_status) if pb else 0
        pos = timeline.position.total_seconds() if timeline else 0.0
        dur = timeline.end_time.total_seconds() if timeline else 0.0
        
        thumbnail_b64 = ""
        if props and props.thumbnail:
            try:
                stream = await props.thumbnail.open_read_async()
                size = stream.size
                if size > 0:
                    reader = wss.DataReader(stream.get_input_stream_at(0))
                    await reader.load_async(size)
                    data_bytes = bytearray(size)
                    reader.read_bytes(data_bytes)
                    thumbnail_b64 = base64.b64encode(data_bytes).decode('utf-8')
            except Exception:
                pass

        return {
            "status": "success",
            "title": props.title if props else "Unknown Title",
            "artist": props.artist if props else "Unknown Artist",
            "playback_status": status_val,
            "position": pos,
            "duration": dur,
            "thumbnail": thumbnail_b64,
            "source": session.source_app_user_model_id
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def control_windows_media(action):
    import winrt.windows.media.control as wmc
    try:
        manager = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
        session = manager.get_current_session()
        if not session:
            return False
        
        if action == "play_pause":
            return await session.try_toggle_play_pause_async()
        elif action == "next":
            return await session.try_next_async()
        elif action == "previous":
            return await session.try_previous_async()
        return False
    except Exception as e:
        print("Error sending media control:", e)
        return False


class AudioControlHandler(BaseHTTPRequestHandler):
    # Quiet logger to keep terminal output clean
    def log_message(self, format, *args):
        pass

    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _resolve_static_path(self, url_path):
        """Resolves a request path to a file strictly inside WEB_DIR,
        preventing directory-traversal (`..`) escapes - the previous
        implementation joined the raw path straight into the filesystem
        path with no containment check."""
        if url_path == "/":
            candidate = os.path.join(WEB_DIR, "index.html")
        elif url_path.lstrip("/") == "samsung_splash.jpg":
            candidate = os.path.join(BASE_DIR, "Splash.jpg")
        else:
            clean_path = url_path.lstrip("/").split("?")[0]
            candidate = os.path.normpath(os.path.join(WEB_DIR, clean_path))

        # Containment check: resolved path must stay within WEB_DIR/BASE_DIR
        allowed_roots = (os.path.realpath(WEB_DIR), os.path.realpath(BASE_DIR))
        real_candidate = os.path.realpath(candidate)
        if not any(real_candidate == root or real_candidate.startswith(root + os.sep) for root in allowed_roots):
            return None
        return candidate

    def do_GET(self):
        try:
            path_only = self.path.split("?")[0]

            if path_only == "/api/status":
                master_vol, muted = backend.get_master_volume()
                channel_vols = backend.get_channel_volumes()
                self._send_json({
                    "status": "success",
                    "active_device": backend.current_device_name,
                    "channel_count": backend.channel_count,
                    "master_volume": master_vol,
                    "muted": muted,
                    "channel_volumes": channel_vols,
                    "solo": backend.get_solo_status(),
                })
                return

            if path_only == "/api/devices":
                devices = backend.refresh_devices()
                self._send_json({
                    "status": "success",
                    "devices": devices,
                    "active_device": backend.current_device_name
                })
                return

            if path_only == "/api/settings":
                self._send_json({
                    "status": "success",
                    "settings": config_manager.get_all(),
                    "startup_enabled": startup_manager.is_startup_enabled(),
                })
                return

            if path_only == "/api/startup/status":
                self._send_json({"status": "success", "enabled": startup_manager.is_startup_enabled()})
                return

            if path_only == "/api/media/status":
                import asyncio
                res = asyncio.run(get_windows_media_status())
                self._send_json(res)
                return

            if path_only == "/api/audio_stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                
                import time
                try:
                    while True:
                        peak = backend.get_audio_peak()
                        data_payload = f"data: {json.dumps({'peak': peak})}\n\n"
                        self.wfile.write(data_payload.encode('utf-8'))
                        self.wfile.flush()
                        time.sleep(0.03)  # ~33 fps
                except Exception:
                    # Client disconnected or connection interrupted
                    pass
                return

            # Static assets
            filepath = self._resolve_static_path(path_only)
            if filepath is None:
                self.send_error(403, "Forbidden")
                return

            if os.path.exists(filepath) and not os.path.isdir(filepath):
                self.send_response(200)
                if filepath.endswith(".html"):
                    self.send_header("Content-Type", "text/html")
                elif filepath.endswith(".css"):
                    self.send_header("Content-Type", "text/css")
                elif filepath.endswith(".js"):
                    self.send_header("Content-Type", "application/javascript")
                elif filepath.endswith(".jpg") or filepath.endswith(".jpeg"):
                    self.send_header("Content-Type", "image/jpeg")
                elif filepath.endswith(".png"):
                    self.send_header("Content-Type", "image/png")
                elif filepath.endswith(".svg"):
                    self.send_header("Content-Type", "image/svg+xml")
                else:
                    self.send_header("Content-Type", "application/octet-stream")
                self.end_headers()
                with open(filepath, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "File Not Found")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            traceback.print_exc()
            try:
                self._send_json({"status": "error", "message": "Internal server error"}, 500)
            except Exception:
                pass

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length) if content_length > 0 else b""

            try:
                data = json.loads(post_data.decode("utf-8")) if post_data else {}
            except Exception:
                data = {}

            response = {"status": "error", "message": "Endpoint not found"}
            status_code = 404
            path_only = self.path.split("?")[0]

            if path_only == "/api/select_device":
                device_name = data.get("device")
                if device_name and backend.activate_device(device_name):
                    config_manager.set("last_device", device_name)
                    notify_if_enabled(
                        "Output Device Changed",
                        f"Now playing through: {device_name}",
                        dedupe_key="device_change",
                    )
                    response = {"status": "success", "channel_count": backend.channel_count}
                    status_code = 200
                else:
                    response = {"status": "error", "message": "Failed to activate device"}
                    status_code = 400

            elif path_only == "/api/master_volume":
                vol = data.get("volume")
                if vol is not None:
                    backend.set_master_volume(vol)
                    response = {"status": "success"}
                    status_code = 200
                else:
                    response = {"status": "error", "message": "Missing volume parameter"}
                    status_code = 400

            elif path_only == "/api/channel_volume":
                ch = data.get("channel")
                vol = data.get("volume")
                if ch is not None and vol is not None:
                    if backend.is_channel_locked(int(ch)):
                        # Someone tried to move the subwoofer fader via a raw
                        # API call (e.g. curl / bypassing the disabled UI
                        # control). Reject it and notify, instead of silently
                        # forcing 100 like before.
                        notify_if_enabled(
                            "Subwoofer Level Locked",
                            "Subwoofer volume is fixed at 100%. Use the physical remote control to adjust subwoofer level.",
                            dedupe_key="subwoofer_lock",
                        )
                        response = {"status": "error", "message": "Subwoofer channel is locked at 100%"}
                        status_code = 423  # Locked
                    else:
                        backend.set_channel_volume(int(ch), vol)
                        response = {"status": "success"}
                        status_code = 200
                else:
                    response = {"status": "error", "message": "Missing channel or volume parameter"}
                    status_code = 400

            elif path_only == "/api/subwoofer_lock_notice":
                # Fired by the frontend whenever the user clicks/drags the
                # visually-locked subwoofer slider, so we can surface a native
                # Windows toast explaining *why* nothing happened.
                notify_if_enabled(
                    "Subwoofer Level Locked",
                    "Subwoofer volume is fixed at 100%. Use the physical remote control to adjust subwoofer level.",
                    dedupe_key="subwoofer_lock",
                )
                response = {"status": "success"}
                status_code = 200

            elif path_only == "/api/media/control":
                action = data.get("action")
                import asyncio
                success = asyncio.run(control_windows_media(action))
                if success:
                    response = {"status": "success"}
                    status_code = 200
                else:
                    response = {"status": "error", "message": "Failed to control media session"}
                    status_code = 500

            elif path_only == "/api/notify":
                title = data.get("title")
                message = data.get("message")
                dedupe = data.get("dedupe_key")
                if title and message:
                    notify_if_enabled(title, message, dedupe_key=dedupe)
                    response = {"status": "success"}
                    status_code = 200
                else:
                    response = {"status": "error", "message": "Missing title or message"}
                    status_code = 400

            elif path_only == "/api/toggle_mute":
                new_mute = backend.toggle_mute()
                notify_if_enabled(
                    "System Muted" if new_mute else "System Unmuted",
                    "Hardware master output silenced." if new_mute else "Acoustic channels active again.",
                    dedupe_key="mute_toggle",
                )
                response = {"status": "success", "muted": new_mute}
                status_code = 200

            elif path_only == "/api/reset_balance":
                backend.reset_balance()
                notify_if_enabled(
                    "Balance Reset",
                    "All speaker channels reset to 100% gain.",
                    dedupe_key="reset_balance",
                )
                response = {"status": "success"}
                status_code = 200

            elif path_only == "/api/apply_profile":
                profile = data.get("profile")
                if profile:
                    profile_data = backend.get_profile_values(profile)
                    channels = profile_data.get("channels", {})
                    master_val = profile_data.get("master")

                    if master_val is not None:
                        backend.set_master_volume(master_val)

                    for idx, val in channels.items():
                        idx = int(idx)
                        if backend.is_channel_locked(idx):
                            continue
                        backend.set_channel_volume(idx, val)

                    notify_if_enabled(
                        "Sound Profile Applied",
                        f"Switched to the {profile} sound profile.",
                        dedupe_key="profile_apply",
                    )
                    response = {"status": "success"}
                    status_code = 200
                else:
                    response = {"status": "error", "message": "Missing profile parameter"}
                    status_code = 400

            elif path_only == "/api/solo/start":
                ch = data.get("channel")
                if ch is not None and backend.start_solo(int(ch)):
                    backend.play_channel_test(int(ch))
                    response = {"status": "success", "solo": backend.get_solo_status()}
                    status_code = 200
                else:
                    response = {"status": "error", "message": "Failed to start channel solo"}
                    status_code = 400

            elif path_only == "/api/solo/stop":
                backend.stop_solo()
                response = {"status": "success", "solo": backend.get_solo_status()}
                status_code = 200

            elif path_only == "/api/window/minimize":
                win = getattr(backend, 'window', None)
                if win:
                    try:
                        win.minimize()
                        response = {"status": "success"}
                        status_code = 200
                    except Exception as win_err:
                        print(f"Error minimizing window: {win_err}")
                        response = {"status": "error", "message": str(win_err)}
                        status_code = 500
                else:
                    response = {"status": "error", "message": "No active GUI window"}
                    status_code = 400

            elif path_only == "/api/window/close":
                win = getattr(backend, 'window', None)
                if win:
                    try:
                        win.hide()
                        if config_manager.get("notifications_enabled", True):
                            notify_if_enabled(
                                "Still Running",
                                "Samsung Audioscape Controller is minimized to the system tray.",
                                dedupe_key="minimize_to_tray",
                            )
                        response = {"status": "success"}
                        status_code = 200
                    except Exception as win_err:
                        print(f"Error hiding window: {win_err}")
                        response = {"status": "error", "message": str(win_err)}
                        status_code = 500
                else:
                    response = {"status": "error", "message": "No active GUI window"}
                    status_code = 400

            elif path_only == "/api/test_channel":
                ch = data.get("channel")
                if ch is not None:
                    backend.play_channel_test(ch)
                    response = {"status": "success"}
                    status_code = 200
                else:
                    response = {"status": "error", "message": "Missing channel parameter"}
                    status_code = 400

            elif path_only == "/api/settings/update":
                allowed_keys = {
                    "notifications_enabled",
                    "crossover_hz",
                    "minimize_to_tray_on_close",
                    "calibration_enabled",
                    "calibration_focus_x",
                    "calibration_focus_y",
                    "calibration_delays",
                    "calibration_eq",
                    "active_profile",
                    "user_preset_channels",
                    "user_preset_master",
                }
                partial = {k: v for k, v in data.items() if k in allowed_keys}
                new_settings = config_manager.update(partial)
                response = {"status": "success", "settings": new_settings}
                status_code = 200

            elif path_only == "/api/calibration/optimize":
                x = data.get("x")
                y = data.get("y")
                if x is not None and y is not None:
                    # Calculate speaker delays dynamically based on sound speed and distance in the room map
                    speakers = {
                        "towerL": {"x": 100, "y": 80},
                        "towerR": {"x": 300, "y": 80},
                        "center": {"x": 200, "y": 60},
                        "subwoofer": {"x": 270, "y": 60},
                        "surroundL": {"x": 70, "y": 300},
                        "surroundR": {"x": 330, "y": 300}
                    }
                    delays = {}
                    distances = {}
                    for name, spk in speakers.items():
                        dx = x - spk["x"]
                        dy = y - spk["y"]
                        pixel_dist = (dx**2 + dy**2) ** 0.5
                        meters = pixel_dist / 80.0
                        ms = meters / 0.343
                        
                        delays[name] = int(round(ms * 10))
                        distances[name] = round(meters, 2)
                    
                    config_manager.update({
                        "calibration_focus_x": x,
                        "calibration_focus_y": y,
                        "calibration_delays": delays
                    })
                    
                    notify_if_enabled(
                        "Calibration Complete",
                        f"Sweet-spot focused at coordinates [{int(round(x))}, {int(round(y))}]. Phase delays synced.",
                        dedupe_key="calibration_optimize"
                    )
                    
                    response = {
                        "status": "success",
                        "delays": delays,
                        "distances": distances
                    }
                    status_code = 200
            elif path_only == "/api/profile/apply":
                profile = data.get("profile")
                if profile in ["Movie", "Music", "Game", "Night", "Concert", "Vocal", "Sports", "Club", "User"]:
                    if profile == "User":
                        # Fetch levels from config manager
                        channels = config_manager.get("user_preset_channels", {})
                        master_vol = config_manager.get("user_preset_master", 85)
                        
                        # Apply to hardware
                        name_to_idx = {
                            "towerL": 0,
                            "towerR": 1,
                            "center": 2,
                            "subwoofer": 3,
                            "surroundL": 4,
                            "surroundR": 5
                        }
                        
                        channels_out = {}
                        for name, vol in channels.items():
                            ch_idx = name_to_idx.get(name)
                            if ch_idx is not None:
                                channels_out[ch_idx] = vol
                                try:
                                    if ch_idx < backend.channel_count:
                                        backend.set_channel_volume(ch_idx, vol)
                                except Exception as ch_err:
                                    print(f"Error applying custom channel volume: {ch_err}")
                                    
                        if master_vol is not None:
                            try:
                                backend.set_master_volume(master_vol)
                            except Exception as m_err:
                                print(f"Error applying custom master volume: {m_err}")
                                
                        config_manager.update({"active_profile": "User"})
                        notify_if_enabled(
                            "Acoustic Preset Applied",
                            "Custom soundstage User preset profile loaded.",
                            dedupe_key="profile_apply"
                        )
                        
                        response = {
                            "status": "success",
                            "profile": "User",
                            "channels": channels_out,
                            "master": master_vol
                        }
                        status_code = 200
                    else:
                        # Fetch preset levels from backend
                        profile_data = backend.get_profile_values(profile)
                        
                        # Apply channel volumes up to physical limit
                        for ch_idx, vol in profile_data.get("channels", {}).items():
                            try:
                                if int(ch_idx) < backend.channel_count:
                                    backend.set_channel_volume(int(ch_idx), vol)
                            except Exception as ch_err:
                                print(f"Error applying preset channel volume: {ch_err}")
                                
                        # Apply master volume if present (e.g. Night Mode caps master volume at 30%)
                        master_vol = profile_data.get("master")
                        if master_vol is not None:
                            try:
                                backend.set_master_volume(master_vol)
                            except Exception as m_err:
                                print(f"Error applying preset master volume: {m_err}")
                                
                        # Save to config
                        config_manager.update({
                            "active_profile": profile
                        })
                        
                        # Notify
                        notify_if_enabled(
                            "Acoustic Preset Applied",
                            f"Samsung Audioscape optimized for {profile} playback.",
                            dedupe_key="profile_apply"
                        )
                        
                        response = {
                            "status": "success",
                            "profile": profile,
                            "channels": profile_data.get("channels", {}),
                            "master": master_vol
                        }
                        status_code = 200
                else:
                    response = {"status": "error", "message": "Invalid profile name"}
                    status_code = 400

            elif path_only == "/api/startup/toggle":
                enabled = bool(data.get("enabled"))
                ok = startup_manager.set_startup(enabled)
                if ok:
                    config_manager.set("launch_on_startup", enabled)
                    notify_if_enabled(
                        "Startup Setting Updated",
                        "App will now launch automatically with Windows." if enabled
                        else "App will no longer launch automatically with Windows.",
                        dedupe_key="startup_toggle",
                    )
                    response = {"status": "success", "enabled": enabled}
                    status_code = 200
                else:
                    response = {"status": "error", "message": "Failed to update Windows startup registration"}
                    status_code = 500

            elif path_only == "/api/notify":
                title = data.get("title", "Samsung Audioscape Controller")
                message = data.get("message", "")
                notify_if_enabled(title, message, dedupe_key=data.get("dedupe_key"))
                response = {"status": "success"}
                status_code = 200

            self._send_json(response, status_code)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            traceback.print_exc()
            try:
                self._send_json({"status": "error", "message": "Internal server error"}, 500)
            except Exception:
                pass


def on_window_closing():
    global window
    if window:
        window.hide()
        if config_manager.get("minimize_to_tray_on_close", True):
            notify_if_enabled(
                "Still Running",
                "Samsung Audioscape Controller is minimized to the system tray.",
                dedupe_key="minimize_to_tray",
            )
    # Return False to cancel the default window closing/destruction action
    return False


# ----------------------------------------------------------------------
# System Tray Icon Support
# ----------------------------------------------------------------------
def generate_tray_icon_image(muted=False):
    try:
        from PIL import Image, ImageDraw
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
        try:
            from PIL import Image
            return Image.new("RGB", (64, 64), color=(212, 175, 55))
        except Exception:
            return None


def start_tray_icon():
    global tray_icon_ref
    try:
        import pystray

        def on_open_dashboard(icon, item):
            global window
            if window:
                window.show()

        def on_toggle_mute(icon, item):
            new_mute = backend.toggle_mute()
            notify_if_enabled(
                "System Muted" if new_mute else "System Unmuted",
                "Hardware master output silenced." if new_mute else "Acoustic channels active again.",
                dedupe_key="mute_toggle",
            )
            refresh_tray_icon()

        def on_reset_balance(icon, item):
            backend.reset_balance()
            notify_if_enabled("Balance Reset", "All speaker channels reset to 100% gain.", dedupe_key="reset_balance")

        def on_toggle_startup(icon, item):
            new_state = not startup_manager.is_startup_enabled()
            if startup_manager.set_startup(new_state):
                config_manager.set("launch_on_startup", new_state)
                notify_if_enabled(
                    "Startup Setting Updated",
                    "App will now launch automatically with Windows." if new_state
                    else "App will no longer launch automatically with Windows.",
                    dedupe_key="startup_toggle",
                )

        def startup_checked(item):
            return startup_manager.is_startup_enabled()

        def mute_label(item):
            _, muted = backend.get_master_volume()
            return "Unmute" if muted else "Mute"

        def on_exit(icon, item):
            global window
            icon.stop()
            if window:
                try:
                    window.events.closing -= on_window_closing
                except Exception:
                    pass
                window.destroy()
            os._exit(0)

        icon_img = generate_tray_icon_image()
        if icon_img is None:
            return

        menu = pystray.Menu(
            pystray.MenuItem("Open Dashboard", on_open_dashboard, default=True),
            pystray.MenuItem(mute_label, on_toggle_mute),
            pystray.MenuItem("Reset Balance", on_reset_balance),
            pystray.MenuItem("Start with Windows", on_toggle_startup, checked=startup_checked),
            pystray.MenuItem("Exit", on_exit)
        )

        tray_icon_ref = pystray.Icon(
            "HT-F4B3 Controller",
            icon_img,
            "Samsung HT-F4B3 Audioscape Controller",
            menu
        )
        tray_icon_ref.run()
    except Exception as e:
        print(f"Failed to initialize background system tray: {e}")


def refresh_tray_icon():
    """Swaps the tray icon glyph so it visibly reflects mute state."""
    global tray_icon_ref
    if not tray_icon_ref:
        return
    try:
        _, muted = backend.get_master_volume()
        tray_icon_ref.icon = generate_tray_icon_image(muted=muted)
    except Exception:
        pass


def init_server():
    global PORT, server_instance
    for attempt in range(5):
        try:
            server_instance = ThreadingHTTPServer(("localhost", PORT), AudioControlHandler)
            print(f"Bound HTTP server successfully to port {PORT}")
            return True
        except OSError:
            print(f"Port {PORT} is busy. Trying next port...")
            PORT += 1
    return False


splash_root = None

def run_splash_screen_thread():
    global splash_root
    try:
        import tkinter as tk
        from PIL import Image, ImageTk
        
        splash_root = tk.Tk()
        splash_root.overrideredirect(True)
        splash_root.attributes("-topmost", True)
        
        img_path = os.path.join(BASE_DIR, "Splash.jpg")
        if os.path.exists(img_path):
            img = Image.open(img_path)
            
            # Resize image to a smaller, elegant width of 600px
            original_width, original_height = img.size
            target_width = 600
            target_height = int((target_width / original_width) * original_height)
            
            # Safe high-quality resampling filter fallback
            try:
                resample_filter = Image.Resampling.LANCZOS
            except AttributeError:
                try:
                    resample_filter = Image.ANTIALIAS
                except AttributeError:
                    resample_filter = Image.BICUBIC
            
            img = img.resize((target_width, target_height), resample_filter)
            photo = ImageTk.PhotoImage(img)
            
            # Center splash window
            width, height = target_width, target_height
            screen_width = splash_root.winfo_screenwidth()
            screen_height = splash_root.winfo_screenheight()
            x = (screen_width - width) // 2
            y = (screen_height - height) // 2
            splash_root.geometry(f"{width}x{height}+{x}+{y}")
            
            label = tk.Label(splash_root, image=photo, borderwidth=0, highlightthickness=0)
            label.pack()
            
            # Keep a reference to prevent garbage collection
            label.image = photo
            
            splash_root.mainloop()
        else:
            splash_root = None
    except Exception as splash_err:
        print(f"Failed to display native splash screen: {splash_err}")
        splash_root = None


def main():
    global window

    # Start native splash screen in a background thread to overlap PyWebview setup latency
    splash_thread = threading.Thread(target=run_splash_screen_thread, daemon=True)
    splash_thread.start()

    # 1. Bind HTTP server in main thread to ensure port is selected before creating webview
    if not init_server():
        print("Error: Could not bind server to any port from 5000 to 5004.")
        sys.exit(1)

    # 2. Run HTTP server thread as a background daemon (ThreadingHTTPServer
    #    handles each request on its own thread, so the polling requests
    #    from the UI, tray, and any test-tone playback no longer serialize
    #    behind one another or risk hanging the whole server on error).
    server_thread = threading.Thread(target=server_instance.serve_forever, daemon=True)
    server_thread.start()

    # 3. Run System Tray thread
    tray_thread = threading.Thread(target=start_tray_icon, daemon=True)
    tray_thread.start()

    # 4. Sync "launch on startup" registry state with the saved preference
    #    (handles the case where the user enabled it, then the app .exe was
    #    moved/reinstalled - keeps the registry command path current).
    if config_manager.get("launch_on_startup", False):
        startup_manager.enable_startup()

    notify_if_enabled(
        "Samsung Audioscape Controller",
        "Controller started and running in the system tray.",
        dedupe_key="app_started",
    )

    # 5. Initialize and run PyWebview GUI on the main thread (required)
    try:
        x = None
        y = None
        try:
            screens = webview.screens
            if screens:
                primary = next((s for s in screens if s.x == 0 and s.y == 0), screens[0])
                x = int(primary.x + (primary.width - 1200) / 2)
                y = int(primary.y + (primary.height - 960) / 2)
        except Exception as scr_err:
            print(f"Failed to query monitor coordinates: {scr_err}")

        window = webview.create_window(
            title="Samsung HT-F4B3 Audioscape Controller",
            url=f"http://localhost:{PORT}",
            width=1200,
            height=960,
            resizable=False,
            frameless=True,
            easy_drag=False,
            x=x,
            y=y,
            hidden=True,  # Start hidden to prevent rendering black frame during initialization
            background_color='#050508'  # Match dark theme to prevent white flash during boot
        )
        backend.window = window

        # Define loaded callback to perform a seamless transition once the page paints
        def on_window_loaded():
            def reveal_and_clear_splash():
                try:
                    window.show()
                except Exception:
                    pass
                global splash_root
                if splash_root:
                    try:
                        splash_root.after(0, splash_root.destroy)
                    except Exception:
                        pass
            
            # 150ms timer to allow WebView2 first-paint to complete in background
            threading.Timer(0.15, reveal_and_clear_splash).start()

        window.events.loaded += on_window_loaded

        # Capture close requests and trap them to minimize to system tray instead
        try:
            window.events.closing += on_window_closing
        except Exception:
            pass

        # Start webview loop
        webview.start()
    except Exception as gui_err:
        print(f"GUI window initialization failed (running in headless mode): {gui_err}")
        print("Falling back to console-only mode. HTTP server remains active.")
        try:
            # Keep main thread alive by serving requests
            server_instance.serve_forever()
        except KeyboardInterrupt:
            print("Stopping server...")


if __name__ == "__main__":
    main()

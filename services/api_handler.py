import os
import json
import threading
import traceback
import asyncio
import concurrent.futures
from http.server import BaseHTTPRequestHandler

import config_manager
import startup_manager
from services import apo_service, dolby_service, media_service

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, "web")

class AudioControlHandler(BaseHTTPRequestHandler):
    # Injected dependencies from web_server.py
    backend = None
    ui_manager = None
    get_ddl_state = None
    set_ddl_state = None
    notify_fn = None

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
        preventing directory-traversal escapes."""
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

    def _is_authenticated(self):
        """Checks if the request is local or authenticated via various header styles or query string."""
        client_ip = self.client_address[0]
        if client_ip in ("127.0.0.1", "localhost", "::1"):
            return True

        configured_token = config_manager.get("access_token", "SamsungAudioscapeSecureToken7777")
        token = self.headers.get("X-Access-Token")
        
        if not token:
            token = self.headers.get("access-token")
        if not token:
            token = self.headers.get("access_token")
            
        if not token:
            auth_header = self.headers.get("Authorization")
            if auth_header:
                if auth_header.lower().startswith("bearer "):
                    token = auth_header[7:]
                else:
                    token = auth_header
        
        if not token:
            parts = self.path.split("?")
            if len(parts) > 1:
                from urllib.parse import parse_qs
                params = parse_qs(parts[1])
                token_list = params.get("token")
                if token_list:
                    token = token_list[0]

        is_valid = (token == configured_token)
        print(f"[AUTH] Client IP: {client_ip} | Path: {self.path} | Extracted Token: {token} | Validated: {is_valid}")
        return is_valid

    def do_GET(self):
        try:
            path_only = self.path.split("?")[0]

            # Enforce authentication on all API routes for external clients
            if path_only.startswith("/api/"):
                if not self._is_authenticated():
                    self._send_json({"status": "unauthorized", "message": "Access Token Required or Invalid"}, 401)
                    return

            if path_only == "/api/connect":
                self._send_json({"status": "success", "authenticated": True, "message": "Connected to HomeTheaterX Backend successfully."}, 200)
                return

            if path_only == "/api/status":
                master_vol, muted = self.backend.get_master_volume()
                channel_vols = self.backend.get_channel_volumes()
                
                bass_active = False
                eightd_active = False
                config_path = os.path.join(apo_service.APO_CONFIG_DIR, "config.txt")
                if os.path.exists(config_path):
                    try:
                        with open(config_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        for line in content.splitlines():
                            line_stripped = line.strip()
                            if "BassManagement" in line and "Include" in line and not line_stripped.startswith("#"):
                                bass_active = True
                            if "8D" in line and "Include" in line and not line_stripped.startswith("#"):
                                eightd_active = True
                    except Exception:
                        pass

                ddl_active = self.get_ddl_state() if self.get_ddl_state else False

                self._send_json({
                    "status": "success",
                    "active_device": self.backend.current_device_name,
                    "channel_count": self.backend.channel_count,
                    "master_volume": master_vol,
                    "muted": muted,
                    "channel_volumes": channel_vols,
                    "solo": self.backend.get_solo_status(),
                    "bass_management": bass_active,
                    "eightd_apo_active": eightd_active,
                    "ddl_active": ddl_active,
                    "active_preset": config_manager.get("active_preset")
                })
                return

            if path_only == "/api/devices":
                devices = self.backend.refresh_devices()
                self._send_json({
                    "status": "success",
                    "devices": devices,
                    "active_device": self.backend.current_device_name
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
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(
                        lambda: asyncio.run(media_service.get_windows_media_status())
                    )
                    try:
                        res = future.result(timeout=5)
                    except Exception as media_err:
                        res = {"status": "error", "message": str(media_err)}
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
                        peak = self.backend.get_audio_peak()
                        data_payload = f"data: {json.dumps({'peak': peak})}\n\n"
                        self.wfile.write(data_payload.encode('utf-8'))
                        self.wfile.flush()
                        time.sleep(0.03)  # ~33 fps
                except Exception:
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
            path_only = self.path.split("?")[0]

            # Enforce authentication on all API routes for external clients
            if path_only.startswith("/api/"):
                if not self._is_authenticated():
                    self._send_json({"status": "unauthorized", "message": "Access Token Required or Invalid"}, 401)
                    return

            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length) if content_length > 0 else b""

            try:
                data = json.loads(post_data.decode("utf-8")) if post_data else {}
            except Exception:
                data = {}

            response = {"status": "error", "message": "Endpoint not found"}
            status_code = 404

            if path_only == "/api/connect":
                self._send_json({"status": "success", "authenticated": True, "message": "Connected to Audioscape Backend successfully."}, 200)
                return

            if path_only == "/api/select_device":
                device_name = data.get("device")
                if device_name and self.backend.activate_device(device_name):
                    config_manager.set("last_device", device_name)
                    if self.notify_fn:
                        self.notify_fn(
                            "Output Device Changed",
                            f"Now playing through: {device_name}",
                            dedupe_key="device_change",
                        )
                    response = {"status": "success", "channel_count": self.backend.channel_count}
                    status_code = 200
                else:
                    response = {"status": "error", "message": "Failed to activate device"}
                    status_code = 400

            elif path_only == "/api/master_volume":
                vol = data.get("volume")
                if vol is not None:
                    self.backend.set_master_volume(vol)
                    response = {"status": "success"}
                    status_code = 200
                else:
                    response = {"status": "error", "message": "Missing volume parameter"}
                    status_code = 400

            elif path_only == "/api/channel_volume":
                ch = data.get("channel")
                vol = data.get("volume")
                if ch is not None and vol is not None:
                    if self.backend.is_channel_locked(int(ch)):
                        if self.notify_fn:
                            self.notify_fn(
                                "Subwoofer Level Locked",
                                "Subwoofer volume is fixed at 100%. Use the physical remote control to adjust subwoofer level.",
                                dedupe_key="subwoofer_lock",
                            )
                        response = {"status": "error", "message": "Subwoofer channel is locked at 100%"}
                        status_code = 423
                    else:
                        self.backend.set_channel_volume(int(ch), vol)
                        response = {"status": "success"}
                        status_code = 200
                else:
                    response = {"status": "error", "message": "Missing channel or volume parameter"}
                    status_code = 400

            elif path_only == "/api/subwoofer_lock_notice":
                if self.notify_fn:
                    self.notify_fn(
                        "Subwoofer Level Locked",
                        "Subwoofer volume is fixed at 100%. Use the physical remote control to adjust subwoofer level.",
                        dedupe_key="subwoofer_lock",
                    )
                response = {"status": "success"}
                status_code = 200

            elif path_only == "/api/media/control":
                action = data.get("action")
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(
                        lambda: asyncio.run(media_service.control_windows_media(action))
                    )
                    try:
                        success = future.result(timeout=5)
                    except Exception:
                        success = False
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
                    if self.notify_fn:
                        self.notify_fn(title, message, dedupe_key=dedupe)
                    response = {"status": "success"}
                    status_code = 200
                else:
                    response = {"status": "error", "message": "Missing title or message"}
                    status_code = 400

            elif path_only == "/api/toggle_mute":
                new_mute = self.backend.toggle_mute()
                if self.notify_fn:
                    self.notify_fn(
                        "System Muted" if new_mute else "System Unmuted",
                        "Hardware master output silenced." if new_mute else "Acoustic channels active again.",
                        dedupe_key="mute_toggle",
                    )
                if self.ui_manager:
                    self.ui_manager.refresh_tray_icon()
                response = {"status": "success", "muted": new_mute}
                status_code = 200

            elif path_only == "/api/reset_balance":
                self.backend.reset_balance()
                apo_service.set_bass_management_state(False)
                apo_service.set_apo_include_state("8D.txt", False)
                if self.notify_fn:
                    self.notify_fn(
                        "Balance Reset",
                        "All speaker channels reset to 100% gain.",
                        dedupe_key="reset_balance",
                    )
                response = {"status": "success"}
                status_code = 200

            elif path_only == "/api/apply_profile":
                profile = data.get("profile")
                if profile:
                    profile_data = self.backend.get_profile_values(profile)
                    channels = profile_data.get("channels", {})
                    master_val = profile_data.get("master")

                    if master_val is not None:
                        self.backend.ramp_master_volume(master_val, duration_ms=220)

                    for idx, val in channels.items():
                        idx = int(idx)
                        if self.backend.is_channel_locked(idx):
                            continue
                        self.backend.ramp_channel_volume(idx, val, duration_ms=220)

                    if self.notify_fn:
                        self.notify_fn(
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
                if ch is not None and self.backend.start_solo(int(ch)):
                    self.backend.play_channel_test(int(ch))
                    response = {"status": "success", "solo": self.backend.get_solo_status()}
                    status_code = 200
                else:
                    response = {"status": "error", "message": "Failed to start channel solo"}
                    status_code = 400

            elif path_only == "/api/solo/stop":
                self.backend.stop_solo()
                apo_service.set_bass_management_state(False)
                apo_service.set_apo_include_state("8D.txt", False)
                response = {"status": "success", "solo": self.backend.get_solo_status()}
                status_code = 200

            elif path_only == "/api/window/minimize":
                win = self.ui_manager.window if self.ui_manager else None
                if win:
                    threading.Thread(target=lambda: win.minimize(), daemon=True).start()
                    response = {"status": "success"}
                    status_code = 200
                else:
                    response = {"status": "error", "message": "No active GUI window"}
                    status_code = 400

            elif path_only == "/api/window/close":
                if self.ui_manager:
                    threading.Thread(target=lambda: self.ui_manager.on_window_closing(), daemon=True).start()
                    response = {"status": "success"}
                    status_code = 200
                else:
                    response = {"status": "error", "message": "No active GUI window"}
                    status_code = 400

            elif path_only == "/api/test_channel":
                ch = data.get("channel")
                if ch is not None:
                    self.backend.play_channel_test(ch)
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
                    "calibration_gains",
                    "calibration_mode",
                    "calibration_eq",
                    "active_profile",
                    "user_preset_channels",
                    "user_preset_master",
                }
                partial = {k: v for k, v in data.items() if k in allowed_keys}
                new_settings = config_manager.update(partial)

                if "calibration_enabled" in partial:
                    apo_service.set_room_calibration_state(partial["calibration_enabled"])

                response = {"status": "success", "settings": new_settings}
                status_code = 200

            elif path_only == "/api/calibration/toggle":
                cal_enabled = data.get("enabled")
                if cal_enabled is None:
                    cal_enabled = not config_manager.get("calibration_enabled", True)

                # Auto-disable Dolby Digital Live when enabling calibration
                ddl_was_on = False
                ddl_active = self.get_ddl_state() if self.get_ddl_state else False
                if cal_enabled and ddl_active:
                    ddl_was_on = True
                    success_ddl, new_ddl = dolby_service.toggle_dolby_in_system()
                    if success_ddl:
                        if self.set_ddl_state:
                            self.set_ddl_state(new_ddl)

                # Auto-disable active presets if enabling calibration
                if cal_enabled:
                    active_preset = config_manager.get("active_preset")
                    if active_preset:
                        apo_service.set_preset_state(active_preset, False)
                        config_manager.set("active_preset", None)

                ok = apo_service.set_room_calibration_state(cal_enabled)
                config_manager.update({"calibration_enabled": cal_enabled})

                if self.notify_fn:
                    self.notify_fn(
                        "Room Calibration Enabled" if cal_enabled else "Room Calibration Disabled",
                        "Stereo upmix + phase delay active via Equalizer APO." if cal_enabled
                        else "Phase delays and upmix bypassed.",
                        dedupe_key="calibration_toggle"
                    )

                response = {
                    "status": "success" if ok else "partial",
                    "calibration_enabled": cal_enabled,
                    "ddl_disabled": ddl_was_on,
                }
                status_code = 200

            elif path_only == "/api/calibration/optimize":
                x = data.get("x")
                y = data.get("y")
                if x is not None and y is not None:
                    speakers = {
                        "towerL":    {"x": 100, "y": 80},
                        "towerR":    {"x": 300, "y": 80},
                        "center":    {"x": 200, "y": 60},
                        "subwoofer": {"x": 270, "y": 60},
                        "surroundL": {"x": 70,  "y": 300},
                        "surroundR": {"x": 330, "y": 300}
                    }
                    
                    mode = config_manager.get("calibration_mode", "sweetspot")
                    
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

                    # Normalize delays if we are in sweetspot mode
                    if mode == "sweetspot":
                        if delays:
                            min_raw = min(delays.values())
                            delays = {k: max(0, v - min_raw) for k, v in delays.items()}
                    else:
                        # Steering and Level-Only modes have zero delay line adjustments
                        delays = {k: 0 for k in delays.keys()}

                    # Method B: Gain Compensation based on Inverse-Square Law (SPL: 20 * log10(distance))
                    import math
                    losses = {}
                    for name, m in distances.items():
                        # Clamp distance to minimum 0.5m to avoid extreme offsets
                        dist_clamped = max(0.5, m)
                        losses[name] = 20.0 * math.log10(dist_clamped)

                    gains = {}
                    if mode == "steering":
                        # Panning/Steering: Closest speaker to focus spot gets 0 dB (loudest)
                        # Further speakers get attenuated.
                        min_loss = min(losses.values())
                        for name, loss in losses.items():
                            gains[name] = round(-(loss - min_loss), 1)
                    else:
                        # sweetspot or levelonly: Attenuate closest speaker to equalize volume at spot
                        max_loss = max(losses.values())
                        for name, loss in losses.items():
                            gains[name] = round(-(max_loss - loss), 1)

                    apo_service.write_calibration_delay_file(delays, gains=gains)

                    config_manager.update({
                        "calibration_focus_x": x,
                        "calibration_focus_y": y,
                        "calibration_delays": delays,
                        "calibration_gains": gains
                    })

                    if self.notify_fn:
                        self.notify_fn(
                            "Calibration Complete",
                            f"Focus map updated ({mode.upper()}). Timing alignment and level correction written to Equalizer APO.",
                            dedupe_key="calibration_optimize"
                        )

                    response = {
                        "status": "success",
                        "delays": delays,
                        "distances": distances,
                        "gains": gains
                    }
                    status_code = 200
            elif path_only == "/api/profile/apply":
                profile = data.get("profile")
                if profile in ["Movie", "Music", "Game", "Night", "Concert", "Vocal", "Sports", "Club", "User"]:
                    if profile == "User":
                        channels = config_manager.get("user_preset_channels", {})
                        master_vol = config_manager.get("user_preset_master", 85)
                        
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
                                    if ch_idx < self.backend.channel_count:
                                        self.backend.ramp_channel_volume(ch_idx, vol, duration_ms=220)
                                except Exception as ch_err:
                                    print(f"Error applying custom channel volume: {ch_err}")
                                    
                        if master_vol is not None:
                            try:
                                self.backend.ramp_master_volume(master_vol, duration_ms=220)
                            except Exception as m_err:
                                print(f"Error applying custom master volume: {m_err}")
                                
                        config_manager.update({"active_profile": "User"})
                        if self.notify_fn:
                            self.notify_fn(
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
                        profile_data = self.backend.get_profile_values(profile)
                        
                        for ch_idx, vol in profile_data.get("channels", {}).items():
                            try:
                                if int(ch_idx) < self.backend.channel_count:
                                    self.backend.ramp_channel_volume(int(ch_idx), vol, duration_ms=220)
                            except Exception as ch_err:
                                print(f"Error applying preset channel volume: {ch_err}")
                                
                        master_vol = profile_data.get("master")
                        if master_vol is not None:
                            try:
                                self.backend.ramp_master_volume(master_vol, duration_ms=220)
                            except Exception as m_err:
                                print(f"Error applying preset master volume: {m_err}")
                                
                        config_manager.update({
                            "active_profile": profile
                        })
                        
                        if self.notify_fn:
                            self.notify_fn(
                                "Acoustic Preset Applied",
                                f"HomeTheaterX optimized for {profile} playback.",
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
                    if self.notify_fn:
                        self.notify_fn(
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

            elif path_only == "/api/channel_volumes_multi":
                vols = data.get("volumes")
                if vols is not None:
                    for ch, vol in vols.items():
                        try:
                            ch_idx = int(ch)
                            if self.backend.is_channel_locked(ch_idx):
                                continue
                            self.backend.set_channel_volume(ch_idx, int(vol))
                        except Exception:
                            pass
                    response = {"status": "success"}
                    status_code = 200
                else:
                    response = {"status": "error", "message": "Missing volumes parameter"}
                    status_code = 400

            elif path_only == "/api/apo/toggle_bass":
                enabled = bool(data.get("enabled"))
                config_path = os.path.join(apo_service.APO_CONFIG_DIR, "config.txt")
                if not os.path.exists(config_path):
                    response = {"status": "error", "message": "Equalizer APO config not found"}
                    status_code = 404
                else:
                    try:
                        with open(config_path, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                        
                        modified = False
                        new_lines = []
                        for line in lines:
                            if "BassManagement" in line and "Include" in line:
                                clean_line = line.replace("#", "").strip()
                                if enabled:
                                    new_lines.append(clean_line + "\n")
                                else:
                                    new_lines.append("# " + clean_line + "\n")
                                modified = True
                            else:
                                new_lines.append(line)
                        
                        if not modified:
                            line_to_add = "Include: BassManagement.txt\n" if enabled else "# Include: BassManagement.txt\n"
                            new_lines.append(line_to_add)
                            
                        with open(config_path, "w", encoding="utf-8") as f:
                            f.writelines(new_lines)
                            
                        response = {"status": "success", "enabled": enabled}
                        status_code = 200
                    except PermissionError:
                        response = {"status": "error", "message": "Permission denied. Run application as Administrator."}
                        status_code = 403
                    except Exception as e:
                        response = {"status": "error", "message": str(e)}
                        status_code = 500

            elif path_only == "/api/apo/toggle_8d":
                enabled = data.get("enabled", False)
                if enabled:
                    # Auto-disable active presets
                    active_preset = config_manager.get("active_preset")
                    if active_preset:
                        apo_service.set_preset_state(active_preset, False)
                        config_manager.set("active_preset", None)
                if apo_service.set_apo_include_state("8D.txt", enabled):
                    response = {"status": "success", "enabled": enabled}
                    status_code = 200
                else:
                    response = {"status": "error", "message": "Failed to update config.txt"}
                    status_code = 500

            elif path_only == "/api/apo/toggle_ddl":
                success, new_state = dolby_service.toggle_dolby_in_system()
                if success:
                    if self.set_ddl_state:
                        self.set_ddl_state(new_state)
                    
                    cal_was_disabled = False
                    if new_state:
                        if config_manager.get("calibration_enabled", True):
                            apo_service.set_room_calibration_state(False)
                            config_manager.update({"calibration_enabled": False})
                            cal_was_disabled = True
                        
                        # Auto-disable active presets
                        active_preset = config_manager.get("active_preset")
                        if active_preset:
                            apo_service.set_preset_state(active_preset, False)
                            config_manager.set("active_preset", None)
                            
                    response = {
                        "status": "success",
                        "ddl_active": new_state,
                        "calibration_disabled": cal_was_disabled
                    }
                    status_code = 200
                else:
                    response = {"status": "error", "message": "Failed to automate Dolby properties toggle."}
                    status_code = 500

            elif path_only == "/api/apo/toggle_preset":
                preset_name = data.get("preset")   # "bassboosted", "tightbass", "hallvibe", "echo"
                enabled = data.get("enabled", False)
                
                active_preset = config_manager.get("active_preset")
                
                if enabled:
                    # 1. Turn off any other active preset first
                    if active_preset and active_preset != preset_name:
                        apo_service.set_preset_state(active_preset, False)
                    
                    # 2. Capture and save current states of DDL, 8D, and Room Calibration
                    ddl_active = self.get_ddl_state() if self.get_ddl_state else False
                    
                    # Read 8D active state from config.txt
                    eightd_active = False
                    config_path = os.path.join(apo_service.APO_CONFIG_DIR, "config.txt")
                    if os.path.exists(config_path):
                        try:
                            with open(config_path, "r", encoding="utf-8") as f:
                                content = f.read()
                            for line in content.splitlines():
                                if "8D.txt" in line and "Include" in line and not line.strip().startswith("#"):
                                    eightd_active = True
                        except Exception:
                            pass
                            
                    cal_active = config_manager.get("calibration_enabled", True)
                    
                    prev_state = {
                        "ddl": ddl_active,
                        "eightd": eightd_active,
                        "calibration": cal_active
                    }
                    config_manager.set("preset_prev_state", prev_state)
                    
                    # 3. Disable active systems
                    if ddl_active:
                        dolby_service.toggle_dolby_in_system()
                        if self.set_ddl_state:
                            self.set_ddl_state(False)
                            
                    if eightd_active:
                        apo_service.set_apo_include_state("8D.txt", False)
                        
                    if cal_active:
                        apo_service.set_room_calibration_state(False)
                        config_manager.set("calibration_enabled", False)
                        
                    # 4. Turn preset ON
                    ok = apo_service.set_preset_state(preset_name, True)
                    config_manager.set("active_preset", preset_name)
                    
                    response = {
                        "status": "success" if ok else "error",
                        "active_preset": preset_name,
                        "calibration_disabled": cal_active,
                        "ddl_disabled": ddl_active,
                        "eightd_disabled": eightd_active
                    }
                    status_code = 200 if ok else 500
                    
                else:
                    # Disabling preset
                    ok = apo_service.set_preset_state(preset_name, False)
                    config_manager.set("active_preset", None)
                    
                    # Restore previous state
                    prev = config_manager.get("preset_prev_state", {}) or {}
                    ddl_restored = False
                    eightd_restored = False
                    cal_restored = False
                    
                    if prev.get("ddl"):
                        dolby_service.toggle_dolby_in_system()
                        if self.set_ddl_state:
                            self.set_ddl_state(True)
                        ddl_restored = True
                        
                    if prev.get("eightd"):
                        apo_service.set_apo_include_state("8D.txt", True)
                        eightd_restored = True
                        
                    if prev.get("calibration"):
                        apo_service.set_room_calibration_state(True)
                        config_manager.set("calibration_enabled", True)
                        cal_restored = True
                        
                    response = {
                        "status": "success" if ok else "error",
                        "active_preset": None,
                        "ddl_restored": ddl_restored,
                        "eightd_restored": eightd_restored,
                        "calibration_restored": cal_restored
                    }
                    status_code = 200 if ok else 500

            self._send_json(response, status_code)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            traceback.print_exc()
            try:
                self._send_json({"status": "error", "message": "Internal server error"}, 500)
            except Exception:
                pass

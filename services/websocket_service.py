import os
import json
import asyncio
import threading
import urllib.parse
from comtypes import CoInitialize, CoUninitialize
import websockets
try:
    from websockets.asyncio.server import serve as ws_serve
except ImportError:
    from websockets import serve as ws_serve

from services import media_service


class WebSocketManager:
    """
    Manages WebSocket server lifecycle and real-time event broadcasting
    for HomeTheaterX (Samsung Audioscape Controller).
    Runs asynchronously on a dedicated daemon thread.
    """
    def __init__(self, backend, config_manager, host="0.0.0.0", port=5010):
        self.backend = backend
        self.config_manager = config_manager
        self.host = host
        self.port = port
        self.clients = set()
        self.clients_lock = threading.Lock()
        self.loop = None
        self.server = None
        self.thread = None
        self.running = False
        
        # State tracking caches to deduplicate broadcasts
        self._last_media_snapshot = None
        self._last_volume_snapshot = None

    def start(self):
        """Starts the WebSocket server thread."""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_event_loop, daemon=True, name="HomeTheaterX-WebSocket")
        self.thread.start()

    def _run_event_loop(self):
        """Background thread executing the asyncio event loop."""
        try:
            CoInitialize()
        except Exception:
            pass

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            self.loop.run_until_complete(self._main_async())
        except Exception as e:
            print(f"[WebSocket] Event loop terminated: {e}")
        finally:
            try:
                CoUninitialize()
            except Exception:
                pass

    async def _main_async(self):
        """Initializes the WebSocket server with automatic port retry and launches broadcast tasks."""
        base_port = self.port
        for offset in range(5):
            candidate_port = base_port + offset
            try:
                self.server = await ws_serve(
                    self._handler_entry,
                    self.host,
                    candidate_port,
                    ping_interval=20,
                    ping_timeout=20
                )
                self.port = candidate_port
                print(f"[WebSocket] Server listening on ws://{self.host}:{self.port}")
                break
            except OSError:
                print(f"[WebSocket] Port {candidate_port} occupied. Trying next...")
        else:
            print("[WebSocket] Error: Could not bind WebSocket server to any port in range.")
            self.running = False
            return

        # Start concurrent background periodic broadcasters
        await asyncio.gather(
            self._audio_peak_loop(),
            self._media_sync_loop(),
            self._volume_sync_loop(),
            self._keep_alive_loop()
        )

    def _is_client_authenticated(self, path_or_query):
        """Validates incoming connection access token against configuration."""
        configured_token = self.config_manager.get("access_token", "SamsungAudioscapeSecureToken7777")
        if "?" in path_or_query:
            query = path_or_query.split("?", 1)[1]
            params = urllib.parse.parse_qs(query)
            token_list = params.get("token") or params.get("access_token")
            if token_list and token_list[0] == configured_token:
                return True
        return False

    async def _handler_entry(self, websocket):
        """Entry point for incoming WebSocket client connections."""
        path_str = getattr(websocket, "path", "") or getattr(websocket.request, "path", "")
        client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
        
        # Localhost connections are trusted; external connections require token check
        is_local = client_ip in ("127.0.0.1", "localhost", "::1")
        if not is_local and not self._is_client_authenticated(path_str):
            print(f"[WebSocket] Unauthorized connection attempt from {client_ip}")
            await websocket.close(code=4001, reason="Unauthorized: Valid access token required")
            return

        with self.clients_lock:
            self.clients.add(websocket)
        print(f"[WebSocket] Client connected: {client_ip} (Total active: {len(self.clients)})")

        # Send initial full state snapshot upon connecting in a background task
        asyncio.create_task(self._safe_send_snapshot(websocket))

        try:
            async for message in websocket:
                await self._handle_client_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as err:
            print(f"[WebSocket] Client handler error: {err}")
        finally:
            with self.clients_lock:
                self.clients.discard(websocket)
            print(f"[WebSocket] Client disconnected: {client_ip} (Remaining: {len(self.clients)})")

    async def _safe_send_snapshot(self, websocket):
        try:
            await self._send_full_status_snapshot(websocket)
        except Exception as e:
            print(f"[WebSocket] Snapshot error: {e}")

    async def _get_media_status_safe(self):
        """Safely queries Windows Media Transport on an STA thread to prevent asyncio COM deadlocks."""
        try:
            return await asyncio.to_thread(lambda: asyncio.run(media_service.get_windows_media_status()))
        except Exception:
            return {"status": "no_session"}

    async def _control_media_safe(self, action):
        """Safely executes Windows Media Control on an STA thread."""
        try:
            return await asyncio.to_thread(lambda: asyncio.run(media_service.control_windows_media(action)))
        except Exception:
            return False

    async def _handle_client_message(self, websocket, raw_message):
        """Processes inbound JSON commands from connected clients."""
        try:
            data = json.loads(raw_message)
            msg_type = data.get("type", "")

            if msg_type == "ping":
                await websocket.send(json.dumps({"type": "pong", "timestamp": data.get("timestamp")}))
            
            elif msg_type == "get_status":
                await self._send_full_status_snapshot(websocket)

            elif msg_type == "media_control":
                action = data.get("action")
                if action:
                    await self._control_media_safe(action)
                    media_data = await self._get_media_status_safe()
                    await self.broadcast({"type": "media_status", "data": media_data})

            elif msg_type == "master_volume":
                level = data.get("level")
                if level is not None:
                    self.backend.set_master_volume(level)

            elif msg_type == "channel_volume":
                channel_idx = data.get("channel_idx")
                level = data.get("level")
                if channel_idx is not None and level is not None:
                    self.backend.set_channel_volume(channel_idx, level)

            elif msg_type == "toggle_mute":
                self.backend.toggle_mute()

        except Exception as e:
            print(f"[WebSocket] Error handling client message: {e}")

    async def _send_full_status_snapshot(self, websocket):
        """Sends a complete status payload to a freshly connected client."""
        try:
            master_vol, muted = self.backend.get_master_volume()
            channel_vols = self.backend.get_channel_volumes()
            current_dev = self.backend.current_device_name
            media_data = await self._get_media_status_safe()

            payload = {
                "type": "full_status",
                "master": master_vol,
                "muted": muted,
                "channels": channel_vols,
                "current_device": current_dev,
                "channel_count": self.backend.channel_count,
                "is_stereo": (self.backend.channel_count <= 2),
                "media": media_data,
                "active_profile": self.config_manager.get("active_profile", "User"),
                "calibration_enabled": self.config_manager.get("calibration_enabled", False)
            }
            await websocket.send(json.dumps(payload))
        except Exception as err:
            print(f"[WebSocket] Error sending full snapshot: {err}")

    async def broadcast(self, payload):
        """Broadcasts a JSON dictionary to all connected active clients."""
        with self.clients_lock:
            if not self.clients:
                return
            active_clients = list(self.clients)

        message = json.dumps(payload)
        tasks = []
        for client in active_clients:
            try:
                tasks.append(client.send(message))
            except Exception:
                pass
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # -------------------------------------------------------------------------
    # Periodic Asynchronous Broadcasters
    # -------------------------------------------------------------------------

    async def _audio_peak_loop(self):
        """Broadcasts real-time audio output meter peak ~33fps for oscilloscope visualization."""
        while self.running:
            try:
                with self.clients_lock:
                    has_clients = bool(self.clients)
                
                if has_clients:
                    peak = self.backend.get_audio_peak()
                    # Only broadcast if there are listeners
                    await self.broadcast({
                        "type": "audio_peak",
                        "peak": peak
                    })
                await asyncio.sleep(0.03)  # ~33 fps
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.1)

    async def _media_sync_loop(self):
        """
        Periodically polls Windows System Media Transport and broadcasts
        playback, track metadata, and position updates when changes occur.
        """
        while self.running:
            try:
                with self.clients_lock:
                    has_clients = bool(self.clients)

                if has_clients:
                    media_data = await self._get_media_status_safe()
                    # Broadcast update
                    current_snap = (
                        media_data.get("status"),
                        media_data.get("title"),
                        media_data.get("artist"),
                        media_data.get("playback_status"),
                        int(media_data.get("position", 0))
                    )
                    
                    if current_snap != self._last_media_snapshot:
                        self._last_media_snapshot = current_snap
                        await self.broadcast({
                            "type": "media_status",
                            "data": media_data
                        })
                await asyncio.sleep(0.4)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1.0)

    async def _volume_sync_loop(self):
        """
        Broadcasts hardware volume changes (master, mute state, channels, and active output device changes)
        when modified externally or via Windows settings.
        """
        while self.running:
            try:
                # 1. Check if default audio output device changed in Windows
                current_default = self.backend.get_default_device_name()
                if current_default and current_default != self.backend.current_device_name:
                    print(f"[WebSocket] Windows default output device changed: {current_default}")
                    self.backend.activate_device(current_default)
                    is_stereo = (self.backend.channel_count <= 2)
                    await self.broadcast({
                        "type": "device_changed",
                        "device_name": current_default,
                        "channel_count": self.backend.channel_count,
                        "is_stereo": is_stereo
                    })

                with self.clients_lock:
                    has_clients = bool(self.clients)

                if has_clients:
                    master_vol, muted = self.backend.get_master_volume()
                    channel_vols = self.backend.get_channel_volumes()

                    snap = (master_vol, muted, tuple(channel_vols.items()), self.backend.current_device_name)
                    if snap != self._last_volume_snapshot:
                        self._last_volume_snapshot = snap
                        await self.broadcast({
                            "type": "volume_status",
                            "master": master_vol,
                            "muted": muted,
                            "channels": channel_vols,
                            "device_name": self.backend.current_device_name,
                            "channel_count": self.backend.channel_count,
                            "is_stereo": (self.backend.channel_count <= 2)
                        })
                await asyncio.sleep(0.3)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.5)

    async def _keep_alive_loop(self):
        """Heartbeat to keep the asyncio event loop active."""
        while self.running:
            await asyncio.sleep(10)

    def stop(self):
        """Stops the WebSocket server."""
        self.running = False
        if self.server:
            self.server.close()
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

import os
import time
import threading
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL, CoInitialize
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume, IAudioMeterInformation

def safe_coinit():
    try:
        CoInitialize()
    except Exception:
        pass

class AudioBackend:
    def __init__(self):
        self.active_devices = []
        self.volume_interface = None
        self.channel_count = 0
        self.current_device_id = None
        self.current_device_name = None
        # Solo/Isolate ("check speakers one by one") state
        self.solo_active = False
        self.solo_channel = None
        self.solo_snapshot = {}
        # Smooth volume ramping state
        # key: int (channel idx) or 'master' -> threading.Event that signals stop
        self._ramp_events = {}
        self._ramp_lock = threading.Lock()

    def refresh_devices(self):
        """Fetches active audio OUTPUT devices from Pycaw (state == Active), falling back to sounddevice if empty."""
        safe_coinit()
        self.active_devices = []
        try:
            all_devices = AudioUtilities.GetAllDevices()
            for device in all_devices:
                state = getattr(device, 'state', None)
                # AudioDeviceState is an IntEnum — compare by .value or by string representation
                is_active = False
                if state is not None:
                    try:
                        is_active = (int(state) == 1)  # AudioDeviceState.Active == 1
                    except (TypeError, ValueError):
                        is_active = ('Active' in str(state))

                if not is_active:
                    continue

                # Filter to output (render) devices only — microphones won't expose
                # IAudioEndpointVolume with output channels > 0 via sounddevice.
                # Quick heuristic: skip names that are clearly inputs.
                name = getattr(device, 'FriendlyName', '') or ''
                lower = name.lower()
                if any(kw in lower for kw in ('microphone', 'mic array', 'stereo mix', 'what u hear', 'loopback')):
                    continue

                self.active_devices.append(device)
            
            names = [dev.FriendlyName for dev in self.active_devices if getattr(dev, 'FriendlyName', None)]
            if names:
                return names
        except Exception as e:
            print(f"Error refreshing devices with Pycaw: {e}")

        # Fallback to sounddevice if Pycaw returns nothing or fails
        try:
            devices_info = sd.query_devices()
            seen = set()
            sd_names = []
            for dev in devices_info:
                if dev.get('max_output_channels', 0) > 0:
                    name = dev.get('name', '')
                    if name and name not in seen:
                        # Skip generic driver wrappers
                        if any(kw in name.lower() for kw in ('microsoft sound mapper', 'primary sound driver')):
                            continue
                        seen.add(name)
                        sd_names.append(name)
            return sd_names
        except Exception as sd_err:
            print(f"Sounddevice fallback error: {sd_err}")
            return []

    def get_default_device_name(self):
        """Returns friendly name of the default speaker, falling back to sounddevice default output if needed."""
        safe_coinit()
        try:
            # GetSpeakers() returns an AudioDevice object that HAS .FriendlyName and .id
            default_dev = AudioUtilities.GetSpeakers()
            default_name = getattr(default_dev, 'FriendlyName', None)
            if default_name:
                # Confirm it is in the active output list we already built
                for dev in self.active_devices:
                    if dev.FriendlyName == default_name:
                        return default_name
            # Fallback: match by .id
            default_id = getattr(default_dev, 'id', None)
            if default_id:
                for dev in self.active_devices:
                    if getattr(dev, 'id', None) == default_id:
                        return dev.FriendlyName
            if default_name:
                return default_name
        except Exception:
            pass

        # Fallback to sounddevice default output
        try:
            default_idx = sd.default.device[1]
            if default_idx is not None and default_idx >= 0:
                dev = sd.query_devices(default_idx)
                return dev.get('name')
        except Exception:
            pass

        # Last resort: first device
        if self.active_devices:
            return self.active_devices[0].FriendlyName
        return None

    def activate_device(self, device_name):
        """Activates volume interface for the specified device."""
        safe_coinit()
        selected_device = None
        
        # 1. Search in cached self.active_devices
        for dev in self.active_devices:
            if getattr(dev, 'FriendlyName', None) == device_name:
                selected_device = dev
                break

        # 2. Search on the fly if not found in cache (e.g. fallback name used)
        if not selected_device:
            try:
                all_devices = AudioUtilities.GetAllDevices()
                for dev in all_devices:
                    name = getattr(dev, 'FriendlyName', None)
                    if name:
                        # Match exact or substring (sounddevice names are sometimes truncated)
                        if name == device_name or device_name in name or name in device_name:
                            selected_device = dev
                            break
            except Exception:
                pass

        if not selected_device:
            return False

        self.current_device_id = getattr(selected_device, 'id', None)
        self.current_device_name = getattr(selected_device, 'FriendlyName', device_name)
        # Switching output devices invalidates any in-progress solo/isolate snapshot
        self.solo_active = False
        self.solo_channel = None
        self.solo_snapshot = {}

        try:
            dev_obj = selected_device._dev if hasattr(selected_device, '_dev') else selected_device
            interface = dev_obj.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self.volume_interface = cast(interface, POINTER(IAudioEndpointVolume))
            self.channel_count = self.volume_interface.GetChannelCount()

            # Activate and cache the peak meter interface
            try:
                meter_iface = dev_obj.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None)
                self.meter_interface = cast(meter_iface, POINTER(IAudioMeterInformation))
            except Exception as meter_err:
                print(f"Could not activate peak meter for device {device_name}: {meter_err}")
                self.meter_interface = None

            # Only engage 100% Master Volume Auto-Lock for Multi-channel 5.1 setups
            # If the device is Stereo (<= 2 channels, e.g. Headphones/Laptop), leave volume unlocked for user control
            if self.channel_count > 2:
                try:
                    self.volume_interface.SetMasterVolumeLevelScalar(1.0, None)
                except Exception:
                    pass
                self.start_master_volume_lock()
            else:
                self.stop_master_volume_lock()

            return True
        except Exception as e:
            print(f"Error activating device {device_name}: {e}")
            self.volume_interface = None
            self.meter_interface = None
            self.channel_count = 0
            return False

    def start_master_volume_lock(self):
        """Runs a background loop to keep Windows Endpoint Master Volume pinned at 100% on multi-channel setups."""
        if getattr(self, 'channel_count', 0) <= 2:
            self._master_lock_running = False
            return

        self._master_lock_running = True
        if hasattr(self, '_master_lock_thread') and self._master_lock_thread and self._master_lock_thread.is_alive():
            return

        def _lock_loop():
            safe_coinit()
            while getattr(self, '_master_lock_running', True) and getattr(self, 'channel_count', 0) > 2:
                try:
                    if self.volume_interface:
                        val = self.volume_interface.GetMasterVolumeLevelScalar()
                        if val < 0.999:
                            self.volume_interface.SetMasterVolumeLevelScalar(1.0, None)
                except Exception:
                    pass
                time.sleep(0.15)

        self._master_lock_thread = threading.Thread(target=_lock_loop, daemon=True)
        self._master_lock_thread.start()

    def stop_master_volume_lock(self):
        self._master_lock_running = False

    def get_master_volume(self):
        """Gets master volume scalar (0 to 100) and mute state."""
        safe_coinit()
        if not self.volume_interface:
            return 100, False
        try:
            val = self.volume_interface.GetMasterVolumeLevelScalar()
            muted = self.volume_interface.GetMute()
            return int(round(val * 100)), muted
        except Exception as e:
            print(f"Error reading master volume: {e}")
            return 100, False

    def set_master_volume(self, val):
        """Sets master volume from slider value (0 to 100)."""
        safe_coinit()
        if not self.volume_interface:
            return False
        try:
            self.volume_interface.SetMasterVolumeLevelScalar(val / 100.0, None)
            return True
        except Exception as e:
            print(f"Error setting master volume: {e}")
            return False

    # ------------------------------------------------------------------
    # Smooth Volume Ramping
    # ------------------------------------------------------------------
    def _ramp_scalar(self, key, get_fn, set_fn, target_scalar, steps=12, duration_ms=200):
        """
        Smoothly interpolates from the current hardware value to target_scalar
        over duration_ms milliseconds (split into `steps` equal steps).
        Runs entirely on a daemon background thread — never blocks the caller.
        If a ramp is already running for the same `key`, it is cancelled first.

        key     : int = channel index, 'master' = master volume.
        get_fn  : callable() -> current hardware scalar (0.0-1.0)
        set_fn  : callable(scalar) -> writes value to hardware
        """
        with self._ramp_lock:
            prev = self._ramp_events.get(key)
            if prev:
                prev.set()              # cancel any in-progress ramp for this key
            stop_evt = threading.Event()
            self._ramp_events[key] = stop_evt

        def _worker():
            try:
                safe_coinit()
                current = get_fn()
                step_delay = (duration_ms / 1000.0) / steps
                for i in range(1, steps + 1):
                    if stop_evt.is_set():
                        break
                    interp = current + (target_scalar - current) * (i / steps)
                    try:
                        set_fn(interp)
                    except Exception as hw_err:
                        print(f"[ramp] hw error (key={key}): {hw_err}")
                        break
                    time.sleep(step_delay)
            except Exception as e:
                print(f"[ramp] worker error (key={key}): {e}")
            finally:
                with self._ramp_lock:
                    if self._ramp_events.get(key) is stop_evt:
                        del self._ramp_events[key]

        threading.Thread(target=_worker, daemon=True).start()

    def ramp_channel_volume(self, idx, val, duration_ms=200, steps=12):
        """Smoothly fades channel `idx` to `val`% over `duration_ms` ms.
        Non-blocking — returns immediately; the fade runs on a background thread.
        A new call for the same channel cancels any ramp already in progress.
        """
        if not self.volume_interface:
            return
        if self.is_channel_locked(idx):
            val = 100
        target = val / 100.0
        self._ramp_scalar(
            key=idx,
            get_fn=lambda: self.volume_interface.GetChannelVolumeLevelScalar(idx),
            set_fn=lambda s: self.volume_interface.SetChannelVolumeLevelScalar(idx, s, None),
            target_scalar=target,
            steps=steps,
            duration_ms=duration_ms,
        )

    def ramp_master_volume(self, val, duration_ms=200, steps=12):
        """Smoothly fades master volume to `val`% over `duration_ms` ms.
        Non-blocking — returns immediately; the fade runs on a background thread.
        """
        if not self.volume_interface:
            return
        target = val / 100.0
        self._ramp_scalar(
            key='master',
            get_fn=lambda: self.volume_interface.GetMasterVolumeLevelScalar(),
            set_fn=lambda s: self.volume_interface.SetMasterVolumeLevelScalar(s, None),
            target_scalar=target,
            steps=steps,
            duration_ms=duration_ms,
        )

    def get_channel_volumes(self):
        """Gets volumes for each channel as percentages (0 to 100)."""
        safe_coinit()
        if not self.volume_interface:
            return []
        try:
            volumes = []
            for i in range(self.channel_count):
                if self.channel_count == 6 and i == 3:
                    # Lock subwoofer at 1.0 (100%) in hardware. Only issue the
                    # COM write when it has actually drifted (e.g. another app,
                    # or Windows itself, changed it) instead of on every single
                    # 600ms poll tick - avoids unnecessary COM churn / clicks.
                    current = self.volume_interface.GetChannelVolumeLevelScalar(3)
                    if round(current, 3) != 1.0:
                        self.volume_interface.SetChannelVolumeLevelScalar(3, 1.0, None)
                    volumes.append(100)
                else:
                    val = self.volume_interface.GetChannelVolumeLevelScalar(i)
                    volumes.append(int(round(val * 100)))
            return volumes
        except Exception as e:
            print(f"Error reading channel volumes: {e}")
            return []

    def set_channel_volume(self, idx, val):
        """Sets individual channel volume scalar from slider value (0 to 100)."""
        safe_coinit()
        if not self.volume_interface:
            return False
        # Lock subwoofer at 100% for 5.1 layouts
        if self.channel_count == 6 and idx == 3:
            val = 100
        try:
            self.volume_interface.SetChannelVolumeLevelScalar(idx, val / 100.0, None)
            return True
        except Exception as e:
            print(f"Error setting channel {idx} volume: {e}")
            return False

    def toggle_mute(self):
        """Toggles mute state, returns new state (True if muted, False otherwise)."""
        safe_coinit()
        if not self.volume_interface:
            return False
        try:
            current_mute = self.volume_interface.GetMute()
            new_mute = not current_mute
            self.volume_interface.SetMute(new_mute, None)
            return new_mute
        except Exception as e:
            print(f"Error toggling mute: {e}")
            return False

    def reset_balance(self, smooth=True, duration_ms=250):
        """Resets all channel volumes to 100%.
        smooth=True  (default) → smooth ramp over duration_ms, non-blocking.
        smooth=False → instant COM write (for internal/programmatic use).
        """
        safe_coinit()
        if not self.volume_interface:
            return False
        try:
            for i in range(self.channel_count):
                if smooth:
                    self.ramp_channel_volume(i, 100, duration_ms=duration_ms, steps=12)
                else:
                    self.volume_interface.SetChannelVolumeLevelScalar(i, 1.0, None)
            return True
        except Exception as e:
            print(f"Error resetting balance: {e}")
            return False

    def is_channel_locked(self, idx):
        """Subwoofer (LFE, channel index 3) is hardware-locked at 100% for 5.1 layouts."""
        return self.channel_count == 6 and idx == 3

    # ------------------------------------------------------------------
    # Solo / Isolate ("check speakers one by one")
    # ------------------------------------------------------------------
    def start_solo(self, idx):
        """
        Isolates a single channel: snapshots current volumes (once, on the
        first solo activation), pushes the target channel to 100% and mutes
        every other (non-locked) channel to 0%. Calling this again with a
        different idx just moves the isolation to the new channel while
        keeping the original snapshot, so the very first pre-solo levels are
        always what gets restored on stop_solo().
        """
        safe_coinit()
        if not self.volume_interface or idx < 0 or idx >= self.channel_count:
            return False
        try:
            if not self.solo_active:
                self.solo_snapshot = {
                    i: self.volume_interface.GetChannelVolumeLevelScalar(i)
                    for i in range(self.channel_count)
                }
            self.solo_active = True
            self.solo_channel = idx

            for i in range(self.channel_count):
                if self.is_channel_locked(i):
                    continue  # subwoofer always stays at its locked 100%
                target_pct = 100 if i == idx else 0
                # Smooth 150ms ramp — eliminates the "thump" from instant 0/100% jumps
                self.ramp_channel_volume(i, target_pct, duration_ms=150, steps=10)
            return True
        except Exception as e:
            print(f"Error starting solo on channel {idx}: {e}")
            return False

    def stop_solo(self):
        """Restores the channel levels captured before solo/isolate started."""
        safe_coinit()
        if not self.volume_interface:
            self.solo_active = False
            self.solo_channel = None
            self.solo_snapshot = {}
            return False
        try:
            for i, saved_scalar in self.solo_snapshot.items():
                if self.is_channel_locked(i):
                    continue
                target_pct = int(round(saved_scalar * 100))
                # Smooth 200ms fade back to the original pre-solo levels
                self.ramp_channel_volume(i, target_pct, duration_ms=200, steps=12)
            return True
        except Exception as e:
            print(f"Error restoring channels after solo: {e}")
            return False
        finally:
            self.solo_active = False
            self.solo_channel = None
            self.solo_snapshot = {}

    def get_solo_status(self):
        return {"active": self.solo_active, "channel": self.solo_channel}

    def play_channel_test(self, channel_idx):
        """Requests tone generator service to play a short test tone on specific channel."""
        from services.tone_generator import play_channel_test
        play_channel_test(channel_idx, self.channel_count, self.current_device_name)

    def get_profile_values(self, profile):
        """Returns dict of preset values based on layout and profile, loaded from config manager."""
        import config_manager
        profiles = config_manager.get("sound_profiles", {})
        raw_profile = profiles.get(profile, {"channels": {}, "master": None})
        
        # Convert channel keys from string to int
        channels = {int(k): v for k, v in raw_profile.get("channels", {}).items()}
        return {"channels": channels, "master": raw_profile.get("master")}

    def get_audio_peak(self):
        """Returns the real-time master peak audio level from Windows output (0.0 to 1.0)."""
        safe_coinit()
        if not hasattr(self, 'meter_interface') or not self.meter_interface:
            return 0.0
        try:
            return self.meter_interface.GetPeakValue()
        except Exception:
            return 0.0

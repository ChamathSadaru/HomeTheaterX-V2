import os
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL, CoInitialize
import numpy as np
import sounddevice as sd
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

            return True
        except Exception as e:
            print(f"Error activating device {device_name}: {e}")
            self.volume_interface = None
            self.meter_interface = None
            self.channel_count = 0
            return False

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

    def reset_balance(self):
        """Resets all channel volumes to 1.0 (100%)."""
        safe_coinit()
        if not self.volume_interface:
            return False
        try:
            for i in range(self.channel_count):
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
                target = 1.0 if i == idx else 0.0
                self.volume_interface.SetChannelVolumeLevelScalar(i, target, None)
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
            for i, val in self.solo_snapshot.items():
                if self.is_channel_locked(i):
                    continue
                self.volume_interface.SetChannelVolumeLevelScalar(i, val, None)
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

    def get_sounddevice_index(self, friendly_name):
        """Finds matching output device index in sounddevice using substrings."""
        try:
            devices = sd.query_devices()
            clean_name = friendly_name.lower().split('(')[0].strip()
            
            # Exact match
            for idx, dev in enumerate(devices):
                if dev['max_output_channels'] > 0:
                    if dev['name'] == friendly_name:
                        return idx
            
            # Substring match
            for idx, dev in enumerate(devices):
                if dev['max_output_channels'] > 0:
                    dev_name_clean = dev['name'].lower().split('(')[0].strip()
                    if clean_name in dev_name_clean or dev_name_clean in clean_name:
                        return idx
                        
            default_out = sd.default.device[1]
            return default_out if default_out is not None else 0
        except Exception as e:
            print(f"Error finding sounddevice index: {e}")
            try:
                return sd.default.device[1]
            except Exception:
                return 0

    def play_channel_test(self, channel_idx):
        """Generates a 0.8s 440Hz test sine wave with 100ms fadeout, playing it only on target channel."""
        if not self.current_device_name:
            return
        # Run in a daemon thread so the HTTP handler is not blocked
        import threading
        t = threading.Thread(target=self._play_channel_test_sync, args=(channel_idx,), daemon=True)
        t.start()

    def _play_channel_test_sync(self, channel_idx):
        """Synchronous tone playback (run on a background thread)."""
        try:
            sd_idx = self.get_sounddevice_index(self.current_device_name)

            duration = 0.8
            sample_rate = 44100

            if channel_idx == 3: # Subwoofer (Bass / LFE)
                frequency = 60.0
                t = np.linspace(0, duration, int(sample_rate * duration), False)
                
                # Generate a "dum dum" double-pulsed bass envelope
                envelope = np.zeros(len(t))
                p1_end = int(sample_rate * 0.35)
                t1 = t[:p1_end]
                envelope[:p1_end] = np.sin(np.pi * (t1 / 0.35)) ** 2
                
                p2_start = int(sample_rate * 0.4)
                p2_end = int(sample_rate * 0.75)
                t2 = t[p2_start:p2_end]
                envelope[p2_start:p2_end] = np.sin(np.pi * ((t2 - 0.4) / 0.35)) ** 2
                
                tone = np.sin(2 * np.pi * frequency * t) * 0.65 * envelope
            else:
                frequency = 440.0
                t = np.linspace(0, duration, int(sample_rate * duration), False)
                tone = np.sin(2 * np.pi * frequency * t) * 0.4
                # Fade out last 100ms to prevent clicking pops
                fade_len = int(sample_rate * 0.1)
                fade_out = np.linspace(1.0, 0.0, fade_len)
                tone[-fade_len:] *= fade_out

            # Create channel layout mapping
            data = np.zeros((len(tone), self.channel_count))
            if channel_idx < self.channel_count:
                data[:, channel_idx] = tone

            sd.play(data, sample_rate, device=sd_idx)
            sd.wait()  # Wait inside the thread so tones don't overlap
        except Exception as e:
            print(f"Error playing test tone: {e}")

    def get_profile_values(self, profile):
        """Returns dict of preset values based on layout and profile."""
        # Always return the full 5.1 (6 channel) profile layout,
        # which the web server will scale down to hardware channel limits
        if profile == "Movie":
            return {"channels": {0: 85, 1: 85, 2: 100, 3: 100, 4: 80, 5: 80}, "master": None}
        elif profile == "Music":
            return {"channels": {0: 100, 1: 100, 2: 70, 3: 100, 4: 80, 5: 80}, "master": None}
        elif profile == "Game":
            return {"channels": {0: 90, 1: 90, 2: 85, 3: 100, 4: 95, 5: 95}, "master": None}
        elif profile == "Night":
            return {"channels": {0: 75, 1: 75, 2: 95, 3: 100, 4: 70, 5: 70}, "master": 30}
        elif profile == "Concert":
            return {"channels": {0: 100, 1: 100, 2: 80, 3: 95, 4: 75, 5: 75}, "master": None}
        elif profile == "Vocal":
            return {"channels": {0: 60, 1: 60, 2: 100, 3: 50, 4: 40, 5: 40}, "master": None}
        elif profile == "Sports":
            return {"channels": {0: 80, 1: 80, 2: 100, 3: 85, 4: 90, 5: 90}, "master": None}
        elif profile == "Club":
            return {"channels": {0: 90, 1: 90, 2: 80, 3: 100, 4: 85, 5: 85}, "master": None}
        return {"channels": {}, "master": None}

    def get_audio_peak(self):
        """Returns the real-time master peak audio level from Windows output (0.0 to 1.0)."""
        safe_coinit()
        if not hasattr(self, 'meter_interface') or not self.meter_interface:
            return 0.0
        try:
            return self.meter_interface.GetPeakValue()
        except Exception:
            return 0.0

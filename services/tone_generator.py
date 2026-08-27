import os
import threading
import wave
import numpy as np
import sounddevice as sd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_DIR = os.path.join(BASE_DIR, "web", "audio")

VOICE_FILES = {
    0: "voice_front_left.wav",
    1: "voice_front_right.wav",
    2: "voice_center.wav",
    3: "voice_subwoofer.wav",
    4: "voice_surround_left.wav",
    5: "voice_surround_right.wav"
}

def get_sounddevice_index(friendly_name):
    """Finds matching output device index in sounddevice using substrings."""
    try:
        devices = sd.query_devices()
        if not friendly_name:
            default_out = sd.default.device[1]
            return default_out if default_out is not None else 0

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


def play_channel_test(channel_idx, channel_count, current_device_name):
    """Plays spoken voice announcement for the designated channel on a background thread."""
    t = threading.Thread(
        target=_play_channel_test_sync,
        args=(channel_idx, channel_count, current_device_name),
        daemon=True
    )
    t.start()


def _play_channel_test_sync(channel_idx, channel_count, current_device_name):
    """Synchronous audio playback with multi-channel routing and safe fallback."""
    try:
        wav_name = VOICE_FILES.get(channel_idx, "voice_center.wav")
        wav_path = os.path.join(AUDIO_DIR, wav_name)
        
        if not os.path.exists(wav_path):
            print(f"[Voice Announcer] Voice file not found: {wav_path}")
            return

        with wave.open(wav_path, "rb") as w:
            sample_rate = w.getframerate()
            n_frames = w.getnframes()
            audio_bytes = w.readframes(n_frames)
            audio_mono = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        sd_idx = get_sounddevice_index(current_device_name)
        dev_info = sd.query_devices(sd_idx)
        dev_channels = dev_info.get("max_output_channels", 2)
        
        actual_channels = max(2, min(int(channel_count or 6), int(dev_channels or 6)))
        
        # Multi-channel matrix
        output_buffer = np.zeros((len(audio_mono), actual_channels), dtype=np.float32)
        target_ch = min(int(channel_idx), actual_channels - 1)
        output_buffer[:, target_ch] = audio_mono

        sd.play(output_buffer, sample_rate, device=sd_idx)
        sd.wait()
    except Exception as e:
        print(f"[Voice Announcer] Playback fallback error: {e}")

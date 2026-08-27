import threading
import numpy as np
import sounddevice as sd

def get_sounddevice_index(friendly_name):
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


def play_channel_test(channel_idx, channel_count, current_device_name):
    """Generates a 0.8s 440Hz test sine wave with 100ms fadeout, playing it only on target channel."""
    if not current_device_name:
        return
    # Run in a daemon thread so the caller is not blocked
    t = threading.Thread(
        target=_play_channel_test_sync,
        args=(channel_idx, channel_count, current_device_name),
        daemon=True
    )
    t.start()


def _play_channel_test_sync(channel_idx, channel_count, current_device_name):
    """Synchronous tone playback (run on a background thread)."""
    try:
        sd_idx = get_sounddevice_index(current_device_name)

        duration = 0.8
        sample_rate = 44100

        if channel_idx == 3:  # Subwoofer (Bass / LFE)
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
        data = np.zeros((len(tone), channel_count))
        if channel_idx < channel_count:
            data[:, channel_idx] = tone

        sd.play(data, sample_rate, device=sd_idx)
        sd.wait()  # Wait inside the thread so tones don't overlap
    except Exception as e:
        print(f"Error playing test tone: {e}")

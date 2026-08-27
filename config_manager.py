"""
config_manager.py
------------------
Very small JSON-file-backed settings store, so user preferences (native
notifications on/off, launch-on-startup, last selected device, crossover
frequency, etc.) survive an app restart. This was previously missing -
every setting reset back to defaults each time the app launched.
"""

import json
import os
import threading

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

_DEFAULTS = {
    "notifications_enabled": True,
    "launch_on_startup": False,
    "last_device": None,
    "crossover_hz": 80,
    "minimize_to_tray_on_close": True,
    "calibration_enabled": True,
    "calibration_focus_x": 200,
    "calibration_focus_y": 240,
    "calibration_delays": {
        "surroundL": 24,
        "towerL": 20,
        "center": 12,
        "subwoofer": 36,
        "towerR": 20,
        "surroundR": 24
    },
    "calibration_gains": {
        "surroundL": 0.0,
        "towerL": 0.0,
        "center": 0.0,
        "subwoofer": 0.0,
        "towerR": 0.0,
        "surroundR": 0.0
    },
    "calibration_eq": {
        "bass": 2.0,
        "mid": 0.0,
        "treble": 1.5
    },
    "calibration_mode": "sweetspot",
    "active_preset": None,
    "preset_prev_state": None,
    "active_profile": "Movie",
    "user_preset_channels": {
        "surroundL": 100,
        "towerL": 100,
        "center": 100,
        "subwoofer": 100,
        "towerR": 100,
        "surroundR": 100
    },
    "user_preset_master": 85,
    "access_token": "SamsungAudioscapeSecureToken7777",
    "sound_profiles": {
        "Movie": {"channels": {"0": 85, "1": 85, "2": 100, "3": 100, "4": 80, "5": 80}, "master": None},
        "Music": {"channels": {"0": 100, "1": 100, "2": 70, "3": 100, "4": 80, "5": 80}, "master": None},
        "Game": {"channels": {"0": 90, "1": 90, "2": 85, "3": 100, "4": 95, "5": 95}, "master": None},
        "Night": {"channels": {"0": 75, "1": 75, "2": 95, "3": 100, "4": 70, "5": 70}, "master": 30},
        "Concert": {"channels": {"0": 100, "1": 100, "2": 80, "3": 95, "4": 75, "5": 75}, "master": None},
        "Vocal": {"channels": {"0": 60, "1": 60, "2": 100, "3": 50, "4": 40, "5": 40}, "master": None},
        "Sports": {"channels": {"0": 80, "1": 80, "2": 100, "3": 85, "4": 90, "5": 90}, "master": None},
        "Club": {"channels": {"0": 90, "1": 90, "2": 80, "3": 100, "4": 85, "5": 85}, "master": None}
    }
}

# Bug Fix #3: Use RLock so the same thread can re-acquire the lock
# without deadlocking when _load() is called inside set()/update()
# which then calls _save() — both of which acquire _lock.
_lock = threading.RLock()
_cache = None


def _load():
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
        data = dict(_DEFAULTS)
        try:
            if os.path.exists(_CONFIG_PATH):
                with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if isinstance(saved, dict):
                        data.update(saved)
        except Exception as e:
            print(f"Error loading config.json, using defaults: {e}")
        _cache = data
        return _cache


def _save():
    with _lock:
        try:
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(_cache, f, indent=2)
        except Exception as e:
            print(f"Error saving config.json: {e}")


def get(key, default=None):
    data = _load()
    return data.get(key, default)


def get_all():
    return dict(_load())


def set(key, value):
    data = _load()
    with _lock:
        data[key] = value
    _save()
    return data[key]


def update(partial: dict):
    data = _load()
    with _lock:
        data.update(partial)
    _save()
    return dict(data)

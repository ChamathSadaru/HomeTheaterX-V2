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
    "calibration_eq": {
        "bass": 2.0,
        "mid": 0.0,
        "treble": 1.5
    },
    "active_profile": "Movie",
    "user_preset_channels": {
        "surroundL": 100,
        "towerL": 100,
        "center": 100,
        "subwoofer": 100,
        "towerR": 100,
        "surroundR": 100
    },
    "user_preset_master": 85
}

_lock = threading.Lock()
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

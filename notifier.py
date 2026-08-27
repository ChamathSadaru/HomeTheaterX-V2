"""
notifier.py
-----------
Sends native Windows toast notifications for the Samsung HT-F4B3 Audioscape
Controller. Falls back gracefully (prints to console) on non-Windows
platforms or if no supported notification backend is installed, so the
rest of the app never crashes because of a missing notification library.

Supported backends (tried in this order):
    1. winotify   (pure-python, no COM/async headaches, Win10/11 Action Center)
    2. win11toast (WinRT based, richer toasts)
    3. plyer      (cross-platform fallback)
Install at least one of these on the target machine:
    pip install winotify
"""

import os
import sys
import threading
import time

_IS_WINDOWS = sys.platform.startswith("win")

# Simple rate-limiter so a chatty UI (e.g. someone hammering the locked
# subwoofer slider) cannot spam the Windows notification center.
_last_sent = {}
_RATE_LIMIT_SECONDS = 2.5
_lock = threading.Lock()

_ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Splash.jpg")


def _rate_limited(key):
    with _lock:
        now = time.time()
        last = _last_sent.get(key, 0)
        if now - last < _RATE_LIMIT_SECONDS:
            return True
        _last_sent[key] = now
        return False


def _send_winotify(title, message):
    from winotify import Notification
    toast = Notification(
        app_id="HomeTheaterX",
        title=title,
        msg=message,
        icon=_ICON_PATH if os.path.exists(_ICON_PATH) else ""
    )
    toast.show()
    return True


def _send_win11toast(title, message):
    from win11toast import notify as w11_notify
    w11_notify(title, message, icon=_ICON_PATH if os.path.exists(_ICON_PATH) else None)
    return True


def _send_plyer(title, message):
    from plyer import notification as plyer_notification
    plyer_notification.notify(title=title, message=message, timeout=5)
    return True


def notify(title, message, dedupe_key=None):
    """
    Fire a native OS notification. Runs in a background thread so a slow
    or blocking notification backend never stalls the HTTP request that
    triggered it.

    dedupe_key: optional string used to rate-limit noisy/repeated
    notifications (e.g. repeated attempts to drag the locked subwoofer
    slider). If omitted, the title is used as the key.
    """
    key = dedupe_key or title
    if _rate_limited(key):
        return False

    def _worker():
        if not _IS_WINDOWS:
            print(f"[notify:non-windows] {title} - {message}")
            return

        for sender in (_send_winotify, _send_win11toast, _send_plyer):
            try:
                if sender(title, message):
                    return
            except Exception:
                continue

        # Nothing worked (no backend installed) - degrade quietly.
        print(f"[notify:fallback] {title} - {message}")

    threading.Thread(target=_worker, daemon=True).start()
    return True

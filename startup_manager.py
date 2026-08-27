"""
startup_manager.py
-------------------
Registers / unregisters the Samsung HT-F4B3 Audioscape Controller to launch
automatically when Windows starts, using the per-user registry Run key:

    HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run

This does not require admin rights (per-user key) and does not touch any
system-wide startup folder, so it is safe to toggle from inside the app.
"""

import os
import sys

APP_NAME = "HomeTheaterXController"
_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

_IS_WINDOWS = sys.platform.startswith("win")


def _get_launch_command():
    """
    Builds the command line used to relaunch the app.
    - If frozen (PyInstaller .exe build) -> point straight at the exe.
    - Otherwise -> "pythonw.exe <path-to-web_server.py>" (pythonw avoids a
      console window flashing up on login).
    """
    if getattr(sys, "frozen", False):
        exe = sys.executable
        return f'"{exe}"'

    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_server.py")
    python_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(python_dir, "pythonw.exe")
    interpreter = pythonw if os.path.exists(pythonw) else sys.executable
    return f'"{interpreter}" "{script_path}"'


def is_startup_enabled():
    if not _IS_WINDOWS:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False
    except Exception as e:
        print(f"Error checking startup status: {e}")
        return False


def enable_startup():
    if not _IS_WINDOWS:
        print("Startup registration is only supported on Windows.")
        return False
    try:
        import winreg
        command = _get_launch_command()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
        return True
    except Exception as e:
        print(f"Error enabling startup: {e}")
        return False


def disable_startup():
    if not _IS_WINDOWS:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        return True
    except Exception as e:
        print(f"Error disabling startup: {e}")
        return False


def set_startup(enabled):
    return enable_startup() if enabled else disable_startup()

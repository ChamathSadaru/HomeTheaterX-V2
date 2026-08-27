import subprocess
import time

def _get_target_device_name(preferred_name=None):
    """Dynamically resolves the active audio device name without hardcoding."""
    if preferred_name:
        return preferred_name
    try:
        import config_manager
        saved = config_manager.get("last_device")
        if saved:
            return saved
    except Exception:
        pass
    try:
        from pycaw.pycaw import AudioUtilities
        speakers = AudioUtilities.GetSpeakers()
        if hasattr(speakers, "FriendlyName") and speakers.FriendlyName:
            return speakers.FriendlyName
    except Exception:
        pass
    return "Samsung Home Theater 5.1"


def check_dolby_state(target_device_name=None):
    """
    Launches control mmsys.cpl, parses the Sound control panel UI using pywinauto,
    dynamically searches for the active device, determines if Dolby Digital Live is currently 'ON',
    and gracefully handles devices without a Dolby tab (e.g. Stereo/Headphones).
    """
    from pywinauto import Application
    
    device_name = _get_target_device_name(target_device_name)
    clean_target = device_name.split("(")[0].strip().lower()

    subprocess.Popen("control mmsys.cpl", shell=True)
    time.sleep(1.2)
    
    state = False
    try:
        app = Application(backend="win32").connect(title="Sound", timeout=5)
        sound_win = app.window(title="Sound")
        device_list = sound_win.child_window(class_name="SysListView32", control_id=1000)
        
        target_idx = None
        # 1. Match by clean target device name
        for idx in range(device_list.item_count()):
            item_text = device_list.get_item(idx).text().lower()
            if clean_target in item_text:
                target_idx = idx
                break
        
        # 2. Fallback: match by keywords or default device mark
        if target_idx is None:
            for idx in range(device_list.item_count()):
                item_text = device_list.get_item(idx).text().lower()
                if "default" in item_text or "home theater" in item_text or "5.1" in item_text:
                    target_idx = idx
                    break

        if target_idx is not None:
            device_list.get_item(target_idx).select()
            time.sleep(0.5)
            prop_btn = sound_win.child_window(title="&Properties", class_name="Button", control_id=1003)
            prop_btn.click()
            time.sleep(1.5)
            
            # Dynamic window regex matching any device properties window
            prop_app = Application(backend="win32").connect(title_re=".*Properties.*", timeout=5)
            prop_win = prop_app.window(title_re=".*Properties.*")
            
            tab_ctrl = prop_win.child_window(class_name="SysTabControl32")
            dolby_idx = None
            for t_idx in range(tab_ctrl.tab_count()):
                if "Dolby" in tab_ctrl.get_tab_text(t_idx):
                    dolby_idx = t_idx
                    break
                    
            if dolby_idx is not None:
                tab_ctrl.select(dolby_idx)
                time.sleep(1.0)
                
                try:
                    dolby_btn = prop_win.child_window(title_re=".*Dolby.*", class_name="Button")
                    btn_text = dolby_btn.window_text()
                    if "ON" in btn_text:
                        state = True
                except Exception:
                    pass
            prop_win.close()
        sound_win.close()
    except Exception as e:
        print(f"[check_dolby_state] Error: {e}")
        try:
            sound_win.close()
        except Exception:
            pass
    return state


def toggle_dolby_in_system(target_device_name=None):
    """
    Automates clicking the Dolby Digital Plus button in the Sound Properties window
    to toggle Dolby Digital Live on/off for the dynamically detected active device.
    """
    from pywinauto import Application
    
    device_name = _get_target_device_name(target_device_name)
    clean_target = device_name.split("(")[0].strip().lower()

    subprocess.Popen("control mmsys.cpl", shell=True)
    time.sleep(1.2)
    
    success = False
    new_state = False
    try:
        app = Application(backend="win32").connect(title="Sound", timeout=5)
        sound_win = app.window(title="Sound")
        device_list = sound_win.child_window(class_name="SysListView32", control_id=1000)
        
        target_idx = None
        for idx in range(device_list.item_count()):
            item_text = device_list.get_item(idx).text().lower()
            if clean_target in item_text:
                target_idx = idx
                break
                
        if target_idx is None:
            for idx in range(device_list.item_count()):
                item_text = device_list.get_item(idx).text().lower()
                if "default" in item_text or "home theater" in item_text or "5.1" in item_text:
                    target_idx = idx
                    break

        if target_idx is not None:
            device_list.get_item(target_idx).select()
            time.sleep(0.5)
            prop_btn = sound_win.child_window(title="&Properties", class_name="Button", control_id=1003)
            prop_btn.click()
            time.sleep(1.5)
            
            prop_app = Application(backend="win32").connect(title_re=".*Properties.*", timeout=5)
            prop_win = prop_app.window(title_re=".*Properties.*")
            
            tab_ctrl = prop_win.child_window(class_name="SysTabControl32")
            dolby_idx = None
            for t_idx in range(tab_ctrl.tab_count()):
                if "Dolby" in tab_ctrl.get_tab_text(t_idx):
                    dolby_idx = t_idx
                    break
                    
            if dolby_idx is not None:
                tab_ctrl.select(dolby_idx)
                time.sleep(1.0)
                
                dolby_btn = prop_win.child_window(title_re=".*Dolby.*", class_name="Button")
                dolby_btn.click()
                time.sleep(0.5)
                
                new_text = dolby_btn.window_text()
                new_state = "ON" in new_text
                
                apply_btn = prop_win.child_window(title="&Apply", class_name="Button")
                if apply_btn.is_enabled():
                    apply_btn.click()
                    time.sleep(0.5)
                
                ok_btn = prop_win.child_window(title="OK", class_name="Button")
                ok_btn.click()
                success = True
            else:
                prop_win.close()
        sound_win.close()
    except Exception as e:
        print(f"[toggle_dolby_in_system] Error: {e}")
        try:
            sound_win.close()
        except Exception:
            pass
    return success, new_state


def async_check_dolby(on_complete_callback, target_device_name=None):
    """
    Runs check_dolby_state on a background thread with COM initialized,
    triggering the provided callback with the result.
    """
    import threading
    def _run():
        try:
            import comtypes
            comtypes.CoInitialize()
            state = check_dolby_state(target_device_name)
            on_complete_callback(state)
            comtypes.CoUninitialize()
        except Exception as e:
            print(f"Error checking Dolby in background thread: {e}")

    threading.Thread(target=_run, daemon=True).start()

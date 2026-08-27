import subprocess
import time

def check_dolby_state():
    """
    Launches control mmsys.cpl, parses the Sound control panel UI using pywinauto,
    determines if Dolby Digital Live is currently 'ON', and cleans up.
    """
    from pywinauto import Application
    
    subprocess.Popen("control mmsys.cpl", shell=True)
    time.sleep(1.2)
    
    state = False
    try:
        app = Application(backend="win32").connect(title="Sound", timeout=5)
        sound_win = app.window(title="Sound")
        device_list = sound_win.child_window(class_name="SysListView32", control_id=1000)
        
        target_idx = None
        for idx in range(device_list.item_count()):
            if "Samsung Home Theater 5.1" in device_list.get_item(idx).text():
                target_idx = idx
                break
                
        if target_idx is not None:
            device_list.get_item(target_idx).select()
            time.sleep(0.5)
            prop_btn = sound_win.child_window(title="&Properties", class_name="Button", control_id=1003)
            prop_btn.click()
            time.sleep(1.5)
            
            prop_app = Application(backend="win32").connect(title_re=".*Samsung Home Theater 5.1 Properties.*", timeout=5)
            prop_win = prop_app.window(title_re=".*Samsung Home Theater 5.1 Properties.*")
            
            tab_ctrl = prop_win.child_window(class_name="SysTabControl32")
            dolby_idx = None
            for t_idx in range(tab_ctrl.tab_count()):
                if "Dolby" in tab_ctrl.get_tab_text(t_idx):
                    dolby_idx = t_idx
                    break
                    
            if dolby_idx is not None:
                tab_ctrl.select(dolby_idx)
                time.sleep(1.0)
                
                dolby_btn = prop_win.child_window(title_re=".*Dolby Digital Plus.*", class_name="Button")
                btn_text = dolby_btn.window_text()
                if "ON" in btn_text:
                    state = True
            prop_win.close()
        sound_win.close()
    except Exception as e:
        print(f"[check_dolby_state] Error: {e}")
        try:
            sound_win.close()
        except Exception:
            pass
    return state


def toggle_dolby_in_system():
    """
    Automates clicking the Dolby Digital Plus button in the Sound Properties window
    to toggle Dolby Digital Live on/off, applies changes, and saves state.
    """
    from pywinauto import Application
    
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
            if "Samsung Home Theater 5.1" in device_list.get_item(idx).text():
                target_idx = idx
                break
                
        if target_idx is not None:
            device_list.get_item(target_idx).select()
            time.sleep(0.5)
            prop_btn = sound_win.child_window(title="&Properties", class_name="Button", control_id=1003)
            prop_btn.click()
            time.sleep(1.5)
            
            prop_app = Application(backend="win32").connect(title_re=".*Samsung Home Theater 5.1 Properties.*", timeout=5)
            prop_win = prop_app.window(title_re=".*Samsung Home Theater 5.1 Properties.*")
            
            tab_ctrl = prop_win.child_window(class_name="SysTabControl32")
            dolby_idx = None
            for t_idx in range(tab_ctrl.tab_count()):
                if "Dolby" in tab_ctrl.get_tab_text(t_idx):
                    dolby_idx = t_idx
                    break
                    
            if dolby_idx is not None:
                tab_ctrl.select(dolby_idx)
                time.sleep(1.0)
                
                dolby_btn = prop_win.child_window(title_re=".*Dolby Digital Plus.*", class_name="Button")
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


def async_check_dolby(on_complete_callback):
    """
    Runs check_dolby_state on a background thread with COM initialized,
    triggering the provided callback with the result.
    """
    import threading
    def _run():
        try:
            import comtypes
            comtypes.CoInitialize()
            state = check_dolby_state()
            on_complete_callback(state)
            comtypes.CoUninitialize()
        except Exception as e:
            print(f"Error checking Dolby in background thread: {e}")

    threading.Thread(target=_run, daemon=True).start()

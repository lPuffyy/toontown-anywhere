"""Removes the installed app: the Start menu and desktop shortcuts, the entry in Windows' app list, the program folder and (if the player
says so) the downloaded game files and settings. Run as `TTAnywhere.exe --uninstall` (the app list's Uninstall button does this)."""
import os
import shutil
import subprocess
import sys

REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\TTAnywhere"
SHORTCUT_NAME = "Toontown Anywhere.lnk"


def shortcut_paths():
    start = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", SHORTCUT_NAME)
    desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop", SHORTCUT_NAME)
    return [start, desktop]


def ask_yes_no(title, text):
    """True for Yes. A plain Windows message box (the app has no console)."""
    try:
        import ctypes
        return ctypes.windll.user32.MessageBoxW(0, text, title, 0x24) == 6        # MB_YESNO | MB_ICONQUESTION -> IDYES
    except Exception:
        return False


def run(silent=False, keep_data=None):
    import winreg
    from .settings import data_dir
    app = os.path.dirname(sys.executable)
    if keep_data is None:
        if silent:
            keep_data = True
        else:
            delete = ask_yes_no("Uninstall Toontown: Anywhere", "Also delete the downloaded game files and your saved settings (about 1 GB)?\n\n"
                                                                "Choose No to keep them for a later reinstall.")
            keep_data = not delete
    for p in shortcut_paths():
        try:
            os.remove(p)
        except OSError:
            pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_KEY)
    except OSError:
        pass
    data = data_dir()
    # the program folder holds this running program, so a script removes it once this program has closed
    bat = os.path.join(os.environ.get("TEMP", data), "tta-uninstall.bat")
    lines = ["@echo off", 'powershell -NoProfile -Command "try { Wait-Process -Id %d -Timeout 60 } catch {}"' % os.getpid(),
             'rmdir /S /Q "%s"' % app]
    if not keep_data:
        lines.append('rmdir /S /Q "%s"' % data)
    lines.append('del "%~f0"')
    with open(bat, "w") as f:
        f.write("\r\n".join(lines) + "\r\n")
    DETACHED, NEW_GROUP = 0x00000008, 0x00000200
    subprocess.Popen(["cmd", "/c", bat], creationflags=DETACHED | NEW_GROUP, close_fds=True)
    if not silent:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, "Toontown: Anywhere has been removed.", "Uninstall", 0x40)
        except Exception:
            pass
    os._exit(0)

"""Setup program for the Windows app (built by build_windows.py into TTAnywhere-Setup-<version>.exe, with the app's zip inside it).

Installs for the current user only (no administrator needed) into %LOCALAPPDATA%\\Programs\\TTAnywhere, adds a Start menu shortcut (and a
desktop one), and an entry in Windows' app list whose Uninstall button runs `TTAnywhere.exe --uninstall`.

Options (for scripts and testing):  --silent   --dir FOLDER   --no-shortcuts   --no-launch   --desktop-shortcut
"""
import argparse
import os
import subprocess
import sys
import threading
import zipfile

APP_NAME = "Toontown: Anywhere"
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\TTAnywhere"
SHORTCUT = "Toontown Anywhere.lnk"


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def find_zip():
    p = resource("app.zip")
    if os.path.exists(p):
        return p
    import glob
    dist = glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "TTAnywhere-*-windows.zip"))
    return dist[-1] if dist else None


def default_dir():
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Programs", "TTAnywhere")


def make_shortcut(path, target, workdir, icon):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ps = ('$s = (New-Object -ComObject WScript.Shell).CreateShortcut("%s"); $s.TargetPath = "%s"; $s.WorkingDirectory = "%s"; '
          '$s.IconLocation = "%s"; $s.Description = "Toontown: Anywhere"; $s.Save()') % (path, target, workdir, icon)
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False, creationflags=0x08000000)


def install(target, shortcuts=True, desktop=False, progress=lambda frac, text: None):
    zpath = find_zip()
    if not zpath:
        raise RuntimeError("The setup file is damaged (the app is missing).")
    with zipfile.ZipFile(zpath) as z:
        infos = [i for i in z.infolist() if not i.filename.endswith("/")]
        total = sum(i.file_size for i in infos) or 1
        done = 0
        for info in infos:
            rel = info.filename.split("/", 1)[1] if "/" in info.filename else info.filename     # drop the leading TTAnywhere/
            dest = os.path.normpath(os.path.join(target, rel))
            if not dest.startswith(os.path.normpath(target) + os.sep):
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(info) as src, open(dest, "wb") as out:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    progress(done / total * 0.9, "Installing...")
    exe = os.path.join(target, "TTAnywhere.exe")
    version = open(os.path.join(target, "VERSION.txt")).read().strip() if os.path.exists(os.path.join(target, "VERSION.txt")) else ""
    progress(0.93, "Adding shortcuts...")
    if shortcuts:
        start = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", SHORTCUT)
        make_shortcut(start, exe, target, exe)
        if desktop:
            make_shortcut(os.path.join(os.environ.get("USERPROFILE", ""), "Desktop", SHORTCUT), exe, target, exe)
    progress(0.97, "Registering...")
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
        for name, value in (("DisplayName", APP_NAME), ("DisplayVersion", version), ("Publisher", "Toontown: Anywhere"),
                            ("InstallLocation", target), ("DisplayIcon", exe), ("UninstallString", '"%s" --uninstall' % exe),
                            ("QuietUninstallString", '"%s" --uninstall --silent' % exe)):
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
    progress(1.0, "Done.")
    return exe


def running_in(target):
    """True if the app is running from the folder being installed over (its files cannot be replaced then)."""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              '(Get-Process TTAnywhere -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "%s*" }).Count' % target],
                             capture_output=True, text=True, creationflags=0x08000000).stdout.strip()
        return out not in ("", "0")
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--silent", action="store_true")
    ap.add_argument("--dir", default=default_dir())
    ap.add_argument("--no-shortcuts", action="store_true")
    ap.add_argument("--no-launch", action="store_true")
    ap.add_argument("--desktop-shortcut", action="store_true")
    a = ap.parse_args()
    target = os.path.abspath(a.dir)

    if a.silent:
        exe = install(target, not a.no_shortcuts, a.desktop_shortcut)
        if not a.no_launch:
            subprocess.Popen([exe], cwd=target)
        return 0

    import tkinter as tk
    from tkinter import messagebox, ttk
    root = tk.Tk()
    root.title("Toontown: Anywhere Setup")
    root.geometry("460x230")
    root.resizable(False, False)
    root.configure(bg="#489cf0")
    tk.Label(root, text="TOONTOWN: ANYWHERE", font=("Segoe UI", 18, "bold"), fg="#ffd926", bg="#489cf0").pack(pady=(18, 4))
    msg = tk.StringVar(value="This installs the game for your account.\nThe game files (about 400 MB) download the first time you play.")
    tk.Label(root, textvariable=msg, font=("Segoe UI", 10), fg="white", bg="#489cf0", justify="center").pack(pady=4)
    bar = ttk.Progressbar(root, length=380, maximum=100)
    bar.pack(pady=10)
    desk = tk.BooleanVar(value=True)
    tk.Checkbutton(root, text="Add a desktop shortcut", variable=desk, bg="#489cf0", fg="white", selectcolor="#2d6fc0",
                   activebackground="#489cf0", activeforeground="white").pack()
    btn = tk.Button(root, text="Install", width=14, font=("Segoe UI", 10, "bold"))
    btn.pack(pady=8)
    state = {"exe": None}

    def progress(frac, text):
        root.after(0, lambda: (bar.configure(value=frac * 100), msg.set(text)))

    def work():
        try:
            state["exe"] = install(target, True, desk.get(), progress)
            root.after(0, finished)
        except Exception as e:
            root.after(0, lambda: (messagebox.showerror("Setup", "Setup could not finish:\n%s" % e), root.destroy()))

    def finished():
        msg.set("Installed. Have fun!")
        btn.configure(text="Play", state="normal", command=lambda: (subprocess.Popen([state["exe"]], cwd=target), root.destroy()))

    def start():
        if running_in(target):
            messagebox.showinfo("Setup", "Toontown: Anywhere is running. Close it and press Install again.")
            return
        btn.configure(state="disabled")
        threading.Thread(target=work, daemon=True).start()
    btn.configure(command=start)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

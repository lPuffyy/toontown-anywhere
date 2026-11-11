"""Builds the Windows app: a folder with TTAnywhere.exe (PyInstaller, one-folder). The game's own code is NOT in it: it is downloaded on first
start (and updated) like the browser version's, so the app only carries Python, Panda3D and the launcher. Because that downloaded
code can import any standard-library module, the whole standard library is included.

    .venv\\Scripts\\pip install pyinstaller
    .venv\\Scripts\\python build_windows.py            ->  dist\\TTAnywhere\\TTAnywhere.exe  and  dist\\TTAnywhere-<version>-windows.zip
"""
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tta_native import __version__          # noqa: E402

SKIP = {"tkinter", "turtle", "turtledemo", "idlelib", "test", "lib2to3", "ensurepip", "venv", "this", "antigravity", "__main__",
        "_tkinter", "pydoc_data", "distutils", "msilib", "nt", "winreg_extra"}


def stdlib_modules():
    names = sorted(n for n in sys.stdlib_module_names if n not in SKIP and not n.startswith("_test"))
    return names


def sync_shared():
    """native/tta_native/controls.py is the browser's web/game/webui_core.py (the game-control and chat-helper logic both clients share);
    it is regenerated from it here so the native copy can never drift. `python build_windows.py --check-shared` only checks (for CI)."""
    src = os.path.join(HERE, "..", "web", "game", "webui_core.py")
    dst = os.path.join(HERE, "tta_native", "controls.py")
    with open(src, encoding="utf8", newline="") as f:
        text = f.read().replace(chr(13) + chr(10), chr(10))
    head = text.split(chr(10), 1)[0]
    new = ('"""Game-control logic shared with the browser version (generated from web/game/webui_core.py by build_windows.py; do not edit):\n'
           "drives the game's own input states and camera calls. The native client's controller support and chat helpers use it the way\n"
           'the web page\'s touch controls do."""') + text[len(head):]
    spec_src = os.path.join(HERE, "..", "shared", "settings-spec.json")
    spec_dst = os.path.join(HERE, "tta_native", "settings-spec.json")
    with open(spec_src, encoding="utf8", newline="") as f:
        spec_text = f.read().replace(chr(13) + chr(10), chr(10))
    spec_cur = ""
    if os.path.exists(spec_dst):
        with open(spec_dst, encoding="utf8", newline="") as f:
            spec_cur = f.read().replace(chr(13) + chr(10), chr(10))
    if spec_cur != spec_text:
        if "--check-shared" in sys.argv:
            sys.exit("native/tta_native/settings-spec.json is out of date: run build_windows.py to copy it from shared/settings-spec.json")
        with open(spec_dst, "w", encoding="utf8", newline=chr(10)) as f:
            f.write(spec_text)
        print("copied settings-spec.json from shared/")
    hud_src = os.path.join(HERE, "..", "web", "game", "hud.py")
    hud_dst = os.path.join(HERE, "tta_native", "hud.py")
    with open(hud_src, encoding="utf8", newline="") as f:
        hud_text = f.read().replace(chr(13) + chr(10), chr(10))
    hud_cur = ""
    if os.path.exists(hud_dst):
        with open(hud_dst, encoding="utf8", newline="") as f:
            hud_cur = f.read().replace(chr(13) + chr(10), chr(10))
    if hud_cur != hud_text:
        if "--check-shared" in sys.argv:
            sys.exit("native/tta_native/hud.py is out of date: run build_windows.py to copy it from web/game/hud.py")
        with open(hud_dst, "w", encoding="utf8", newline=chr(10)) as f:
            f.write(hud_text)
        print("copied hud.py from web/game/")
    cur = ""
    if os.path.exists(dst):
        with open(dst, encoding="utf8", newline="") as f:
            cur = f.read().replace(chr(13) + chr(10), chr(10))
    if cur != new:
        if "--check-shared" in sys.argv:
            sys.exit("native/tta_native/controls.py is out of date: run build_windows.py to regenerate it from web/game/webui_core.py")
        with open(dst, "w", encoding="utf8", newline=chr(10)) as f:
            f.write(new)
        print("regenerated controls.py from webui_core.py")


def main():
    sync_shared()
    if "--check-shared" in sys.argv:
        print("controls.py matches webui_core.py")
        return
    import PyInstaller.__main__ as pi
    args = [os.path.join(HERE, "run_tta.py"), "--name", "TTAnywhere", "--noconfirm", "--clean", "--onedir",
            "--noconsole", "--paths", HERE, "--add-data", os.path.join(HERE, "tta_native", "settings-spec.json") + os.pathsep + "tta_native", "--collect-all", "panda3d", "--collect-all", "direct", "--collect-submodules", "websocket",
            "--distpath", os.path.join(HERE, "dist"), "--workpath", os.path.join(HERE, "build"), "--specpath", os.path.join(HERE, "build")]
    for n in stdlib_modules():
        args += ["--hidden-import", n]
    icon = os.path.join(HERE, "tta.ico")
    if os.path.exists(icon):
        args += ["--icon", icon]
    pi.run(args)
    out = os.path.join(HERE, "dist", "TTAnywhere")
    with open(os.path.join(out, "VERSION.txt"), "w") as f:
        f.write(__version__ + "\n")
    zpath = os.path.join(HERE, "dist", "TTAnywhere-%s-windows.zip" % __version__)
    if os.path.exists(zpath):
        os.remove(zpath)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, _dirs, files in os.walk(out):
            for fn in files:
                full = os.path.join(root, fn)
                z.write(full, os.path.join("TTAnywhere", os.path.relpath(full, out)))
    print("built", out, "and", zpath, "%.0f MB" % (os.path.getsize(zpath) / 1048576))
    build_installer(zpath)


def build_installer(zpath):
    """TTAnywhere-Setup-<version>.exe: one file that installs the app zip for the current user (see installer.py)."""
    import PyInstaller.__main__ as pi
    stage = os.path.join(HERE, "build", "installer-data")
    os.makedirs(stage, exist_ok=True)
    shutil.copyfile(zpath, os.path.join(stage, "app.zip"))
    args = [os.path.join(HERE, "installer.py"), "--name", "TTAnywhere-Setup-%s" % __version__, "--noconfirm", "--onefile", "--noconsole",
            "--add-data", os.path.join(stage, "app.zip") + os.pathsep + ".", "--distpath", os.path.join(HERE, "dist"),
            "--workpath", os.path.join(HERE, "build", "installer"), "--specpath", os.path.join(HERE, "build")]
    icon = os.path.join(HERE, "tta.ico")
    if os.path.exists(icon):
        args += ["--icon", icon]
    pi.run(args)
    print("built", os.path.join(HERE, "dist", "TTAnywhere-Setup-%s.exe" % __version__))


if __name__ == "__main__":
    main()

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


def main():
    import PyInstaller.__main__ as pi
    args = [os.path.join(HERE, "run_tta.py"), "--name", "TTAnywhere", "--noconfirm", "--clean", "--onedir",
            "--noconsole", "--paths", HERE, "--collect-all", "panda3d", "--collect-all", "direct", "--collect-submodules", "websocket",
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

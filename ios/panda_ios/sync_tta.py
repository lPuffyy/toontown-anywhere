"""Copies the shared Toontown: Anywhere client code into this folder before the iOS app is built (the workflow runs it):

    python ios/panda_ios/sync_tta.py            (from the repo root)

native/tta_native/*.py is the one source of truth for the sign-in, packs, chat helpers, control code, HUD layout and WebSocket
connection; the phone app uses the parts that are not desktop-only. The pure-Python websocket-client package is installed into ./vendor."""
import os
import py_compile
import shutil
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.abspath(os.path.join(here, "..", ".."))
src = os.path.join(root, "native", "tta_native")
dst = os.path.join(here, "tta_native")
shutil.rmtree(dst, ignore_errors=True)
os.makedirs(dst)
# desktop-only modules (windows, installer, full-screen, controller UI, settings cog) are left out; the phone app has its own UIKit settings
KEEP = ("__init__", "app", "auth", "chat", "controls", "display", "hud", "inputs", "netlayer", "packs", "securestore", "settings", "spec",
        "settings-spec")
for f in sorted(os.listdir(src)):
    base, ext = os.path.splitext(f)
    if base in KEEP and ext in (".py", ".json"):
        shutil.copyfile(os.path.join(src, f), os.path.join(dst, f))
print("copied", sorted(os.listdir(dst)))
vend = os.path.join(here, "vendor")
shutil.rmtree(vend, ignore_errors=True)
subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "--no-compile", "--target", vend, "websocket-client==1.9.2"])
for junk in ("bin",):
    shutil.rmtree(os.path.join(vend, junk), ignore_errors=True)
print("vendored websocket-client")
py_compile.compile(os.path.join(here, "ios_game.py"), doraise=True)
print("ios_game.py compiles")

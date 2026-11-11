"""Updates of the app itself (the launcher, Python and Panda3D): rare, because the game's code and files update on their own through the
packs. Releases are published on GitHub: every release carries windows.json (version, file, url, size, sha256) and windows.json.sig, an
Ed25519 signature made with the release key; the public half is built into the app (updatekey.py). The app reads the newest release's list
from GitHub's "latest release" address. Nothing is installed unless the signature and the file's hash match."""
import hashlib
import json
import os
import subprocess
import sys
import threading
import urllib.request
import zipfile

from . import __version__
from .updatekey import PUBLIC_KEY_HEX

PLATFORM_FILE = "windows.json"
# the newest published (not draft, not pre-release) GitHub release; its files are found under this address
DEFAULT_UPDATE_BASE = "https://github.com/lPuffyy/toontown-anywhere/releases/latest/download/"


def update_base():
    """Where the update list lives: GitHub's latest release, or TTA_UPDATE_BASE (testing against another address)."""
    base = os.environ.get("TTA_UPDATE_BASE") or DEFAULT_UPDATE_BASE
    return base if base.endswith("/") else base + "/"


def parse_version(v):
    out = []
    for part in str(v).split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits or 0))
    return tuple(out)


def frozen():
    return bool(getattr(sys, "frozen", False))


def app_dir():
    return os.path.dirname(sys.executable)


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "TTAnywhere-native"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def verify(data, sig_hex, public_hex=PUBLIC_KEY_HEX):
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex)).verify(bytes.fromhex(sig_hex.strip()), data)
        return True
    except (InvalidSignature, ValueError):
        return False


def fetch_manifest(base=None):
    """-> the signed manifest dict; raises if it cannot be read or the signature does not match."""
    base = base or update_base()
    data = _get(base + PLATFORM_FILE)
    sig = _get(base + PLATFORM_FILE + ".sig").decode("ascii", "replace")
    if not verify(data, sig):
        raise ValueError("the update list's signature is not valid")
    return json.loads(data.decode("utf8"))


class ShellUpdater:
    """Checks for a newer app and, if there is one, downloads, verifies and unpacks it, then writes the script that swaps the files in once
    this program has closed. state: {'phase', 'text', 'done_bytes', 'total_bytes', 'finished', 'restart', 'error'}."""

    def __init__(self, server, data_root, log=print):
        self.server = server.rstrip("/")
        self.root = data_root
        self.log = log
        self.state = {"phase": "check", "text": "", "done_bytes": 0, "total_bytes": 0, "finished": False, "restart": False, "error": ""}
        self.script = None

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self._update()
        except Exception as e:
            self.log("app update check failed: %r" % (e,))
        self.state["finished"] = True

    def _update(self):
        s = self.state
        if not frozen() and not os.environ.get("TTA_FORCE_SHELL_UPDATE"):
            return                              # running from source: nothing to replace
        base = update_base()
        m = fetch_manifest(base)
        if parse_version(m["version"]) <= parse_version(__version__):
            return
        s.update(phase="download", text="Updating the app to %s..." % m["version"], total_bytes=int(m["size"]))
        os.makedirs(os.path.join(self.root, "update"), exist_ok=True)
        zpath = os.path.join(self.root, "update", m["file"])
        h = hashlib.sha256()
        url = m.get("url") or (base + m["file"])          # the list says where the file is (a GitHub release asset)
        if not url.startswith("https://") and not base.startswith("http://"):
            raise ValueError("the update address is not secure")
        req = urllib.request.Request(url, headers={"User-Agent": "TTAnywhere-native"})
        with urllib.request.urlopen(req, timeout=60) as r, open(zpath, "wb") as f:
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                s["done_bytes"] += len(chunk)
        if h.hexdigest() != m["sha256"] or os.path.getsize(zpath) != int(m["size"]):
            os.remove(zpath)
            raise ValueError("the downloaded update does not match its signed description")
        s.update(phase="install", text="Installing the update...")
        stage = os.path.join(self.root, "update", "staged")
        if os.path.isdir(stage):
            import shutil
            shutil.rmtree(stage, ignore_errors=True)
        with zipfile.ZipFile(zpath) as z:
            for info in z.infolist():
                target = os.path.normpath(os.path.join(stage, info.filename))
                if not target.startswith(os.path.normpath(stage) + os.sep):
                    raise ValueError("unsafe path in update")
            z.extractall(stage)
        os.remove(zpath)
        src = os.path.join(stage, "TTAnywhere")
        self.script = self._write_script(src)
        s.update(phase="restart", text="Restarting...", restart=True)

    def _write_script(self, src):
        exe = os.path.join(app_dir(), "TTAnywhere.exe") if frozen() else sys.executable
        bat = os.path.join(self.root, "update", "apply.bat")
        with open(bat, "w") as f:
            f.write("@echo off\r\n"
                    'powershell -NoProfile -Command "try { Wait-Process -Id %d -Timeout 90 } catch {}"\r\n' % os.getpid() +
                    'robocopy "%s" "%s" /E /NFL /NDL /NJH /NJS /NP >nul\r\n' % (src, app_dir()) +
                    'rmdir /S /Q "%s" >nul 2>&1\r\n' % os.path.dirname(src) +
                    ("" if os.environ.get("TTA_NO_RESTART") else 'start "" "%s"\r\n' % exe))
        return bat

    def launch_and_exit(self):
        """Start the swap script (it waits for this program to close) and quit."""
        DETACHED, NEW_GROUP, BREAKAWAY = 0x00000008, 0x00000200, 0x01000000
        try:                                    # break away from any job this program runs in, so closing it does not end the swap script
            subprocess.Popen(["cmd", "/c", self.script], creationflags=DETACHED | NEW_GROUP | BREAKAWAY, close_fds=True)
        except OSError:
            subprocess.Popen(["cmd", "/c", self.script], creationflags=DETACHED | NEW_GROUP, close_fds=True)
        os._exit(0)

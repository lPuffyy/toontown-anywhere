"""Downloads and keeps up to date the game's files: the code pack (_code) and the resource packs (phase_3, phase_4, ...). The server
lists them in /packs.json as [[name, size], ...] and serves each at /_packs/<name>.zip; a pack is fetched again whenever its size changes.
The same lists the browser version uses, so one release updates every kind of client."""
import json
import os
import shutil
import threading
import time
import urllib.request
import zipfile

CODE_PACK = "_code"
CODE_DIRS = ("toontown", "otp", "otpy", "etc", "pytz")      # replaced as a whole when the code pack changes (so removed files go too)
UI_FILES = ("ToonDisplay.ttf", "background.jpg", "logo.png", "settings-spec.json")


def http_get(url, timeout=30, binary=True):
    req = urllib.request.Request(url, headers={"User-Agent": "TTAnywhere-native"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if binary else data.decode("utf8", "replace")


class Updater:
    """Run with start(); read .state from the UI thread: {'phase', 'text', 'done_bytes', 'total_bytes', 'error', 'finished'}."""

    def __init__(self, server, data_dir, log=print):
        self.server = server.rstrip("/")
        self.root = data_dir
        self.game_dir = os.path.join(data_dir, "game")
        self.res_dir = os.path.join(self.game_dir, "resources")
        self.ui_dir = os.path.join(data_dir, "ui")
        self.state_file = os.path.join(data_dir, "installed.json")
        self.log = log
        self.state = {"phase": "check", "text": "Checking for updates...", "done_bytes": 0, "total_bytes": 0, "error": "", "finished": False}
        self._thread = None

    # ---- bookkeeping
    def _installed(self):
        try:
            with open(self.state_file, encoding="utf8") as f:
                v = json.load(f)
            return v if isinstance(v, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_installed(self, d):
        tmp = self.state_file + ".tmp"
        with open(tmp, "w", encoding="utf8") as f:
            json.dump(d, f)
        os.replace(tmp, self.state_file)

    def ready_offline(self):
        """True when the packs are all on the computer already (so the game can start even if the server's file list cannot be read)."""
        inst = self._installed()
        return CODE_PACK in inst and os.path.isdir(os.path.join(self.game_dir, "toontown")) and os.path.isdir(self.res_dir)

    def fetch_ui(self):
        """The sign-in screen's font and pictures (small; refreshed daily)."""
        os.makedirs(self.ui_dir, exist_ok=True)
        for name in UI_FILES:
            path = os.path.join(self.ui_dir, name)
            if os.path.exists(path) and time.time() - os.path.getmtime(path) < 86400:
                continue
            try:
                data = http_get("%s/_ui/%s" % (self.server, name))
                with open(path, "wb") as f:
                    f.write(data)
            except Exception as e:
                if name != "logo.png":
                    self.log("ui file %s: %s" % (name, e))

    # ---- the update itself
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self._update()
        except Exception as e:
            self.log("update failed: %r" % (e,))
            if self.ready_offline():
                self.state.update(phase="done", text="Could not check for updates; using the files already here.", error="")
            else:
                self.state.update(phase="error", error="Could not download the game files: %s" % (e,), text="")
        self.state["finished"] = True

    def _update(self):
        s = self.state
        s.update(phase="check", text="Checking for updates...")
        self.fetch_ui()
        want = json.loads(http_get(self.server + "/packs.json", binary=False))
        inst = self._installed()
        todo = [(n, int(sz)) for n, sz in want if inst.get(n) != int(sz) or not self._present(n)]
        s["total_bytes"] = sum(sz for _, sz in todo)
        s["done_bytes"] = 0
        if not todo:
            s.update(phase="done", text="Up to date.")
            return
        os.makedirs(self.res_dir, exist_ok=True)
        for i, (name, size) in enumerate(todo, 1):
            s.update(phase="download", text="Downloading %s (%d of %d)" % (name, i, len(todo)))
            part = self._download(name, size)
            s.update(phase="install", text="Installing %s (%d of %d)" % (name, i, len(todo)))
            self._install(name, part)
            os.remove(part)
            inst[name] = size
            self._save_installed(inst)
        s.update(phase="done", text="Ready.")

    def _present(self, name):
        path = os.path.join(self.game_dir, "toontown") if name == CODE_PACK else os.path.join(self.res_dir, name)
        return os.path.isdir(path)

    def _download(self, name, size):
        url = "%s/_packs/%s.zip?s=%d" % (self.server, name, size)
        part = os.path.join(self.root, name + ".zip.part")
        req = urllib.request.Request(url, headers={"User-Agent": "TTAnywhere-native"})
        got = 0
        with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                self.state["done_bytes"] += len(chunk)
        if size and got != size:
            os.remove(part)
            raise IOError("%s came down as %d bytes, expected %d" % (name, got, size))
        return part

    def _install(self, name, zip_path):
        with zipfile.ZipFile(zip_path) as z:
            if name == CODE_PACK:
                for d in CODE_DIRS:
                    shutil.rmtree(os.path.join(self.game_dir, d), ignore_errors=True)
                prefix, dest = CODE_PACK + "/", self.game_dir
            else:
                prefix, dest = "", self.res_dir
            for info in z.infolist():
                n = info.filename
                if prefix:
                    if not n.startswith(prefix):
                        continue
                    n = n[len(prefix):]
                if not n or n.endswith("/"):
                    continue
                target = os.path.normpath(os.path.join(dest, n))
                if not target.startswith(os.path.normpath(dest) + os.sep):
                    continue              # never write outside the game folder
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)

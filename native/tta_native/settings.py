"""Where things live on the player's computer, and the few settings the launcher remembers."""
import json
import os
import sys

DEFAULT_SERVER = "https://toontown.puffsco.com"


def data_dir():
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    path = os.path.join(base, "TTAnywhere")
    os.makedirs(path, exist_ok=True)
    return path


class Settings:
    """settings.json in the data folder. The saved password is kept protected (see securestore.py), never as plain text."""
    def __init__(self, path=None):
        self.path = path or os.path.join(data_dir(), "settings.json")
        self.data = {}
        try:
            with open(self.path, encoding="utf8") as f:
                v = json.load(f)
            if isinstance(v, dict):
                self.data = v
        except (OSError, ValueError):
            pass

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf8") as f:
                json.dump(self.data, f, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass

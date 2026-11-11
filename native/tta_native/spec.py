"""The settings spec: one description of the settings cog and the keyboard keys card, shared with the web app (shared/settings-spec.json in the
repository). The newest copy is downloaded from the game server with the other launcher files (so a change reaches every app at once); the
copy that ships inside this app is used when that is missing or not valid."""
import json
import os

PLATFORM = "desktop"


def _valid(d):
    return isinstance(d, dict) and d.get("version") == 1 and isinstance(d.get("sections"), list) and isinstance(d.get("keys"), dict) \
        and isinstance(d["keys"].get("actions"), list)


def load(ui_dir=None):
    paths = []
    if ui_dir:
        paths.append(os.path.join(ui_dir, "settings-spec.json"))
    paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings-spec.json"))
    for p in paths:
        try:
            with open(p, encoding="utf8") as f:
                d = json.load(f)
            if _valid(d):
                return d
        except (OSError, ValueError):
            pass
    raise RuntimeError("the settings spec is missing")


def rows(spec, section):
    """The rows of a section that this app shows."""
    return [r for r in section.get("rows", []) if PLATFORM in r.get("platforms", [PLATFORM])]


def sections(spec):
    """[(section, rows)] for the sections that have anything to show here."""
    out = []
    for s in spec["sections"]:
        r = rows(spec, s)
        if r:
            out.append((s, r))
    return out

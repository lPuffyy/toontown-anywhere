"""Fails if the settings spec embedded in web/tta-ui.js (the web app's fallback copy) differs from shared/settings-spec.json,
or if native/tta_native/settings-spec.json (the native fallback copy) does. Run in CI."""
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
shared = json.load(open(os.path.join(ROOT, "shared", "settings-spec.json"), encoding="utf8"))
js = open(os.path.join(ROOT, "web", "tta-ui.js"), encoding="utf8").read()
m = re.search(r"const SPEC_DEFAULT = (\{.*?\});\n  let SPEC", js, re.S)
if not m:
    sys.exit("web/tta-ui.js has no embedded SPEC_DEFAULT")
if json.loads(m.group(1)) != shared:
    sys.exit("web/tta-ui.js embeds an out-of-date settings spec: regenerate it from shared/settings-spec.json")
native = json.load(open(os.path.join(ROOT, "native", "tta_native", "settings-spec.json"), encoding="utf8"))
if native != shared:
    sys.exit("native/tta_native/settings-spec.json is out of date: run native/build_windows.py")
print("the web and native copies of the settings spec match shared/settings-spec.json")

"""After pygbag has built the page (pygbag --build game), put our screens into it:
   python patch_web.py [ws url]      ("auto" for a hosted site: the page then connects to wss://<this site>/ws)"""
import base64
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
app = "game"       # the folder that holds main.py, built by pygbag into game/build/web
ws = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8766"
if ws == "auto":
    ws = ""        # hosted build: the page works out the address itself (wss://<this site>/ws)
web = os.path.join(HERE, app, "build", "web")
index = os.path.join(web, "index.html")
s = open(index, encoding="utf-8").read()
import re
s = re.sub(r"ume_block\s*:\s*\d", "ume_block : 0", s)   # do not wait for a tap before starting Python (iOS Safari would wait forever behind our screens)
open(index, "w", encoding="utf-8").write(s)
# one viewport setting only: the page has two, and the second (height=device-height) cancels viewport-fit=cover (blue bars at the notch)
s = re.sub(r'<meta name="viewport" content="height=device-height, initial-scale=1.0">\s*', '', s)
s = s.replace('<meta name="viewport" content="width=device-width, initial-scale=1.0">',
              '<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover, user-scalable=no">')
open(index, "w", encoding="utf-8").write(s)
if "ttr-ui.js" not in s:
    s = s.replace('<meta name="viewport" content="width=device-width, initial-scale=1.0">',
                  '<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover, user-scalable=no">', 1)
    s = s.replace("</head>", '<link rel="stylesheet" href="ttr-ui.css">\n</head>', 1)
    s = s.replace("</body>", '<script>window.TTR_WS = %r;</script>\n<script src="ttr-icons.js"></script>\n<script src="ttr-audio.js"></script>\n<script src="ttr-ui.js"></script>\n</body>' % ws, 1)
    open(index, "w", encoding="utf-8").write(s)
# home-screen app: manifest, icons, iOS app tags
import json
for f in ("icon-180.png", "icon-192.png", "icon-512.png"):
    shutil.copy(os.path.join(HERE, f), os.path.join(web, f))
json.dump({"name": "Toontown: Anywhere", "short_name": "TT: Anywhere", "start_url": "./", "scope": "./", "display": "standalone",
           "orientation": "landscape", "background_color": "#1c4cc4", "theme_color": "#1c4cc4",
           "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"}, {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"}]},
          open(os.path.join(web, "manifest.webmanifest"), "w"))
s = open(index, encoding="utf-8").read()
s = re.sub(r"<title>[^<]*</title>", "<title>TT: Anywhere</title>", s, count=1)
if "apple-touch-icon" not in s:
    tags = "".join(t + chr(10) for t in (
        '<link rel="manifest" href="manifest.webmanifest">',
        '<link rel="apple-touch-icon" href="icon-180.png">',
        '<meta name="apple-mobile-web-app-title" content="TT: Anywhere">',
        '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">',
        '<meta name="theme-color" content="#1c4cc4">'))
    s = s.replace("</head>", tags + "</head>", 1)
open(index, "w", encoding="utf-8").write(s)
for f in ("ttr-ui.css", "ttr-ui.js", "ttr-audio.js"):
    shutil.copy(os.path.join(HERE, f), os.path.join(web, f))
icons = {}
for name in ("discord", "reddit"):
    icons[name] = "data:image/png;base64," + base64.b64encode(open(os.path.join(HERE, "icons", name + ".png"), "rb").read()).decode()
open(os.path.join(web, "ttr-icons.js"), "w").write("window.TTR_ICONS = " + repr(icons).replace("'", '"') + ";\n")
print("patched", index)

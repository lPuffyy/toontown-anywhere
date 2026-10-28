"""Build the browser download packs: _code.zip (the game's Python + config + our otpy) and one zip per resource folder, plus packs.json.
   OT_DIR=<open-toontown-anywhere fork checkout, with its resources folder>  [OTPY_BASE=<folder holding otpy/> if OT_DIR has none]  python make_ot_packs.py      (writes into web/build/site)"""
import json
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
OT = os.environ.get("OT_DIR")
if not OT or not os.path.isdir(os.path.join(OT, "toontown")):
    raise SystemExit("set OT_DIR to a checkout of the open-toontown-anywhere fork that has its resources folder")
RES = os.path.join(OT, "resources")
# otpy/ (our replacement for the game's compiled libraries) is in the open-toontown-anywhere fork; use the one in OT_DIR, or OTPY_BASE=<folder that holds otpy/>
OTPY_BASE = os.environ.get("OTPY_BASE") or OT
if not os.path.isdir(os.path.join(OTPY_BASE, "otpy")):
    raise SystemExit("otpy/ not found: build from a checkout of the open-toontown-anywhere fork, or set OTPY_BASE to the folder that holds otpy/")
SITE = os.path.join(HERE, "build", "site")
OUT = os.path.join(SITE, "_packs")
os.makedirs(OUT, exist_ok=True)
packs = []


def add(z, full, arc):
    z.write(full, arc)



def web_patch(arc, text):
    """Phone-friendly chat (the same idea as the Toontown Anywhere build): big chat buttons placed against the screen corner, so the
    page's safe-area margins can move them clear of the notch."""
    def sub(a, b):
        nonlocal text
        if a not in text:
            print("  WARNING: patch text not found in", arc, ":", a[:60])
        text = text.replace(a, b, 1)
    if arc.endswith("toontown/chat/ToontownChatManager.py"):
        text = "\n".join(["_CHAT_SCALE = 2.0", "_NORMAL_POS = (0.135, 0, -0.135)", "_SC_POS = (0.36, 0, -0.135)", ""]) + text
        sub("pos=(-1.2647, 0, 0.928), scale=1.179,", "pos=_NORMAL_POS, parent=base.a2dTopLeft, scale=_CHAT_SCALE,")
        sub("pos=TTLocalizer.TCMscButtonPos, scale=1.179,", "pos=_SC_POS, parent=base.a2dTopLeft, scale=_CHAT_SCALE,")
        sub("DirectFrame(parent=aspect2dp, relief=None, image=DGG.getDefaultDialogGeom(), image_scale=(0.45, 0.45, 0.45),",
            "DirectFrame(parent=base.a2dTopLeft, relief=None, image=DGG.getDefaultDialogGeom(), image_scale=(0.77, 0.70, 0.20),")
        sub("pos=(-0.4, 0, 0.754),", "pos=(0.40, 0, -0.105),")
        sub("pos=(-0.125, 0, -0.1), scale=1.179,", "pos=(-0.33, 0, 0.033), scale=1.179,")
        sub("pos=(0.0, 0, -0.1), scale=1.179,", "pos=(-0.195, 0, 0.033), scale=1.179,")
        sub("pos=(0.125, 0, -0.1), scale=1.179,", "pos=(-0.06, 0, 0.033), scale=1.179,")
        sub("self.normalPos = Vec3(-1.083, 0, 0.804)", "self.normalPos = Vec3(0.25, 0, -0.196)")
        sub("self.whisperPos = Vec3(0.0, 0, 0.71)", "self.whisperPos = Vec3(0.25, 0, -0.28)")
        sub("self.chatInputWhiteList.setPos(self.speedChatPlusPos)", "self.chatInputWhiteList.setPos(self.speedChatPlusPos)" + "\n" + "        self.chatInputWhiteList.reparentTo(base.a2dTopLeft)")
    elif arc.endswith("toontown/chat/TTChatInputSpeedChat.py"):
        text = "\n".join(["_SC_SCALE = 0.085", "_SC_X = 0.52", ""]) + text
        sub("self.speedChat.reparentTo(aspect2dp, DGG.FOREGROUND_SORT_INDEX)", "self.speedChat.reparentTo(base.a2dpTopLeft, DGG.FOREGROUND_SORT_INDEX)")
        sub("scZ = 0.96", "scZ = -0.04")
        sub("self.speedChat.setPos(-1.05, 0, scZ)", "self.speedChat.setPos(_SC_X, 0, scZ)")
        sub("self.speedChat.setScale(TTLocalizer.TTCISCspeedChat)", "self.speedChat.setScale(_SC_SCALE)")
    elif arc.endswith("toontown/toon/LocalToon.py"):
        # the page hangs screen-edge buttons from the side anchors, so a slide to an absolute spot would throw this one off screen: only scale it
        sub("self.__furnitureGui.posHprScaleInterval(pos=Point3(-1.19, 0.0, 0.33), hpr=Vec3(0.0, 0.0, 0.0), scale=Vec3(0.04, 0.04, 0.04), duration=1.0, blendType='easeInOut', name='lerpFurnitureButton')",
            "self.__furnitureGui.scaleInterval(1.0, Vec3(0.04, 0.04, 0.04), blendType='easeInOut', name='lerpFurnitureButton')")
    elif arc.endswith("otp/otpbase/OTPGlobals.py"):
        # a phone's wide screen with the stock 52 degrees feels zoomed in: widen the default view (everything resets to this value)
        sub("DefaultCameraFov = 52.0", "DefaultCameraFov = 75.0")
    elif arc.endswith("toontown/minigame/Purchase.py"):
        # the jellybean results scene is a small set built for the original view: at our wider default it shows the edges and bends the shop
        sub("base.camLens.setFov(ToontownGlobals.DefaultCameraFov)", "base.camLens.setFov(52.0)")
    elif arc.endswith("toontown/chat/TTWhiteList.py"):
        # the chat word list: without it every typed word is refused and nothing is sent
        sub("        if __debug__:\n            searchPath.appendDirectory(Filename('resources/phase_3/etc'))",
            "\n".join(["        for _d in ('resources/phase_3/etc', '/data/data/game_ot/assets/resources/phase_3/etc', '/data/data/game_ot/assets/phase_3/etc'):",
                       "            searchPath.appendDirectory(Filename(_d))"]))
    elif arc.endswith("toontown/pets/PetNameGenerator.py"):
        sub("        filename = Filename(TTLocalizer.PetNameMaster)",
            "\n".join(["        for _d in ('resources/phase_3/etc', '/data/data/game_ot/assets/resources/phase_3/etc', '/data/data/game_ot/assets/phase_3/etc'):",
                       "            searchPath.appendDirectory(Filename(_d))",
                       "        filename = Filename(TTLocalizer.PetNameMaster)"]))
    return text

zp =os.path.join(OUT, "_code.zip")
n = 0
with zipfile.ZipFile(zp, "w", zipfile.ZIP_STORED) as z:
    for pkg, base in (("otp", OT), ("toontown", OT), ("otpy", OTPY_BASE)):
        for r, ds, fs in os.walk(os.path.join(base, pkg)):
            ds[:] = [d for d in ds if d != "__pycache__"]
            for f in fs:
                if f.endswith(".py"):
                    full = os.path.join(r, f)
                    arc = "_code/" + os.path.relpath(full, base).replace(os.sep, "/")
                    text = open(full, encoding="utf-8", errors="surrogateescape").read()
                    # a browser's graphics layer has no alpha test, so the game's "binary"/"dual" see-through modes draw solid: use plain blending
                    text = text.replace("TransparencyAttrib.MDual", "TransparencyAttrib.MAlpha").replace("TransparencyAttrib.MBinary", "TransparencyAttrib.MAlpha")
                    text = web_patch(arc, text)
                    z.writestr(arc, text.encode("utf-8", errors="surrogateescape"))
                    n += 1
    import pytz
    pz = os.path.dirname(os.path.dirname(pytz.__file__))
    for r, ds, fs in os.walk(os.path.join(pz, "pytz")):          # the game's time code needs pytz (pure Python + zone data)
        ds[:] = [d for d in ds if d != "__pycache__"]
        for f in fs:
            full = os.path.join(r, f)
            add(z, full, "_code/" + os.path.relpath(full, pz).replace(os.sep, "/"))
            n += 1
    for f in os.listdir(os.path.join(OT, "etc")):
        add(z, os.path.join(OT, "etc", f), "_code/etc/" + f)
        n += 1
    add(z, os.path.join(OT, "LICENSE"), "_code/LICENSE-OpenToontown")          # BSD: source redistributions keep the licence notice
    add(z, os.path.join(HERE, "NOTICE.txt"), "_code/NOTICE.txt")
    n += 2
packs.append(["_code", os.path.getsize(zp)])
print("_code", n, "files", os.path.getsize(zp) // 1024, "KB")
for d in sorted(os.listdir(RES)):
    p = os.path.join(RES, d)
    if not os.path.isdir(p) or d.startswith("."):
        continue
    zp = os.path.join(OUT, d + ".zip")
    n = 0
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_STORED) as z:
        for r, _, fs in os.walk(p):
            for f in fs:
                full = os.path.join(r, f)
                add(z, full, os.path.relpath(full, RES).replace(os.sep, "/"))
                n += 1
    packs.append([d, os.path.getsize(zp)])
    print("%-10s %6d files %8.1f MB" % (d, n, os.path.getsize(zp) / 1e6))
json.dump(packs, open(os.path.join(SITE, "packs.json"), "w"))
json.dump({"files": [], "code": []}, open(os.path.join(SITE, "manifest.json"), "w"))
print("packs.json:", len(packs), "packs")

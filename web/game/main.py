# /// script
# dependencies = [
#     "panda3d",
# ]
# ///
# Toontown: Anywhere in the browser (local experiment). The page (ttr-ui.js) shows the loading, sign-in and control screens
# and downloads the game files into the browser's file system; this script runs the real game once the player has signed in.
import asyncio
import builtins
import json
import os
import sys
import traceback
import types

import platform
import xmlshim
xmlshim.install()


class _Tee:
    """Send everything Python prints to the browser console (so it can be read from outside)."""
    def __init__(self, orig):
        self.orig = orig
        self.buf = ""

    def write(self, text):
        try:
            self.orig.write(text)
        except Exception:
            pass
        self.buf += text
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            try:
                platform.window.console.log("PY| " + line)
            except Exception:
                pass
        return len(text)

    def flush(self):
        try:
            self.orig.flush()
        except Exception:
            pass

    def __getattr__(self, n):
        return getattr(self.orig, n)


sys.stdout = _Tee(sys.stdout)
sys.stderr = _Tee(sys.stderr)

print("web: starting, cwd =", os.getcwd(), "python", sys.version.split()[0])
sys.path.insert(0, os.getcwd())
TTR = platform.window.ttr


# ---- stand-ins for pieces the browser build does not have (the browser has no native libraries, so small Python versions are provided) ----
class _Dummy:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return _Dummy()

    def __call__(self, *a, **k):
        return _Dummy()

    def __iter__(self):
        return iter(())

    def __bool__(self):
        return False


def _stub_module(name):
    class _M(types.ModuleType):
        def __getattr__(self, n):
            if n.startswith("__"):
                raise AttributeError(n)
            c = type(n, (_Dummy,), {})
            setattr(self, n, c)
            return c
    m = _M(name)
    sys.modules[name] = m
    return m


for _name in ("pdb", "bdb", "cmd", "profile", "cProfile", "pstats", "tkinter", "curses", "readline", "sqlite3", "dbm", "ssl"):
    try:
        __import__(_name)
    except ImportError:
        _m = _stub_module(_name)
        _m.__path__ = []        # lets "import pkg.sub" work too
        if _name == "dbm":
            _stub_module("dbm.dumb")
_stub_module("panda3d.ode")

import panda3d.core as _c


class _Anything:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: _Anything()

    def __bool__(self):
        return False


class HTTPClient(_Anything):
    VSNoVerify = 0
    VSNoDateCheck = 1
    VSNoCertCheck = 2
    VSNoVerify2 = 3

    @staticmethod
    def getGlobalPtr():
        return HTTPClient()

    get_global_ptr = getGlobalPtr

    def getVerifySsl(self):
        return HTTPClient.VSNoVerify

    def setVerifySsl(self, *a):
        pass


_c.HTTPClient = HTTPClient      # the browser build has an HTTPClient that cannot be created: always use the stand-in

import webnet
webnet.install()
import webui

from panda3d.core import PNMFileTypeRegistry as _Reg
_r = _Reg.getGlobalPtr()
print("web: image types:", [(_r.getType(i).getName(), list(_r.getType(i).getExtensions()) if hasattr(_r.getType(i), "getExtensions") else "") for i in range(_r.getNumTypes())])

from panda3d.core import loadPrcFileData

for line in ("load-display pandagles2", "audio-library-name null", "toontown-auto-run 0", "want-dev #f",
             "connect-method native", "sync-video 0", "notify-level warning",
             "garbage-collect-states-rate 0.05"):       # the engine's cache clean-up checked everything every frame and grew to 10 ms a frame
    loadPrcFileData("", line)
# The server runs in normal mode, so the game must too: dev mode makes the client ask the server for a cog factory's level spec (which a
# normal server denies), run leak checks and call Python 2 code. "want-dev #f" alone is too late if the engine has already read the setting.
try:
    from direct.showbase import ShowBaseGlobal as _SBG
    _SBG.__dev__ = False
    builtins.__dev__ = False
    print("web: dev mode off")
except BaseException:
    print("web: could not turn dev mode off", traceback.format_exc())
# Keep each neighbourhood's models in memory after the first visit, so going back is nearly instant (the original game read them again on
# every visit). Not on iPhone or iPad, where memory is what gets the page killed.
try:
    _ua = str(platform.window.navigator.userAgent)
    _ios = "iPhone" in _ua or "iPad" in _ua or ("Macintosh" in _ua and int(platform.window.navigator.maxTouchPoints or 0) > 1)
except BaseException:
    _ios = True
loadPrcFileData("", "dna-ram-cache-hood-models %s" % ("#f" if _ios else "#t"))
print("web: keep area models in memory:", not _ios)
# ?dmul=N : the building code (hosted DNA files) multiplies the depth offsets of windows, flat doors, cornices and door holes by N
try:
    from urllib.parse import parse_qs as _pq0
    _dm = (_pq0(str(platform.window.location.search).lstrip("?")).get("dmul", ["6"]) or ["6"])[0]
    os.environ["TTR_DEPTH_MUL"] = str(int(_dm))
    print("web: depth offset multiplier =", os.environ["TTR_DEPTH_MUL"])
except BaseException:
    os.environ["TTR_DEPTH_MUL"] = "6"
# test switches: the page address can carry extra engine settings, e.g. ?prc=texture-minfilter%20linear;another-setting%20value
try:
    from urllib.parse import parse_qs as _pq
    for _v in _pq(str(platform.window.location.search).lstrip("?")).get("prc", []):
        for _line in _v.split(";"):
            _line = _line.strip()
            if _line:
                loadPrcFileData("", _line)
                print("web: extra setting:", _line)
except BaseException:
    print("web: could not read extra settings", traceback.format_exc())
# the page's Display settings: smooth edges off asks for a context without multisampling (takes effect when the game starts)
try:
    if str(TTR.aa) == "0":
        for _line in ("framebuffer-multisample 0", "multisamples 0"):
            loadPrcFileData("", _line)
        print("web: smooth edges off")
except BaseException:
    pass
from panda3d.core import WindowProperties
try:
    if int(TTR.winW) > 0:
        loadPrcFileData("", "win-size %d %d" % (int(TTR.winW), int(TTR.winH)))
except Exception:
    pass

# The browser's graphics layer has no alpha test, so the "binary" and "dual" cut-out modes (trees, backdrops, fences) would draw
# their see-through parts as solid white. Blend them instead: convert every model as it loads, and any later setTransparency.
from panda3d.core import TransparencyAttrib as _TA, NodePath as _NP
_CUTOUT = (_TA.MBinary, _TA.MDual)


# Cut-outs (trees, fences, lamps, backdrops) are drawn with a tiny shader that skips see-through texels, so they still write depth
# like on the phone app. (Panda's automatic shaders did not do this in the browser.) ?blend=1 falls back to plain blending.
from panda3d.core import ShaderAttrib as _SA, Shader as _Sh, DepthWriteAttrib as _DW
try:
    _q = str(platform.window.location.search)
except BaseException:
    _q = ""
# ?cut=ms (multisample alpha-to-coverage) was tried and does not work in the browser: every see-through texel came out solid. Kept off.
_MS = False
_USE_TEST = "blend=1" not in _q and not _MS            # cut-out shader by default; ?blend=1 falls back to plain blending
print("web: cut-out mode =", "multisample" if _MS else ("shader" if _USE_TEST else "blend"))
_VERT = """#version 100
invariant gl_Position;
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform vec4 p3d_ColorScale;
attribute vec4 p3d_Vertex;
uniform vec4 p3d_Color;       // flat colour (or white): as an attribute it kept the previous object's colour whenever a model had no vertex colours
attribute vec2 p3d_MultiTexCoord0;
varying vec2 uv;
varying vec4 col;
void main() {
  gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
  uv = p3d_MultiTexCoord0;
  col = p3d_Color * p3d_ColorScale;
}
"""
_FRAG = """#version 100
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform sampler2D p3d_Texture0;
varying vec2 uv;
varying vec4 col;
void main() {
  vec4 t = texture2D(p3d_Texture0, uv) * col;
  if (t.a < 0.5) discard;
  gl_FragColor = vec4(t.rgb, 1.0);
}
"""
_shader = [None]


def _cut_attrib():
    if _shader[0] is None:
        _shader[0] = _Sh.make(_Sh.SL_GLSL, _VERT, _FRAG)
    return _SA.make(_shader[0], 1)


def _cut_state(st):
    st = st.setAttrib(_TA.make(_TA.MNone))
    return st.setAttrib(_cut_attrib())


def fix_transparency(root, shader=True):
    use_shader = _USE_TEST and shader
    use_ms = _MS and shader
    try:
        for gn in root.findAllMatches("**/+GeomNode"):
            node = gn.node()
            for i in range(node.getNumGeoms()):
                st = node.getGeomState(i)
                ta = st.getAttrib(_TA)
                if ta is not None and ta.getMode() in _CUTOUT:
                    if use_ms:
                        node.setGeomState(i, st.setAttrib(_TA.make(_TA.MMultisampleMask)))
                    elif use_shader:
                        ns = _cut_state(st)
                        if _OFF > 0 and any(k in str(gn).lower() for k in _OFFK):
                            cur = gn.getNetState().compose(st).getAttrib(_DOA)
                            ns = ns.setAttrib(_DOA.make((cur.getOffset() if cur is not None else 0) + _OFF))      # added on top, so a piece that already sits in front of another still does
                        node.setGeomState(i, ns)
                    elif not shader:
                        node.setGeomState(i, st.setAttrib(_TA.make(_TA.MAlpha)))        # characters: faces need the plain blend look
                    else:
                        node.setGeomState(i, st.setAttrib(_TA.make(_TA.MAlpha)).setAttrib(_DW.make(_DW.MOff)))
        for n in root.findAllMatches("**"):
            ta = n.node().getAttrib(_TA)
            if ta is not None and ta.getMode() in _CUTOUT:
                if use_ms:
                    n.setTransparency(_TA.MMultisampleMask)
                elif use_shader:
                    n.setTransparency(_TA.MNone)
                    n.setAttrib(_cut_attrib())
                elif not shader:
                    n.setTransparency(_TA.MAlpha)
                else:
                    n.setTransparency(_TA.MAlpha)
                    n.setDepthWrite(False)     # see-through texels must not hide what is behind them
    except BaseException:
        print("web: transparency fix failed", traceback.format_exc())


# ?uber=1 (experiment): draw every loaded model with our own two shaders (textured / plain), not just the see-through ones, so that
# overlapping pieces (doors on walls) are all computed the same way and line up exactly.
from panda3d.core import TextureAttrib as _TxA, TexMatrixAttrib as _TMA, TexGenAttrib as _TGA
from panda3d.core import DepthOffsetAttrib as _DOA
try:
    from urllib.parse import parse_qs as _pq2
    _pqq = _pq2(_q.lstrip("?"))
    _OFF = int((_pqq.get("off", ["0"]) or ["0"])[0])
    _OFFK = tuple(k.strip().lower() for k in (_pqq.get("offk", ["door,window"]) or ["door,window"])[0].split(",") if k.strip())
except BaseException:
    _OFF = 0
    _OFFK = ("door", "window")
print("web: see-through depth push =", _OFF, "for names containing", _OFFK)
_UBER = "uber=1" in _q
_FRAG_TEX = """#version 100
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform sampler2D p3d_Texture0;
varying vec2 uv;
varying vec4 col;
void main() {
  gl_FragColor = texture2D(p3d_Texture0, uv) * col;
}
"""
_FRAG_FLAT = """#version 100
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
varying vec2 uv;
varying vec4 col;
void main() {
  gl_FragColor = col;
}
"""
_uber = {}


def _uber_attr(textured):
    a = _uber.get(textured)
    if a is None:
        a = _SA.make(_Sh.make(_Sh.SL_GLSL, _VERT, _FRAG_TEX if textured else _FRAG_FLAT), 0)
        _uber[textured] = a
    return a


def apply_uber(root):
    if not _UBER:
        return
    try:
        for gn in root.findAllMatches("**/+GeomNode"):
            node = gn.node()
            net = gn.getNetState()
            for i in range(node.getNumGeoms()):
                st = node.getGeomState(i)
                full = net.compose(st)
                if full.getAttrib(_SA) is not None and full.getAttrib(_SA).getShader() is not None:
                    continue                      # already has a shader (the see-through ones)
                if full.getAttrib(_TMA) is not None or full.getAttrib(_TGA) is not None:
                    continue                      # animated / generated texture coordinates: leave to the engine
                ta = full.getAttrib(_TxA)
                textured = ta is not None and ta.getNumOnStages() > 0
                node.setGeomState(i, st.setAttrib(_uber_attr(textured)))
    except BaseException:
        print("web: uber shader pass failed", traceback.format_exc())


print("web: uber shaders =", _UBER)

# Decals (windows and doors drawn on walls) are made to win over the wall only by a depth offset of 1 per level. On the phone's graphics
# layer that is too little, which is what makes them flicker. ?decal=N adds N more per level.
from panda3d.core import DecalEffect as _DE
try:
    _DECAL = int((_pq2(_q.lstrip("?")).get("decal", ["0"]) or ["0"])[0])
except BaseException:
    _DECAL = 0
print("web: extra decal depth offset =", _DECAL)


def boost_decals(root):
    if _DECAL <= 0:
        return
    try:
        nodes = [root] + [n for n in root.findAllMatches("**")]
        for n in nodes:
            if n.hasEffect(_DE):
                for i in range(n.getNumChildren()):
                    c = n.getChild(i)
                    c.setDepthOffset(_DECAL)
    except BaseException:
        print("web: decal boost failed", traceback.format_exc())




from direct.showbase import Loader as _Loader
_orig_loadModel = _Loader.Loader.loadModel


def _loadModel(self, *a, **k):
    r = _orig_loadModel(self, *a, **k)
    try:
        is_char = "/char/" in str(a[0] if a else k.get("modelPath", "")).replace(chr(92), "/")
        if isinstance(r, _NP):
            fix_transparency(r, not is_char)
            apply_uber(r)
            boost_decals(r)
        elif isinstance(r, (list, tuple)):
            for x in r:
                if isinstance(x, _NP):
                    fix_transparency(x, not is_char)
                    apply_uber(x)
                    boost_decals(x)
    except BaseException:
        print("web: transparency fix failed", traceback.format_exc())
    return r


_Loader.Loader.loadModel = _loadModel


# Actors (toons, cogs, NPCs) load their models straight through Panda's own loader, not Loader.loadModel, so convert those too.
from direct.actor import Actor as _ActorMod
_orig_actor_loadModel = _ActorMod.Actor.loadModel


def _actor_loadModel(self, *a, **k):
    r = _orig_actor_loadModel(self, *a, **k)
    try:
        fix_transparency(self, False)
        apply_uber(self)
        boost_decals(self)
    except BaseException:
        print("web: actor transparency fix failed", traceback.format_exc())
    return r


_ActorMod.Actor.loadModel = _actor_loadModel
_orig_setT = _NP.setTransparency


def _setTransparency(self, *a, **k):
    a = list(a)
    if a and a[0] in _CUTOUT:
        if _USE_TEST:
            _orig_setT(self, _TA.MNone)
            self.setAttrib(_cut_attrib())
            return None
        a[0] = _TA.MAlpha
        self.setDepthWrite(False)
    return _orig_setT(self, *a, **k)


try:
    _NP.setTransparency = _setTransparency
except BaseException:
    print("web: could not patch NodePath.setTransparency")

# the game's start script ends with base.run(), which would block the browser: do the stepping ourselves instead
from direct.showbase.ShowBase import ShowBase
ShowBase.run = lambda self: None

# sound: the page plays it (see webaudio.py / ttr-audio.js)
import webaudio
webaudio.install(ShowBase)
_orig_loadSound = _Loader.Loader.loadSound


def _loadSound(self, manager, soundPath, positional=False, callback=None, extraArgs=[]):
    if not isinstance(manager, webaudio.WebAudioManager):
        return _orig_loadSound(self, manager, soundPath, positional, callback, extraArgs)
    many = isinstance(soundPath, (tuple, list, set))
    res = [manager.getSound(p, positional) for p in (soundPath if many else [soundPath])]
    out = res if many else res[0]
    if callback is not None:
        callback(out, *extraArgs)
        return None
    return out


_Loader.Loader.loadSound = _loadSound


# Panda's GUI widgets only accept its own C++ sound objects. Keep our sounds out of them and play the button-click sound ourselves.
from direct.gui import DirectButton as _DB, DirectEntry as _DE, DirectOptionMenu as _DOM
_isweb = lambda snd: isinstance(snd, webaudio.WebSound)
_orig_db_click = _DB.DirectButton.setClickSound
_orig_db_roll = _DB.DirectButton.setRolloverSound
_orig_db_cmd = _DB.DirectButton.commandFunc
_orig_de_click = _DE.DirectEntry.setClickSound
_orig_de_roll = _DE.DirectEntry.setRolloverSound
_orig_dom_init = _DOM.DirectOptionMenu.__init__


def _db_click(self):
    snd = self['clickSound']
    if _isweb(snd):
        self._webClick = snd
        from direct.gui import DirectGuiGlobals as G
        for ev in (G.B1PRESS, G.B2PRESS, G.B3PRESS):
            self.guiItem.clearSound(ev + self.guiId)
    else:
        self._webClick = None
        _orig_db_click(self)


def _db_roll(self):
    if _isweb(self['rolloverSound']):
        from direct.gui import DirectGuiGlobals as G
        self.guiItem.clearSound(G.ENTER + self.guiId)
    else:
        _orig_db_roll(self)


def _db_cmd(self, event):
    snd = getattr(self, "_webClick", None)
    if snd is not None:
        try:
            snd.play()
        except BaseException:
            pass
    return _orig_db_cmd(self, event)


def _de_click(self):
    if not _isweb(self['clickSound']):
        _orig_de_click(self)


def _de_roll(self):
    if not _isweb(self['rolloverSound']):
        _orig_de_roll(self)


def _dom_init(self, parent=None, **kw):
    kw.setdefault("clickSound", None)
    kw.setdefault("rolloverSound", None)
    _orig_dom_init(self, parent, **kw)


_DB.DirectButton.setClickSound = _db_click
_DB.DirectButton.setRolloverSound = _db_roll
_DB.DirectButton.commandFunc = _db_cmd
_DE.DirectEntry.setClickSound = _de_click
_DE.DirectEntry.setRolloverSound = _de_roll
_DOM.DirectOptionMenu.__init__ = _dom_init


# Keep the game's own on-screen items (chat buttons, laff meter, book, FPS) inside the phone's safe area (notch, rounded corners,
# home bar). The game places them on Panda's screen-edge anchors, so we nudge the anchors inward by the safe-area sizes.
_orig_adjust = ShowBase.adjustWindowAspectRatio
_ANCHORS = (("a2dTopLeft", 1, -1, 1, 0), ("a2dTopRight", -1, -1, 0, 0), ("a2dBottomLeft", 1, 1, 1, 0), ("a2dBottomRight", -1, 1, 0, 0),
            ("a2dTopCenter", 0, -1, 0, 0), ("a2dBottomCenter", 0, 1, 0, 0), ("a2dLeftCenter", 1, 0, 0, 0), ("a2dRightCenter", -1, 0, 0, 0))


_applied = [0.0, 0.0, 0.0, 0.0]        # insets already added to the anchors (they are reset whenever the window's aspect ratio changes)


def _apply_insets(b, reset):
    """Move the anchors by (wanted insets - already applied ones). Panda only rewrites the anchors when the aspect ratio changes,
    so adding the full insets on every call (e.g. each window-focus event) would push everything further in."""
    try:
        if reset:
            _applied[:] = [0.0, 0.0, 0.0, 0.0]
        k = 2.0 / (float(TTR.vh) or 1.0)           # screen-height units (aspect2d spans 2.0 over the height) per page pixel
        want = [float(TTR.safeL) * k, float(TTR.safeR) * k, float(TTR.safeT) * k, float(TTR.safeB) * k]
        dL, dR, dT, dB = [want[i] - _applied[i] for i in range(4)]
        if abs(dL) + abs(dR) + abs(dT) + abs(dB) < 1e-6:
            return
        for base_name, sx, sz, _a, _b in _ANCHORS:
            for suffix in ("", "Ns"):
                n = getattr(b, base_name + suffix, None)
                if n is None:
                    continue
                dx = dL if sx > 0 else (-dR if sx < 0 else 0.0)
                dz = dB if sz > 0 else (-dT if sz < 0 else 0.0)
                n.setPos(n.getX() + dx, n.getY(), n.getZ() + dz)
        _applied[:] = want
    except BaseException:
        print("web: safe-area adjust failed", traceback.format_exc())


def _adjust(self, aspectRatio):
    old = getattr(self, "_ShowBase__oldAspectRatio", None)
    _orig_adjust(self, aspectRatio)
    _apply_insets(self, getattr(self, "_ShowBase__oldAspectRatio", None) != old)


ShowBase.adjustWindowAspectRatio = _adjust


def _install_smooth_walk():
    """Ease walking and turning in and out. The stock walker jumps to full speed the frame a key goes down and stops the frame it comes up,
    which feels jerky. We scale the walker's speeds by a ramp, and while a ramp is still running down after the key came up we make the
    walker see the key as held, so the toon glides to a stop."""
    from direct.controls import GravityWalker as _gravity_walker
    GravityWalker = _gravity_walker.GravityWalker
    inputState = _gravity_walker.inputState        # the walker's own handle: importing InputStateGlobal fresh trips a circular import in the web build
    from panda3d.core import ClockObject
    orig = GravityWalker.handleAvatarControls
    UP_MOVE, DOWN_MOVE, UP_TURN, DOWN_TURN = 0.16, 0.12, 0.09, 0.07        # seconds to reach full speed / to stop

    def ramp(v, target, dt, up, down):
        rate = (up if abs(target) > abs(v) or (target and v * target < 0) else down)
        step = dt / rate
        if v < target:
            return min(target, v + step)
        return max(target, v - step)

    def handle(self, task):
        st = self.__dict__.setdefault("_smooth", [0.0, 0.0])
        dt = min(ClockObject.getGlobalClock().getDt(), 0.1)
        isset = inputState.isSet
        fw, rv = isset("forward"), isset("reverse")
        tl, tr = isset("turnLeft"), isset("turnRight")
        try:
            la = base.localAvatar
            if la and la.getAutoRun():
                fw, rv = True, False
        except BaseException:
            pass
        st[0] = ramp(st[0], 1.0 if fw else (-1.0 if rv else 0.0), dt, UP_MOVE, DOWN_MOVE)
        st[1] = ramp(st[1], 1.0 if tl else (-1.0 if tr else 0.0), dt, UP_TURN, DOWN_TURN)
        held = {"forward": st[0] > 0.0, "reverse": st[0] < 0.0, "turnLeft": st[1] > 0.0, "turnRight": st[1] < 0.0}
        fs, rs, ts = self.avatarControlForwardSpeed, self.avatarControlReverseSpeed, self.avatarControlRotateSpeed
        self.avatarControlForwardSpeed, self.avatarControlReverseSpeed = fs * abs(st[0]), rs * abs(st[0])
        self.avatarControlRotateSpeed = ts * abs(st[1])

        def fake(name):
            if name in held:
                return held[name]
            return isset(name)
        inputState.isSet = fake
        try:
            return orig(self, task)
        finally:
            del inputState.isSet
            self.avatarControlForwardSpeed, self.avatarControlReverseSpeed, self.avatarControlRotateSpeed = fs, rs, ts

    GravityWalker.handleAvatarControls = handle


_last_code = [""]


_A43 = 4.0 / 3.0


_PERF = {"slow": [], "gc": []}


def _install_perf_probes(b):
    """Find what makes the game hitch: time garbage collections and the loader's calls, and tune the collector so it does not run
    long collections in the middle of play (the program is long lived: what it has built by now is not garbage)."""
    import gc
    import time as _t
    try:
        gc.collect()
        gc.freeze()                       # what exists now is permanent: the collector stops re-scanning it every time
        gc.set_threshold(20000, 20, 1000)
    except BaseException:
        print("web: gc tuning failed", traceback.format_exc())
    t0 = [0.0]

    def gc_cb(phase, info):
        if phase == "start":
            t0[0] = _t.perf_counter()
        else:
            dt = (_t.perf_counter() - t0[0]) * 1000.0
            if dt > 15:
                _PERF["gc"].append("gen%d %.0fms" % (info.get("generation", -1), dt))
    gc.callbacks.append(gc_cb)

    ld = getattr(b, "loader", None)
    if ld is not None:
        for name in ("loadModel", "loadSfx", "loadMusic", "loadTexture", "loadFont", "loadDNAFile"):
            orig = getattr(ld, name, None)
            if orig is None:
                continue

            def wrap(*a, __orig=orig, __name=name, **k):
                t = _t.perf_counter()
                try:
                    return __orig(*a, **k)
                finally:
                    dt = (_t.perf_counter() - t) * 1000.0
                    if dt > 25:
                        _PERF["slow"].append("%s %s %.0fms" % (__name, str(a[0])[-48:] if a else "", dt))
            setattr(ld, name, wrap)
    print("web: perf probes installed")


def _anchor_hud(b):
    """The game lays its screen-edge buttons (laff meter, book, friends...) out for a 4:3 screen with absolute positions. On a wide phone they
    would float in from the edges (and sit under the notch), so hang the ones near the side edges from the left / right edge anchors instead,
    keeping their distance from the edge; the page's safe-area margins then move them clear of the notch."""
    try:
        if getattr(builtins, "localAvatar", None) is None:
            return          # not in the game yet: menu screens (pick a toon, make a toon) are laid out as whole 4:3 pictures and must stay together
        left, right = b.a2dLeftCenter, b.a2dRightCenter
        for c in list(b.aspect2d.getChildren()):
            name = c.getName()
            if name.startswith(("a2d", "pixel")) or c.getTag("anch"):
                continue
            pos = c.getPos()
            if abs(pos.getX()) < 0.8:
                continue
            s = c.getSort()
            if pos.getX() < 0:
                c.reparentTo(left, s)
                c.setPos(pos.getX() + _A43, pos.getY(), pos.getZ())
            else:
                c.reparentTo(right, s)
                c.setPos(pos.getX() - _A43, pos.getY(), pos.getZ())
            c.setTag("anch", "1")
    except BaseException:
        print("web: HUD anchoring failed", traceback.format_exc())


def _sync_size(b):
    try:
        w, h = int(TTR.winW), int(TTR.winH)
        try:
            TTR.pw, TTR.ph = int(b.win.getXSize()), int(b.win.getYSize())
        except BaseException:
            pass
        if w > 0 and h > 0 and getattr(b, "win", None) is not None and (b.win.getXSize(), b.win.getYSize()) != (w, h):
            props = WindowProperties()
            props.setSize(w, h)
            b.win.requestProperties(props)
    except BaseException:
        print("web: size sync failed", traceback.format_exc())


def _run_debug_code():
    """Developer console: the page can set ttr.pycode to Python source, which runs here once."""
    try:
        code = str(TTR.pycode)
    except BaseException:
        return
    if code and code != _last_code[0]:
        _last_code[0] = code
        try:
            exec(code, globals())
        except BaseException:
            print("web: debug code failed")
            print(traceback.format_exc())


def TTR_mark(msg):
    try:
        platform.window.console.log("PY| MARK " + msg)
    except Exception:
        pass


async def main():
    TTR.pyReady = True
    print("web: ready, waiting for the page to download the game files and sign in")
    while not bool(TTR.go) and not bool(TTR.dbg):
        await asyncio.sleep(0.1)
    cookie = str(TTR.cookie)
    webnet.WS_URL = str(TTR.wsUrl)
    os.makedirs("logs", exist_ok=True)
    started = False
    try:
        # Open Toontown: the compiled libotp / libtoontown are replaced by our pure-Python versions
        TTR_mark("importing otpy")
        import otpy.install
        otpy.install.install()
        try:
            _install_smooth_walk()
        except BaseException:
            print("web: smooth walking not installed", traceback.format_exc())
        import otpy.dnaparser

        def _dna_model_hook(np):
            is_char = False
            fix_transparency(np, not is_char)
            apply_uber(np)
            boost_decals(np)
        otpy.dnaparser.MODEL_HOOK = _dna_model_hook
        TTR_mark("otpy installed")
        from panda3d.core import loadPrcFile
        loadPrcFile("etc/Configrc.prc")
        for line in ("load-display pandagles2", "audio-library-name null", "toontown-auto-run 0", "want-dev #f", "connect-method native",
                     "sync-video 0", "notify-level warning", "garbage-collect-states-rate 0.05", "dna-path resources", "default-model-extension .bam",
                     "interpolate-frames 1",       # blend between an animation's frames (the toon animations are authored at 24 fps and look choppy without it)
                     "vertex-buffers 1", "aspect-ratio 0"):      # the game's own config turns vertex buffers OFF, which a browser (WebGL) cannot do
            loadPrcFileData("", line)
        try:
            if int(TTR.winW) > 0:
                loadPrcFileData("", "win-size %d %d" % (int(TTR.winW), int(TTR.winH)))
        except Exception:
            pass
        user = cookie.split(":")[0] or "dev"
        os.environ["LOGIN_TOKEN"] = user
        import runpy
        _out, _err = sys.stdout, sys.stderr
        from toontown.launcher.ToontownDummyLauncher import ToontownDummyLauncher
        sys.stdout, sys.stderr = _out, _err         # the game's launcher module redirects output to a log file; keep ours (it shows in the browser console)

        class WebLauncher(ToontownDummyLauncher):
            def getPlayToken(self):
                return user

        builtins.launcher = WebLauncher()

        class _Game:
            name = "toontown"
            process = "client"

        builtins.game = _Game()
        print("web: running toontown.toonbase.ToontownStart as", user)
        runpy.run_module("toontown.toonbase.ToontownStart", run_name="__main__")
        print("web: ToontownStart returned; base =", getattr(builtins, "base", None))
    except BaseException:
        print("web: STARTUP FAILED")
        print(traceback.format_exc())
    frames = 0
    import time as _time
    _pf = {"last": None, "dts": [], "steps": []}      # frame timing: how long frames take, and how much of that is the game's own step
    while True:
        b = getattr(builtins, "base", None)
        if b is not None:
            try:
                _t0 = _time.perf_counter()
                b.taskMgr.step()
                _t1 = _time.perf_counter()
                if _pf["last"] is not None:
                    _pf["dts"].append((_t0 - _pf["last"]) * 1000.0)
                _pf["last"] = _t0
                _pf["steps"].append((_t1 - _t0) * 1000.0)
            except BaseException:
                print("web: STEP FAILED")
                print(traceback.format_exc())
                await asyncio.sleep(1)
            webui.poll()
            webaudio.tick()
            frames += 1
            if frames % 20 == 0:
                _sync_size(b)
                _anchor_hud(b)
                _run_debug_code()
            if frames == 30 and not started:
                started = True
                TTR.started()
                try:
                    _install_perf_probes(b)
                except BaseException:
                    print("web: perf probes failed", traceback.format_exc())
            if frames % 600 == 0:
                print("web: frames", frames)
            if len(_pf["dts"]) >= 300:
                d, st = sorted(_pf["dts"]), sorted(_pf["steps"])
                n = len(d)
                print("web: perf fps=%.1f frame avg=%.1fms p95=%.1fms max=%.0fms slow(>50ms)=%d | step avg=%.1fms p95=%.1fms max=%.0fms" % (
                    1000.0 * n / sum(d), sum(d) / n, d[int(n * 0.95)], d[-1], sum(1 for x in d if x > 50), sum(st) / len(st), st[int(len(st) * 0.95)], st[-1]))
                _pf["dts"], _pf["steps"] = [], []
                if _PERF["slow"] or _PERF["gc"]:
                    print("web: hitches in that window: loads", _PERF["slow"][-8:], "| gc", _PERF["gc"][-6:])
                    _PERF["slow"], _PERF["gc"] = [], []
        await asyncio.sleep(0)


asyncio.run(main())

# /// script
# dependencies = [
#     "panda3d",
# ]
# ///
# Toontown: Anywhere in the browser (local experiment). The page (tta-ui.js) shows the loading, sign-in and control screens
# and downloads the game files into the browser's file system; this script runs the real game once the player has signed in.
import asyncio
import builtins
import gc
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
TTA = platform.window.tta


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
builtins._tta_webui_module = webui

from panda3d.core import PNMFileTypeRegistry as _Reg
_r = _Reg.getGlobalPtr()
print("web: image types:", [(_r.getType(i).getName(), list(_r.getType(i).getExtensions()) if hasattr(_r.getType(i), "getExtensions") else "") for i in range(_r.getNumTypes())])

from panda3d.core import loadPrcFileData

for line in ("load-display pandagles2", "audio-library-name null", "toontown-auto-run 0", "want-dev #f",
             "connect-method native", "sync-video 0", "notify-level warning",
             "uniquify-transforms 0", "transform-cache 0",        # transform-cache maintenance was taking 6-23 ms per frame on streets
             "hardware-animated-vertices 1",                       # GPU vertex skinning instead of CPU
             "gl-force-no-error 1",                                # skip WebGL error polling per draw call
             "gl-finish 0",                                        # prevent CPU stalling to wait for GPU pipeline drain
             "gl-force-flush 0",                                   # prevent explicit glFlush calls between frames
             "preload-textures 1",                                 # upload textures to GPU VRAM up front
             "textures-power-2 none",                              # WebGL2 supports NPOT natively; skip CPU rescaling
             "flatten-geoms 1"):                                   # merge compatible geometry to reduce draw calls
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
# ?hoodcache=1 turns the cache back on for an iOS A/B test of its FPS cost.
try:
    _hoodcache = "hoodcache=1" in str(platform.window.location.search)
except BaseException:
    _hoodcache = False
loadPrcFileData("", "dna-ram-cache-hood-models %s" % ("#t" if (_hoodcache or not _ios) else "#f"))
print("web: keep area models in memory:", bool(_hoodcache or not _ios))
# ?dmul=N : the building code (hosted DNA files) multiplies the depth offsets of windows, flat doors, cornices and door holes by N
try:
    from urllib.parse import parse_qs as _pq0
    _dm = (_pq0(str(platform.window.location.search).lstrip("?")).get("dmul", ["6"]) or ["6"])[0]
    os.environ["TTA_DEPTH_MUL"] = str(int(_dm))
    print("web: depth offset multiplier =", os.environ["TTA_DEPTH_MUL"])
except BaseException:
    os.environ["TTA_DEPTH_MUL"] = "6"
os.environ["TTR_DEPTH_MUL"] = os.environ["TTA_DEPTH_MUL"]      # the code pack's town loader still reads the earlier name
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
from panda3d.core import WindowProperties
try:
    if int(TTA.winW) > 0:
        loadPrcFileData("", "win-size %d %d" % (int(TTA.winW), int(TTA.winH)))
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
_CUT_HARD = "cut=smooth" not in _q and "blend=1" not in _q   # hard alpha test by default; ?cut=smooth restores the blended shader
_USE_TEST = "blend=1" not in _q and not _MS            # cut-out shader by default; ?blend=1 falls back to plain blending
print("web: cut-out mode =", "multisample" if _MS else ("hard" if _CUT_HARD else ("smooth" if _USE_TEST else "blend")))
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
_FRAG_HARD = """#version 100
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
# Smooth alpha cut-outs: the mask is bilinearly sampled, so keeping its fractional
# alpha blends the edge pixels instead of chopping them at a hard 0.5 threshold.
# MSAA then antialiases the remaining silhouette. Only fully clear texels are
# discarded; depth is still written so the art keeps its old occlusion behaviour.
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
  if (t.a < 0.02) discard;
  gl_FragColor = vec4(t.rgb, t.a);
}
"""
_shader = [None]


def _is_eye_part(np):
    """The real eye/pupil quads live on the head. Eyelashes are separate meshes whose
    names also contain 'eye'; they must keep their normal material."""
    name = str(np).lower()
    if "lash" in name:
        return False
    return "eye" in name or "pupil" in name


def _cut_attrib():
    if _shader[0] is None:
        _shader[0] = _Sh.make(_Sh.SL_GLSL, _VERT, _FRAG_HARD if _CUT_HARD else _FRAG)
    return _SA.make(_shader[0], 1)


def _cut_state(st):
    if _CUT_HARD:
        st = st.setAttrib(_TA.make(_TA.MNone))
    else:
        st = st.setAttrib(_TA.make(_TA.MAlpha)).setAttrib(_DW.make(_DW.MOn))
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
                        # Actors (toons) load through this path. Keep their normal material;
                        # only add a depth offset to eye/pupil quads so they don't sink into
                        # the head at certain angles.
                        is_eye = _is_eye_part(gn)
                        if is_eye and _EYE_OFF:
                            cur = st.getAttrib(_DOA)
                            ns = st.setAttrib(_DOA.make((cur.getOffset() if cur is not None else 0) - _EYE_OFF))
                            node.setGeomState(i, ns)
                            _log_decal_node(gn, "eye-actor")
                        else:
                            node.setGeomState(i, st.setAttrib(_TA.make(_TA.MAlpha)))        # characters: faces need the plain blend look
                    else:
                        node.setGeomState(i, st.setAttrib(_TA.make(_TA.MAlpha)).setAttrib(_DW.make(_DW.MOff)))
        for n in root.findAllMatches("**"):
            ta = n.node().getAttrib(_TA)
            if ta is not None and ta.getMode() in _CUTOUT:
                is_eye_node = _is_eye_part(n)
                if any(k in str(n).lower() for k in ("sign", "eye", "pupil", "lash", "window", "trolley", "billboard", "poster", "banner")):
                    _log_decal_node(n, "cutout")
                if use_ms:
                    n.setTransparency(_TA.MMultisampleMask)
                elif use_shader:
                    if _CUT_HARD:
                        n.setTransparency(_TA.MNone)
                    else:
                        n.setTransparency(_TA.MAlpha)
                        n.setDepthWrite(True)   # keep occlusion; only the blended edge pixels are see-through
                    n.setAttrib(_cut_attrib())
                elif not shader:
                    if is_eye_node and _EYE_OFF:
                        cur = n.getAttrib(_DOA)
                        n.setAttrib(_DOA.make((cur.getOffset() if cur is not None else 0) - _EYE_OFF))
                        _log_decal_node(n, "eye-actor")
                    else:
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

# Panda's built-in shader for phones and browsers (everything without a shader of its own) works out vertex positions at "mediump"
# precision. Most phone GPUs quietly use full precision anyway, but Mali GPUs really use half precision there, so walls and ground
# wobble apart and the sky shows through the gaps. Draw the 3D world with the same shader at full precision. Being tried first by a
# player with a Mali phone, so for now only ?hp=1 turns it on.
_HP_VERT = """#version 100
precision highp float;
attribute vec4 p3d_Vertex;
attribute vec4 p3d_Color;
attribute vec4 p3d_MultiTexCoord0;
varying lowp vec4 color;
varying highp vec3 texcoord;
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_TextureMatrix;
uniform vec4 p3d_ColorScale;
void main(void) {
  gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
  texcoord = (p3d_TextureMatrix * p3d_MultiTexCoord0).xyw;
  color = p3d_Color * p3d_ColorScale;
}
"""
_HP_FRAG = """#version 100
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
varying lowp vec4 color;
varying highp vec3 texcoord;
uniform lowp sampler2D p3d_Texture0;
uniform lowp vec4 p3d_TexAlphaOnly;
void main(void) {
  gl_FragColor = texture2DProj(p3d_Texture0, texcoord);
  gl_FragColor += p3d_TexAlphaOnly;
  gl_FragColor *= color;
}
"""


def _full_precision_shader(b):
    if "hp=1" not in _q:
        print("web: full precision shader off")
        return
    try:
        b.render.setShader(_Sh.make(_Sh.SL_GLSL, _HP_VERT, _HP_FRAG))     # models with a shader of their own (the cut-outs) keep theirs
        print("web: full precision shader on")
    except BaseException:
        print("web: full precision shader failed", traceback.format_exc())

# Some phone graphics drivers (seen on a Mali GPU, in both Chrome and Firefox) do not clear the depth buffer between frames. Every
# surface then ties with its own depth from the frame before and loses about half its pixels, so the sky, which is drawn first,
# shows through walls in flickering patches (even indoors). Reset the depth buffer ourselves: before anything else each frame,
# draw one invisible card over the whole screen that writes "farthest away" everywhere. On by default for Mali GPUs;
# ?zfix=1 turns it on for any device, ?zfix=0 turns it off.
_ZF_VERT = """#version 100
attribute vec4 p3d_Vertex;
void main() {
  gl_Position = vec4(p3d_Vertex.x, p3d_Vertex.z, 0.999999, 1.0);   // just inside the far plane, so it is never clipped
}
"""
_ZF_FRAG = """#version 100
precision mediump float;
void main() {
  gl_FragColor = vec4(0.0);
}
"""


def _depth_reset(b):
    try:
        gpu = str(getattr(TTA, "gpu", "") or "")
    except BaseException:
        gpu = ""
    on = "zfix=1" in _q or ("mali" in gpu.lower() and "zfix=0" not in _q)
    print("web: gpu =", gpu or "?", "| depth reset", "on" if on else "off")
    if not on:
        return
    try:
        from panda3d.core import CardMaker, ColorWriteAttrib, DepthTestAttrib, OmniBoundingVolume
        cm = CardMaker("tta-depth-reset")
        cm.setFrame(-1, 1, -1, 1)
        card = b.render.attachNewNode(cm.generate())
        card.setShader(_Sh.make(_Sh.SL_GLSL, _ZF_VERT, _ZF_FRAG), 10000)
        card.setAttrib(ColorWriteAttrib.make(ColorWriteAttrib.COff), 10000)
        card.setAttrib(DepthTestAttrib.make(DepthTestAttrib.MAlways), 10000)
        card.setDepthWrite(True, 10000)
        card.setTwoSided(True, 10000)
        card.setBin("background", -1000, 10000)          # before the sky (background 100) and everything else
        card.setLightOff(10000)
        card.setFogOff(10000)
        card.node().setBounds(OmniBoundingVolume())       # never culled: the shader puts it over the whole screen
        card.node().setFinal(True)
    except BaseException:
        print("web: depth reset failed", traceback.format_exc())

# Decals (windows and doors drawn on walls) are made to win over the wall only by a depth offset of 1 per level. On the phone's graphics
# layer that is too little, which is what makes them flicker. ?decal=N adds N more per level.
from panda3d.core import DecalEffect as _DECALFX
try:
    _DECAL = int((_pq2(_q.lstrip("?")).get("decal", ["2"]) or ["2"])[0])
except BaseException:
    _DECAL = 2
try:
    _EYE_OFF = int((_pq2(_q.lstrip("?")).get("eyeoff", ["0"]) or ["0"])[0])
except BaseException:
    _EYE_OFF = 0
print("web: extra decal depth offset =", _DECAL)
print("web: eye depth offset =", _EYE_OFF)

_DECALSEEN = set()


def _decal_name(np):
    return str(np).lower()


def _log_decal_node(np, tag):
    try:
        name = str(np)
        key = tag + ':' + name
        if key in _DECALSEEN:
            return
        _DECALSEEN.add(key)
        if len(_DECALSEEN) > 40:
            return
        ta = np.getAttrib(_TA) if hasattr(np, 'getAttrib') else None
        mode = ta.getMode() if ta is not None else '?'
        dw = np.getAttrib(_DW) if hasattr(np, 'getAttrib') else None
        doff = np.getAttrib(_DOA) if hasattr(np, 'getAttrib') else None
        print("web: decal node %s name=%s ta=%s dw=%s doff=%s decal=%s" % (
            tag, name[-90:], mode,
            dw.getMode() if dw is not None else '?',
            doff.getOffset() if doff is not None else '?',
            np.hasEffect(_DECALFX.getClassType()) if hasattr(np, 'hasEffect') else '?'))
    except BaseException:
        pass


def boost_decals(root):
    if _DECAL <= 0:
        return
    try:
        nodes = [root] + [n for n in root.findAllMatches("**")]
        for n in nodes:
            if n.hasEffect(_DECALFX.getClassType()):
                for i in range(n.getNumChildren()):
                    c = n.getChild(i)
                    c.setDepthOffset(_DECAL)
                    if any(k in _decal_name(c) for k in ("sign", "window", "door", "trolley", "billboard")):
                        _log_decal_node(c, "boost")
    except BaseException:
        print("web: decal boost failed", traceback.format_exc())




from direct.showbase import Loader as _Loader
_orig_loadModel = _Loader.Loader.loadModel
_remastered = False


def sharpen_world_textures(model):
    """Use consistent oblique-angle filtering for Remastered world maps."""
    if not _remastered:
        return
    for texture in model.findAllTextures():
        if not texture.usesMipmaps() or texture.getAnisotropicDegree() >= 4:
            continue
        path = texture.getFilename().getFullpath().lower()
        name = path.rsplit("/", 1)[-1]
        # Keep standalone alpha masks, eye art, shadows and interface maps
        # on their authored samplers.
        if ("/maps/" not in path or name.endswith((".rgb", ".rgba"))
                or any(part in name for part in ("shadow", "eyes", "pupil", "lash", "gui", "interface"))):
            continue
        texture.setAnisotropicDegree(4)


def _loadModel(self, *a, **k):
    r = _orig_loadModel(self, *a, **k)
    try:
        path = str(a[0] if a else k.get("modelPath", "")).replace(chr(92), "/").lower()
        # Characters, and the skies: the sky's cloud cards are drawn first with depth testing off, and Mali's hidden-surface
        # pass (Immortalis-G925) let a cut-out shader there (it uses discard) win over the walls drawn after it, so clouds
        # showed through buildings. The sky never writes depth, so plain blending loses nothing and looks like the original.
        is_char = "/char/" in path or "_sky" in path
        if isinstance(r, _NP):
            fix_transparency(r, not is_char)
            apply_uber(r)
            boost_decals(r)
            if "/gui/" not in path:
                sharpen_world_textures(r)
        elif isinstance(r, (list, tuple)):
            for x in r:
                if isinstance(x, _NP):
                    fix_transparency(x, not is_char)
                    apply_uber(x)
                    boost_decals(x)
                    if "/gui/" not in path:
                        sharpen_world_textures(x)
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
        sharpen_world_textures(self)
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

# sound: the page plays it (see webaudio.py / tta-audio.js)
import webaudio
builtins._tta_webaudio_module = webaudio
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
# home bar). The layout code is shared with the native apps (hud.py); the page tells it how big the safe area is.
import hud
hud.install(ShowBase, lambda: (float(TTA.safeL), float(TTA.safeR), float(TTA.safeT), float(TTA.safeB), float(TTA.vh)))


def _install_smooth_walk():
    """Ease walking and turning in and out. The stock walker jumps to full speed the frame a key goes down and stops the frame it comes up,
    which feels jerky. We scale the walker's speeds by a ramp, and while a ramp is still running down after the key came up we make the
    walker see the key as held, so the toon glides to a stop."""
    from direct.controls import GravityWalker as _gravity_walker
    GravityWalker = _gravity_walker.GravityWalker
    inputState = _gravity_walker.inputState        # the walker's own handle: importing InputStateGlobal fresh trips a circular import in the web build
    from panda3d.core import ClockObject
    orig = GravityWalker.handleAvatarControls
    # Easing is off: the toon reaches the stick's speed at once and stops when it is let go (as the stock walker does). The stick itself is
    # analog, so how far it is pushed still sets the speed. Set EASING to True to ease in and out again over the times below.
    EASING = False
    UP_MOVE, DOWN_MOVE, UP_TURN, DOWN_TURN = 0.16, 0.12, 0.09, 0.07        # seconds to reach full speed / to stop

    def ramp(v, target, dt, up, down):
        if not EASING:
            return target
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
        tf, tt = 1.0 if fw else (-1.0 if rv else 0.0), 1.0 if tl else (-1.0 if tr else 0.0)
        try:
            # the thumb stick is analog: how far it is pushed sets how fast the toon walks and turns (keys and auto-run stay full speed)
            import webui_core as _wc
            ax, ay = _wc._analog
            if ay and not bool(base.localAvatar and base.localAvatar.getAutoRun()):
                tf = max(-1.0, min(1.0, ay))
            if ax:
                tt = max(-1.0, min(1.0, -ax))
        except BaseException:
            pass
        st[0] = ramp(st[0], tf, dt, UP_MOVE, DOWN_MOVE)
        st[1] = ramp(st[1], tt, dt, UP_TURN, DOWN_TURN)
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
_TASK_TIMERS = []


def _perf_device_label():
    """Tag frame samples with browser/device context to disambiguate shared logs."""
    try:
        win = platform.window
        nav = win.navigator
        ua = str(nav.userAgent)
        if "iPhone" in ua:
            device = "iPhone"
        elif "iPad" in ua or ("Macintosh" in ua and int(nav.maxTouchPoints or 0) > 1):
            device = "iPad"
        else:
            device = "other"
        standalone = bool(getattr(nav, "standalone", False))
        try:
            standalone = standalone or bool(win.matchMedia("(display-mode: standalone)").matches)
        except BaseException:
            pass
        return "%s mode=%s viewport=%sx%s dpr=%s" % (
            device, "standalone" if standalone else "browser",
            int(win.innerWidth), int(win.innerHeight), float(win.devicePixelRatio or 1))
    except BaseException:
        return "device=unknown"


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


def _start_task_timers(b):
    """Time PythonTask callbacks without Panda's incompatible web TaskProfiler."""
    import time as _t
    _TASK_TIMERS[:] = []
    try:
        tasks = b.taskMgr.getTasks()
    except BaseException:
        print("web: task timing unavailable", traceback.format_exc())
        return 0
    for task in tasks:
        try:
            original = task.getFunction()
            if not callable(original) or getattr(original, "_tta_timed", False):
                continue
            metric = {"name": str(task.getName()), "calls": 0, "total": 0.0, "max": 0.0}

            def timed(*args, __func=original, __metric=metric, **kwargs):
                start = _t.perf_counter()
                try:
                    return __func(*args, **kwargs)
                finally:
                    elapsed = (_t.perf_counter() - start) * 1000.0
                    __metric["calls"] += 1
                    __metric["total"] += elapsed
                    if elapsed > __metric["max"]:
                        __metric["max"] = elapsed

            timed._tta_timed = True
            task.setFunction(timed)
            _TASK_TIMERS.append((task, original, timed, metric))
        except BaseException:
            continue
    print("web: task timing started callbacks=%d" % len(_TASK_TIMERS))
    return len(_TASK_TIMERS)


def _stop_task_timers(sample_frames=0):
    for task, original, timed, _metric in _TASK_TIMERS:
        try:
            if task.getFunction() is timed:
                task.setFunction(original)
        except BaseException:
            pass
    rows = [metric for _task, _original, _timed, metric in _TASK_TIMERS if metric["calls"]]
    rows.sort(key=lambda row: row["total"], reverse=True)
    total_ms = sum(row["total"] for row in rows)
    per_frame = total_ms / sample_frames if sample_frames else 0.0
    print("web: task timing complete callbacks=%d sampled=%d aggregate=%.1fms avg/frame=%.2fms frames=%d" % (
        len(_TASK_TIMERS), len(rows), total_ms, per_frame, sample_frames))
    for row in rows[:20]:
        print("web: task cost total=%.1fms avg=%.3fms max=%.1fms calls=%d name=%s" % (
            row["total"], row["total"] / row["calls"], row["max"], row["calls"], row["name"]))
    _TASK_TIMERS[:] = []


def _anchor_hud(b):
    """The game lays its screen-edge buttons out for a 4:3 screen; hud.py hangs the ones near the sides from the screen's edges."""
    hud.anchor_hud(b)


def _web_mouse_click_count():
    """Read the wrapper click counter across the tta/ttr compatibility aliases."""
    try:
        bridge = getattr(platform.window, "tta", None)
        if bridge is None:
            bridge = getattr(platform.window, "ttr", None)
        return int(getattr(bridge, "mc", 0))
    except BaseException:
        return 0


def _install_chat_click_fallback(b):
    """Advance a local NPC speech page if its 3D nametag click target misses."""
    if getattr(b, "_tta_chat_click_fallback", False):
        return
    b._tta_chat_click_fallback = True

    def on_mouse1():
        try:
            from otp.avatar.Avatar import Avatar
            from direct.task import Task
            local = getattr(builtins, "localAvatar", None)
            candidates = list(Avatar.ActiveAvatars)
            try:
                candidates.extend(b.cr.doId2do.values())
            except BaseException:
                pass
            seen = set()
            for av in reversed(candidates):
                if id(av) in seen:
                    continue
                seen.add(id(av))
                if av is local or not hasattr(av, "nametag"):
                    continue
                if getattr(av, "_Avatar__chatAddressee", None) != getattr(local, "doId", None):
                    continue
                if not av.nametag.hasButton():
                    continue
                page = getattr(av, "_Avatar__chatPageNumber", None)
                def advance_if_missed(task, av=av, page=page):
                    try:
                        if (getattr(av, "_Avatar__chatPageNumber", None) == page
                                and av.nametag.hasButton()):
                            av.advancePageNumber()
                    except BaseException:
                        pass
                    return Task.done
                b.taskMgr.doMethodLater(0.08, advance_if_missed,
                                        "tta-chat-click-fallback-%s" % id(av))
                return
        except BaseException:
            print("web: chat-click fallback failed", traceback.format_exc())

    b._tta_chat_click_handler = on_mouse1
    b._tta_last_mouse_click = _web_mouse_click_count()
    b.accept("mouse1", on_mouse1)


def _poll_chat_click_fallback(b):
    try:
        current = _web_mouse_click_count()
        previous = int(getattr(b, "_tta_last_mouse_click", current))
        if current != previous:
            b._tta_last_mouse_click = current
            handler = getattr(b, "_tta_chat_click_handler", None)
            if handler:
                handler()
    except BaseException:
        pass


def _sync_size(b):
    try:
        w, h = int(TTA.winW), int(TTA.winH)
        _install_chat_click_fallback(b)
        _poll_chat_click_fallback(b)
        try:
            TTA.pw, TTA.ph = int(b.win.getXSize()), int(b.win.getYSize())
        except BaseException:
            pass
        if w > 0 and h > 0 and getattr(b, "win", None) is not None and (b.win.getXSize(), b.win.getYSize()) != (w, h):
            props = WindowProperties()
            props.setSize(w, h)
            b.win.requestProperties(props)
    except BaseException:
        print("web: size sync failed", traceback.format_exc())


def _run_debug_code():
    """Developer console: the page can set tta.pycode to Python source, which runs here once."""
    try:
        code = str(TTA.pycode)
    except BaseException:
        return
    if code and code != _last_code[0]:
        _last_code[0] = code
        try:
            exec(code, globals())
        except BaseException:
            print("web: debug code failed")
            print(traceback.format_exc())


def TTA_mark(msg):
    try:
        platform.window.console.log("PY| MARK " + msg)
    except Exception:
        pass


async def main(_sleep=asyncio.sleep):
    TTA.pyReady = True
    print("web: ready, waiting for the page to download the game files and sign in")
    while not bool(TTA.go) and not bool(TTA.dbg):
        await asyncio.sleep(0.1)
    cookie = str(TTA.cookie)
    webnet.WS_URL = str(TTA.wsUrl)
    os.makedirs("logs", exist_ok=True)
    started = False
    try:
        # Open Toontown: the compiled libotp / libtoontown are replaced by our pure-Python versions
        TTA_mark("importing otpy")
        import otpy.install
        otpy.install.install()
        try:
            _install_smooth_walk()
        except BaseException:
            print("web: smooth walking not installed", traceback.format_exc())
        import otpy.dnaparser
        global _remastered
        _remastered = str(getattr(TTA, "textureMode", "original")) == "remastered"

        def _dna_model_hook(np):
            is_char = False
            fix_transparency(np, not is_char)
            apply_uber(np)
            boost_decals(np)
            sharpen_world_textures(np)
        otpy.dnaparser.MODEL_HOOK = _dna_model_hook
        TTA_mark("otpy installed")
        from panda3d.core import loadPrcFile
        # TTA: make relative etc/*.dc resolve to the freshly-downloaded code pack.
        import os as _tta_os
        _tta_os.chdir('/data/data/game_ot/assets')
        print('web: CWD for DC =', _tta_os.getcwd())
        loadPrcFile("etc/Configrc.prc")
        # Set the requested framebuffer before Panda creates its window.
        edges = str(TTA.aa) == "1"
        loadPrcFileData("", "framebuffer-multisample %d" % int(edges))
        loadPrcFileData("", "multisamples %d" % (4 if edges else 0))
        loadPrcFileData("", "framebuffer-optional 1")
        print("web: smooth edges", "on" if edges else "off")
        for line in ("load-display pandagles2", "audio-library-name null", "toontown-auto-run 0", "want-dev #f", "connect-method native",
                     "sync-video 0", "notify-level warning", "uniquify-transforms 0", "transform-cache 0", "dna-path resources", "default-model-extension .bam",
                     "interpolate-frames 1",       # blend between an animation's frames (the toon animations are authored at 24 fps and look choppy without it)
                     "hardware-animated-vertices 1",    # GPU vertex skinning instead of CPU
                     "gl-force-no-error 1",             # skip WebGL error polling per draw call
                     "gl-finish 0",                     # prevent CPU stalling to wait for GPU pipeline drain
                     "gl-force-flush 0",                # prevent explicit glFlush calls between frames
                     "preload-textures 1",              # upload textures to GPU VRAM up front
                     "textures-power-2 none",           # WebGL2 supports NPOT natively; skip CPU rescaling
                     "flatten-geoms 1",                 # merge compatible geometry to reduce draw calls
                     "vertex-buffers 1", "aspect-ratio 0"):      # the game's own config turns vertex buffers OFF, which a browser (WebGL) cannot do
            loadPrcFileData("", line)
        try:
            if int(TTA.winW) > 0:
                loadPrcFileData("", "win-size %d %d" % (int(TTA.winW), int(TTA.winH)))
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
        try:
            from panda3d.core import ClockObject
            ClockObject.getGlobalClock().setMode(ClockObject.MNormal)
            print("web: global clock mode explicitly set to MNormal (uncapped, matches display refresh rate)")
        except BaseException:
            pass
        _full_precision_shader(builtins.base)
        _depth_reset(builtins.base)
    except BaseException:
        print("web: STARTUP FAILED")
        print(traceback.format_exc())
    frames = 0
    import time as _time
    try:
        _profile_location = platform.window.location
        _profile_host = str(_profile_location.hostname).lower()
        _profile_port = str(_profile_location.port)
        _profile_standalone = bool(platform.window.navigator.standalone)
        try:
            _profile_standalone = _profile_standalone or bool(
                platform.window.matchMedia("(display-mode: standalone)").matches)
        except BaseException:
            pass
        _profile_local = (_profile_port == "7380" or _profile_host in ("localhost", "127.0.0.1") or
                          _profile_host.startswith(("192.168.", "10.", "172.16.")))
        profile_requested = _profile_local and _profile_standalone
    except BaseException:
        _profile_host = "unknown"
        _profile_port = "unknown"
        _profile_standalone = False
        profile_requested = False
    print("web: task profiling requested =", profile_requested,
          "local_host=", _profile_host, "port=", _profile_port, "standalone=", _profile_standalone)
    profile_state = {"start_frame": None, "done": False}
    def _where(b):
        """Where the toon is and how much is around it: the zone, how many objects, toons and Cogs the game holds."""
        try:
            zone = b.cr.playGame.getPlace().getZoneId()
            toons = suits = 0
            objs = list(b.cr.doId2do.values())
            for o in objs:
                n = o.__class__.__name__
                if n == "DistributedToon":
                    toons += 1
                elif n.startswith("DistributedSuit") or n == "DistributedFactorySuit":
                    suits += 1
            try:
                from panda3d.core import TransformState as _TS, RenderState as _RS
                states = " states=%d/%d" % (_TS.getNumStates(), _RS.getNumStates())
            except BaseException:
                states = ""
            return "zone=%s objs=%d toons=%d suits=%d%s" % (zone, len(objs), toons, suits, states)
        except BaseException:
            return "place=?"

    _pf = {"last": None, "dts": [], "steps": [], "work": []}      # frame timing: how long frames take, and how much of that is the game's own step
    _perf_label = _perf_device_label()
    print("web: perf device", _perf_label)
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
                await _sleep(1)
            # The browser runner may execute ToontownStart as __main__, which can disturb this module's import globals.
            # Keep these bridges on builtins so reconnects cannot kill the frame pump with NameError.
            try:
                _ui_bridge = getattr(builtins, "_tta_webui_module", None)
                if _ui_bridge is not None:
                    _ui_bridge.poll()
            except BaseException:
                if not getattr(builtins, "_tta_webui_poll_error_logged", False):
                    builtins._tta_webui_poll_error_logged = True
                    print("web: UI bridge poll failed", traceback.format_exc())
            try:
                _audio_bridge = getattr(builtins, "_tta_webaudio_module", None)
                if _audio_bridge is not None:
                    _audio_bridge.tick()
            except BaseException:
                if not getattr(builtins, "_tta_webaudio_tick_error_logged", False):
                    builtins._tta_webaudio_tick_error_logged = True
                    print("web: audio bridge tick failed", traceback.format_exc())
            frames += 1
            if frames % 20 == 0:
                _sync_size(b)
                _anchor_hud(b)
                _run_debug_code()
            if frames == 30 and not started:
                started = True
                TTA.started()
                try:
                    _install_perf_probes(b)
                    if bool(getattr(TTA, "perfOn", False)):       # (test sessions only: timing every task costs a little)
                        _instrument_tasks(b)
                except BaseException:
                    print("web: perf probes failed", traceback.format_exc())
            if frames % 600 == 0:
                print("web: frames", frames)
            _pf["work"].append((_time.perf_counter() - _t0) * 1000.0)
            if len(_pf["dts"]) >= 300:
                d, st = sorted(_pf["dts"]), sorted(_pf["steps"])
                n = len(d)
                print("web: perf device=%s fps=%.1f frame avg=%.1fms p95=%.1fms max=%.0fms slow(>50ms)=%d | step avg=%.1fms p95=%.1fms max=%.0fms | full game work avg=%.1fms" % (
                    _perf_label, 1000.0 * n / sum(d), sum(d) / n, d[int(n * 0.95)], d[-1], sum(1 for x in d if x > 50), sum(st) / len(st), st[int(len(st) * 0.95)], st[-1], sum(_pf["work"]) / len(_pf["work"])))
                print("web: perf where " + _where(b))
                _pf["dts"], _pf["steps"], _pf["work"] = [], [], []
                if _PERF["slow"] or _PERF["gc"]:
                    print("web: hitches in that window: loads", _PERF["slow"][-8:], "| gc", _PERF["gc"][-6:])
                    _PERF["slow"], _PERF["gc"] = [], []
            # Time Python callbacks briefly after the world has settled. Panda's built-in
            # TaskProfiler crashes in the browser Wasm build, so this opt-in timer wraps the
            # active callbacks directly and restores them after one short sample.
            if started and not profile_state["done"] and profile_requested:
                try:
                    if profile_state.get("start_frame") is None and frames >= 900:
                        _start_task_timers(b)
                        profile_state["start_frame"] = frames
                        print("web: per-task timing sampling started (300 foreground frames)")
                    elif profile_state.get("start_frame") is not None and frames - profile_state["start_frame"] >= 300:
                        _stop_task_timers(frames - profile_state["start_frame"])
                        profile_state["done"] = True
                except BaseException:
                    start_frame = profile_state.get("start_frame")
                    _stop_task_timers(frames - start_frame if start_frame is not None else 0)
                    profile_state["done"] = True
                    print("web: per-task timing unavailable", traceback.format_exc())
        await _sleep(0)


asyncio.run(main())

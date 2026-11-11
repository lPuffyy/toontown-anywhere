"""Launcher for the Toontown: Anywhere client on iOS (the TTA flavour of ios_game.py; the app build copies this file over ios_game.py when
FLAVOR=tta). The UIKit shell (main.m) calls the same functions as before; they now do the Toontown: Anywhere things:

  start_download(docs, server)   - background: check /packs.json and download what changed (same packs the browser and Windows apps use)
  ui_status()                    - 'fraction|message|detail|done|error' for the progress screen
  check_login(server, cookie)    - the server's /auth; 'ok', 'setup' (no recovery answers yet) or a message
  recovery_call(_hex)            - /setrecovery and /recover
  test_server(_hex)              - "Change server": checks that the address serves Toontown: Anywhere's game files
  set_screen(w, h, l, r, t, b)   - the screen's size and safe area in pixels (UIKit's safeAreaInsets); called again whenever they change
  launch(...)                    - start the game (the game's own ToontownStart, with otpy and the WebSocket connection)
  step()                         - one main-loop iteration (from a CADisplayLink)
  ui_*                           - the touch controls and typed chat, the same game-control code the browser and the Windows app use

Everything that is not iOS-specific is the shared tta_native package (copied in next to this file by sync_tta.py).
"""
import json
import os
import sys
import threading
import time
import traceback
import ssl

_HERE = os.path.dirname(os.path.abspath(__file__))
_CA = os.path.join(_HERE, "cacert.pem")
if os.path.exists(_CA):
    ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=_CA)        # iOS has no system CA store for Python
for _p in (_HERE, os.path.join(_HERE, "vendor")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import urllib.request
_op = urllib.request.build_opener()
_op.addheaders = [("User-Agent", "TTAnywhere-iOS/0.1")]          # Cloudflare rejects Python's own user agent
urllib.request.install_opener(_op)

from tta_native import auth as _auth                                   # noqa: E402
from tta_native import controls as _controls                           # noqa: E402
from tta_native.packs import Updater as _Updater                       # noqa: E402

RESOURCE_SERVER_HINT = [None]
_opts = {}                      # options chosen in the settings cog (main.m sends them): 'fps', 'smooth_edges' (same names as the spec's row ids)
_updater = [None]
_screen = {"w": 0.0, "h": 0.0, "l": 0.0, "r": 0.0, "t": 0.0, "b": 0.0}
_frames = [0]
_step_err = [0]

# the touch controls and typed chat: the shell calls these by name (see main.m)
for _n in dir(_controls):
    if _n.startswith("ui_"):
        globals()[_n] = getattr(_controls, _n)


# ---- files
def start_download(docs, server):
    RESOURCE_SERVER_HINT[0] = server
    u = _Updater(server, docs, log=lambda m: print("ios_game:", m, flush=True))
    _updater[0] = u
    u.start()


def ui_status():
    u = _updater[0]
    if u is None:
        return "0.0000|starting||0|"
    st = u.state
    total = st.get("total_bytes", 0)
    frac = min(1.0, st.get("done_bytes", 0) / total) if total else (1.0 if st.get("finished") and not st.get("error") else 0.0)
    detail = ("%d MB of %d MB" % (st["done_bytes"] // 1048576, total // 1048576)) if total else ""
    return "%.4f|%s|%s|%d|%s" % (frac, str(st.get("text", "")).replace("|", "/"), detail, 1 if (st.get("finished") and not st.get("error")) else 0,
                                 str(st.get("error", "")).replace(chr(10), " | "))


def status():
    u = _updater[0]
    if u is None:
        return "starting", False, None
    st = u.state
    return st.get("text", ""), bool(st.get("finished")) and not st.get("error"), st.get("error") or None


# ---- sign-in and recovery
def check_login(server, cookie):
    user, _, pw = cookie.partition(":")
    ok, text = _auth.sign_in(server, user, pw)
    return ("setup" if text == "setup" else "ok") if ok else (text or "Sign-in failed.")


def recovery_call(server, path, text):
    from tta_native.auth import _post
    status, msg = _post(server, path, text)
    return "ok" if status == 200 else (msg or "That didn't work.")


def recovery_call_hex(server, path, hextext):
    return recovery_call(server, path, bytes.fromhex(hextext).decode("utf-8"))


def test_server(res, game):
    """'ok|<file server>|<game server>' or a message. The game server field is not used (the game connects through the file server's
    /ws address), so it is passed through unchanged."""
    res = res.strip().rstrip("/")
    cands = [res] if "://" in res else ["https://" + res, "http://" + res]
    if "://" in res and not res.lower().startswith(("http://", "https://")):
        return "The server address should start with http:// or https://"
    last = "Can't reach the server."
    for u in cands:
        try:
            with urllib.request.urlopen(u + "/packs.json", timeout=12) as r:
                head = r.read(64).lstrip()
            if head[:1] == b"[":
                return "ok|%s|%s" % (u, game.strip() or u)
            last = "That address doesn't look like a Toontown: Anywhere server (no game file list found)."
        except Exception:
            last = "Can't reach the server. Check the address and your connection."
    return last


def test_server_hex(res_hex, game_hex):
    return test_server(bytes.fromhex(res_hex).decode("utf-8"), bytes.fromhex(game_hex).decode("utf-8"))


# ---- screen shape and safe area
def set_screen(w, h, left, right, top, bottom):
    """Pixels. Called before the game starts and again whenever the screen's size or safe area changes (a rotation, a foldable opening or
    closing, Stage Manager resizing the window, a bar showing or hiding)."""
    new = {"w": float(w), "h": float(h), "l": float(left), "r": float(right), "t": float(top), "b": float(bottom)}
    changed = new != _screen
    _screen.update(new)
    if changed:
        try:
            from tta_native import display
            display.refresh()
        except BaseException:
            pass
        _resize_game_window()


def _screen_insets():
    return _screen["l"], _screen["r"], _screen["t"], _screen["b"]


def _resize_game_window():
    """Ask the game's window to match the screen's new size (the window object follows the UIKit view on iOS; this makes sure Panda's
    own idea of the size, which sets the 3D view's shape and the screen-edge anchors, is updated)."""
    import builtins
    b = getattr(builtins, "base", None)
    if b is None or getattr(b, "win", None) is None or _screen["w"] <= 0:
        return
    try:
        from panda3d.core import WindowProperties
        cur = b.win.getProperties()
        if (cur.getXSize(), cur.getYSize()) != (int(_screen["w"]), int(_screen["h"])):
            props = WindowProperties()
            props.setSize(int(_screen["w"]), int(_screen["h"]))
            b.win.requestProperties(props)
            print("ios_game: window resize requested to %dx%d (was %dx%d)" % (_screen["w"], _screen["h"], cur.getXSize(), cur.getYSize()), flush=True)
    except BaseException:
        print("ios_game: window resize failed", traceback.format_exc(), flush=True)


# ---- options from the settings cog
def set_option(name, value):
    """'fps': show or hide the frame counter now. 'smooth_edges': used the next time the game starts."""
    _opts[name] = str(value)
    if name == "fps":
        import builtins
        b = getattr(builtins, "base", None)
        if b is not None:
            try:
                b.setFrameRateMeter(str(value) != "0")
            except BaseException:
                print("ios_game: frame counter failed", traceback.format_exc(), flush=True)


# ---- the game
def launch(docs, frameworks, game_server, cookie, app_dir):
    from panda3d.core import ExecutionEnvironment, Filename, VirtualFileSystem, loadPrcFile, loadPrcFileData
    server = (RESOURCE_SERVER_HINT[0] or "").rstrip("/")
    if not server:
        raise RuntimeError("no server address")
    game_dir = os.path.join(docs, "game")
    os.chdir(game_dir)
    VirtualFileSystem.get_global_ptr().chdir(Filename.from_os_specific(game_dir))        # Panda caches the folder it started in
    ExecutionEnvironment.set_environment_variable("MAIN_DIR", Filename.from_os_specific(game_dir).get_fullpath())
    sys.path.insert(0, game_dir)
    os.makedirs(os.path.join(docs, "logs"), exist_ok=True)
    print("ios_game.launch: cwd =", os.getcwd(), "server", server, flush=True)

    from tta_native import display, hud, netlayer
    from tta_native.app import ws_url
    netlayer.WS_URL = ws_url(server)
    netlayer.CA_FILE = _CA if os.path.exists(_CA) else None
    display.set_provider(_screen_insets)

    # the game's own options file picks the window size: full screen at this screen's size, so the game fills the whole screen
    try:
        opts = {}
        p = os.path.join(game_dir, "useropt.json")
        if os.path.exists(p):
            try:
                opts = json.load(open(p, encoding="utf8"))
            except (OSError, ValueError):
                opts = {}
        opts["windowed-mode"] = False
        if _screen["w"] > 0:
            opts["resolution"] = [int(_screen["w"]), int(_screen["h"])]
        json.dump(opts, open(p, "w", encoding="utf8"), indent=4)
    except OSError:
        pass

    loadPrcFile(Filename("etc/Configrc.prc"))
    audio = "p3openal_audio" if os.path.exists(os.path.join(frameworks, "libp3openal_audio.dylib")) else "null"
    for line in ("plugin-path " + frameworks, "load-display pandagles", "audio-library-name " + audio, "toontown-auto-run 0", "want-dev #f",
                 "connect-method native", "notify-level warning", "dna-path resources", "default-model-extension .bam", "interpolate-frames 1",
                 "aspect-ratio 0", "sync-video 1", "garbage-collect-states-rate 0.05", "dna-ram-cache-hood-models #f"):    # (no model cache: memory is what iOS kills for)
        loadPrcFileData("", line)
    smooth = _opts.get("smooth_edges", "1") != "0"                         # the cog's "Smooth edges"
    loadPrcFileData("", "framebuffer-multisample %d" % (1 if smooth else 0))
    loadPrcFileData("", "multisamples %d" % (4 if smooth else 0))
    try:
        from direct.showbase import ShowBaseGlobal
        import builtins
        ShowBaseGlobal.__dev__ = False
        builtins.__dev__ = False
    except BaseException:
        pass
    from direct.showbase.ShowBase import ShowBase
    hud.install(ShowBase, lambda: tuple(list(_screen_insets()) + [max(1.0, _screen["h"])]))
    # No startup splash in this app (the Disney logo, the version text and the loading bar flickered and are not wanted): everything the
    # game draws in 2D while it starts is hidden until launch() has finished, and the loading screen is switched off for that time.
    try:
        from toontown.toontowngui import ToontownLoadingScreen as _tls
        _cls = _tls.ToontownLoadingScreen
        _saved = {n: getattr(_cls, n) for n in ("begin", "tick", "abort", "end")}
        _cls.begin = lambda self, range, label, gui, tipCategory: None
        _cls.tick = lambda self: None
        _cls.abort = lambda self: None
        _cls.end = lambda self: (0, 0)
        _loading_saved.update(cls=_cls, methods=_saved)
    except BaseException:
        print("ios_game: could not turn the loading screen off", traceback.format_exc(), flush=True)
    _orig_open = ShowBase.openMainWindow

    def _open_main_window(self, *args, **kwargs):
        # EAGL's buffer is undefined after presenting: clear all of it every frame from the very first one (the loading screen is drawn
        # before the shell's main loop starts, and without this it flickers)
        res = _orig_open(self, *args, **kwargs)
        try:
            from panda3d.core import Vec4
            w = self.win
            w.set_clear_color_active(True)
            w.set_clear_color(Vec4(0, 0, 0, 1))
            w.set_clear_depth_active(True)
            w.set_clear_stencil_active(True)
            self.aspect2d.hide()                  # (shown again when launch() has finished)
        except BaseException:
            print("ios_game: early clear failed", traceback.format_exc(), flush=True)
        return res
    ShowBase.openMainWindow = _open_main_window
    netlayer.install()
    import otpy.install
    otpy.install.install()
    os.environ["LOGIN_TOKEN"] = cookie.split(":")[0]

    import builtins
    from toontown.launcher.ToontownDummyLauncher import ToontownDummyLauncher
    user = cookie.split(":")[0]

    class IOSLauncher(ToontownDummyLauncher):
        def getPlayToken(self):
            return user

    class _Game:
        name = "toontown"
        process = "client"
    builtins.launcher = IOSLauncher()
    builtins.game = _Game()

    sys.argv = ["ToontownStart"]
    import runpy
    try:
        runpy.run_module("toontown.toonbase.ToontownStart", run_name="__main__")
        print("ios_game.launch: ToontownStart returned; base =", getattr(builtins, "base", None), flush=True)
    except SystemExit as e:
        print("ios_game.launch: SystemExit", e.code, flush=True)
        raise
    except BaseException:
        print("ios_game.launch: EXCEPTION", traceback.format_exc(), flush=True)
        raise
    _end_startup()
    _install_extras()      # (the shell steps the main loop itself, so the helpers are set up here, once the window exists)


_loading_saved = {}


def _end_startup():
    """The game has started: show the 2D layer again and give the loading screen its drawing back (it is used between areas)."""
    import builtins
    b = getattr(builtins, "base", None)
    try:
        if b is not None:
            b.aspect2d.show()
        cls = _loading_saved.get("cls")
        for n, f in (_loading_saved.get("methods") or {}).items():
            setattr(cls, n, f)
    except BaseException:
        print("ios_game: could not end the startup", traceback.format_exc(), flush=True)


_extras = [False]


def _install_extras():
    """The game's window exists now (launch returned): add the helpers that need it."""
    import builtins
    b = getattr(builtins, "base", None)
    if b is None or _extras[0]:
        return
    _extras[0] = True
    try:
        from tta_native import chat, hud
        chat.install(b)
        b.taskMgr.doMethodLater(0.4, lambda task: (hud.ensure(b), hud.anchor_hud(b), task.again)[2], "tta-anchor-hud")
        _resize_game_window()
        set_option("fps", _opts.get("fps", "1"))
    except BaseException:
        print("ios_game: extras not installed", traceback.format_exc(), flush=True)





_converted_tex = set()


def _fix_two_channel_textures():
    """Mipmapped 1/2-channel textures render black on iOS GLES1, and luminance+alpha textures (quick chat panels,
    some GUI frames) came out faint. Use plain linear filtering for all of them, and convert luminance+alpha
    textures to ordinary RGBA so the phone never has to use that format."""
    from panda3d.core import TexturePool, SamplerState, Texture, PNMImage
    tc = TexturePool.find_all_textures()
    n = tc.get_num_textures()
    for i in range(n):
        t = tc.get_texture(i)
        comps = t.get_num_components()
        if comps in (1, 2) and t.uses_mipmaps():
            t.set_minfilter(SamplerState.FT_linear)
        if comps == 2 and t.get_format() == Texture.F_luminance_alpha and t.has_ram_image():
            key = (t.get_name(), t.get_x_size(), t.get_y_size())
            if key in _converted_tex:
                continue
            _converted_tex.add(key)
            try:
                img = PNMImage()
                if t.store(img):
                    rgba = PNMImage(img.get_x_size(), img.get_y_size(), 4)
                    rgba.copy_from(img)
                    if rgba.get_num_channels() == 4 and t.load(rgba):
                        print("converted LA texture to RGBA:", key, flush=True)
            except BaseException:
                print("LA convert failed", key, traceback.format_exc().splitlines()[-1], flush=True)


def step():
    import builtins
    b = getattr(builtins, "base", None)
    if b is not None:
        try:
            _frames[0] += 1
            if _frames[0] in (1, 2, 3, 30, 120) or _frames[0] % 600 == 0:
                w = getattr(b, "win", None)
                print("FRAME %d size=%s screen=%s" % (_frames[0], (w.get_x_size(), w.get_y_size()) if w else None, _screen), flush=True)
            if _frames[0] == 2:
                try:
                    from panda3d.core import Vec4
                    w = b.win
                    w.set_clear_color_active(True)
                    w.set_clear_color(Vec4(0, 0, 0, 1))
                    w.set_clear_depth_active(True)
                    w.set_clear_stencil_active(True)                  # EAGL's buffer is undefined after presenting: clear all of it every frame
                except BaseException:
                    pass
            if _frames[0] % 16 == 0:
                _fix_two_channel_textures()
            b.taskMgr.step()
        except SystemExit:
            raise
        except BaseException:
            if _step_err[0] < 5:
                _step_err[0] += 1
                print("STEP ERROR:", traceback.format_exc(), flush=True)

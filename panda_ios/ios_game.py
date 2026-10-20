"""Launcher for the real TTR-Offline client on iOS.

  start_download(docs, server)  - background thread: mirror <server>/manifest.json into <docs>/resources
  status()                      - (message, done, error) for the progress screen
  launch(docs, frameworks, game_server, cookie)  - chdir to docs and start toontown.toonbase.ToontownStart
  step()                        - one main-loop iteration (called from a CADisplayLink)
"""
import json
import os
import shutil
import sys
import threading
import time
import traceback
import urllib.request
import urllib.error
import ssl


def _install_ca():
    """iOS has no system CA store for Python's OpenSSL: use the bundled public CA list for https."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cacert.pem")
    if os.path.exists(p):
        ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=p)


_install_ca()
from concurrent.futures import ThreadPoolExecutor

_st = {"msg": "starting", "detail": "", "done": False, "err": None, "bytes": 0, "total": 0, "files": 0, "nfiles": 0}
_lock = threading.Lock()
_frames = [0]


def status():
    with _lock:
        return _st["msg"], _st["done"], _st["err"]


def _set(**kw):
    with _lock:
        _st.update(kw)


def _download_all(docs, server):
    try:
        res = os.path.join(docs, "resources")
        os.makedirs(res, exist_ok=True)
        _set(msg="Checking game files...", detail="")
        with urllib.request.urlopen(server + "/manifest.json", timeout=30) as r:
            manifest = json.loads(r.read().decode())
        files = manifest["files"]
        code = manifest.get("code", [])
        code_dir = os.path.join(docs, "code")
        import hashlib
        todo = []          # (local path, url path, size)
        total = 0
        for rel, size in files:
            p = os.path.join(res, rel)
            total += size
            if not (os.path.exists(p) and os.path.getsize(p) == size):
                todo.append((p, rel, size))
        # game code: compare size and md5 so an updated file with the same size is replaced too
        for rel, size, md5 in code:
            p = os.path.join(code_dir, rel)
            ok = os.path.exists(p) and os.path.getsize(p) == size
            if ok:
                with open(p, "rb") as f:
                    ok = hashlib.md5(f.read()).hexdigest() == md5
            if not ok:
                todo.append((p, "_code/" + rel, size))
        need = sum(s for _, _, s in todo)
        _set(total=need, nfiles=len(todo), bytes=0, files=0)
        if not todo:
            _set(msg="Ready", detail="", done=True)
            return
        n_big = sum(1 for _, rel, _ in todo if not rel.startswith("_code/"))
        if n_big:
            _set(msg="Downloading game files", detail="First launch only: about %.0f MB. Keep the app open." % (need / 1e6))
        else:
            _set(msg="Updating game files", detail="")

        def get(item):
            p, rel, size = item
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = p + ".part"
            for attempt in range(4):
                try:
                    with urllib.request.urlopen(server + "/" + rel.replace(" ", "%20"), timeout=60) as r, open(tmp, "wb") as f:
                        shutil.copyfileobj(r, f, 1 << 16)
                    os.replace(tmp, p)
                    break
                except Exception:
                    if attempt == 3:
                        raise
                    time.sleep(1.5)
            with _lock:
                _st["bytes"] += size
                _st["files"] += 1
                done_mb = _st["bytes"] / 1e6
                _st["msg"] = "Downloading game files"
                _st["detail"] = "%.0f of %.0f MB   (%d of %d files)" % (done_mb, _st["total"] / 1e6, _st["files"], _st["nfiles"])

        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(get, todo))
        _set(msg="Ready", detail="", done=True)
    except BaseException:
        _set(err=" | ".join(traceback.format_exc().strip().splitlines()[-3:]), msg="Download failed", detail="")


def _upload_log(docs, server):
    """Send the log to the log receiver on the server box every couple of seconds (for remote debugging)."""
    from urllib.parse import urlparse
    host = urlparse(server).hostname
    url = "http://%s:7381/phone" % host
    path = os.path.join(docs, "ttr_log.txt")
    last = None
    while True:
        try:
            data = b""
            if os.path.exists(path):
                with open(path, "rb") as f:
                    f.seek(0, 2)
                    size = f.tell()
                    f.seek(max(0, size - 60000))
                    data = f.read()
            head = ("STATUS: %s" % _st["msg"] + chr(10) + "FRAMES: %d" % _frames[0] + chr(10) + "----" + chr(10)).encode()
            payload = head + data
            if payload != last:
                req = urllib.request.Request(url, data=payload, method="POST")
                urllib.request.urlopen(req, timeout=5).read()
                last = payload
        except Exception:
            pass
        time.sleep(2)


RESOURCE_SERVER_HINT = [None]


def _fetch_art(docs, server):
    """Start-screen art (hosted on the game server, never bundled in the app)."""
    try:
        d = os.path.join(docs, "ui")
        os.makedirs(d, exist_ok=True)
        for name in ("background.jpg", "logo.png"):
            with urllib.request.urlopen("%s/_ui/%s" % (server, name), timeout=15) as r:
                data = r.read()
            with open(os.path.join(d, name + ".part"), "wb") as f:
                f.write(data)
            os.replace(os.path.join(d, name + ".part"), os.path.join(d, name))
    except Exception:
        pass


def check_login(server, cookie):
    """Ask the server whether user:password is acceptable (creates the account if registration is open).
    Returns 'ok' or a message to show the player."""
    from urllib.parse import urlparse
    try:
        rq = urllib.request.Request(server.rstrip("/") + "/auth", data=cookie.encode(), method="POST")
        with urllib.request.urlopen(rq, timeout=10) as r:
            return "ok"
    except urllib.error.HTTPError as e:
        return e.read().decode("utf-8", "replace") or "Sign-in failed."
    except Exception as e:
        return "Can't reach the Toontown server. Check your Wi-Fi."


def start_download(docs, server):
    RESOURCE_SERVER_HINT[0] = server
    threading.Thread(target=_fetch_art, args=(docs, server), daemon=True).start()
    threading.Thread(target=_download_all, args=(docs, server), daemon=True).start()


def _stub_http():
    """This Panda build has no OpenSSL, so HTTPClient is missing. The game only uses it for optional web
    features (news, word lists, usage reports); give it a do-nothing stand-in."""
    import panda3d.core as c
    if hasattr(c, "HTTPClient"):
        return

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

    c.HTTPClient = HTTPClient


def launch(docs, frameworks, game_server, cookie, app_dir):
    _stub_http()
    os.chdir(docs)
    # Panda caches its working directory at startup; tell its virtual file system about the new one
    from panda3d.core import VirtualFileSystem, Filename
    VirtualFileSystem.get_global_ptr().chdir(Filename.from_os_specific(docs))
    print("ios_game.launch: cwd =", os.getcwd(), "vfs cwd =", VirtualFileSystem.get_global_ptr().get_cwd(), flush=True)
    os.makedirs("logs", exist_ok=True)
    # the game's Python code and config come from the server (docs/code), not from the app
    code_dir = os.path.join(docs, "code")
    if os.path.isdir(os.path.join(code_dir, "toontown")):
        sys.path.insert(0, code_dir)
        src = os.path.join(code_dir, "config")
    else:
        src = os.path.join(app_dir, "game_config")           # older builds bundled it
    dst = os.path.join(docs, "config")
    if os.path.isdir(src):
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst)
    print("ios_game.launch: game code from", code_dir if code_dir in sys.path else "app bundle", flush=True)
    if not os.path.exists("settings.json"):
        with open("settings.json", "w") as f:
            json.dump({"game": {"mongodb-client": False, "auto-start-server": False, "elections": False,
                                "smoothanimations": True, "retro-rewritten": False, "antialiasing": 0}}, f)
    from urllib.parse import urlparse
    _debug_state["url"] = None   # remote debug hook disabled in public builds
    os.environ["TTR_PLAYCOOKIE"] = cookie
    os.environ["TTR_GAMESERVER"] = game_server
    from panda3d.core import loadPrcFileData
    for line in ("plugin-path " + frameworks, "load-display pandagles", "audio-library-name " + ("p3openal_audio" if os.path.exists(os.path.join(frameworks, "libp3openal_audio.dylib")) else "null"), "sync-video 0",
                 "toontown-auto-run 0", "want-dev #f", "connect-method native",
                 "notify-level-display info", "notify-level-glesgsg info", "gl-check-errors #t"):
        loadPrcFileData("", line)
    import faulthandler
    _fh = open(os.path.join(docs, "ttr_log.txt"), "a")
    faulthandler.enable(file=_fh)
    faulthandler.dump_traceback_later(25, repeat=True, file=_fh)
    sys.argv = ["ToontownStart"]
    print("ios_game.launch: starting ToontownStart in", os.getcwd(), flush=True)
    import runpy
    try:
        runpy.run_module("toontown.toonbase.ToontownStart", run_name="__main__")
        print("ios_game.launch: ToontownStart returned normally; base=%s" % getattr(__import__("builtins"), "base", None), flush=True)
    except SystemExit as e:
        print("ios_game.launch: SystemExit", e.code, flush=True)
        raise
    except BaseException:
        print("ios_game.launch: EXCEPTION", traceback.format_exc(), flush=True)
        raise


_step_err = [0]
_tex_seen = [0]


def _fix_two_channel_textures():
    """Mipmapped 1/2-channel (alpha, luminance, luminance+alpha) textures render black on iOS GLES1: the driver
    can't build their mipmaps. That blanked the bitmap-font text and the toons' eyes. Use plain linear filtering."""
    from panda3d.core import TexturePool, SamplerState
    tc = TexturePool.find_all_textures()
    n = tc.get_num_textures()
    if n == _tex_seen[0]:
        return
    _tex_seen[0] = n
    for i in range(n):
        t = tc.get_texture(i)
        if t.get_num_components() in (1, 2) and t.uses_mipmaps():
            t.set_minfilter(SamplerState.FT_linear)
_debug_state = {"url": None, "last": None}


def _debug_poll():
    """Development aid: run a diagnostic script from <server>:7380/debug/run.py when it changes."""
    url = _debug_state["url"]
    if not url:
        return
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            code = r.read().decode()
    except Exception:
        return
    if code == _debug_state["last"]:
        return
    _debug_state["last"] = code
    import builtins
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            def upload(name, data):
                from urllib.parse import urlparse
                rq = urllib.request.Request("http://%s:7381/%s" % (urlparse(url).hostname, name), data=data, method="POST")
                urllib.request.urlopen(rq, timeout=10).read()

            def shot(name):
                """Render a couple of frames, take a screenshot of the window and send it to the server."""
                from panda3d.core import PNMImage, Filename, StringStream
                b = getattr(builtins, "base", None)
                b.graphicsEngine.render_frame()
                b.graphicsEngine.render_frame()
                img = PNMImage()
                if b.win.get_screenshot(img):
                    path = os.path.join(os.getcwd(), "shot_%s.png" % name)
                    img.write(Filename.from_os_specific(path))
                    with open(path, "rb") as f:
                        upload("shot_" + name, f.read())
                    print("shot", name, img.get_x_size(), img.get_y_size())
                else:
                    print("screenshot failed")

            exec(compile(code, "debug/run.py", "exec"),
                 {"__name__": "debug", "base": getattr(builtins, "base", None), "upload": upload, "shot": shot})
        except BaseException:
            print("DEBUG SCRIPT ERROR:", traceback.format_exc())
    out = buf.getvalue()
    print("=== DEBUG SCRIPT RAN (%d chars of output) ===" % len(out), flush=True)
    try:
        from urllib.parse import urlparse
        req = urllib.request.Request("http://%s:7381/debug" % urlparse(url).hostname, data=out.encode(), method="POST")
        urllib.request.urlopen(req, timeout=5).read()
    except Exception:
        pass


def _fix_clear(b):
    """Clear the whole drawable every frame: EAGL's buffer contents are undefined after presenting, which showed
    up as flicker in the parts of the screen outside the 4:3 game area."""
    try:
        from panda3d.core import Vec4
        w = b.win
        w.set_clear_color_active(True)
        w.set_clear_color(Vec4(0, 0, 0, 1))
        w.set_clear_depth_active(True)
        w.set_clear_stencil_active(True)
        print("ios_game: window clear enabled, size", w.get_x_size(), w.get_y_size(), flush=True)
    except BaseException:
        print("ios_game: clear fix failed", traceback.format_exc(), flush=True)


def step():
    import builtins
    b = getattr(builtins, "base", None)
    if b is not None:
        try:
            _frames[0] += 1
            if _frames[0] in (1, 2, 3, 30, 120) or _frames[0] % 600 == 0:
                w = getattr(b, "win", None)
                print("FRAME %d win=%s open=%s size=%s gsg=%s" % (
                    _frames[0], w, w.is_valid() if w else None,
                    (w.get_x_size(), w.get_y_size()) if w else None, w.get_gsg() if w else None), flush=True)
            if _frames[0] == 2:
                _fix_clear(b)
            if _frames[0] % 8 == 0:
                _fix_two_channel_textures()
            if _frames[0] % 150 == 0:
                _debug_poll()
            b.taskMgr.step()
        except SystemExit:
            raise
        except BaseException:
            if _step_err[0] < 5:
                _step_err[0] += 1
                print("STEP ERROR:", traceback.format_exc(), flush=True)


def ui_status():
    """'fraction|message|detail|done|error' for the native loading screen."""
    with _lock:
        total = _st["total"]
        frac = (_st["bytes"] / total) if total else (1.0 if _st["done"] else 0.0)
        return "%.4f|%s|%s|%d|%s" % (frac, _st["msg"].replace("|", "/"), _st["detail"].replace("|", "/"),
                                      1 if _st["done"] else 0, (_st["err"] or "").replace(chr(10), " | "))


def _input_state():
    from direct.showbase.InputStateGlobal import inputState
    return inputState


def ui_move(fwd, back, left, right):
    """Joystick: drive the same input states the arrow keys drive."""
    try:
        st = _input_state()
        for name, on in (("forward", fwd), ("reverse", back), ("turnLeft", left), ("turnRight", right)):
            st.set(name, bool(on), "touch")
    except BaseException:
        print("ui_move error", traceback.format_exc(), flush=True)


def ui_jump(down):
    try:
        _input_state().set("jump", bool(down), "touch")
    except BaseException:
        print("ui_jump error", traceback.format_exc(), flush=True)

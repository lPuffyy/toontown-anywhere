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


def _install_ua():
    """Cloudflare rejects Python's default user agent (403), so identify as the app."""
    import urllib.request as _u
    op = _u.build_opener()
    op.addheaders = [("User-Agent", "TTR-Mobile/1.0 (iOS)")]
    _u.install_opener(op)


_install_ua()
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


def _download_packs(docs, server):
    """Download the server's pack files (one big uncompressed zip per game folder) in a few streams, resuming
    interrupted ones, and unpack them. Thousands of tiny requests are what made the first download crawl."""
    import zipfile
    try:
        with urllib.request.urlopen(server + "/packs.json", timeout=30) as r:
            packs = json.loads(r.read().decode())
    except Exception:
        return False
    pdir = os.path.join(docs, "packs")
    os.makedirs(pdir, exist_ok=True)
    total = sum(p[1] for p in packs)
    _set(total=total, nfiles=len(packs), bytes=0, files=0, msg="Downloading game files",
         detail="First launch only: about %.0f MB. Keep the app open." % (total / 1e6))

    def unpack(zp):
        with zipfile.ZipFile(zp) as z:
            for info in z.infolist():
                n = info.filename
                if n.endswith("/") or ".." in n.split("/"):
                    continue
                dest = os.path.join(docs, "code", n[6:]) if n.startswith("_code/") else os.path.join(docs, "resources", n)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with z.open(info) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1 << 16)

    def fetch(pack):
        name, size = pack[0], pack[1]
        zp = os.path.join(pdir, name + ".zip")
        part = zp + ".part"
        try:
            for attempt in range(6):
                try:
                    have = os.path.getsize(part) if os.path.exists(part) else 0
                    if have > size:
                        os.remove(part)
                        have = 0
                    if have < size:
                        rq = urllib.request.Request("%s/_packs/%s.zip" % (server, name))
                        if have:
                            rq.add_header("Range", "bytes=%d-" % have)
                        with urllib.request.urlopen(rq, timeout=60) as r:
                            if have and getattr(r, "status", 200) != 206:
                                have = 0
                            with open(part, "ab" if have else "wb") as f:
                                while True:
                                    chunk = r.read(1 << 16)
                                    if not chunk:
                                        break
                                    f.write(chunk)
                                    with _lock:
                                        _st["bytes"] += len(chunk)
                        if os.path.getsize(part) != size:
                            raise IOError("short pack")
                    os.replace(part, zp)
                    break
                except Exception:
                    if attempt == 5:
                        raise
                    time.sleep(2)
            unpack(zp)
            os.remove(zp)
            with _lock:
                _st["files"] += 1
                _st["detail"] = "%.0f of %.0f MB   (%d of %d packs)" % (_st["bytes"] / 1e6, _st["total"] / 1e6, _st["files"], _st["nfiles"])
        except Exception:
            print("pack failed", name, traceback.format_exc().splitlines()[-1], flush=True)

    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(fetch, packs))
    return True


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

        def scan():
            found = []          # (local path, url path, size)
            for rel, size in files:
                p = os.path.join(res, rel)
                if not (os.path.exists(p) and os.path.getsize(p) == size):
                    found.append((p, rel, size))
            # game code: compare size and md5 so an updated file with the same size is replaced too
            for rel, size, md5 in code:
                p = os.path.join(code_dir, rel)
                ok = os.path.exists(p) and os.path.getsize(p) == size
                if ok:
                    with open(p, "rb") as f:
                        ok = hashlib.md5(f.read()).hexdigest() == md5
                if not ok:
                    found.append((p, "_code/" + rel, size))
            return found

        todo = scan()
        if len(todo) > 400:
            # first install (thousands of small files): fetch the big packs instead, then fill in any gaps
            if _download_packs(docs, server):
                _set(msg="Checking game files...", detail="")
                todo = scan()
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

        with ThreadPoolExecutor(max_workers=12) as ex:
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


def _start_relay(game_server):
    """The game's own sockets are IPv4-only. Run a local relay so it talks to 127.0.0.1 while the app
    reaches the real server with the phone's normal networking (works on IPv6-only cellular too)."""
    import socket
    host, _, port = game_server.rpartition(":")
    port = int(port)
    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind(("127.0.0.1", 0))
    lsock.listen(8)
    lport = lsock.getsockname()[1]

    def pipe(a, b):
        try:
            while True:
                d = a.recv(65536)
                if not d:
                    break
                b.sendall(d)
        except Exception:
            pass
        for x in (a, b):
            try:
                x.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass

    def serve():
        while True:
            c, _ = lsock.accept()
            try:
                c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                print("RELAY: connecting to %s:%d" % (host, port), flush=True)
                u = socket.create_connection((host, port), timeout=15)
                u.settimeout(None)
                u.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                print("RELAY: connected via %s" % (u.getpeername(),), flush=True)
            except Exception as e:
                print("RELAY: connect failed: %r" % (e,), flush=True)
                c.close()
                continue
            threading.Thread(target=pipe, args=(c, u), daemon=True).start()
            threading.Thread(target=pipe, args=(u, c), daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()
    print("RELAY: listening on 127.0.0.1:%d for %s:%d" % (lport, host, port), flush=True)
    return "127.0.0.1:%d" % lport


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
    os.environ["TTR_GAMESERVER"] = _start_relay(game_server)
    from panda3d.core import loadPrcFileData
    for line in ("plugin-path " + frameworks, "load-display pandagles", "audio-library-name " + ("p3openal_audio" if os.path.exists(os.path.join(frameworks, "libp3openal_audio.dylib")) else "null"), "sync-video 0",
                 "toontown-auto-run 0", "want-dev #f", "connect-method native",
                 "notify-level-display info", "notify-level-glesgsg info", "gl-check-errors #t"):
        loadPrcFileData("", line)
    import faulthandler
    _fh = open(os.path.join(docs, "ttr_log.txt"), "a")
    faulthandler.enable(file=_fh)
    sys.argv = ["ToontownStart"]
    print("ios_game.launch: starting ToontownStart in", os.getcwd(), flush=True)
    import runpy
    try:
        _hook_entries()
    except BaseException:
        print("entry hook failed", traceback.format_exc(), flush=True)
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
            if _frames[0] % 16 == 0:
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
        frac = min(1.0, _st["bytes"] / total) if total else (1.0 if _st["done"] else 0.0)
        return "%.4f|%s|%s|%d|%s" % (frac, _st["msg"].replace("|", "/"), _st["detail"].replace("|", "/"),
                                      1 if _st["done"] else 0, (_st["err"] or "").replace(chr(10), " | "))


def _input_state():
    from direct.showbase.InputStateGlobal import inputState
    return inputState


_dirs = {"forward": False, "reverse": False, "turnLeft": False, "turnRight": False}
_dir_keys = {"forward": ("arrow_up", "w"), "reverse": ("arrow_down", "s"),
             "turnLeft": ("arrow_left", "a"), "turnRight": ("arrow_right", "d")}


def _send_keys(names, down):
    import builtins
    m = getattr(builtins, "messenger", None)
    if m is None:
        return
    for n in names:
        m.send(n if down else n + "-up")


def ui_move(fwd, back, left, right):
    """Joystick: drive the same input states the arrow keys drive, and send the key events too
    (minigames read W/A/S/D and the arrow keys directly)."""
    try:
        st = _input_state()
        for name, on in (("forward", fwd), ("reverse", back), ("turnLeft", left), ("turnRight", right)):
            on = bool(on)
            st.set(name, on, "touch")
            if _dirs[name] != on:
                _dirs[name] = on
                _send_keys(_dir_keys[name], on)
    except BaseException:
        print("ui_move error", traceback.format_exc(), flush=True)


def ui_jump(down):
    try:
        _input_state().set("jump", bool(down), "touch")
        _send_keys(("space",), bool(down))
    except BaseException:
        print("ui_jump error", traceback.format_exc(), flush=True)


# ---- touch UI bridge: camera, action button, chat keyboard ------------------------------------

_entries = []


def _hook_entries():
    """Remember every DirectEntry so the native side can mirror the iOS keyboard into the focused one."""
    import weakref
    from direct.gui import DirectEntry as DE
    cls = DE.DirectEntry
    if getattr(cls, "_ios_hooked", False):
        return
    orig = cls.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        _entries.append(weakref.ref(self))
    cls.__init__ = init
    cls._ios_hooked = True


def _focused_entry():
    found = None
    alive = []
    for r in _entries:
        e = r()
        if e is None:
            continue
        alive.append(r)
        try:
            if not e.isEmpty() and e.guiItem.getFocus() and not e.isHidden():
                found = e
        except BaseException:
            pass
    _entries[:] = alive
    return found


def ui_text_state():
    """'1|text' while a game text box has focus (native shows the keyboard), else '0|'."""
    try:
        e = _focused_entry()
        if e is None:
            return "0|"
        return "1|" + e.get().replace(chr(10), " ")
    except BaseException:
        return "0|"


def ui_text_set(text):
    try:
        e = _focused_entry()
        if e is not None:
            e.set(text)
    except BaseException:
        print("ui_text_set error", traceback.format_exc(), flush=True)


def ui_text_submit():
    try:
        e = _focused_entry()
        if e is not None:
            e.commandFunc(None)
    except BaseException:
        print("ui_text_submit error", traceback.format_exc(), flush=True)


def ui_camera():
    """Camera button: the same as the Tab key (next camera position)."""
    try:
        import builtins
        la = getattr(builtins, "localAvatar", None)
        if la is not None:
            la.nextCameraPos(1)
    except BaseException:
        print("ui_camera error", traceback.format_exc(), flush=True)


_ACTION_NAMES = ("control", "delete", "insert", "alt")
_ACTION_OWNERS = {
    "DistributedCashbotBossCrane", "DistCogdoCrane", "DistributedBanquetTable", "DistributedGolfSpot",
    "DistributedVehicle", "DistributedCannonGame", "DistributedCogThiefGame", "DistributedPairingGame",
    "CogdoMazeLocalPlayer", "CogdoFlyingLocalPlayer", "DistributedPartyTrampolineActivity",
    "DistributedToonfestTrampolineActivity", "DistributedIceGame",
}
_action_down = [None]


def _action_key():
    """The key some game object (crane, banquet table, minigame...) is listening for, ignoring the plain
    movement/jump input that always listens to Control."""
    import builtins
    m = getattr(builtins, "messenger", None)
    if m is None:
        return None
    for name in _ACTION_NAMES:
        who = m.whoAccepts(name)
        if not who:
            continue
        for entry in list(who.values()):
            owner = getattr(entry[0], "__self__", None)
            if owner is None:
                continue
            # only the specific cranes, tables and minigames that really use an action key
            if any(c.__name__ in _ACTION_OWNERS for c in type(owner).__mro__):
                return name
    return None


def ui_action_available():
    try:
        return 1 if _action_key() else 0
    except BaseException:
        return 0


def ui_action(down):
    """ACTION button: press the key the current game is waiting for (Control, Delete, Insert or Alt)."""
    try:
        if down:
            _action_down[0] = _action_key() or "control"
            _send_keys((_action_down[0],), True)
        else:
            _send_keys((_action_down[0] or "control",), False)
            _action_down[0] = None
    except BaseException:
        print("ui_action error", traceback.format_exc(), flush=True)


def ui_tug_active():
    """1 while the tug-of-war minigame is being played (it needs fast alternating left/right presses)."""
    try:
        import builtins
        cr = getattr(getattr(builtins, "base", None), "cr", None)
        if cr is None:
            return 0
        for do in list(cr.doId2do.values()):
            if type(do).__name__ == "DistributedTugOfWarGame" and getattr(do, "arrowKeys", None):
                return 1
    except BaseException:
        pass
    return 0


def ui_pad(side, down):
    """Tug-of-war buttons: side 0 = left (A), 1 = right (D)."""
    try:
        _send_keys(("a", "arrow_left") if side == 0 else ("d", "arrow_right"), bool(down))
    except BaseException:
        print("ui_pad error", traceback.format_exc(), flush=True)

def _arrowkeys_active():
    """True while a minigame's ArrowKeys helper (W/A/S/D + Space) is listening."""
    import builtins
    m = getattr(builtins, "messenger", None)
    if m is None:
        return False
    for name in ("a", "d", "w", "s"):
        who = m.whoAccepts(name)
        if not who:
            continue
        for entry in list(who.values()):
            owner = getattr(entry[0], "__self__", None)
            if owner is not None and type(owner).__name__ == "ArrowKeys":
                return True
    return False


_last_ui_state = [None]


def _place_state():
    """Name of the current place state ('walk', 'stopped', 'stickerBook', ...), or None."""
    import builtins
    cr = getattr(getattr(builtins, "base", None), "cr", None)
    pg = getattr(cr, "playGame", None)
    place = getattr(pg, "place", None)
    fsm = getattr(place, "fsm", None)
    st = fsm.getCurrentState() if fsm is not None else None
    return st.getName() if st is not None else None


def ui_controls_visible():
    """1 only while the player can actually move or act: hidden on the start screen, avatar chooser, Make-A-Toon
    and in menus/conversations (so the buttons never cover them)."""
    try:
        import builtins
        cr = getattr(getattr(builtins, "base", None), "cr", None)
        if cr is not None and getattr(cr, "avCreate", None):
            return 0
        la = getattr(builtins, "localAvatar", None)
        if la is None:
            return 0
        state = _place_state()
        if state != _last_ui_state[0]:
            _last_ui_state[0] = state
            print("UI place state:", state, flush=True)
        if state in ("walk", "swim"):
            return 1
        if _action_key() or ui_tug_active() or _arrowkeys_active():
            return 1
        if state is None:
            cm = getattr(la, "controlManager", None)
            return 1 if (cm is not None and getattr(cm, "isEnabled", 0)) else 0
        return 0
    except BaseException:
        return 1

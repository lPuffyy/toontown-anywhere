"""Starts the game itself once the launcher has the files and the player is signed in. Same steps as the browser version's start-up (the
game's own ToontownStart, with the pure-Python otpy standing in for libotp/libtoontown), minus everything that only exists to work around
the browser: here the graphics are plain desktop OpenGL and the connection is the Python WebSocket in netlayer.py."""
import builtins
import os
import sys
import traceback

TITLE = "Toontown: Anywhere"


class _Tee:
    """Everything the game prints goes to the console and to logs/client.log in the data folder."""

    def __init__(self, orig, path):
        self.orig = orig
        self.f = open(path, "a", encoding="utf8", buffering=1)

    def write(self, text):
        try:
            if self.orig:
                self.orig.write(text)
        except Exception:
            pass
        try:
            self.f.write(text)
        except Exception:
            pass
        return len(text)

    def flush(self):
        for h in (self.orig, self.f):
            try:
                if h:
                    h.flush()
            except Exception:
                pass

    def __getattr__(self, n):
        return getattr(self.orig, n)


def start(server, user, password, data_root):
    from panda3d.core import loadPrcFile, loadPrcFileData, Filename
    from .app import ws_url
    game_dir = os.path.join(data_root, "game")
    os.makedirs(os.path.join(data_root, "logs"), exist_ok=True)
    log_path = os.path.join(data_root, "logs", "client.log")
    if os.path.exists(log_path) and os.path.getsize(log_path) > 5 * 1024 * 1024:
        os.replace(log_path, log_path + ".old")
    sys.stdout, sys.stderr = _Tee(sys.stdout, log_path), _Tee(sys.stderr, log_path)
    print("native: starting the game as %s on %s (data %s)" % (user, server, data_root))

    os.chdir(game_dir)                       # the game's config and model paths are relative to its own folder
    sys.path.insert(0, game_dir)
    # Panda remembers the folder it started in, so tell it about the move too (its own file system layer and its MAIN_DIR)
    from panda3d.core import ExecutionEnvironment, VirtualFileSystem
    VirtualFileSystem.getGlobalPtr().chdir(Filename.fromOsSpecific(game_dir))
    ExecutionEnvironment.setEnvironmentVariable("MAIN_DIR", Filename.fromOsSpecific(game_dir).getFullpath())

    from . import netlayer
    netlayer.WS_URL = ws_url(server)

    loadPrcFile(Filename("etc/Configrc.prc"))
    for line in ("window-title " + TITLE, "load-display pandagl", "audio-library-name p3openal_audio", "toontown-auto-run 1", "want-dev #f",
                 "connect-method native", "notify-level warning", "dna-path resources", "default-model-extension .bam",
                 "interpolate-frames 1", "aspect-ratio 0", "win-size 1280 720", "sync-video 1", "dna-ram-cache-hood-models #t",
                 "garbage-collect-states-rate 0.05", "framebuffer-multisample 1", "multisamples 4"):
        loadPrcFileData("", line)
    if os.environ.get("TTA_HIDDEN"):                  # testing: a real window (the game needs a mouse), parked off the screen, no sound
        loadPrcFileData("", "win-origin -3000 0")
        loadPrcFileData("", "audio-library-name null")
    if os.environ.get("TTA_AUTO_AVATAR"):             # testing: pick this toon slot (0-5) on the Pick a Toon screen by itself
        loadPrcFileData("", "auto-avatar-choice " + os.environ["TTA_AUTO_AVATAR"])
    # the server runs in normal mode, so the game must too (dev mode asks the server for things a normal server refuses)
    try:
        from direct.showbase import ShowBaseGlobal
        ShowBaseGlobal.__dev__ = False
        builtins.__dev__ = False
    except BaseException:
        print("native: could not turn dev mode off", traceback.format_exc())

    netlayer.install()
    import otpy.install
    otpy.install.install()
    os.environ["LOGIN_TOKEN"] = user

    out, err = sys.stdout, sys.stderr
    from toontown.launcher.ToontownDummyLauncher import ToontownDummyLauncher
    sys.stdout, sys.stderr = out, err        # the game's launcher module redirects output to its own file; keep ours

    class NativeLauncher(ToontownDummyLauncher):
        def getPlayToken(self):
            return user

    builtins.launcher = NativeLauncher()

    class _Game:
        name = "toontown"
        process = "client"

    builtins.game = _Game()

    # open the way the player left it (a 16:9 window the first time; the game's own default is 800x600). The game reads its own options file
    # first, so that is where the mode and size go; the in-game Options page and F11 keep both in step afterwards.
    from . import window
    from .settings import Settings
    native_settings = Settings()
    full, size = window.saved_state(native_settings)
    dw = window.desktop_size()
    try:
        import json
        useropt = os.path.join(game_dir, "useropt.json")
        opts = {}
        if os.path.exists(useropt):
            try:
                with open(useropt, encoding="utf8") as f:
                    opts = json.load(f)
            except (OSError, ValueError):
                opts = {}
        have_choice = "fullscreen" in native_settings.data or "windowed-mode" not in opts
        if have_choice:
            opts["windowed-mode"] = not (full and dw)
            opts["resolution"] = list(dw if (full and dw) else size)
        with open(useropt, "w", encoding="utf8") as f:
            json.dump(opts, f, indent=4)
    except OSError:
        pass

    # things added around the running game (F11 full screen, widescreen HUD, controller): installed just before its main loop starts
    from direct.showbase.ShowBase import ShowBase
    orig_run = ShowBase.run
    hook = os.environ.get("TTA_TEST_SHOT")           # testing: save a picture of the game after N seconds, then quit ("path.png,seconds")

    def run(self):
        try:
            from . import hooks
            hooks.install(self, native_settings)
        except BaseException:
            print("native: extras not installed", traceback.format_exc())
        fs_test = os.environ.get("TTA_TEST_FULLSCREEN")     # testing: after N seconds go full screen, save a picture, go back, report ("path.png,seconds")
        if fs_test:
            fpath, fsecs = fs_test.rsplit(",", 1)

            def go_full(task):
                self.tta_fullscreen.set_full(True)
                self.taskMgr.doMethodLater(6.0, report, "tta-test-fs-report")
                return task.done

            def report(task):
                p = self.win.getProperties()
                print("native: full screen test: fullscreen=%s size=%dx%d desktop=%s a2dRight=%.3f" % (
                    p.getFullscreen(), p.getXSize(), p.getYSize(), window.desktop_size(), self.a2dRight))
                self.win.saveScreenshot(Filename.fromOsSpecific(fpath))
                self.taskMgr.doMethodLater(2.0, back, "tta-test-fs-back")
                return task.done

            def back(task):
                self.tta_fullscreen.set_full(False)
                self.taskMgr.doMethodLater(3.0, done, "tta-test-fs-done")
                return task.done

            def done(task):
                p = self.win.getProperties()
                print("native: back in a window: fullscreen=%s size=%dx%d" % (p.getFullscreen(), p.getXSize(), p.getYSize()))
                os._exit(0)
            self.taskMgr.doMethodLater(float(fsecs), go_full, "tta-test-fs")
        if hook:
            path, secs = hook.rsplit(",", 1)

            def shot(task):
                self.win.saveScreenshot(Filename.fromOsSpecific(path))
                print("native: test screenshot saved", path)
                if os.environ.get("TTA_TEST_QUIT", "1") == "1":
                    os._exit(0)
                return task.done
            self.taskMgr.doMethodLater(float(secs), shot, "tta-test-shot")
        orig_run(self)
    ShowBase.run = run

    import runpy
    try:
        runpy.run_module("toontown.toonbase.ToontownStart", run_name="__main__")
    except SystemExit:
        pass
    except BaseException:
        print("native: the game stopped with an error")
        print(traceback.format_exc())
        raise

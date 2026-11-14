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
    from .settings import Settings
    game_dir = os.path.join(data_root, "game")
    os.makedirs(os.path.join(data_root, "logs"), exist_ok=True)
    log_path = os.path.join(data_root, "logs", "client.log")
    if os.path.exists(log_path) and os.path.getsize(log_path) > 5 * 1024 * 1024:
        os.replace(log_path, log_path + ".old")
    out0 = sys.stdout
    sys.stdout, sys.stderr = _Tee(sys.stdout, log_path), _Tee(sys.stderr, log_path)
    print("native: starting the game as %s on %s (data %s)" % (user, server, data_root))
    from .nlog import note
    from . import __version__
    note("start: version %s, stdout was %s" % (__version__, type(out0).__name__))

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
                 "garbage-collect-states-rate 0.05"):
        loadPrcFileData("", line)
    smooth = str(Settings().get("smooth_edges", "1")) != "0"          # the settings cog's "Smooth edges" (takes effect at the next start)
    loadPrcFileData("", "framebuffer-multisample %d" % (1 if smooth else 0))
    loadPrcFileData("", "multisamples %d" % (4 if smooth else 0))
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

    from . import display, hud
    from direct.showbase.ShowBase import ShowBase as _SB
    hud.install(_SB, display.insets)          # the game's screen-edge items stay inside the safe area (none on a desktop)
    netlayer.install()
    import otpy.install
    otpy.install.install()
    os.environ["LOGIN_TOKEN"] = user

    out, err = sys.stdout, sys.stderr
    # the app has no console window, so Python has no original stdout/stderr (both None); the game's launcher module wraps
    # sys.__stdout__ / sys.__stderr__ and would crash on the first print, so hand it our log streams instead
    if sys.__stdout__ is None:
        sys.__stdout__ = out
    if sys.__stderr__ is None:
        sys.__stderr__ = err
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
    native_settings = Settings()
    full, size = window.saved_state(native_settings)
    ts = os.environ.get("TTA_TEST_SIZE")            # testing: open at this size (and as a window), e.g. "852x393"
    if ts:
        full, size = False, tuple(int(n) for n in ts.split("x"))
    ti = os.environ.get("TTA_TEST_INSETS")          # testing: pretend the screen has this safe area in pixels, "left,right,top,bottom"
    if ti:
        from . import display as _display
        _vals = tuple(float(n) for n in ti.split(","))
        _display.set_provider(lambda: _vals)
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
            note("extras not installed: " + traceback.format_exc())
        try:
            note("extras: cog=%s keys=%s fullscreen=%s; sfx manager %s, music manager %s (valid %s)" % (
                hasattr(self, "tta_settings_ui"), hasattr(self, "tta_keymap"), hasattr(self, "tta_fullscreen"),
                type(self.sfxManagerList[0]).__name__ if self.sfxManagerList else None, type(self.musicManager).__name__,
                getattr(self, "musicManagerIsValid", None)))
        except BaseException:
            pass
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
        st_test = os.environ.get("TTA_TEST_SETTINGS")       # testing: open the settings cog's screens, try a remapped key, save pictures ("folder,seconds")
        if st_test:
            folder, ssecs = st_test.rsplit(",", 1)

            def shot_to(name):
                self.win.saveScreenshot(Filename.fromOsSpecific(os.path.join(folder, name)))

            def st_open(task):
                self.tta_settings_ui.open()
                self.taskMgr.doMethodLater(1.0, st_main, "tta-test-st-main")
                return task.done

            def st_main(task):
                shot_to("settings-main.png")
                self.tta_settings_ui.show_keys()
                self.taskMgr.doMethodLater(1.0, st_keys, "tta-test-st-keys")
                return task.done

            def st_keys(task):
                shot_to("settings-keys.png")
                ui, km = self.tta_settings_ui, self.tta_keymap
                from panda3d.core import KeyboardButton
                from . import controls
                ui._capture("fwd")
                self.messenger.send("tta-btn-down", [KeyboardButton.ascii_key("i")])
                print("native: settings test: i now means:", km.map.get("i"), "| saved:", Settings().get("keys"))
                ui.close()
                ist = controls._input_state()
                self.messenger.send("tta-btn-down", [KeyboardButton.ascii_key("i")])
                print("native: settings test: pressing i -> forward is set:", ist.isSet("forward"))
                self.messenger.send("tta-btn-up", [KeyboardButton.ascii_key("i")])
                print("native: settings test: released -> forward is set:", ist.isSet("forward"))
                km.reset()
                print("native: settings test: after reset, map:", km.map)
                os._exit(0)
            self.taskMgr.doMethodLater(float(ssecs), st_open, "tta-test-st")
        chat_test = os.environ.get("TTA_TEST_CHAT")         # testing: open typed chat, put non-plain text in the box, report what the box holds ("seconds")
        if chat_test:
            def open_chat(task):
                import builtins
                builtins.localAvatar.chatMgr.fsm.request("whiteListOpenChat")
                self.taskMgr.doMethodLater(1.0, type_text, "tta-test-chat-type")
                return task.done

            def type_text(task):
                from . import controls
                e = controls._focused_entry()
                print("native: chat test: focused chat box found:", e is not None)
                if e is not None:
                    e.enterText("it’s café 😀 ok — fine…")
                self.taskMgr.doMethodLater(1.0, report_chat, "tta-test-chat-report")
                return task.done

            def report_chat(task):
                from . import controls
                e = controls._focused_entry()
                print("native: chat test: box now holds:", repr(e.get()) if e is not None else None)
                os._exit(0)
            self.taskMgr.doMethodLater(float(chat_test), open_chat, "tta-test-chat")
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
        note("the game stopped with an error: " + traceback.format_exc())
        raise

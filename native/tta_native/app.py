"""The launcher: loading screen (checks and downloads the game files), sign-in, recovery answers, then it hands over to the game."""
import os
import sys
import threading

from . import auth, securestore
from .packs import Updater
from .settings import DEFAULT_SERVER, Settings, data_dir

TITLE = "Toontown: Anywhere"


def ws_url(server):
    return server.rstrip("/").replace("https://", "wss://", 1).replace("http://", "ws://", 1) + "/ws"


class Launcher:
    def __init__(self, server=None, offscreen=False):
        from panda3d.core import loadPrcFileData
        self.settings = Settings()
        self.server = (server or self.settings.get("server") or DEFAULT_SERVER).rstrip("/")
        self.root = data_dir()
        for line in ("window-title " + TITLE, "win-size 1280 720", "audio-library-name null", "notify-level warning", "sync-video 1",
                     "framebuffer-multisample 1", "multisamples 4"):
            loadPrcFileData("", line)
        if offscreen:
            loadPrcFileData("", "window-type offscreen")
        from direct.showbase.ShowBase import ShowBase
        self.base = ShowBase()
        self.base.disableMouse()
        self.updater = Updater(self.server, self.root, log=print)
        self.updater.fetch_ui()                          # the lettering font and sky picture, so the first screen already looks right
        from .ui import Backdrop, Style
        self.style = Style(self.base.loader, self.updater.ui_dir)
        self.backdrop = Backdrop(self.base, self.style)
        self.screen = None
        self.result = None                               # (user, password) once the player is signed in and the game should start
        self._jobs = []
        self.base.taskMgr.add(self._poll_jobs, "launcher-jobs")

    # ---- small helpers
    def _set_screen(self, screen):
        if self.screen is not None:
            self.screen.destroy()
        self.screen = screen

    def run_async(self, fn, done):
        """Run fn() in a thread; done(result) is called on the main thread."""
        box = {}

        def work():
            try:
                box["r"] = fn()
            except Exception as e:
                box["r"] = (False, "Something went wrong: %s" % (e,))
        t = threading.Thread(target=work, daemon=True)
        t.start()
        self._jobs.append((t, box, done))

    def _poll_jobs(self, task):
        for job in list(self._jobs):
            t, box, done = job
            if not t.is_alive():
                self._jobs.remove(job)
                done(box.get("r"))
        return task.cont

    # ---- screens
    def show_loading(self):
        from .ui import LoadingScreen
        self.updater = Updater(self.server, self.root, log=print)
        scr = LoadingScreen(self.base, self.style)
        self._set_screen(scr)
        from .shell_update import ShellUpdater
        shell = ShellUpdater(self.server, self.root, log=print)         # a newer app first (rare), then the game files
        shell.start()
        started = [False]

        def poll(task):
            if not shell.state["finished"]:
                scr.update(shell.state)
                return task.cont
            if shell.state["restart"]:
                shell.launch_and_exit()
            if not started[0]:
                started[0] = True
                self.updater.start()
            st = self.updater.state
            scr.update(st)
            if st.get("finished"):
                if st.get("error"):
                    self.show_error(st["error"])
                else:
                    self.show_login()
                return task.done
            return task.cont
        self.base.taskMgr.add(poll, "launcher-loading")

    def show_error(self, message):
        from .ui import CardScreen
        scr = CardScreen(self.base, self.style, "Can't start", message, [], "Try again", self.show_loading, "Change server", self.show_server)
        self._set_screen(scr)

    def show_login(self, message="", bad=False, password=None):
        from .ui import LoginScreen
        scr = LoginScreen(self.base, self.style, self.on_play, self.show_forgot, self.show_server)
        self._set_screen(scr)
        user = self.settings.get("user", "")
        pw = password if password is not None else securestore.unprotect(self.settings.get("pw", ""))
        scr.set_credentials(user, pw)
        if message:
            scr.set_message(message, bad)
        scr.focus_pass() if user else scr.focus_user()

    def on_play(self, user, password):
        scr = self.screen
        if not user or not password:
            return scr.set_message("Enter your toon name and password.", True)
        if ":" in user or "\n" in user or "\n" in password:
            return scr.set_message("Please don't use colons in your name.", True)
        scr.set_busy(True)
        scr.set_message("Signing in...", False)

        def done(r):
            ok, text = r
            if self.screen is not scr:
                return
            scr.set_busy(False)
            if not ok:
                return scr.set_message(text or "Sign-in failed.", True)
            self.settings.data["user"] = user
            self.settings.data["pw"] = securestore.protect(password)
            self.settings.save()
            if text == "setup":
                self.show_recovery(user, password)
            else:
                self.start_game(user, password)
        self.run_async(lambda: auth.sign_in(self.server, user, password), done)

    def show_recovery(self, user, password):
        """Two answers that let a player set a new password later. Can be skipped twice; after that they have to be filled in."""
        from .ui import CardScreen
        skips = int(self.settings.get("recskips", 0) or 0)
        must = skips >= 2

        def save():
            n, t = scr.values()
            if not n or not t:
                return scr.set_message("Fill in every box.", True)
            scr.set_message("Saving...", False)

            def done(r):
                ok, text = r
                if not ok:
                    return scr.set_message(text or "That didn't work.", True)
                self.start_game(user, password)
            self.run_async(lambda: auth.set_recovery(self.server, user, password, n, t), done)

        def skip():
            self.settings.set("recskips", skips + 1)
            self.start_game(user, password)
        scr = CardScreen(self.base, self.style, "Forgot-password help",
                         "Pick two answers only you will remember. If you ever forget your password, they let you set a new one.",
                         [("Your nickname", False), ("A toon name you made", False)], "Save", save, None if must else "Skip for now", skip)
        self._set_screen(scr)

    def show_forgot(self):
        from .ui import CardScreen
        user = self.screen.user.get().strip().lower() if self.screen is not None and hasattr(self.screen, "user") else ""
        if not user:
            return self.screen.set_message("Type your toon name above first, then tap Forgot password.", True)

        def go():
            n, t, p = scr.values()
            if not n or not t or not p:
                return scr.set_message("Fill in every box.", True)
            if ":" in p:
                return scr.set_message("Please don't use colons in a password.", True)
            scr.set_message("Checking...", False)

            def done(r):
                ok, text = r
                if not ok:
                    return scr.set_message(text or "That didn't work.", True)
                self.show_login("Password changed! Tap PLAY.", False, password=p)
            self.run_async(lambda: auth.recover(self.server, user, n, t, p), done)
        scr = CardScreen(self.base, self.style, "Reset password",
                         "Answer the two questions you saved for %s, then pick a new password." % user,
                         [("Your nickname", False), ("A toon name you made", False), ("New password", True)], "Reset password", go, "Cancel", self.show_login)
        self._set_screen(scr)

    def show_server(self):
        """For testing: point the launcher at another server (e.g. the dev one). Empty goes back to the normal server."""
        from .ui import CardScreen

        def save():
            v = scr.values()[0].strip().rstrip("/") or DEFAULT_SERVER
            if not v.startswith(("http://", "https://")):
                v = "https://" + v
            self.server = v
            self.settings.set("server", "" if v == DEFAULT_SERVER else v)
            self.show_loading()
        scr = CardScreen(self.base, self.style, "Change server", "Leave empty for the normal server (%s). The game files are checked again." % DEFAULT_SERVER,
                         [("Server address", False)], "Save", save, "Cancel", self.show_login)
        self._set_screen(scr)

    def start_game(self, user, password):
        self.result = (user, password)
        self.base.taskMgr.stop()

    # ---- run
    def run(self):
        self.show_loading()
        self.base.run()
        return self.result


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="tta_native", description="Toontown: Anywhere, native client")
    ap.add_argument("--server", help="server address (default %s)" % DEFAULT_SERVER)
    ap.add_argument("--selftest-ui", metavar="DIR", help="draw each launcher screen offscreen into DIR as pictures, then quit")
    ap.add_argument("--autologin", metavar="USER:PASSWORD", help="testing: skip the launcher screens (files are still checked) and start the game")
    ap.add_argument("--check-update", action="store_true", help="testing: check for a newer app, install it and quit")
    args = ap.parse_args(argv)
    if args.check_update:
        import time
        from .shell_update import ShellUpdater
        os.makedirs(os.path.join(data_dir(), "logs"), exist_ok=True)
        sys.stdout = sys.stderr = open(os.path.join(data_dir(), "logs", "update.log"), "w", buffering=1)
        su = ShellUpdater((args.server or DEFAULT_SERVER).rstrip("/"), data_dir())
        su.start()
        while not su.state["finished"]:
            time.sleep(0.5)
        print("native: update state:", su.state)
        if su.state["restart"]:
            su.launch_and_exit()
        return 0
    if args.autologin:
        server = (args.server or DEFAULT_SERVER).rstrip("/")
        root = data_dir()
        up = Updater(server, root)
        up._update()
        user, password = args.autologin.split(":", 1)
        ok, text = auth.sign_in(server, user, password)
        print("native: sign-in:", ok, text)
        if not ok:
            return 1
        from . import game
        game.start(server, user, password, root)
        return 0
    if args.selftest_ui:
        from . import selftest
        return selftest.run(args.server, args.selftest_ui)
    app = Launcher(args.server)
    result = app.run()
    if not result:
        return 0
    app.base.destroy()
    from . import game
    game.start(app.server, result[0], result[1], app.root)
    return 0

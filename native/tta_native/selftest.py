"""Draws each launcher screen offscreen and saves pictures, so the look can be checked without opening a window."""
import os

from panda3d.core import Filename


def run(server, out_dir):
    from .app import Launcher
    os.makedirs(out_dir, exist_ok=True)
    app = Launcher(server, offscreen=True)
    base = app.base

    def shot(name):
        for _ in range(6):
            base.taskMgr.step()
        path = os.path.join(out_dir, name + ".png")
        base.win.saveScreenshot(Filename.fromOsSpecific(path))
        print("saved", path)

    from .ui import CardScreen, LoadingScreen, LoginScreen
    scr = LoadingScreen(base, app.style)
    scr.update({"text": "Downloading phase_5 (6 of 15)", "done_bytes": 140 * 1048576, "total_bytes": 380 * 1048576})
    app._set_screen(scr)
    shot("1-loading")
    app._set_screen(LoginScreen(base, app.style, lambda *a: None, lambda: None, lambda: None))
    app.screen.set_credentials("lpuffyy", "secret")
    shot("2-login")
    app.screen.set_message("That name is taken, or the password is wrong. New here? Try another name.", True)
    shot("3-login-error")
    app._set_screen(CardScreen(base, app.style, "Forgot-password help",
                               "Pick two answers only you will remember. If you ever forget your password, they let you set a new one.",
                               [("Your nickname", False), ("A toon name you made", False)], "Save", lambda: None, "Skip for now", lambda: None))
    shot("4-recovery")
    return 0

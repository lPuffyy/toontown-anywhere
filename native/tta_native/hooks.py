"""Things the native client adds around the running game: F11 full screen (window.py), the widescreen HUD anchoring the browser version also does,
and controller support. install(base) is called once the game's window exists, just before its main loop starts."""
import builtins
import traceback

from . import hud
from .nlog import note


def install(base, settings=None):
    from .settings import Settings
    from .window import FullScreen
    settings = settings or Settings()

    def remember(full, size):
        """Also tell the game's own options, so its next start (which reads them first) opens the same way."""
        try:
            from .window import desktop_size
            opts = base.settings
            opts.updateSetting("windowed-mode", not full)
            opts.updateSetting("resolution", list(desktop_size() or size) if full else list(size))
            opts.writeSettings()
        except Exception:
            pass
    fs = FullScreen(base, settings, on_change=remember)
    base.tta_fullscreen = fs
    try:
        import os
        from . import settings_ui
        from .settings import data_dir
        settings_ui.install(base, settings, fs, os.path.join(data_dir(), "ui"))
    except BaseException:
        print("native: settings not installed", traceback.format_exc())
        note("settings not installed: " + traceback.format_exc())

    def anchor(task):
        hud.anchor_hud(base)
        return task.again
    base.taskMgr.doMethodLater(0.4, anchor, "tta-anchor-hud")
    try:
        from . import chat
        chat.install(base)
    except BaseException:
        print("native: chat helpers not installed", traceback.format_exc())
        note("chat helpers not installed: " + traceback.format_exc())
    try:
        from . import gamepad
        gamepad.install(base)
    except BaseException:
        print("native: controller support not installed", traceback.format_exc())
        note("controller support not installed: " + traceback.format_exc())

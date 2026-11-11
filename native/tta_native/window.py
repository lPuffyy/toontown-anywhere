"""Window size and full screen, shared by the launcher and the game. F11 (or Alt+Enter) switches; the choice and the window's size are
remembered in settings.json and used the next time (the launcher and the game both open the way the player left them)."""
import sys

from panda3d.core import WindowProperties

DEFAULT_SIZE = (1280, 720)


def desktop_size():
    """The main screen's size in pixels (what full screen uses so the screen's own resolution is not changed)."""
    if sys.platform == "win32":
        try:
            import ctypes
            u = ctypes.windll.user32
            try:
                u.SetProcessDPIAware()
            except Exception:
                pass
            w, h = int(u.GetSystemMetrics(0)), int(u.GetSystemMetrics(1))
            if w > 0 and h > 0:
                return w, h
        except Exception:
            pass
    return None


def saved_state(settings):
    """-> (fullscreen, (w, h)) the way the player left it."""
    full = bool(settings.get("fullscreen", False))
    size = settings.get("window_size") or DEFAULT_SIZE
    try:
        size = (max(640, int(size[0])), max(360, int(size[1])))
    except Exception:
        size = DEFAULT_SIZE
    return full, size


def prc_lines(settings):
    """Engine settings for opening in the saved mode."""
    full, size = saved_state(settings)
    dw = desktop_size()
    if full and dw:
        return ["fullscreen 1", "win-size %d %d" % dw, "undecorated 0"]
    return ["fullscreen 0", "win-size %d %d" % size]


class FullScreen:
    """F11 / Alt+Enter toggle for a ShowBase. on_change(fullscreen, window_size) is called after each switch (to remember it)."""

    def __init__(self, base, settings, on_change=None):
        self.base = base
        self.settings = settings
        self.on_change = on_change
        self.window_size = saved_state(settings)[1]
        base.accept("f11", self.toggle)
        base.accept("alt-enter", self.toggle)

    def is_full(self):
        try:
            return bool(self.base.win.getProperties().getFullscreen())
        except Exception:
            return False

    def toggle(self):
        self.set_full(not self.is_full())

    def set_window_size(self, w, h):
        """The size the window has (used now if it is a window, and the next time it becomes one)."""
        self.window_size = (int(w), int(h))
        self.settings.data["window_size"] = list(self.window_size)
        self.settings.save()
        if not self.is_full():
            props = WindowProperties()
            props.setSize(int(w), int(h))
            self.base.win.requestProperties(props)
        if self.on_change:
            try:
                self.on_change(self.is_full(), self.window_size)
            except Exception:
                pass

    def set_full(self, full):
        b = self.base
        cur = b.win.getProperties()
        props = WindowProperties()
        if full:
            if not cur.getFullscreen():
                self.window_size = (cur.getXSize(), cur.getYSize())
            dw = desktop_size() or (b.pipe.getDisplayWidth(), b.pipe.getDisplayHeight())
            props.setSize(*dw)
            props.setFullscreen(True)
        else:
            props.setFullscreen(False)
            props.setSize(*self.window_size)
            props.setOrigin(-2, -2)
        b.win.requestProperties(props)
        self.settings.data["fullscreen"] = bool(full)
        self.settings.data["window_size"] = list(self.window_size)
        self.settings.save()
        if self.on_change:
            try:
                self.on_change(bool(full), self.window_size)
            except Exception:
                pass

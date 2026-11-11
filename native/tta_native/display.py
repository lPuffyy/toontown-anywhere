"""What the app tells the game about its screen: the safe area (camera cut-out, rounded corners, home bar, a fold) in pixels.
The desktop apps have none. A phone app sets a provider that reads the system's real values (UIKit's safeAreaInsets on iOS, the
window insets on Android) with set_provider(); it is asked again whenever the window changes shape, and refresh() asks the game to
apply new values at once (a bar showed or hid)."""
import builtins

_provider = [None]


def set_provider(fn):
    """fn() -> (left, right, top, bottom) in pixels."""
    _provider[0] = fn


def insets():
    """-> (left, right, top, bottom, window_height) in pixels, the form hud.install wants."""
    h = 720.0
    try:
        h = float(builtins.base.win.getYSize())
    except Exception:
        pass
    if _provider[0] is not None:
        try:
            l, r, t, b = _provider[0]()
            return float(l), float(r), float(t), float(b), h
        except Exception:
            pass
    return 0.0, 0.0, 0.0, 0.0, h


def refresh():
    try:
        from . import hud
        hud.refresh(builtins.base)
    except Exception:
        pass

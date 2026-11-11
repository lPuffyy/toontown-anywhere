"""Things the native client adds around the running game: F11 full screen (window.py), the widescreen HUD anchoring the browser version also does,
and controller support. install(base) is called once the game's window exists, just before its main loop starts."""
import builtins
import traceback

_A43 = 4.0 / 3.0


def anchor_hud(b):
    """The game lays its screen-edge buttons (laff meter, book, friends...) out for a 4:3 screen with absolute positions. On a wider window
    they would float in from the edges, so hang the ones near the side edges from the left / right edge anchors instead, keeping their
    distance from the edge. (Same as _anchor_hud in the browser version.)"""
    try:
        if getattr(builtins, "localAvatar", None) is None:
            return          # not in the game yet: menu screens (pick a toon, make a toon) are laid out as whole 4:3 pictures and must stay together
        left, right = b.a2dLeftCenter, b.a2dRightCenter
        for c in list(b.aspect2d.getChildren()):
            name = c.getName()
            if name.startswith(("a2d", "pixel")) or c.getTag("anch"):
                continue
            pos = c.getPos()
            if abs(pos.getX()) < 0.8:
                continue
            s = c.getSort()
            if pos.getX() < 0:
                c.reparentTo(left, s)
                c.setPos(pos.getX() + _A43, pos.getY(), pos.getZ())
            else:
                c.reparentTo(right, s)
                c.setPos(pos.getX() - _A43, pos.getY(), pos.getZ())
            c.setTag("anch", "1")
    except BaseException:
        print("native: HUD anchoring failed", traceback.format_exc())


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

    def anchor(task):
        anchor_hud(base)
        return task.again
    base.taskMgr.doMethodLater(0.4, anchor, "tta-anchor-hud")
    try:
        from . import gamepad
        gamepad.install(base)
    except BaseException:
        print("native: controller support not installed", traceback.format_exc())

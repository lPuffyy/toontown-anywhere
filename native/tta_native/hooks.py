"""Things the native client adds around the running game: F11 full screen, the widescreen HUD anchoring the browser version also does,
and controller support. install(base) is called once the game's window exists, just before its main loop starts."""
import builtins
import traceback

from panda3d.core import WindowProperties

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


class FullScreen:
    """F11 switches between a window and full screen at the desktop's size, remembering the window's size."""

    def __init__(self, base):
        self.base = base
        self.window_size = (1280, 720)
        base.accept("f11", self.toggle)
        base.accept("alt-enter", self.toggle)

    def toggle(self):
        b = self.base
        cur = b.win.getProperties()
        props = WindowProperties()
        if cur.getFullscreen():
            props.setFullscreen(False)
            props.setSize(*self.window_size)
            props.setOrigin(-2, -2)
        else:
            self.window_size = (cur.getXSize(), cur.getYSize())
            props.setSize(b.pipe.getDisplayWidth(), b.pipe.getDisplayHeight())
            props.setFullscreen(True)
        b.win.requestProperties(props)


def install(base):
    FullScreen(base)

    def anchor(task):
        anchor_hud(base)
        return task.again
    base.taskMgr.doMethodLater(0.4, anchor, "tta-anchor-hud")
    try:
        from . import gamepad
        gamepad.install(base)
    except BaseException:
        print("native: controller support not installed", traceback.format_exc())

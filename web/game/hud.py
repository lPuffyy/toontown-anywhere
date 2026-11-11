"""How the game's on-screen items (chat buttons, laff meter, book, friends, FPS) sit on any screen, shared by the browser app and every
native app. The game lays them out for a 4:3 screen with absolute positions; here they are

  * hung from the left / right edges when they are near a side (so they stay at the edges of a wide screen), and
  * kept inside the safe area (camera cut-out, rounded corners, home bar, a fold) by moving Panda's screen-edge anchors inward.

Each app says how big its safe area is with an `insets` function returning (left, right, top, bottom, window_height), all in pixels: the
browser reads them from the page, a phone app from UIKit's safeAreaInsets, a desktop app returns zeros. Nothing here knows about any
platform. Behaviour is the same as the code that used to live in web/game/main.py (_apply_insets, _adjust, _anchor_hud).
"""
import builtins
import traceback

_A43 = 4.0 / 3.0
ANCHORS = (("a2dTopLeft", 1, -1), ("a2dTopRight", -1, -1), ("a2dBottomLeft", 1, 1), ("a2dBottomRight", -1, 1),
           ("a2dTopCenter", 0, -1), ("a2dBottomCenter", 0, 1), ("a2dLeftCenter", 1, 0), ("a2dRightCenter", -1, 0))

_applied = [0.0, 0.0, 0.0, 0.0]        # insets already added to the anchors (they are reset whenever the window's aspect ratio changes)
_provider = [None]


def apply_insets(b, reset):
    """Move the anchors by (wanted insets - already applied ones). Panda only rewrites the anchors when the aspect ratio changes,
    so adding the full insets on every call (e.g. each window-focus event) would push everything further in."""
    try:
        if reset:
            _applied[:] = [0.0, 0.0, 0.0, 0.0]
        if _provider[0] is None:
            return
        left, right, top, bottom, height = _provider[0]()
        k = 2.0 / (float(height) or 1.0)           # screen-height units (aspect2d spans 2.0 over the height) per pixel
        want = [float(left) * k, float(right) * k, float(top) * k, float(bottom) * k]
        dL, dR, dT, dB = [want[i] - _applied[i] for i in range(4)]
        if abs(dL) + abs(dR) + abs(dT) + abs(dB) < 1e-6:
            return
        for base_name, sx, sz in ANCHORS:
            for suffix in ("", "Ns"):
                n = getattr(b, base_name + suffix, None)
                if n is None:
                    continue
                dx = dL if sx > 0 else (-dR if sx < 0 else 0.0)
                dz = dB if sz > 0 else (-dT if sz < 0 else 0.0)
                n.setPos(n.getX() + dx, n.getY(), n.getZ() + dz)
        _applied[:] = want
    except BaseException:
        print("hud: safe-area adjust failed", traceback.format_exc())


def install(show_base_class, insets):
    """Hook ShowBase so the safe area is applied whenever Panda lays the anchors out (call before the game's window is made).
    insets: function -> (left, right, top, bottom, window_height) in pixels."""
    _provider[0] = insets
    if getattr(show_base_class, "_tta_hud_hooked", False):
        return
    orig = show_base_class.adjustWindowAspectRatio

    def adjust(self, aspect_ratio):
        old = getattr(self, "_ShowBase__oldAspectRatio", None)
        orig(self, aspect_ratio)
        apply_insets(self, getattr(self, "_ShowBase__oldAspectRatio", None) != old)
    show_base_class.adjustWindowAspectRatio = adjust
    show_base_class._tta_hud_hooked = True


def refresh(b):
    """The safe area changed without the window changing shape (a phone's bar showed or hid): apply it again."""
    apply_insets(b, False)


_logged = [0]


def ensure(b):
    """Belt and braces: put every screen-edge anchor exactly where the window's shape and the safe area say it belongs (absolute, not relative
    to what Panda did last), whenever it is not there. Cheap enough to call a few times a second."""
    try:
        if _provider[0] is None:
            return
        left, right, top, bottom, height = _provider[0]()
        k = 2.0 / (float(height) or 1.0)
        L, R, T, B = float(left) * k, float(right) * k, float(top) * k, float(bottom) * k
        asp = float(b.getAspectRatio())
        fixed = 0
        for base_name, sx, sz in ANCHORS:
            for suffix in ("", "Ns"):
                n = getattr(b, base_name + suffix, None)
                if n is None:
                    continue
                x = (-asp + L) if sx > 0 else ((asp - R) if sx < 0 else 0.0)
                z = (-1.0 + B) if sz > 0 else ((1.0 - T) if sz < 0 else 0.0)
                if suffix == "Ns":
                    x, z = (-asp + L) if sx > 0 else ((asp - R) if sx < 0 else 0.0), z
                if abs(n.getX() - x) > 1e-3 or abs(n.getZ() - z) > 1e-3:
                    n.setPos(x, n.getY(), z)
                    fixed += 1
        _applied[:] = [L, R, T, B]
        if fixed and _logged[0] < 6:
            _logged[0] += 1
            print("hud.ensure: moved %d anchors; aspect %.3f insets(px) l=%s r=%s t=%s b=%s h=%s" % (fixed, asp, left, right, top, bottom, height), flush=True)
    except BaseException:
        print("hud: ensure failed", traceback.format_exc())


def anchor_hud(b):
    """Hang the items that sit near the left / right edge of the 4:3 layout from the edge anchors, keeping their distance from the edge."""
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
        print("hud: HUD anchoring failed", traceback.format_exc())

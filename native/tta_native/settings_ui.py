"""The settings cog and its screens in the running game: the same sections, rows and keyboard keys card as the web app, built from the shared
spec (spec.py). A cog button sits at the top centre next to the speed counter. What each row does on this app is in SettingsUI.behaviour."""
import math
import traceback

from direct.gui import DirectGuiGlobals as DGG
from direct.gui.DirectGui import DirectButton, DirectFrame
from panda3d.core import PNMImage, SamplerState, Texture, TextNode, TransparencyAttrib

from . import keymap as km
from . import spec as specmod
from .ui import DARK, INK, OUTLINE, pill, rounded_texture, text_line

BLUE_FILL = (0.12, 0.30, 0.65, 1)
LIGHT = (0.92, 0.95, 1.0, 1)
WHITE = (1, 1, 1, 1)
CARD_W, CARD_H = 1.9, 1.78
LEFT, RIGHT = -0.84, 0.84


def cog_texture(size=96):
    """A round translucent button with a white gear in it."""
    img = PNMImage(size, size, 4)
    img.fill(1, 1, 1)
    img.alphaFill(0)
    c = (size - 1) / 2.0
    for y in range(size):
        for x in range(size):
            dx, dy = (x - c) / c, (y - c) / c
            r = math.hypot(dx, dy)
            if r > 1.0:
                continue
            a = 0.62
            col = (0.10, 0.26, 0.62)
            if r > 0.93:
                col, a = (0.85, 0.92, 1.0), 0.9                      # light rim
            ang = math.atan2(dy, dx)
            tooth = 0.5 + 0.5 * math.cos(8 * ang)
            gear_r = 0.50 + (0.12 if tooth > 0.55 else 0.0)
            if 0.2 < r < gear_r:
                col, a = (1, 1, 1), 1.0                               # the gear
            img.setXel(x, y, *col)
            img.setAlpha(x, y, a)
    tex = Texture("tta-cog")
    tex.load(img)
    tex.setMinfilter(SamplerState.FT_linear)
    tex.setMagfilter(SamplerState.FT_linear)
    return tex


class SettingsUI:
    def __init__(self, base, settings, spec, style, fullscreen, keys, on_fps_changed=None):
        self.base, self.settings, self.spec, self.style = base, settings, spec, style
        self.fs, self.keys = fullscreen, keys
        self.root = None
        self.page = None
        self.note = None
        self.restart_shown = False
        self.cog = DirectButton(parent=base.a2dTopCenter, relief=None, image=cog_texture(), image_scale=0.045, pos=(0.20, 0, -0.075),
                                command=self.open, pressEffect=1, text="", sortOrder=900)
        self.cog.setTransparency(TransparencyAttrib.MAlpha)
        self.fps = text_line(base.a2dTopCenter, style, "", (0.14, 0, -0.095), 0.05, fg=WHITE, align=TextNode.ARight)
        self.fps.setBin("gui-popup", 60)
        self.apply_fps()
        base.taskMgr.doMethodLater(0.5, self._fps_tick, "tta-fps")

    # ---- what each row does here (the web app has its own table for the same row ids)
    def behaviour(self):
        s = self.settings

        def size_now():
            return "%dx%d" % tuple(self.fs.window_size)

        def set_size(v):
            w, h = [int(n) for n in v.split("x")]
            self.fs.set_window_size(w, h)

        def smooth(v):
            s.set("smooth_edges", v)
            if self.note is not None:
                self.note.show()

        return {
            "window_mode": (lambda: "full" if self.fs.is_full() else "window", lambda v: self.fs.set_full(v == "full")),
            "window_size": (size_now, set_size),
            "smooth_edges": (lambda: str(s.get("smooth_edges", "1")), smooth),
            "fps": (lambda: str(s.get("fps", "1")), lambda v: (s.set("fps", v), self.apply_fps())),
        }

    # ---- the speed counter
    def apply_fps(self):
        if str(self.settings.get("fps", "1")) == "0":
            self.fps.hide()
        else:
            self.fps.show()

    def _fps_tick(self, task):
        try:
            if str(self.settings.get("fps", "1")) != "0":
                from panda3d.core import ClockObject
                self.fps["text"] = "%d FPS" % round(ClockObject.getGlobalClock().getAverageFrameRate())
        except Exception:
            pass
        return task.again

    # ---- opening and closing
    def open(self):
        if self.root is not None:
            return
        base = self.base
        self.root = base.aspect2d.attachNewNode("tta-settings")
        self.root.reparentTo(base.aspect2d, 1000)
        DirectFrame(parent=self.root, frameColor=(0.03, 0.08, 0.2, 0.58), frameSize=(-8, 8, -2, 2), state=DGG.NORMAL, relief=DGG.FLAT)
        tex = rounded_texture(int(CARD_W * 220), int(CARD_H * 220), (0.97, 0.98, 1.0, 0.98), (0.12, 0.30, 0.65, 1), 5, 40)
        card = DirectFrame(parent=self.root, relief=None, image=tex, image_scale=(CARD_W / 2, 1, CARD_H / 2), state=DGG.NORMAL)
        card.setTransparency(TransparencyAttrib.MAlpha)
        self.show_main()

    def close(self):
        self.keys.capture = None
        if self.root is not None:
            self.root.removeNode()
            self.root = None
        self.page = None

    def _new_page(self):
        if self.page is not None:
            self.page.removeNode()
        self.page = self.root.attachNewNode("page")
        return self.page

    # ---- pieces
    def _seg(self, parent, choices, current, x_right, z, on_pick):
        """Choice buttons in a row ending at x_right; the chosen one is filled."""
        widths = [max(0.20, 0.032 * len(label) + 0.10) for _v, label in choices]
        gap = 0.03
        total = sum(widths) + gap * (len(widths) - 1)
        extra = 0.0
        if total > 1.0:                     # too wide to share a line with the label: put the choices on a line of their own
            z -= 0.11
            extra = 0.11
        x = x_right - total
        btns = []

        def pick(v):
            on_pick(v)
            for b, (val, _l) in zip(btns, choices):
                self._style_choice(b, val == v)
        for (val, label), w in zip(choices, widths):
            b = pill(parent, self.style, label, (x + w / 2, 0, z), (w, 0.085), LIGHT, OUTLINE, 3, DARK, 0.045, command=pick, extra=[val])
            self._style_choice(b, val == current)
            btns.append(b)
            x += w + gap
        return btns, extra

    def _style_choice(self, b, selected):
        b["text_fg"] = WHITE if selected else DARK
        b["image_color"] = (0.38, 0.58, 0.95, 1) if selected else (1, 1, 1, 1)

    def _heading(self, parent, text, z):
        text_line(parent, self.style, text.upper(), (LEFT, 0, z), 0.05, fg=INK, align=TextNode.ALeft)

    # ---- the main page
    def show_main(self):
        self.keys.capture = None
        page = self._new_page()
        text_line(page, self.style, self.spec.get("title", "Settings"), (0, 0, 0.74), 0.12, fg=INK)
        beh = self.behaviour()
        z = 0.60
        self.note = None
        for section, rows in specmod.sections(self.spec):
            self._heading(page, section["title"], z)
            z -= 0.09
            for r in rows:
                if r.get("type") == "page":
                    if r["id"] == "keys":
                        pill(page, self.style, r["label"], (0, 0, z - 0.02), (0.62, 0.095), LIGHT, OUTLINE, 3, DARK, 0.05, command=self.show_keys)
                        z -= 0.14
                    continue
                if r.get("type") == "push" or r["id"] not in beh:
                    continue
                get, setter = beh[r["id"]]
                text_line(page, self.style, r["label"], (LEFT, 0, z), 0.052, fg=DARK, align=TextNode.ALeft)
                if r.get("hint"):
                    text_line(page, self.style, r["hint"], (LEFT, 0, z - 0.05), 0.034, fg=(0.30, 0.36, 0.55, 1), align=TextNode.ALeft)
                _btns, extra = self._seg(page, r["choices"], get(), RIGHT, z, setter)
                if r.get("restart_note"):
                    self.note = text_line(page, self.style, r["restart_note"], (RIGHT, 0, z - 0.075 - extra), 0.036, fg=(0.7, 0.35, 0.05, 1), align=TextNode.ARight)
                    self.note.hide()
                z -= (0.19 if r.get("hint") else 0.13) + extra
            z -= 0.03
        pill(page, self.style, "Done", (0, 0, -CARD_H / 2 + 0.12), (0.5, 0.11), (1.0, 0.851, 0.149, 1), (0.451, 0.22, 0.02, 1), 4,
             (0.451, 0.22, 0.02, 1), 0.07, command=self.close)

    # ---- the keyboard keys page
    def show_keys(self):
        k = self.spec["keys"]
        page = self._new_page()
        text_line(page, self.style, k.get("title", "Keyboard keys"), (0, 0, 0.74), 0.11, fg=INK)
        text_line(page, self.style, k.get("tip", ""), (0, 0, 0.64), 0.04, fg=(0.30, 0.36, 0.55, 1), wordwrap=44)
        buttons = {}
        actions = k["actions"]
        half = (len(actions) + 1) // 2
        for i, a in enumerate(actions):
            col, row = divmod(i, half)
            x0 = -0.90 + col * 0.93
            z = 0.50 - row * 0.145
            text_line(page, self.style, a["label"], (x0 + 0.03, 0, z), 0.045, fg=DARK, align=TextNode.ALeft)
            text_line(page, self.style, "Game key: " + km.key_label(a["game_key"]), (x0 + 0.03, 0, z - 0.045), 0.03, fg=(0.30, 0.36, 0.55, 1),
                      align=TextNode.ALeft)
            mine = self.keys.keys_for(a["id"])
            label = ", ".join(km.key_label(m) for m in mine) if mine else km.key_label(a["game_key"])
            b = pill(page, self.style, label, (x0 + 0.66, 0, z - 0.01), (0.42, 0.085), LIGHT, OUTLINE, 3, DARK, 0.042, command=self._capture, extra=[a["id"]])
            self._style_choice(b, bool(mine))
            buttons[a["id"]] = b
        self._key_buttons = buttons
        pill(page, self.style, k.get("reset", "Use the game's keys"), (-0.45, 0, -0.50), (0.84, 0.09), LIGHT, OUTLINE, 3, DARK, 0.043,
             command=lambda: (self.keys.reset(), self.show_keys()))
        pill(page, self.style, k.get("wasd", "Use WASD and Space"), (0.45, 0, -0.50), (0.84, 0.09), LIGHT, OUTLINE, 3, DARK, 0.043,
             command=lambda: (self.keys.use_wasd(), self.show_keys()))
        pill(page, self.style, "Back", (0, 0, -CARD_H / 2 + 0.12), (0.5, 0.11), (1.0, 0.851, 0.149, 1), (0.451, 0.22, 0.02, 1), 4,
             (0.451, 0.22, 0.02, 1), 0.07, command=self.show_main)

    def _capture(self, action_id):
        b = self._key_buttons[action_id]
        for other in self._key_buttons.values():
            other["text_fg"] = DARK
        b["text"] = self.spec["keys"].get("waiting", "Press a key... (Esc cancels)")
        b["text_scale"] = 0.034

        def got(name):
            if name != "escape":
                self.keys.assign(action_id, name)
            self.show_keys()
        self.keys.capture = got


def install(base, settings, fullscreen, ui_dir):
    """Called from hooks.install once the game's window exists. -> the SettingsUI (kept on base so it stays alive)."""
    from .ui import Style
    try:
        spec = specmod.load(ui_dir)
        style = Style(base.loader, ui_dir)
        keys = km.KeyMap(base, settings, spec)
        ui = SettingsUI(base, settings, spec, style, fullscreen, keys)
        base.tta_settings_ui, base.tta_keymap = ui, keys
        return ui
    except BaseException:
        print("native: settings cog not installed", traceback.format_exc())
        from .nlog import note
        note("settings cog not installed: " + traceback.format_exc())
        return None

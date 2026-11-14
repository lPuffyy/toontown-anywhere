"""The launcher's screens (loading, sign-in, recovery answers), drawn with Panda3D's own GUI in the look of the web app: the cloud
sky, the Toon Display lettering with a blue outline, white rounded fields and a yellow PLAY button. Everything is in aspect2d units,
where the window is 2.0 tall, so it scales with the window."""
import math
import os
import webbrowser

from direct.gui.DirectGui import DirectButton, DirectEntry, DirectFrame, DirectLabel
from panda3d.core import CardMaker, Filename, PNMImage, SamplerState, Texture, TextNode, TextureStage, TransparencyAttrib

GOLD = (1.0, 0.851, 0.149, 1)           # #ffd926
OUTLINE = (0.11, 0.247, 0.612, 1)       # #1c3f9c
INK = (0.102, 0.251, 0.549, 1)          # #1a408c
DARK = (0.10, 0.20, 0.45, 1)
BROWN = (0.451, 0.22, 0.02, 1)          # #733805
ERROR = (0.85, 0.1, 0.1, 1)
DISCORD = (0.345, 0.396, 0.949, 1)
REDDIT = (1.0, 0.27, 0.0, 1)

_tex_cache = {}


def rounded_texture(w, h, fill, border, border_px, radius, name="pill"):
    """A rounded rectangle with a border, anti-aliased, as a texture (w x h pixels)."""
    key = (w, h, fill, border, border_px, radius)
    if key in _tex_cache:
        return _tex_cache[key]
    img = PNMImage(w, h, 4)
    img.fill(0, 0, 0)
    img.alphaFill(0)
    hw, hh = w / 2.0, h / 2.0
    r = min(radius, hh, hw)
    for y in range(h):
        py = abs(y + 0.5 - hh) - (hh - r)
        for x in range(w):
            px = abs(x + 0.5 - hw) - (hw - r)
            qx, qy = max(px, 0.0), max(py, 0.0)
            d = math.hypot(qx, qy) + min(max(px, py), 0.0) - r            # signed distance to the edge (negative inside)
            cover = min(1.0, max(0.0, 0.5 - d))
            if cover <= 0:
                continue
            inner = min(1.0, max(0.0, 0.5 - (d + border_px)))              # how much of this pixel is inside the border
            if border_px <= 0:
                inner = 1.0
            r_, g_, b_ = (fill[i] * inner + border[i] * (1 - inner) for i in range(3))
            img.setXel(x, y, r_, g_, b_)
            img.setAlpha(x, y, cover * (fill[3] * inner + border[3] * (1 - inner)))
    tex = Texture(name)
    tex.load(img)
    tex.setMinfilter(SamplerState.FT_linear)
    tex.setMagfilter(SamplerState.FT_linear)
    _tex_cache[key] = tex
    return tex


class Style:
    """Fonts and file locations shared by the screens."""

    def __init__(self, loader, ui_dir):
        self.loader = loader
        self.ui_dir = ui_dir
        self.font = None
        path = os.path.join(ui_dir, "ToonDisplay.ttf")
        if os.path.exists(path):
            self.font = loader.loadFont(Filename.fromOsSpecific(path).getFullpath())
            # Panda keeps one copy of a font per file for the whole process. The launcher screen already loaded and set up this one, and
            # Panda refuses to change a font that has already drawn text (an assertion), which stopped the settings cog from starting in the game
            if self.font.getNumPages() == 0:
                self.font.setPixelsPerUnit(110)
                self.font.setPageSize(512, 512)
                self.font.setMinfilter(SamplerState.FT_linear)
                self.font.setMagfilter(SamplerState.FT_linear)

    def image(self, name):
        p = os.path.join(self.ui_dir, name)
        return p if os.path.exists(p) else None


def outlined_text(parent, text, scale, fill, outline, thickness, style, pos=(0, 0, 0), align=TextNode.ACenter):
    """Letters with a solid outline: the text drawn in the outline colour around the edge, then in the fill colour on top."""
    root = parent.attachNewNode("outlined")
    root.setPos(*pos)
    for i in range(12):
        a = i * math.tau / 12
        n = TextNode("o")
        n.setText(text)
        if style.font:
            n.setFont(style.font)
        n.setAlign(align)
        n.setTextColor(*outline)
        np_ = root.attachNewNode(n)
        np_.setScale(scale)
        np_.setPos(math.cos(a) * thickness, 0, math.sin(a) * thickness)
    n = TextNode("f")
    n.setText(text)
    if style.font:
        n.setFont(style.font)
    n.setAlign(align)
    n.setTextColor(*fill)
    top = root.attachNewNode(n)
    top.setScale(scale)
    top.setPos(0, -0.001, 0)
    return root


class Backdrop:
    """The cloud-sky picture, covering the whole window at any shape."""

    def __init__(self, base, style):
        self.base = base
        self.root = base.render2d.attachNewNode("backdrop")
        self.root.setBin("background", 0)
        self.root.setDepthWrite(False)
        self.root.setDepthTest(False)
        cm = CardMaker("sky")
        cm.setFrame(-1, 1, -1, 1)
        self.card = self.root.attachNewNode(cm.generate())
        img = style.image("background.jpg")
        self.tex = base.loader.loadTexture(Filename.fromOsSpecific(img)) if img else None
        if self.tex:
            self.card.setTexture(self.tex)
        else:
            self.card.setColor(0.28, 0.61, 0.94, 1)
        base.accept("aspectRatioChanged", self.fit)
        self.fit()

    def fit(self):
        if not self.tex:
            return
        win = self.base.win
        wa = win.getXSize() / max(1.0, float(win.getYSize()))
        ta = self.tex.getXSize() / max(1.0, float(self.tex.getYSize()))
        # cover: crop the picture on one axis so it fills the window without stretching
        sx, sy = (1.0, ta / wa) if wa > ta else (wa / ta, 1.0)
        ts = TextureStage.getDefault()
        self.card.setTexScale(ts, sx, sy)
        self.card.setTexOffset(ts, (1 - sx) / 2, (1 - sy) / 2)

    def destroy(self):
        self.base.ignore("aspectRatioChanged")
        self.root.removeNode()


def pill(parent, style, text, pos, size, fill, border, border_px, text_fg, text_scale, command=None, extra=(), radius=None):
    """A rounded button. size is (width, height) in aspect2d units."""
    w, h = size
    px_w, px_h = max(8, int(w * 300)), max(8, int(h * 300))
    tex = rounded_texture(px_w, px_h, fill, border, border_px, (radius if radius is not None else h * 300 / 2))
    kw = dict(parent=parent, relief=None, image=tex, image_scale=(w / 2, 1, h / 2), pos=pos, text=text, text_scale=text_scale,
              text_fg=text_fg, text_pos=(0, -text_scale * 0.3), pressEffect=1, command=command, extraArgs=list(extra))
    if style.font:
        kw["text_font"] = style.font
    b = DirectButton(**kw)
    b.setTransparency(TransparencyAttrib.MAlpha)
    return b


def link(parent, style, text, pos, scale, command):
    kw = dict(parent=parent, relief=None, text=text, text_scale=scale, text_fg=DARK, pos=pos, command=command, pressEffect=0)
    if style.font:
        kw["text_font"] = style.font
    return DirectButton(**kw)


def text_line(parent, style, text, pos, scale, fg=INK, align=TextNode.ACenter, wordwrap=None):
    kw = dict(parent=parent, relief=None, text=text, text_scale=scale, text_fg=fg, pos=pos, text_align=align)
    if wordwrap:
        kw["text_wordwrap"] = wordwrap
    if style.font:
        kw["text_font"] = style.font
    return DirectLabel(**kw)


def field(parent, style, pos, width, placeholder, secret=False, on_enter=None):
    """A white rounded text box with a blue edge. The placeholder is a faded label that goes away once the box has text."""
    h = 0.115
    holder = DirectFrame(parent=parent, relief=None, pos=pos)
    tex = rounded_texture(int(width * 300), int(h * 300), (0.96, 0.98, 1.0, 0.97), (0.12, 0.30, 0.65, 1), 4, h * 150)
    bg = DirectFrame(parent=holder, relief=None, image=tex, image_scale=(width / 2, 1, h / 2))
    bg.setTransparency(TransparencyAttrib.MAlpha)
    hint = text_line(holder, style, placeholder, (0, 0, -0.03), 0.07, fg=(0.45, 0.52, 0.68, 0.8))
    kw = dict(parent=holder, relief=None, scale=0.075, pos=(-width / 2 + 0.05, 0, -0.027), width=int(width / 0.075 - 1.4), numLines=1,
              initialText="", cursorKeys=1, obscured=1 if secret else 0, text_fg=DARK, focus=0, entryFont=style.font,
              frameColor=(0, 0, 0, 0))
    if on_enter:
        kw["command"] = on_enter
        kw["extraArgs"] = []
    e = DirectEntry(**kw)

    def sync(_=None):
        if e.get():
            hint.hide()
        else:
            hint.show()
    e["focusInCommand"] = sync
    e["focusOutCommand"] = sync
    e.holder, e.hint, e.sync = holder, hint, sync
    return e


class Screen:
    """Base for a screen: a node under aspect2d that can be shown and hidden."""

    def __init__(self, base, style):
        self.base, self.style = base, style
        self.root = base.aspect2d.attachNewNode(self.__class__.__name__)

    def show(self):
        self.root.show()

    def hide(self):
        self.root.hide()

    def destroy(self):
        self.root.removeNode()


class Title:
    """The game's name at the top of a screen: the logo picture when the server provides one, else the outlined lettering."""

    def __init__(self, parent, style, z=0.62, scale=0.19):
        logo = style.image("logo.png")
        self.node = parent.attachNewNode("title")
        tex = style.loader.loadTexture(Filename.fromOsSpecific(logo)) if logo else None
        if tex:
            cm = CardMaker("logo")
            ratio = tex.getXSize() / float(tex.getYSize())
            h = 0.5
            cm.setFrame(-h * ratio / 2, h * ratio / 2, -h / 2, h / 2)
            c = self.node.attachNewNode(cm.generate())
            c.setTexture(tex)
            c.setTransparency(TransparencyAttrib.MAlpha)
            self.node.setPos(0, 0, z + 0.05)
        else:
            outlined_text(self.node, "TOONTOWN: ANYWHERE", scale, GOLD, OUTLINE, scale * 0.07, style, pos=(0, 0, z))


class LoadingScreen(Screen):
    def __init__(self, base, style):
        Screen.__init__(self, base, style)
        Title(self.root, style)
        self.status = text_line(self.root, style, "Checking for updates...", (0, 0, -0.18), 0.085, fg=(1, 1, 1, 1))
        self.detail = text_line(self.root, style, "", (0, 0, -0.52), 0.06, fg=(1, 1, 1, 0.92))
        w, h = 1.3, 0.09
        self.bar_w = w
        bar_bg = rounded_texture(int(w * 300), int(h * 300), (0.10, 0.25, 0.60, 0.55), (1, 1, 1, 0.9), 3, h * 150)
        f = DirectFrame(parent=self.root, relief=None, image=bar_bg, image_scale=(w / 2, 1, h / 2), pos=(0, 0, -0.36))
        f.setTransparency(TransparencyAttrib.MAlpha)
        self.fill_tex = rounded_texture(int(w * 300) - 12, int(h * 300) - 12, (1.0, 0.851, 0.149, 1), (1.0, 0.851, 0.149, 1), 0, (h * 300 - 12) / 2)
        cm = CardMaker("fill")
        cm.setFrame(0, 1, -(h - 0.04) / 2, (h - 0.04) / 2)
        self.fill = self.root.attachNewNode(cm.generate())
        self.fill.setTexture(self.fill_tex)
        self.fill.setTransparency(TransparencyAttrib.MAlpha)
        self.fill.setPos(-w / 2 + 0.02, 0, -0.36)
        self.fill.setScale(0.001, 1, 1)
        self.set_progress(0.0)

    def set_progress(self, frac):
        frac = max(0.0, min(1.0, frac))
        self.fill.setScale(max(0.0001, (self.bar_w - 0.04) * frac), 1, 1)

    def update(self, st):
        self.status.setText(st.get("text", ""))
        tot, done = st.get("total_bytes", 0), st.get("done_bytes", 0)
        if tot:
            self.set_progress(done / float(tot))
            self.detail.setText("%d MB of %d MB" % (done // 1048576, tot // 1048576))
        else:
            self.detail.setText("")


class LoginScreen(Screen):
    def __init__(self, base, style, on_play, on_forgot, on_server):
        Screen.__init__(self, base, style)
        self.on_play = on_play
        Title(self.root, style)
        self.user = field(self.root, style, (0, 0, 0.12), 0.95, "Toon name", on_enter=lambda _=None: self.focus_pass())
        self.pass_ = field(self.root, style, (0, 0, -0.06), 0.95, "Password", secret=True, on_enter=lambda _=None: self.play())
        self.play_btn = pill(self.root, style, "PLAY!", (0, 0, -0.30), (0.56, 0.17), GOLD, BROWN, 4, BROWN, 0.11, command=self.play)
        self.forgot = link(self.root, style, "Forgot password?", (0.62, 0, -0.32), 0.058, on_forgot)
        self.hint = text_line(self.root, style, "New here? Pick a name and password and tap PLAY!", (0, 0, -0.50), 0.052, fg=INK)
        self.msg = text_line(self.root, style, "", (0, 0, -0.60), 0.055, fg=ERROR, wordwrap=34)
        self.credit = text_line(self.root, style, "Official client for Toontown: Anywhere", (0, 0, -0.93), 0.045, fg=INK)
        self.f11 = text_line(self.root, style, "F11: full screen", (0, 0, -0.93), 0.04, fg=INK, align=TextNode.ARight)
        self.server_btn = pill(self.root, style, "Change server", (0, 0, 0), (0.42, 0.085), (0.96, 0.98, 1, 0.97), OUTLINE, 3, OUTLINE, 0.045, command=on_server)
        self.discord = pill(self.root, style, "Discord", (0, 0, 0), (0.40, 0.085), DISCORD, (1, 1, 1, 1), 3, (1, 1, 1, 1), 0.05,
                            command=lambda: webbrowser.open("https://discord.gg/NxdkuR2aCp"))
        self.reddit = pill(self.root, style, "Reddit", (0, 0, 0), (0.40, 0.085), REDDIT, (1, 1, 1, 1), 3, (1, 1, 1, 1), 0.05,
                           command=lambda: webbrowser.open("https://www.reddit.com/r/ToontownAnywhere/s/p7FFnl9jGJ"))
        base.accept("aspectRatioChanged", self.layout)
        self.layout()

    def layout(self):
        """Corner buttons stay in the corners at any window shape."""
        a = self.base.getAspectRatio()
        self.server_btn.setPos(a - 0.26, 0, 0.93)
        self.f11.setPos(a - 0.04, 0, -0.95)
        self.discord.setPos(-a + 0.26, 0, -0.66)
        self.reddit.setPos(-a + 0.26, 0, -0.78)

    def focus_pass(self):
        self.pass_["focus"] = 1
        self.user["focus"] = 0

    def focus_user(self):
        self.user["focus"] = 1
        self.pass_["focus"] = 0

    def set_message(self, text, bad=False):
        self.msg["text_fg"] = ERROR if bad else INK
        self.msg["text"] = text

    def set_credentials(self, user, password):
        self.user.enterText(user or "")
        self.pass_.enterText(password or "")
        self.user.sync()
        self.pass_.sync()

    def play(self):
        self.pass_.sync()
        self.on_play(self.user.get().strip().lower(), self.pass_.get())

    def set_busy(self, busy):
        self.play_btn["state"] = "disabled" if busy else "normal"

    def destroy(self):
        self.base.ignore("aspectRatioChanged")
        Screen.destroy(self)


class CardScreen(Screen):
    """Recovery answers (set them once, or use them to pick a new password): two or three fields, a main button and a smaller one."""

    def __init__(self, base, style, title, subtitle, fields, main_text, on_main, side_text, on_side):
        Screen.__init__(self, base, style)
        Title(self.root, style, z=0.7, scale=0.14)
        text_line(self.root, style, title, (0, 0, 0.42), 0.09, fg=(1, 1, 1, 1))
        text_line(self.root, style, subtitle, (0, 0, 0.30), 0.052, fg=INK, wordwrap=36)
        self.fields = []
        z = 0.12
        for ph, secret in fields:
            self.fields.append(field(self.root, style, (0, 0, z), 0.95, ph, secret=secret))
            z -= 0.18
        self.msg = text_line(self.root, style, "", (0, 0, z + 0.04), 0.055, fg=ERROR, wordwrap=34)
        self.main = pill(self.root, style, main_text, (0, 0, z - 0.14), (0.56, 0.15), GOLD, BROWN, 4, BROWN, 0.095, command=on_main)
        self.side = None
        if side_text:
            self.side = pill(self.root, style, side_text, (0, 0, z - 0.32), (0.40, 0.09), (0.96, 0.98, 1, 0.97), OUTLINE, 3, OUTLINE, 0.05, command=on_side)

    def values(self):
        return [f.get().strip() for f in self.fields]

    def set_message(self, text, bad=False):
        self.msg["text_fg"] = ERROR if bad else INK
        self.msg["text"] = text

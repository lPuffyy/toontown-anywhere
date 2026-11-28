"""Reusable gag-track selection GUI.

mode='start'  -> pick N of all 7 tracks (starting gags), no cancel/timer.
mode='unlock' -> pick 1 of the offered tracks, cancel/timer allowed.

Each choice shows the gag's inventory icon above its label button. Selecting a
track overlays a green checkmark drawn on the icon.
Emits 'trackSelectionDone' with the chosen track list.
"""
from direct.gui.DirectGui import *
from panda3d.core import *
from toontown.toonbase import ToontownTimer, ToontownGlobals, ToontownBattleGlobals, TTLocalizer
from direct.directnotify import DirectNotifyGlobal

notify = DirectNotifyGlobal.directNotify.newCategory('TrackSelectionGui')


def _make_checkmark():
    """Build a simple green check from two thick line segments (no font glyph needed)."""
    try:
        ls = LineSegs()
        ls.setThickness(15.0)
        ls.setColor(0.1, 0.85, 0.1, 1)
        # Symmetric V so its bounding box is centered on the icon origin.
        ls.moveTo(-0.06, 0, 0.0)
        ls.drawTo(-0.01, 0, -0.05)
        ls.drawTo(0.06, 0, 0.06)
        return NodePath(ls.create())
    except Exception:
        return None


class TrackSelectionGui(DirectFrame):
    def __init__(self, tracks, numToPick, timeout=90, mode='start', owned=(),
                 doneEvent='trackSelectionDone'):
        DirectFrame.__init__(self, relief=None, geom=DGG.getDefaultDialogGeom(),
                             geom_color=Vec4(0.8, 0.6, 0.4, 1), geom_scale=(1.45, 1, 1.5),
                             geom_hpr=(0, 0, -90), pos=(0, 0, 0))
        self.initialiseoptions(TrackSelectionGui)
        self.tracks = list(tracks)
        self.numToPick = int(numToPick)
        self.mode = mode
        self.doneEvent = doneEvent
        self.selected = []
        self.buttons = {}
        self.checks = {}

        title = TTLocalizer.TrackSelectGuiTitle if mode == 'start' else TTLocalizer.TrackSelectGuiUnlockTitle
        DirectLabel(parent=self, relief=None, text=title, text_scale=0.09,
                    text_font=ToontownGlobals.getInterfaceFont(), pos=(0, 0, 0.68),
                    text_fg=(0.2, 0.1, 0, 1))

        if owned:
            names = ', '.join(ToontownBattleGlobals.Tracks[t].capitalize() for t in owned)
            label = DirectLabel(parent=self, relief=None, text='Unlocked: ' + names,
                                text_scale=0.047, text_wordwrap=29, pos=(0, 0, 0.52),
                                text_font=ToontownGlobals.getInterfaceFont(),
                                text_fg=(0.2, 0.1, 0, 1))
            label.setBin('gui-popup', 100)
        checkGeom = _make_checkmark()
        guiButton = loader.loadModel('phase_3/models/gui/quit_button')
        invModel = loader.loadModel('phase_3.5/models/gui/inventory_icons')
        whiteCardTex = Texture()
        whiteCardImg = PNMImage(4, 4)
        whiteCardImg.fill(1, 1, 1)
        whiteCardTex.load(whiteCardImg)
        whiteCardTex.setWrapU(Texture.WMClamp)
        whiteCardTex.setWrapV(Texture.WMClamp)
        up = guiButton.find('**/QuitBtn_UP')
        dn = guiButton.find('**/QuitBtn_DN')
        rl = guiButton.find('**/QuitBtn_RLVR')

        for i, trackId in enumerate(self.tracks):
            name = ToontownBattleGlobals.Tracks[trackId].capitalize()
            row, col = divmod(i, 4)
            x = -0.48 + col * 0.32
            z = 0.32 - row * 0.42

            # Black outline behind the white card (slightly larger black quad).
            outline = DirectFrame(parent=self, relief=None, image=whiteCardTex,
                                  image_color=(0, 0, 0, 1),
                                  image_scale=(0.158, 1, 0.178),
                                  pos=(x, 0, z + 0.03))
            outline.setBin('gui-popup', 96)
            outline.setDepthTest(False)
            outline.setDepthWrite(False)

            # Plain white card behind the icon and button.
            card = DirectFrame(parent=self, relief=None, image=whiteCardTex,
                               image_scale=(0.15, 1, 0.17),
                               pos=(x, 0, z + 0.03))
            card.setBin('gui-popup', 98)
            card.setDepthTest(False)
            card.setDepthWrite(False)

            # Gag picture above the label button (larger and easy to see).
            try:
                iconPath = invModel.find('**/' + ToontownBattleGlobals.AvPropsNew[trackId][1])
                if iconPath.isEmpty():
                    iconPath = None
                pic = DirectFrame(parent=self, relief=None, geom=iconPath,
                                  geom_scale=1.0, pos=(x, 0, z + 0.03))
                pic.setBin('gui-popup', 100)
                pic.setDepthTest(False)
                pic.setDepthWrite(False)
            except Exception:
                notify.warning('no icon for track %s' % trackId)

            b = DirectButton(
                parent=self, relief=None, image=(up, dn, rl), image_scale=(0.62, 1, 1),
                text=name, text_scale=0.055, text_pos=(0, -0.02),
                text_font=ToontownGlobals.getInterfaceFont(),
                command=self.toggle, extraArgs=[trackId], pos=(x, 0, z - 0.08), scale=0.8)
            b.setBin('gui-popup', 100)
            b.setDepthTest(False)
            b.setDepthWrite(False)
            self.buttons[trackId] = b

            # Green checkmark in front of the picture, hidden until selected.
            check = None
            if checkGeom:
                try:
                    check = DirectFrame(parent=self, relief=None, geom=checkGeom,
                                        geom_scale=1.0, pos=(x, 0, z + 0.03))
                    check.setBin('gui-popup', 110)
                    check.setDepthTest(False)
                    check.setDepthWrite(False)
                    check.hide()
                except Exception:
                    check = None
            self.checks[trackId] = check

        invModel.removeNode()
        guiButton.removeNode()

        self.confirmButton = DirectButton(
            parent=self, relief=None, image=(up, dn, rl), image_scale=(0.9, 1, 1),
            image3_color=(0.55, 0.55, 0.55, 1),
            text=TTLocalizer.TrackSelectGuiChoose, text_scale=0.07, text_pos=(0, -0.02),
            text3_fg=(0.35, 0.35, 0.35, 1),
            command=self.confirm, pos=(0, 0, -0.66))
        self.confirmButton.setBin('gui-popup', 100)
        self.confirmButton.setDepthTest(False)
        if mode != 'start':
            self.cancelButton = DirectButton(
                parent=self, relief=None, image=(up, dn, rl), image_scale=(0.9, 1, 1),
                text=TTLocalizer.TrackSelectGuiCancel, text_scale=0.07, text_pos=(0, -0.02),
                command=self.cancel, pos=(-0.45, 0, -0.66))
            self.cancelButton.setBin('gui-popup', 100)
            self.cancelButton.setDepthTest(False)
            self.confirmButton.setPos(0.45, 0, -0.66)
        else:
            self.cancelButton = None

        self.timer = None
        if mode != 'start':
            self.timer = ToontownTimer.ToontownTimer()
            self.timer.reparentTo(self)
            self.timer.setScale(0.3)
            self.timer.setPos(0, 0, -0.52)
            self.timer.countdown(timeout, self.timeout)
        self.updateButtons()
        notify.info('created %d track icons for %s' % (len(self.buttons), mode))

    def toggle(self, trackId):
        if trackId in self.selected:
            self.selected.remove(trackId)
        else:
            if len(self.selected) >= self.numToPick:
                self.selected.pop(0)
            self.selected.append(trackId)
        for tid, check in self.checks.items():
            if check:
                if tid in self.selected:
                    check.show()
                else:
                    check.hide()
        self.updateButtons()

    def updateButtons(self):
        ready = len(self.selected) == self.numToPick
        self.confirmButton['state'] = DGG.NORMAL if ready else DGG.DISABLED

    def confirm(self):
        if len(self.selected) != self.numToPick:
            return
        if self.timer:
            self.timer.stop()
        messenger.send(self.doneEvent, [list(self.selected)])

    def cancel(self):
        if self.timer:
            self.timer.stop()
        messenger.send(self.doneEvent, [[]])

    def timeout(self):
        if self.mode == 'start':
            self.selected = list(self.tracks[:self.numToPick])
            self.confirm()
        else:
            self.cancel()

    def destroy(self):
        if self.timer:
            self.timer.destroy()
            self.timer = None
        DirectFrame.destroy(self)

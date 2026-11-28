from . import ShtikerPage
from toontown.toonbase import ToontownBattleGlobals
from direct.gui.DirectGui import *
from panda3d.core import *
from toontown.toonbase import ToontownGlobals
from toontown.toonbase import TTLocalizer

class InventoryPage(ShtikerPage.ShtikerPage):

    def __init__(self):
        ShtikerPage.ShtikerPage.__init__(self)
        self.currentTrackInfo = None
        self.onscreen = 0
        self.lastInventoryTime = globalClock.getRealTime()
        return

    def load(self):
        ShtikerPage.ShtikerPage.load(self)
        self.title = DirectLabel(parent=self, relief=None, text=TTLocalizer.InventoryPageTitle, text_scale=0.12, textMayChange=1, pos=(0, 0, 0.62))
        edge = (0.78, 0.82, 0.88, 1)
        fill = (0.17, 0.19, 0.23, 0.96)
        self.gagFrame = DirectFrame(parent=self, relief=None, pos=(0.1, 0, -0.47), scale=(0.35, 0.35, 0.35))
        DirectFrame(parent=self.gagFrame, relief=DGG.FLAT, frameColor=edge, frameSize=(-0.62, 0.58, -0.68, 0.60))
        DirectFrame(parent=self.gagFrame, relief=DGG.FLAT, frameColor=fill, frameSize=(-0.56, 0.52, -0.62, 0.54))
        self.trackCard = DirectFrame(parent=self, relief=None, pos=(-0.4, 0, -0.47), scale=(0.35, 0.35, 0.35))
        DirectFrame(parent=self.trackCard, relief=DGG.FLAT, frameColor=edge, frameSize=(-0.82, 0.78, -0.66, 0.58))
        self.trackInfo = DirectFrame(parent=self.trackCard, relief=DGG.FLAT, frameColor=fill, frameSize=(-0.76, 0.72, -0.60, 0.52), text='', text_wordwrap=11, text_align=TextNode.ALeft, text_scale=0.12, text_pos=(-0.65, 0.3), text_fg=(0.9, 0.92, 0.95, 1))
        self.trackProgress = DirectWaitBar(parent=self.trackInfo, pos=(0, 0, -0.2), relief=DGG.SUNKEN, frameSize=(-0.6,
         0.6,
         -0.1,
         0.1), borderWidth=(0.025, 0.025), scale=1.1, frameColor=(0.4, 0.6, 0.4, 1), barColor=(0.9, 1, 0.7, 1), text='0/0', text_scale=0.15, text_fg=(1, 1, 1, 1), text_align=TextNode.ACenter, text_pos=(0, -0.22))
        self.trackProgress.hide()
        jarGui = loader.loadModel('phase_3.5/models/gui/jar_gui')
        self.moneyDisplay = DirectLabel(parent=self, relief=None, pos=(0.55, 0, -0.5), scale=0.8, text=str(base.localAvatar.getMoney()), text_scale=0.18, text_fg=(0.95, 0.95, 0, 1), text_shadow=(0, 0, 0, 1), text_pos=(0, -0.1, 0), image=jarGui.find('**/Jar'), text_font=ToontownGlobals.getSignFont())
        jarGui.removeNode()
        return

    def unload(self):
        del self.title
        ShtikerPage.ShtikerPage.unload(self)

    def __moneyChange(self, money):
        self.moneyDisplay['text'] = str(money)

    def enter(self):
        ShtikerPage.ShtikerPage.enter(self)
        base.localAvatar.inventory.setActivateMode('book')
        base.localAvatar.inventory.show()
        base.localAvatar.inventory.reparentTo(self)
        self.moneyDisplay['text'] = str(base.localAvatar.getMoney())
        self.accept('enterBookDelete', self.enterDeleteMode)
        self.accept('exitBookDelete', self.exitDeleteMode)
        self.accept('enterTrackFrame', self.updateTrackInfo)
        self.accept('exitTrackFrame', self.clearTrackInfo)
        self.accept(localAvatar.uniqueName('moneyChange'), self.__moneyChange)

    def exit(self):
        ShtikerPage.ShtikerPage.exit(self)
        self.clearTrackInfo(self.currentTrackInfo)
        self.ignore('enterBookDelete')
        self.ignore('exitBookDelete')
        self.ignore('enterTrackFrame')
        self.ignore('exitTrackFrame')
        self.ignore(localAvatar.uniqueName('moneyChange'))
        self.makePageWhite(None)
        base.localAvatar.inventory.hide()
        base.localAvatar.inventory.reparentTo(hidden)
        self.exitDeleteMode()
        return

    def enterDeleteMode(self):
        self.title['text'] = TTLocalizer.InventoryPageDeleteTitle
        self.title['text_fg'] = (0, 0, 0, 1)
        self.book['image_color'] = Vec4(1, 1, 0, 1)

    def exitDeleteMode(self):
        self.title['text'] = TTLocalizer.InventoryPageTitle
        self.title['text_fg'] = (0, 0, 0, 1)
        self.book['image_color'] = Vec4(1, 1, 1, 1)

    def updateTrackInfo(self, trackIndex):
        self.currentTrackInfo = trackIndex
        trackName = TextEncoder.upper(ToontownBattleGlobals.Tracks[trackIndex])
        if base.localAvatar.hasTrackAccess(trackIndex):
            curExp, nextExp = base.localAvatar.inventory.getCurAndNextExpValues(trackIndex)
            trackText = '%s / %s' % (curExp, nextExp)
            self.trackProgress['range'] = nextExp
            self.trackProgress['value'] = curExp
            if curExp >= ToontownBattleGlobals.regMaxSkill:
                str = TTLocalizer.InventoryPageTrackFull % trackName
                trackText = TTLocalizer.InventoryUberTrackExp % {'nextExp': ToontownBattleGlobals.MaxSkill - curExp}
                self.trackProgress['range'] = ToontownBattleGlobals.UberSkill
                uberCurrExp = curExp - ToontownBattleGlobals.regMaxSkill
                self.trackProgress['value'] = uberCurrExp
            else:
                morePoints = nextExp - curExp
                if morePoints == 1:
                    str = TTLocalizer.InventoryPageSinglePoint % {'trackName': trackName,
                     'numPoints': morePoints}
                else:
                    str = TTLocalizer.InventoryPagePluralPoints % {'trackName': trackName,
                     'numPoints': morePoints}
            self.trackInfo['text'] = str
            self.trackProgress['text'] = trackText
            self.trackProgress['frameColor'] = (ToontownBattleGlobals.TrackColors[trackIndex][0] * 0.6,
             ToontownBattleGlobals.TrackColors[trackIndex][1] * 0.6,
             ToontownBattleGlobals.TrackColors[trackIndex][2] * 0.6,
             1)
            self.trackProgress['barColor'] = (ToontownBattleGlobals.TrackColors[trackIndex][0],
             ToontownBattleGlobals.TrackColors[trackIndex][1],
             ToontownBattleGlobals.TrackColors[trackIndex][2],
             1)
            self.trackProgress.show()
        else:
            str = TTLocalizer.InventoryPageNoAccess % trackName
            self.trackInfo['text'] = str
            self.trackProgress.hide()

    def clearTrackInfo(self, trackIndex):
        if self.currentTrackInfo == trackIndex:
            self.trackInfo['text'] = ''
            self.trackProgress.hide()
            self.currentTrackInfo = None
        return

    def acceptOnscreenHooks(self):
        self.accept(ToontownGlobals.InventoryHotkeyOn, self.showInventoryOnscreen)
        self.accept(ToontownGlobals.InventoryHotkeyOff, self.hideInventoryOnscreen)

    def ignoreOnscreenHooks(self):
        self.ignore(ToontownGlobals.InventoryHotkeyOn)
        self.ignore(ToontownGlobals.InventoryHotkeyOff)

    def showInventoryOnscreen(self):
        messenger.send('wakeup')
        timedif = globalClock.getRealTime() - self.lastInventoryTime
        if timedif < 0.7:
            return
        self.lastInventoryTime = globalClock.getRealTime()
        if self.onscreen or base.localAvatar.questPage.onscreen:
            return
        self.onscreen = 1
        base.localAvatar.inventory.setActivateMode('book')
        base.localAvatar.inventory.show()
        base.localAvatar.inventory.reparentTo(self)
        self.moneyDisplay['text'] = str(base.localAvatar.getMoney())
        self.accept('enterTrackFrame', self.updateTrackInfo)
        self.accept('exitTrackFrame', self.clearTrackInfo)
        self.accept(localAvatar.uniqueName('moneyChange'), self.__moneyChange)
        self.reparentTo(aspect2d)
        self._fitQuickGags()
        self.accept('tta-ui-size-changed', self._fitQuickGags)
        self.accept('aspectRatioChanged', self._fitQuickGags)
        self.title.hide()
        self.show()

    def _fitQuickGags(self):
        self.setScale(ToontownGlobals.getFittedUiScale(1.08, 1.25))

    def hideInventoryOnscreen(self):
        if not self.onscreen:
            return
        self.onscreen = 0
        self.ignore('enterTrackFrame')
        self.ignore('exitTrackFrame')
        self.ignore(localAvatar.uniqueName('moneyChange'))
        base.localAvatar.inventory.hide()
        base.localAvatar.inventory.reparentTo(hidden)
        self.ignore('tta-ui-size-changed')
        self.ignore('aspectRatioChanged')
        self.setScale(1)
        self.reparentTo(self.book)
        self.title.show()
        self.hide()

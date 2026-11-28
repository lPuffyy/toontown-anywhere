from direct.gui.DirectGui import *
from panda3d.core import *
from toontown.toonbase.ToontownBattleGlobals import *
from . import InventoryBase
from toontown.toonbase import TTLocalizer
from toontown.quest import BlinkingArrows
from direct.interval.IntervalGlobal import *
from direct.directnotify import DirectNotifyGlobal
from toontown.toonbase import ToontownGlobals
from otp.otpbase import OTPGlobals

class InventoryNew(InventoryBase.InventoryBase, DirectFrame):
    notify = DirectNotifyGlobal.directNotify.newCategory('InventoryNew')
    PressableTextColor = Vec4(1, 1, 1, 1)
    PressableGeomColor = Vec4(1, 1, 1, 1)
    # Slot colors follow the battle bar: quiet metal, a light hover, gold on press.
    PressableImageColor = Vec4(0.55, 0.62, 0.70, 1)
    PropBonusPressableImageColor = Vec4(0.95, 0.72, 0.28, 1)
    NoncreditPressableImageColor = Vec4(0.32, 0.46, 0.48, 1)
    PropBonusNoncreditPressableImageColor = Vec4(0.55, 0.45, 0.22, 1)
    DeletePressableImageColor = Vec4(0.58, 0.26, 0.24, 1)
    UnpressableTextColor = Vec4(1, 1, 1, 0.3)
    UnpressableGeomColor = Vec4(1, 1, 1, 0.3)
    UnpressableImageColor = Vec4(0.30, 0.32, 0.36, 0.9)
    BookUnpressableTextColor = Vec4(1, 1, 1, 1)
    BookUnpressableGeomColor = Vec4(1, 1, 1, 1)
    BookUnpressableImage0Color = Vec4(0.55, 0.62, 0.70, 1)
    BookUnpressableImage2Color = Vec4(0.82, 0.86, 0.90, 1)
    ShadowColor = Vec4(0, 0, 0, 0)
    ShadowBuffedColor = Vec4(1, 1, 1, 1)
    UnpressableShadowBuffedColor = Vec4(1, 1, 1, 0.3)
    TrackYOffset = 0.0
    TrackYSpacing = -0.12
    ButtonXOffset = -0.31
    ButtonXSpacing = 0.18

    def __init__(self, toon, invStr = None, ShowSuperGags = 1):
        InventoryBase.InventoryBase.__init__(self, toon, invStr)
        DirectFrame.__init__(self, relief=None)
        self.initialiseoptions(InventoryNew)
        self._compactGrid = min(ToontownGlobals.getUiViewport()) < 600
        self.battleCreditLevel = None
        self.detailCredit = None
        self.__battleCreditMultiplier = 1
        self.__invasionCreditMultiplier = 1
        self.__respectInvasions = 1
        self._interactivePropTrackBonus = -1
        self.tutorialFlag = 0
        self.gagTutMode = 0
        self.showSuperGags = ShowSuperGags
        self.clickSuperGags = 1
        self.propAndOrganicBonusStack = base.config.GetBool('prop-and-organic-bonus-stack', 0)
        self.propBonusIval = Parallel()
        self.activateMode = 'book'
        self.load()
        self.hide()
        return

    def setBattleCreditMultiplier(self, mult):
        self.__battleCreditMultiplier = mult

    def getBattleCreditMultiplier(self):
        return self.__battleCreditMultiplier

    def setInteractivePropTrackBonus(self, trackBonus):
        self._interactivePropTrackBonus = trackBonus

    def getInteractivePropTrackBonus(self):
        return self._interactivePropTrackBonus

    def setInvasionCreditMultiplier(self, mult):
        self.__invasionCreditMultiplier = mult

    def getInvasionCreditMultiplier(self):
        return self.__invasionCreditMultiplier

    def setRespectInvasions(self, flag):
        self.__respectInvasions = flag

    def getRespectInvasions(self):
        return self.__respectInvasions

    def layoutTutorialBoard(self):
        """Reuse the book grid in the screen-space layer above Tutorial Tom."""
        self._tutorialBoard = True
        self.invFrame.reparentTo(self)
        self.invFrame.setPos(0, 0, 0)
        self.invFrame.setScale(1)
        self.reparentTo(aspect2d)
        self.setPos(0, 0, 0.52)
        self.setHpr(0, 0, 0)
        self.setScale(1)
        self._fitTrackRig()
        DirectFrame.show(self)
        self.detailFrame.hide()
        self.deleteEnterButton.hide()
        self.deleteExitButton.hide()
        self.deleteHelpText.hide()
        for track in range(len(Tracks)):
            self.trackRows[track].show()
            self.showTrack(track)
            for level in range(len(Levels[track])):
                button = self.buttons[track][level]
                if self.toon.hasTrackAccess(track) and self.itemIsUsable(track, level):
                    button.show()
                    self.makeBookUnpressable(button, track, level)
                else:
                    button.hide()
        return

    def show(self):
        if self.tutorialFlag:
            self.tutArrows.arrowsOn(-0.43, -0.12, 180, -0.43, -0.24, 180, onTime=1.0, offTime=0.2)
            if self.numItem(THROW_TRACK, 0) == 0:
                self.tutArrows.arrow1.reparentTo(hidden)
            else:
                self.tutArrows.arrow1.reparentTo(self.battleFrame, 1)
            if self.numItem(SQUIRT_TRACK, 0) == 0:
                self.tutArrows.arrow2.reparentTo(hidden)
            else:
                self.tutArrows.arrow2.reparentTo(self.battleFrame, 1)
            self.tutText.show()
            self.tutText.reparentTo(self.battleFrame, 1)
        DirectFrame.show(self)

    def uberGagToggle(self, showSuperGags = 1):
        self.showSuperGags = showSuperGags
        for itemList in self.invModels:
            for itemIndex in range(MAX_LEVEL_INDEX + 1):
                if itemIndex <= LAST_REGULAR_GAG_LEVEL + 1 or self.showSuperGags:
                    itemList[itemIndex].show()
                else:
                    itemList[itemIndex].hide()

        for buttonList in self.buttons:
            for buttonIndex in range(MAX_LEVEL_INDEX + 1):
                if buttonIndex <= LAST_REGULAR_GAG_LEVEL or self.showSuperGags:
                    buttonList[buttonIndex].show()
                else:
                    buttonList[buttonIndex].hide()

    def enableUberGags(self, enableSG = -1):
        if enableSG != -1:
            self.clickSuperGags = enableSG
        for buttonList in self.buttons:
            for buttonIndex in range(LAST_REGULAR_GAG_LEVEL + 1, MAX_LEVEL_INDEX + 1):
                if self.clickSuperGags:
                    pass
                else:
                    self.makeUnpressable(buttonList[buttonIndex], self.buttons.index(buttonList), buttonIndex)

    def hide(self):
        if self.tutorialFlag:
            self.tutArrows.arrowsOff()
            self.tutText.hide()
        DirectFrame.hide(self)

    def updateTotalPropsText(self):
        textTotal = TTLocalizer.InventoryTotalGags % (self.totalProps, self.toon.getMaxCarry())
        if localAvatar.getPinkSlips() > 1:
            textTotal = textTotal + '\n\n' + TTLocalizer.InventroyPinkSlips % localAvatar.getPinkSlips()
        elif localAvatar.getPinkSlips() == 1:
            textTotal = textTotal + '\n\n' + TTLocalizer.InventroyPinkSlip
        self.totalLabel['text'] = textTotal

    def unload(self):
        self.notify.debug('Unloading Inventory for %d' % self.toon.doId)
        self.stopAndClearPropBonusIval()
        self.propBonusIval.finish()
        self.propBonusIval = None
        del self.invModels
        self.buttonModels.removeNode()
        del self.buttonModels
        del self.upButton
        del self.downButton
        del self.rolloverButton
        del self.flatButton
        del self.invFrame
        del self.battleFrame
        del self.purchaseFrame
        del self.storePurchaseFrame
        self.deleteEnterButton.destroy()
        del self.deleteEnterButton
        self.deleteExitButton.destroy()
        del self.deleteExitButton
        del self.detailFrame
        del self.detailNameLabel
        del self.detailAmountLabel
        del self.detailDataLabel
        del self.totalLabel
        for row in self.trackRows:
            row.destroy()

        del self.trackRows
        del self.trackNameLabels
        del self.trackLockedLabels
        del self.trackBars
        for buttonList in self.buttons:
            for buttonIndex in range(MAX_LEVEL_INDEX + 1):
                buttonList[buttonIndex].destroy()

        del self.buttons
        InventoryBase.InventoryBase.unload(self)
        DirectFrame.destroy(self)
        return

    def load(self):
        self.notify.debug('Loading Inventory for %d' % self.toon.doId)
        invModel = loader.loadModel('phase_3.5/models/gui/inventory_icons')
        self.invModels = []
        for track in range(len(AvPropsNew)):
            itemList = []
            for item in range(len(AvPropsNew[track])):
                itemList.append(invModel.find('**/' + AvPropsNew[track][item]))

            self.invModels.append(itemList)

        invModel.removeNode()
        del invModel
        self.buttonModels = loader.loadModel('phase_3.5/models/gui/inventory_gui')
        self.rowModel = self.buttonModels.find('**/InventoryRow')
        self.upButton = self.buttonModels.find('**/InventoryButtonUp')
        self.downButton = self.buttonModels.find('**/InventoryButtonDown')
        self.rolloverButton = self.buttonModels.find('**/InventoryButtonRollover')
        self.flatButton = self.buttonModels.find('**/InventoryButtonFlat')
        self.invFrame = DirectFrame(relief=None, parent=self)
        self.battleFrame = None
        self.purchaseFrame = None
        self.storePurchaseFrame = None
        trashcanGui = loader.loadModel('phase_3/models/gui/trashcan_gui')
        self.deleteEnterButton = DirectButton(parent=self.invFrame, image=(trashcanGui.find('**/TrashCan_CLSD'), trashcanGui.find('**/TrashCan_OPEN'), trashcanGui.find('**/TrashCan_RLVR')), text=('', TTLocalizer.InventoryDelete, TTLocalizer.InventoryDelete), text_fg=(1, 1, 1, 1), text_shadow=(0, 0, 0, 1), text_scale=0.1, text_pos=(0, -0.1), text_font=getInterfaceFont(), textMayChange=0, relief=None, pos=(-1, 0, -0.35), scale=1.0)
        self.deleteExitButton = DirectButton(parent=self.invFrame, image=(trashcanGui.find('**/TrashCan_OPEN'), trashcanGui.find('**/TrashCan_CLSD'), trashcanGui.find('**/TrashCan_RLVR')), text=('', TTLocalizer.InventoryDone, TTLocalizer.InventoryDone), text_fg=(1, 1, 1, 1), text_shadow=(0, 0, 0, 1), text_scale=0.1, text_pos=(0, -0.1), text_font=getInterfaceFont(), textMayChange=0, relief=None, pos=(-1, 0, -0.35), scale=1.0)
        trashcanGui.removeNode()
        self.deleteEnterButton.hide()
        self.deleteExitButton.hide()
        self.deleteHelpText = DirectLabel(parent=self.invFrame, relief=None, pos=(0.272, 0.3, -0.907), text=TTLocalizer.InventoryDeleteHelp, text_fg=(0, 0, 0, 1), text_scale=0.08, textMayChange=0)
        self.deleteHelpText.hide()
        self.detailFrame = DirectFrame(parent=self.invFrame, relief=None, pos=(1.05, 0, -0.08))
        self.detailNameLabel = DirectLabel(parent=self.detailFrame, text='', text_scale=TTLocalizer.INdetailNameLabel, text_fg=(0.05, 0.14, 0.4, 1), scale=0.045, pos=(0, 0, 0), text_font=getInterfaceFont(), relief=None, image=self.invModels[0][0])
        self.detailAmountLabel = DirectLabel(parent=self.detailFrame, text='', text_fg=(0.05, 0.14, 0.4, 1), scale=0.04, pos=(0.16, 0, -0.175), text_font=getInterfaceFont(), text_align=TextNode.ARight, relief=None)
        self.detailDataLabel = DirectLabel(parent=self.detailFrame, text='', text_fg=(0.05, 0.14, 0.4, 1), scale=0.04, pos=(-0.22, 0, -0.24), text_font=getInterfaceFont(), text_align=TextNode.ALeft, relief=None)
        self.detailCreditLabel = DirectLabel(parent=self.detailFrame, text=TTLocalizer.InventorySkillCreditNone, text_fg=(0.05, 0.14, 0.4, 1), scale=0.04, pos=(-0.22, 0, -0.365), text_font=getInterfaceFont(), text_align=TextNode.ALeft, relief=None)
        self.detailCreditLabel.hide()
        self.totalLabel = DirectLabel(text='', parent=self.detailFrame, pos=(0, 0, -0.095), scale=0.05, text_fg=(1, 1, 1, 1), text_shadow=(0, 0, 0, 0.6), text_font=getInterfaceFont(), relief=None)
        self.updateTotalPropsText()
        self.trackRows = []
        self.trackNameLabels = []
        self.trackLockedLabels = []
        self.trackBars = []
        self.buttons = []
        # Tracks and their panel live on this node so the book can place them
        # without moving the delete button or the detail card.
        self.trackRig = self.invFrame.attachNewNode('track-rig')
        DirectFrame(parent=self.trackRig, relief=DGG.FLAT, frameColor=(0.78, 0.82, 0.88, 1), frameSize=(-0.982, 0.982, -0.865, 0.145), pos=(0, -1, 0))
        DirectFrame(parent=self.trackRig, relief=DGG.FLAT, frameColor=(0.17, 0.19, 0.23, 0.96), frameSize=(-0.970, 0.970, -0.853, 0.133), pos=(0, -1, 0))
        grid_font = ToontownGlobals.getInterfaceFont()
        # On phones keep the track, progress bar and gag slots in separate
        # columns. Stacking two lines in one row made the shop text illegible.
        compact = self._compactGrid
        track_text_scale = 0.078 if compact else TTLocalizer.INtrackNameLabels
        name_x, name_z = (-0.865, -0.027) if compact else (-0.785, 0.01)
        bar_x, bar_z = (-0.377, 0) if compact else (-0.648, -0.025)
        slot_x = -0.14 if compact else self.ButtonXOffset - 0.065
        slot_spacing = 0.154 if compact else self.ButtonXSpacing
        for track in range(0, len(Tracks)):
            r = TrackColors[track][0]
            g = TrackColors[track][1]
            b = TrackColors[track][2]
            # Same footprint as InventoryRow, so the bar stays on the book page.
            rowPos = (0, 0.3, self.TrackYOffset + track * self.TrackYSpacing)
            DirectFrame(parent=self.trackRig, relief=DGG.FLAT, state=DGG.DISABLED, scale=(1.0, 1.0, 1.1), pos=rowPos, frameColor=(0.90, 0.92, 0.95, 1), frameSize=(-0.906, 0.906, -0.060, 0.060))
            trackFrame = DirectFrame(parent=self.trackRig, relief=DGG.FLAT, state=DGG.NORMAL, scale=(1.0, 1.0, 1.1), pos=rowPos, frameColor=(r * 0.35 + 0.08,
             g * 0.35 + 0.08,
             b * 0.35 + 0.08,
             0.95), frameSize=(-0.900, 0.900, -0.0569, 0.0569))
            DirectFrame(parent=trackFrame, relief=DGG.FLAT, frameColor=(r, g, b, 1), frameSize=(-0.012, 0.012, -0.04, 0.04), pos=(-0.887 if compact else -0.80, 0, 0))
            trackFrame.bind(DGG.WITHIN, self.enterTrackFrame, extraArgs=[track])
            trackFrame.bind(DGG.WITHOUT, self.exitTrackFrame, extraArgs=[track])
            self.trackRows.append(trackFrame)
            self.trackNameLabels.append(DirectLabel(text=TextEncoder.upper(Tracks[track]), parent=self.trackRows[track], pos=(name_x, -0.1, name_z), scale=track_text_scale, relief=None, text_fg=(1, 1, 1, 1), text_font=grid_font, text_align=TextNode.ALeft, textMayChange=0))
            locked = DirectLabel(text='locked', parent=self.trackRows[track], pos=(0, -0.1, -0.027 if compact else -0.012), scale=track_text_scale, relief=None, text_fg=(1, 1, 1, 1), text_font=grid_font, text_align=TextNode.ACenter, textMayChange=0)
            locked.hide()
            self.trackLockedLabels.append(locked)
            self.trackBars.append(DirectWaitBar(parent=self.trackRows[track], pos=(bar_x, -0.1, bar_z), relief=DGG.FLAT, frameSize=(-0.77, 0.77, -0.17, 0.17) if compact else (-0.6, 0.6, -0.1, 0.1), borderWidth=(0.02, 0.02), scale=0.22, frameColor=(0.1, 0.11, 0.13, 1), barColor=(r * 0.9,
             g * 0.9,
             b * 0.9,
             1), text='0 / 0', text_font=grid_font, text_scale=0.211 if compact else 0.16, text_fg=(1, 1, 1, 1), text_shadow=(0, 0, 0, 0.8), text_align=TextNode.ACenter, text_pos=(0, -0.08 if compact else -0.05)))
            self.buttons.append([])
            for item in range(0, len(Levels[track])):
                gagPos = (slot_x + item * slot_spacing, -0.1, 0)
                button = DirectButton(parent=self.trackRows[track], relief=DGG.FLAT, frameSize=(-0.062, 0.080, -0.046, 0.050), frameColor=(0.45, 0.48, 0.52, 0.62), image=(self.upButton,
                 self.downButton,
                 self.rolloverButton,
                 self.flatButton), image_scale=0.001, image_color=(1, 1, 1, 0), geom=self.invModels[track][item], text='50', text_scale=0.068 if compact else 0.04, text_font=grid_font, text_align=TextNode.ARight, geom_scale=0.7, geom_pos=(-0.01, -0.1, 0), text_fg=Vec4(1, 1, 1, 1), text_bg=(0.06, 0.08, 0.10, 0.90), text_pos=(0.067, -0.023), textMayChange=1, pos=gagPos, command=self.__handleSelection, extraArgs=[track, item])
                button.bind(DGG.ENTER, self.showDetail, extraArgs=[track, item])
                button.bind(DGG.EXIT, self.hideDetail)
                self._addGagOutline(button)
                self.buttons[track].append(button)

        return

    def __handleSelection(self, track, level):
        if self.activateMode == 'purchaseDelete' or self.activateMode == 'bookDelete' or self.activateMode == 'storePurchaseDelete':
            if self.numItem(track, level):
                self.useItem(track, level)
                self.updateGUI(track, level)
                messenger.send('inventory-deletion', [track, level])
                self.showDetail(track, level)
        elif self.activateMode == 'purchase' or self.activateMode == 'storePurchase':
            messenger.send('inventory-selection', [track, level])
            self.showDetail(track, level)
        elif self.gagTutMode:
            pass
        else:
            messenger.send('inventory-selection', [track, level])

    def __handleRun(self):
        messenger.send('inventory-run')

    def __handleFire(self):
        messenger.send('inventory-fire')

    def __handleSOS(self):
        messenger.send('inventory-sos')

    def __handlePass(self):
        messenger.send('inventory-pass')

    def __handleBackToPlayground(self):
        messenger.send('inventory-back-to-playground')

    def showDetail(self, track, level, event = None):
        if self.activateMode == 'book':
            return
        self.totalLabel.hide()
        self.detailNameLabel.show()
        self.detailNameLabel.configure(text=AvPropStrings[track][level], image_image=self.invModels[track][level])
        self.detailNameLabel.configure(image_scale=20, image_pos=(-0.2, 0, -2.2))
        self.detailAmountLabel.show()
        self.detailAmountLabel.configure(text=TTLocalizer.InventoryDetailAmount % {'numItems': self.numItem(track, level),
         'maxItems': self.getMax(track, level)})
        self.detailDataLabel.show()
        damage = getAvPropDamage(track, level, self.toon.experience.getExp(track))
        organicBonus = self.toon.checkGagBonus(track, level)
        propBonus = self.checkPropBonus(track)
        damageBonusStr = ''
        damageBonus = 0
        if self.propAndOrganicBonusStack:
            if propBonus:
                damageBonus += getDamageBonus(damage)
            if organicBonus:
                damageBonus += getDamageBonus(damage)
            if damageBonus:
                damageBonusStr = TTLocalizer.InventoryDamageBonus % damageBonus
        else:
            if propBonus or organicBonus:
                damageBonus += getDamageBonus(damage)
            if damageBonus:
                damageBonusStr = TTLocalizer.InventoryDamageBonus % damageBonus
        accString = AvTrackAccStrings[track]
        if (organicBonus or propBonus) and track == LURE_TRACK:
            accString = TTLocalizer.BattleGlobalLureAccMedium
        self.detailDataLabel.configure(text=TTLocalizer.InventoryDetailData % {'accuracy': accString,
         'damageString': self.getToonupDmgStr(track, level),
         'damage': damage,
         'bonus': damageBonusStr,
         'singleOrGroup': self.getSingleGroupStr(track, level)})
        if self.itemIsCredit(track, level):
            mult = self.__battleCreditMultiplier
            if self.__respectInvasions:
                mult *= self.__invasionCreditMultiplier
            self.setDetailCredit(track, (level + 1) * mult * getGagXpBoost())
        else:
            self.setDetailCredit(track, None)
        self.detailCreditLabel.show()
        return

    def setDetailCredit(self, track, credit):
        if credit != None:
            if self.toon.earnedExperience:
                maxCredit = getExperienceCap() - self.toon.earnedExperience[track]
                credit = min(credit, maxCredit)
            credit = int(credit * 10 + 0.5)
            if credit % 10 == 0:
                credit //= 10
            else:
                credit //= 10.0
        if self.detailCredit == credit:
            return
        if credit != None:
            self.detailCreditLabel['text'] = TTLocalizer.InventorySkillCredit % credit
            if self.detailCredit == None:
                self.detailCreditLabel['text_fg'] = (1, 1, 1, 1)
        else:
            self.detailCreditLabel['text'] = TTLocalizer.InventorySkillCreditNone
            self.detailCreditLabel['text_fg'] = (0.5, 0.0, 0.0, 1.0)
        self.detailCredit = credit
        return

    def hideDetail(self, event = None):
        self.totalLabel.show()
        self.detailNameLabel.hide()
        self.detailAmountLabel.hide()
        self.detailDataLabel.hide()
        self.detailCreditLabel.hide()

    def noDetail(self):
        self.totalLabel.hide()
        self.detailNameLabel.hide()
        self.detailAmountLabel.hide()
        self.detailDataLabel.hide()
        self.detailCreditLabel.hide()

    def setActivateMode(self, mode, heal = 1, trap = 1, lure = 1, bldg = 0, creditLevel = None, tutorialFlag = 0, gagTutMode = 0):
        self.notify.debug('setActivateMode() mode:%s heal:%s trap:%s lure:%s bldg:%s' % (mode,
         heal,
         trap,
         lure,
         bldg))
        self.previousActivateMode = self.activateMode
        self.activateMode = mode
        self.detailFrame.show()
        self.detailDataLabel['text_scale'] = 1
        self.detailDataLabel['text_pos'] = (0, 0)
        self.detailDataLabel['text_wordwrap'] = None
        self._resetTrackRig()
        self.deactivateButtons()
        self.heal = heal
        self.trap = trap
        self.lure = lure
        self.bldg = bldg
        self.battleCreditLevel = creditLevel
        self.tutorialFlag = tutorialFlag
        self.gagTutMode = gagTutMode
        self.__activateButtons()
        self.enableUberGags()
        return None

    def setActivateModeBroke(self):
        if self.activateMode == 'storePurchase':
            self.setActivateMode('storePurchaseBroke')
        elif self.activateMode == 'purchase':
            self.setActivateMode('purchaseBroke', gagTutMode=self.gagTutMode)
        else:
            self.notify.error('Unexpected mode in setActivateModeBroke(): %s' % self.activateMode)
        self.enableUberGags()

    def deactivateButtons(self):
        if self.previousActivateMode == 'book':
            self.bookDeactivateButtons()
        elif self.previousActivateMode == 'bookDelete':
            self.bookDeleteDeactivateButtons()
        elif self.previousActivateMode == 'purchaseDelete':
            self.purchaseDeleteDeactivateButtons()
        elif self.previousActivateMode == 'purchase':
            self.purchaseDeactivateButtons()
        elif self.previousActivateMode == 'purchaseBroke':
            self.purchaseBrokeDeactivateButtons()
        elif self.previousActivateMode == 'gagTutDisabled':
            self.gagTutDisabledDeactivateButtons()
        elif self.previousActivateMode == 'battle':
            self.battleDeactivateButtons()
        elif self.previousActivateMode == 'storePurchaseDelete':
            self.storePurchaseDeleteDeactivateButtons()
        elif self.previousActivateMode == 'storePurchase':
            self.storePurchaseDeactivateButtons()
        elif self.previousActivateMode == 'storePurchaseBroke':
            self.storePurchaseBrokeDeactivateButtons()
        elif self.previousActivateMode == 'plantTree':
            self.plantTreeDeactivateButtons()
        else:
            self.notify.error('No such mode as %s' % self.previousActivateMode)
        return None

    def __activateButtons(self):
        if getattr(self, '_tutorialBoard', False):
            self.layoutTutorialBoard()
            return
        if hasattr(self, 'activateMode'):
            if self.activateMode == 'book':
                self.bookActivateButtons()
            elif self.activateMode == 'bookDelete':
                self.bookDeleteActivateButtons()
            elif self.activateMode == 'purchaseDelete':
                self.purchaseDeleteActivateButtons()
            elif self.activateMode == 'purchase':
                self.purchaseActivateButtons()
            elif self.activateMode == 'purchaseBroke':
                self.purchaseBrokeActivateButtons()
            elif self.activateMode == 'gagTutDisabled':
                self.gagTutDisabledActivateButtons()
            elif self.activateMode == 'battle':
                self.battleActivateButtons()
            elif self.activateMode == 'storePurchaseDelete':
                self.storePurchaseDeleteActivateButtons()
            elif self.activateMode == 'storePurchase':
                self.storePurchaseActivateButtons()
            elif self.activateMode == 'storePurchaseBroke':
                self.storePurchaseBrokeActivateButtons()
            elif self.activateMode == 'plantTree':
                self.plantTreeActivateButtons()
            else:
                self.notify.error('No such mode as %s' % self.activateMode)
            if self.activateMode.startswith(('purchase', 'storePurchase')) or self.activateMode == 'gagTutDisabled':
                self._fitShopTrackRig()
        return None

    def bookActivateButtons(self):
        if getattr(self, '_tutorialBoard', False):
            self.layoutTutorialBoard()
            return
        self.setPos(0, 0, 0.52)
        self.setScale(1.0)
        self.detailFrame.setPos(0.1, 0, -0.98)
        self.detailFrame.setScale(0.75)
        self.deleteEnterButton.hide()
        self.deleteEnterButton.setPos(1.029, 0, -0.639)
        self.deleteEnterButton.setScale(0.75)
        self.deleteExitButton.hide()
        self.deleteExitButton.setPos(1.029, 0, -0.639)
        self.deleteExitButton.setScale(0.75)
        self.invFrame.reparentTo(self)
        self.invFrame.setPos(0, 0, 0)
        self.invFrame.setScale(1)
        self._fitTrackRig()
        self.deleteEnterButton['command'] = None
        for track in range(len(Tracks)):
            if self.toon.hasTrackAccess(track):
                self.showTrack(track)
                for level in range(len(Levels[track])):
                    button = self.buttons[track][level]
                    if self.itemIsUsable(track, level):
                        button.show()
                        self.makeBookUnpressable(button, track, level)
                    else:
                        button.hide()

            else:
                self.hideTrack(track)

        return None

    def bookDeactivateButtons(self):
        self.deleteEnterButton['command'] = None
        return

    def bookDeleteActivateButtons(self):
        messenger.send('enterBookDelete')
        self.setPos(-0.2, 0, 0.4)
        self.setScale(0.8)
        self.deleteEnterButton.hide()
        self.deleteEnterButton.setPos(1.029, 0, -0.639)
        self.deleteEnterButton.setScale(0.75)
        self.deleteExitButton.show()
        self.deleteExitButton.setPos(1.029, 0, -0.639)
        self.deleteExitButton.setScale(0.75)
        self.deleteHelpText.show()
        self.invFrame.reparentTo(self)
        self.invFrame.setPos(0, 0, 0)
        self.invFrame.setScale(1)
        self.deleteExitButton['command'] = self.setActivateMode
        self.deleteExitButton['extraArgs'] = [self.previousActivateMode]
        for track in range(len(Tracks)):
            if self.toon.hasTrackAccess(track):
                self.showTrack(track)
                for level in range(len(Levels[track])):
                    button = self.buttons[track][level]
                    if self.itemIsUsable(track, level):
                        button.show()
                        if self.numItem(track, level) <= 0:
                            self.makeUnpressable(button, track, level)
                        else:
                            self.makeDeletePressable(button, track, level)
                    else:
                        button.hide()

            else:
                self.hideTrack(track)

    def bookDeleteDeactivateButtons(self):
        messenger.send('exitBookDelete')
        self.deleteHelpText.hide()
        self.deleteDeactivateButtons()

    def purchaseDeleteActivateButtons(self):
        self.reparentTo(aspect2d)
        self.setPos(0.2, 0, -0.04)
        self.setScale(1)
        if self.purchaseFrame == None:
            self.loadPurchaseFrame()
        self.purchaseFrame.show()
        self.invFrame.reparentTo(self.purchaseFrame)
        self.invFrame.setPos(-0.235, 0, 0.52)
        self.invFrame.setScale(0.81)
        self.detailFrame.setPos(1.17, 0, -0.02)
        self.detailFrame.setScale(1.25)
        self.deleteEnterButton.hide()
        self.deleteEnterButton.setPos(-0.441, 0, -0.917)
        self.deleteEnterButton.setScale(0.75)
        self.deleteExitButton.show()
        self.deleteExitButton.setPos(-0.441, 0, -0.917)
        self.deleteExitButton.setScale(0.75)
        self.deleteExitButton['command'] = self.setActivateMode
        self.deleteExitButton['extraArgs'] = [self.previousActivateMode]
        for track in range(len(Tracks)):
            if self.toon.hasTrackAccess(track):
                self.showTrack(track)
                for level in range(len(Levels[track])):
                    button = self.buttons[track][level]
                    if self.itemIsUsable(track, level):
                        button.show()
                        if self.numItem(track, level) <= 0 or level >= UBER_GAG_LEVEL_INDEX:
                            self.makeUnpressable(button, track, level)
                        else:
                            self.makeDeletePressable(button, track, level)
                    else:
                        button.hide()

            else:
                self.hideTrack(track)

        return

    def purchaseDeleteDeactivateButtons(self):
        self.invFrame.reparentTo(self)
        self.purchaseFrame.hide()
        self.deleteDeactivateButtons()
        for track in range(len(Tracks)):
            if self.toon.hasTrackAccess(track):
                self.showTrack(track)
                for level in range(len(Levels[track])):
                    button = self.buttons[track][level]
                    if self.itemIsUsable(track, level):
                        button.show()
                        if self.numItem(track, level) <= 0 or level >= UBER_GAG_LEVEL_INDEX:
                            self.makeUnpressable(button, track, level)
                        else:
                            self.makeDeletePressable(button, track, level)
                    else:
                        button.hide()

            else:
                self.hideTrack(track)

    def storePurchaseDeleteActivateButtons(self):
        self.reparentTo(aspect2d)
        self.setPos(0.2, 0, -0.04)
        self.setScale(1)
        if self.storePurchaseFrame == None:
            self.loadStorePurchaseFrame()
        self.storePurchaseFrame.show()
        self.invFrame.reparentTo(self.storePurchaseFrame)
        self.invFrame.setPos(-0.23, 0, 0.505)
        self.invFrame.setScale(0.81)
        self.detailFrame.setPos(1.175, 0, 0)
        self.detailFrame.setScale(1.25)
        self.deleteEnterButton.hide()
        self.deleteEnterButton.setPos(-0.55, 0, -0.91)
        self.deleteEnterButton.setScale(0.75)
        self.deleteExitButton.show()
        self.deleteExitButton.setPos(-0.55, 0, -0.91)
        self.deleteExitButton.setScale(0.75)
        self.deleteExitButton['command'] = self.setActivateMode
        self.deleteExitButton['extraArgs'] = [self.previousActivateMode]
        for track in range(len(Tracks)):
            if self.toon.hasTrackAccess(track):
                self.showTrack(track)
                for level in range(len(Levels[track])):
                    button = self.buttons[track][level]
                    if self.itemIsUsable(track, level):
                        button.show()
                        if self.numItem(track, level) <= 0 or level >= UBER_GAG_LEVEL_INDEX:
                            self.makeUnpressable(button, track, level)
                        else:
                            self.makeDeletePressable(button, track, level)
                    else:
                        button.hide()

            else:
                self.hideTrack(track)

        return

    def storePurchaseDeleteDeactivateButtons(self):
        self.invFrame.reparentTo(self)
        self.storePurchaseFrame.hide()
        self.deleteDeactivateButtons()

    def storePurchaseBrokeActivateButtons(self):
        self.reparentTo(aspect2d)
        self.setPos(0.2, 0, -0.04)
        self.setScale(1)
        if self.storePurchaseFrame == None:
            self.loadStorePurchaseFrame()
        self.storePurchaseFrame.show()
        self.invFrame.reparentTo(self.storePurchaseFrame)
        self.invFrame.setPos(-0.23, 0, 0.505)
        self.invFrame.setScale(0.81)
        self.detailFrame.setPos(1.175, 0, 0)
        self.detailFrame.setScale(1.25)
        self.deleteEnterButton.show()
        self.deleteEnterButton.setPos(-0.55, 0, -0.91)
        self.deleteEnterButton.setScale(0.75)
        self.deleteExitButton.hide()
        self.deleteExitButton.setPos(-0.551, 0, -0.91)
        self.deleteExitButton.setScale(0.75)
        for track in range(len(Tracks)):
            if self.toon.hasTrackAccess(track):
                self.showTrack(track)
                for level in range(len(Levels[track])):
                    button = self.buttons[track][level]
                    if self.itemIsUsable(track, level):
                        button.show()
                        self.makeUnpressable(button, track, level)
                    else:
                        button.hide()

            else:
                self.hideTrack(track)

        return

    def storePurchaseBrokeDeactivateButtons(self):
        self.invFrame.reparentTo(self)
        self.storePurchaseFrame.hide()

    def deleteActivateButtons(self):
        self.reparentTo(aspect2d)
        self.setPos(0, 0, 0)
        self.setScale(1)
        self.deleteEnterButton.hide()
        self.deleteExitButton.show()
        self.deleteExitButton['command'] = self.setActivateMode
        self.deleteExitButton['extraArgs'] = [self.previousActivateMode]
        for track in range(len(Tracks)):
            if self.toon.hasTrackAccess(track):
                self.showTrack(track)
                for level in range(len(Levels[track])):
                    button = self.buttons[track][level]
                    if self.itemIsUsable(track, level):
                        button.show()
                        if self.numItem(track, level) <= 0:
                            self.makeUnpressable(button, track, level)
                        else:
                            self.makePressable(button, track, level)
                    else:
                        button.hide()

            else:
                self.hideTrack(track)

        return None

    def deleteDeactivateButtons(self):
        self.deleteExitButton['command'] = None
        return

    def purchaseActivateButtons(self):
        self.reparentTo(aspect2d)
        self.setPos(0.2, 0, -0.04)
        self.setScale(1)
        if self.purchaseFrame == None:
            self.loadPurchaseFrame()
        self.purchaseFrame.show()
        self.invFrame.reparentTo(self.purchaseFrame)
        self.invFrame.setPos(-0.235, 0, 0.52)
        self.invFrame.setScale(0.81)
        self.detailFrame.setPos(1.17, 0, -0.02)
        self.detailFrame.setScale(1.25)
        totalProps = self.totalProps
        maxProps = self.toon.getMaxCarry()
        self.deleteEnterButton.show()
        self.deleteEnterButton.setPos(-0.441, 0, -0.917)
        self.deleteEnterButton.setScale(0.75)
        self.deleteExitButton.hide()
        self.deleteExitButton.setPos(-0.441, 0, -0.917)
        self.deleteExitButton.setScale(0.75)
        if self.gagTutMode:
            self.deleteEnterButton.hide()
        self.deleteEnterButton['command'] = self.setActivateMode
        self.deleteEnterButton['extraArgs'] = ['purchaseDelete']
        for track in range(len(Tracks)):
            if self.toon.hasTrackAccess(track):
                self.showTrack(track)
                for level in range(len(Levels[track])):
                    button = self.buttons[track][level]
                    if self.itemIsUsable(track, level):
                        button.show()
                        unpaid = not base.cr.isPaid()
                        if self.numItem(track, level) >= self.getMax(track, level) or totalProps == maxProps or unpaid and gagIsPaidOnly(track, level) or level > LAST_REGULAR_GAG_LEVEL:
                            if gagIsPaidOnly(track, level):
                                self.makeDisabledPressable(button, track, level)
                            elif unpaid and gagIsVelvetRoped(track, level):
                                self.makeDisabledPressable(button, track, level)
                            else:
                                self.makeUnpressable(button, track, level)
                        elif unpaid and gagIsVelvetRoped(track, level):
                            self.makeDisabledPressable(button, track, level)
                        else:
                            self.makePressable(button, track, level)
                    else:
                        button.hide()

            else:
                self.hideTrack(track)

        return

    def purchaseDeactivateButtons(self):
        self.invFrame.reparentTo(self)
        self.purchaseFrame.hide()

    def storePurchaseActivateButtons(self):
        self.reparentTo(aspect2d)
        self.setPos(0.2, 0, -0.04)
        self.setScale(1)
        if self.storePurchaseFrame == None:
            self.loadStorePurchaseFrame()
        self.storePurchaseFrame.show()
        self.invFrame.reparentTo(self.storePurchaseFrame)
        self.invFrame.setPos(-0.23, 0, 0.505)
        self.invFrame.setScale(0.81)
        self.detailFrame.setPos(1.175, 0, 0)
        self.detailFrame.setScale(1.25)
        totalProps = self.totalProps
        maxProps = self.toon.getMaxCarry()
        self.deleteEnterButton.show()
        self.deleteEnterButton.setPos(-0.55, 0, -0.91)
        self.deleteEnterButton.setScale(0.75)
        self.deleteExitButton.hide()
        self.deleteExitButton.setPos(-0.55, 0, -0.91)
        self.deleteExitButton.setScale(0.75)
        self.deleteEnterButton['command'] = self.setActivateMode
        self.deleteEnterButton['extraArgs'] = ['storePurchaseDelete']
        for track in range(len(Tracks)):
            if self.toon.hasTrackAccess(track):
                self.showTrack(track)
                for level in range(len(Levels[track])):
                    button = self.buttons[track][level]
                    if self.itemIsUsable(track, level):
                        button.show()
                        unpaid = not base.cr.isPaid()
                        if self.numItem(track, level) >= self.getMax(track, level) or totalProps == maxProps or unpaid and gagIsPaidOnly(track, level) or level > LAST_REGULAR_GAG_LEVEL:
                            if gagIsPaidOnly(track, level):
                                self.makeDisabledPressable(button, track, level)
                            elif unpaid and gagIsVelvetRoped(track, level):
                                self.makeDisabledPressable(button, track, level)
                            else:
                                self.makeUnpressable(button, track, level)
                        elif unpaid and gagIsVelvetRoped(track, level):
                            self.makeDisabledPressable(button, track, level)
                        else:
                            self.makePressable(button, track, level)
                    else:
                        button.hide()

            else:
                self.hideTrack(track)

        return

    def storePurchaseDeactivateButtons(self):
        self.invFrame.reparentTo(self)
        self.storePurchaseFrame.hide()

    def purchaseBrokeActivateButtons(self):
        self.reparentTo(aspect2d)
        self.setPos(0.2, 0, -0.04)
        self.setScale(1)
        if self.purchaseFrame == None:
            self.loadPurchaseFrame()
        self.purchaseFrame.show()
        self.invFrame.reparentTo(self.purchaseFrame)
        self.invFrame.setPos(-0.235, 0, 0.52)
        self.invFrame.setScale(0.81)
        self.detailFrame.setPos(1.17, 0, -0.02)
        self.detailFrame.setScale(1.25)
        self.deleteEnterButton.show()
        self.deleteEnterButton.setPos(-0.441, 0, -0.917)
        self.deleteEnterButton.setScale(0.75)
        self.deleteExitButton.hide()
        self.deleteExitButton.setPos(-0.441, 0, -0.917)
        self.deleteExitButton.setScale(0.75)
        if self.gagTutMode:
            self.deleteEnterButton.hide()
        for track in range(len(Tracks)):
            if self.toon.hasTrackAccess(track):
                self.showTrack(track)
                for level in range(len(Levels[track])):
                    button = self.buttons[track][level]
                    if self.itemIsUsable(track, level):
                        button.show()
                        self.makeUnpressable(button, track, level)
                    else:
                        button.hide()

            else:
                self.hideTrack(track)

        return

    def purchaseBrokeDeactivateButtons(self):
        self.invFrame.reparentTo(self)
        self.purchaseFrame.hide()

    def gagTutDisabledActivateButtons(self):
        self.reparentTo(aspect2d)
        self.setPos(0.2, 0, -0.04)
        self.setScale(1)
        if self.purchaseFrame == None:
            self.loadPurchaseFrame()
        self.purchaseFrame.show()
        self.invFrame.reparentTo(self.purchaseFrame)
        self.invFrame.setPos(-0.235, 0, 0.52)
        self.invFrame.setScale(0.81)
        self.detailFrame.setPos(1.17, 0, -0.02)
        self.detailFrame.setScale(1.25)
        self.deleteEnterButton.show()
        self.deleteEnterButton.setPos(-0.441, 0, -0.917)
        self.deleteEnterButton.setScale(0.75)
        self.deleteExitButton.hide()
        self.deleteExitButton.setPos(-0.441, 0, -0.917)
        self.deleteExitButton.setScale(0.75)
        self.deleteEnterButton.hide()
        for track in range(len(Tracks)):
            if self.toon.hasTrackAccess(track):
                self.showTrack(track)
                for level in range(len(Levels[track])):
                    button = self.buttons[track][level]
                    if self.itemIsUsable(track, level):
                        button.show()
                        self.makeUnpressable(button, track, level)
                    else:
                        button.hide()

            else:
                self.hideTrack(track)

        return

    def gagTutDisabledDeactivateButtons(self):
        self.invFrame.reparentTo(self)
        self.purchaseFrame.hide()

    def battleActivateButtons(self):
        self.stopAndClearPropBonusIval()
        self.reparentTo(aspect2d)
        self.setPos(0, 0, 0.1)
        self.setScale(1)
        if self.battleFrame == None:
            self.loadBattleFrame()
        self.battleFrame.show()
        self.battleFrame.setScale(0.9)
        self.invFrame.reparentTo(self.battleFrame)
        self.invFrame.setPos(-0.26, 0, 0.35)
        self.invFrame.setScale(1)
        self.detailFrame.setPos(1.125, 0, -0.08)
        self.detailFrame.setScale(1)
        self.deleteEnterButton.hide()
        self.deleteExitButton.hide()
        if self.bldg == 1:
            self.runButton.hide()
            self.sosButton.show()
            self.passButton.show()
        elif self.tutorialFlag == 1:
            self.runButton.hide()
            self.sosButton.hide()
            self.passButton.hide()
            self.fireButton.hide()
        else:
            self.runButton.show()
            self.sosButton.show()
            self.passButton.show()
            self.fireButton.show()
            if localAvatar.getPinkSlips() > 0:
                self.fireButton['state'] = DGG.NORMAL
                self.fireButton['frameColor'] = (Vec4(0.55, 0.28, 0.26, 1), Vec4(0.95, 0.78, 0.28, 1), Vec4(0.72, 0.36, 0.32, 1), Vec4(0.30, 0.32, 0.36, 1))
                self.fireButton['image_color'] = Vec4(0.55, 0.28, 0.26, 1)
            else:
                self.fireButton['state'] = DGG.DISABLED
                self.fireButton['frameColor'] = Vec4(0.30, 0.32, 0.36, 1)
                self.fireButton['image_color'] = Vec4(0.30, 0.32, 0.36, 1)
        for track in range(len(Tracks)):
            if self.toon.hasTrackAccess(track):
                self.showTrack(track)
                for level in range(len(Levels[track])):
                    button = self.buttons[track][level]
                    if self.itemIsUsable(track, level):
                        unpaid = not base.cr.isPaid()
                        button.show()
                        if self.numItem(track, level) <= 0 or track == HEAL_TRACK and not self.heal or track == TRAP_TRACK and not self.trap or track == LURE_TRACK and not self.lure:
                            self.makeUnpressable(button, track, level)
                        elif unpaid and gagIsVelvetRoped(track, level):
                            self.makeDisabledPressable(button, track, level)
                        elif self.itemIsCredit(track, level):
                            self.makePressable(button, track, level)
                        else:
                            self.makeNoncreditPressable(button, track, level)
                    else:
                        button.hide()

            else:
                self.hideTrack(track)

        self.propBonusIval.loop()
        # The redesigned battle screen owns this moment. Reparenting onto
        # aspect2d would put the red/yellow menu back; stash it again.
        try:
            from toontown.town.TownBattleAttackPanel import AttackPanelHidden
            if AttackPanelHidden:
                self.battleFrame.hide()
                self.hide()
                self.stash()
        except Exception:
            pass
        return

    def battleDeactivateButtons(self):
        self.invFrame.reparentTo(self)
        self.battleFrame.hide()
        self.stopAndClearPropBonusIval()

    def plantTreeActivateButtons(self):
        self.reparentTo(aspect2d)
        self.setPos(0, 0, 0.1)
        self.setScale(1)
        if self.battleFrame == None:
            self.loadBattleFrame()
        self.battleFrame.show()
        self.battleFrame.setScale(0.9)
        self.invFrame.reparentTo(self.battleFrame)
        self.invFrame.setPos(-0.25, 0, 0.35)
        self.invFrame.setScale(1)
        self.detailFrame.setPos(1.125, 0, -0.08)
        self.detailFrame.setScale(1)
        self.deleteEnterButton.hide()
        self.deleteExitButton.hide()
        self.runButton.hide()
        self.sosButton.hide()
        self.fireButton.hide()             # (the battle's Fire button: planting is done by pressing a gag)
        self.passButton['text'] = TTLocalizer.lCancel
        self.passButton.show()
        for track in range(len(Tracks)):
            if self.toon.hasTrackAccess(track):
                self.showTrack(track)
                for level in range(len(Levels[track])):
                    button = self.buttons[track][level]
                    if self.itemIsUsable(track, level) and (level == 0 or self.toon.doIHaveRequiredTrees(track, level)):
                        button.show()
                        self.makeUnpressable(button, track, level)
                        if self.numItem(track, level) > 0:
                            if not self.toon.isTreePlanted(track, level):
                                self.makePressable(button, track, level)
                    else:
                        button.hide()

            else:
                self.hideTrack(track)

        return

    def plantTreeDeactivateButtons(self):
        self.passButton['text'] = TTLocalizer.InventoryPass
        self.invFrame.reparentTo(self)
        self.battleFrame.hide()

    def itemIsUsable(self, track, level):
        curSkill = self.toon.experience.getExp(track)
        if curSkill < Levels[track][level]:
            return 0
        else:
            return 1

    def itemIsCredit(self, track, level):
        if self.toon.earnedExperience:
            if self.toon.earnedExperience[track] >= getExperienceCap():
                return 0
        if self.battleCreditLevel == None:
            return 1
        else:
            return level < self.battleCreditLevel
        return

    def getCurAndNextExpValues(self, track):
        curSkill = self.toon.experience.getExp(track)
        retVal = MaxSkill
        for amount in Levels[track]:
            if curSkill < amount:
                retVal = amount
                return (curSkill, retVal)

        return (curSkill, retVal)

    def _resetTrackRig(self):
        rig = getattr(self, 'trackRig', None)
        if rig is None:
            return
        rig.setPos(0, 0, 0)
        rig.setScale(1)

    def _fitShopTrackRig(self):
        shop_parent = getattr(self, 'shopParent', None)
        if shop_parent is not None:
            self.reparentTo(shop_parent)
        if self._compactGrid:
            # Use spare height above the rows without covering the jar, exit
            # or trash controls beside and below the grid.
            self.trackRig.setScale(0.74, 1, 0.86)
            self.trackRig.setZ(-0.085)
        else:
            self.trackRig.setScale(0.74)
            self.trackRig.setZ(-0.18)

    def showShopPreview(self, levelCount):
        for track in range(len(Tracks)):
            if not self.toon.hasTrackAccess(track):
                continue
            for level, button in enumerate(self.buttons[track]):
                if level < levelCount:
                    self.makeBookUnpressable(button, track, level)
                    button.show()
                else:
                    button.hide()

    def _fitTrackRig(self):
        """Place the colored rows inside the book, under the Gags title."""
        rig = getattr(self, 'trackRig', None)
        if rig is None:
            return
        # Outer edge of the gag panel. Side margin matches the top and bottom.
        left, right = -0.982, 0.982
        top, bottom = 0.145, -0.865
        # A bit taller, still under the title and above the jar and the cards.
        target_left, target_right = -0.78, 0.78
        target_top, target_bottom = 0.50, -0.26
        height = top - bottom
        scale = (target_right - target_left) / (right - left)
        if height * scale > (target_top - target_bottom):
            scale = (target_top - target_bottom) / height
        center_x = (left + right) * 0.5
        center_z = (top + bottom) * 0.5
        rig_x = ((target_left + target_right) * 0.5) - center_x * scale
        rig_z = ((target_top + target_bottom) * 0.5) - 0.52 - center_z * scale
        rig.setPos(rig_x, 0, rig_z)
        rig.setScale(scale)

    def _addGagOutline(self, button):
        """Hairline outline. Hidden with the button, so locked slots draw nothing."""
        # Wraps the icon and the quantity, and stays inside the track row (±0.0569).
        color = (0.93, 0.94, 0.96, 1)
        t = 0.0032
        left, right, bottom, top = -0.062, 0.080, -0.046, 0.050
        edges = (
            (left - t, right + t, top, top + t),
            (left - t, right + t, bottom - t, bottom),
            (left - t, left, bottom, top),
            (right, right + t, bottom, top),
        )
        for frame in edges:
            DirectFrame(parent=button, relief=DGG.FLAT, state=DGG.DISABLED, frameColor=color, frameSize=frame, pos=(0, 0, 0))

    def _paintSlot(self, button, kind):
        """Draw the gag as a thin slot. Keeps the icon, quantity, and click rules."""
        idle = Vec4(0.55, 0.62, 0.70, 1)
        hover = Vec4(0.82, 0.86, 0.90, 1)
        press = Vec4(0.95, 0.78, 0.28, 1)
        dim = Vec4(0.30, 0.32, 0.36, 0.9)
        bonus = self.PropBonusPressableImageColor
        bonusDim = self.PropBonusNoncreditPressableImageColor
        styles = {
            'pressable': (idle, press, hover, dim),
            'bonus': (bonus, press, hover, bonusDim),
            'noncredit': (self.NoncreditPressableImageColor, press, hover, dim),
            'bonus-noncredit': (bonusDim, press, hover, dim),
            'delete': (self.DeletePressableImageColor, press, hover, dim),
            'unpressable': (dim, dim, dim, dim),
            'book': (idle, idle, hover, idle),
            'book-bonus': (bonus, bonus, hover, bonus),
        }
        # Grey you can see the track color through. Smaller than the row, so it stays inside.
        grey = Vec4(0.45, 0.48, 0.52, 0.62)
        button.configure(relief=DGG.FLAT, frameSize=(-0.062, 0.080, -0.046, 0.050), frameColor=(grey, grey, grey, grey), image_scale=0.001, image_color=(1, 1, 1, 0))

    def makePressable(self, button, track, level):
        organicBonus = self.toon.checkGagBonus(track, level)
        propBonus = self.checkPropBonus(track)
        bonus = organicBonus or propBonus
        if bonus:
            shadowColor = self.ShadowBuffedColor
        else:
            shadowColor = self.ShadowColor
        button.configure(image0_image=self.upButton, image2_image=self.rolloverButton, text_shadow=shadowColor, geom_color=self.PressableGeomColor, commandButtons=(DGG.LMB,))
        if self._interactivePropTrackBonus == track:
            self._paintSlot(button, 'bonus')
            self.addToPropBonusIval(button)
        else:
            self._paintSlot(button, 'pressable')

    def makeDisabledPressable(self, button, track, level):
        organicBonus = self.toon.checkGagBonus(track, level)
        propBonus = self.checkPropBonus(track)
        bonus = organicBonus or propBonus
        if bonus:
            shadowColor = self.UnpressableShadowBuffedColor
        else:
            shadowColor = self.ShadowColor
        button.configure(text_shadow=shadowColor, geom_color=self.UnpressableGeomColor, image_image=self.flatButton, commandButtons=(DGG.LMB,))
        self._paintSlot(button, 'unpressable')

    def makeNoncreditPressable(self, button, track, level):
        organicBonus = self.toon.checkGagBonus(track, level)
        propBonus = self.checkPropBonus(track)
        bonus = organicBonus or propBonus
        if bonus:
            shadowColor = self.ShadowBuffedColor
        else:
            shadowColor = self.ShadowColor
        button.configure(image0_image=self.upButton, image2_image=self.rolloverButton, text_shadow=shadowColor, geom_color=self.PressableGeomColor, commandButtons=(DGG.LMB,))
        if self._interactivePropTrackBonus == track:
            self._paintSlot(button, 'bonus-noncredit')
            self.addToPropBonusIval(button)
        else:
            self._paintSlot(button, 'noncredit')

    def makeDeletePressable(self, button, track, level):
        organicBonus = self.toon.checkGagBonus(track, level)
        propBonus = self.checkPropBonus(track)
        bonus = organicBonus or propBonus
        if bonus:
            shadowColor = self.ShadowBuffedColor
        else:
            shadowColor = self.ShadowColor
        button.configure(image0_image=self.upButton, image2_image=self.rolloverButton, text_shadow=shadowColor, geom_color=self.PressableGeomColor, commandButtons=(DGG.LMB,))
        self._paintSlot(button, 'delete')

    def makeUnpressable(self, button, track, level):
        organicBonus = self.toon.checkGagBonus(track, level)
        propBonus = self.checkPropBonus(track)
        bonus = organicBonus or propBonus
        if bonus:
            shadowColor = self.UnpressableShadowBuffedColor
        else:
            shadowColor = self.ShadowColor
        color = Vec4(0.62, 0.62, 0.62, 1) if self.activateMode.startswith(('purchase', 'storePurchase')) else self.UnpressableGeomColor
        button.configure(text_shadow=shadowColor, geom_color=color, image_image=self.flatButton, commandButtons=())
        self._paintSlot(button, 'unpressable')

    def makeBookUnpressable(self, button, track, level):
        organicBonus = self.toon.checkGagBonus(track, level)
        propBonus = self.checkPropBonus(track)
        bonus = organicBonus or propBonus
        if bonus:
            shadowColor = self.ShadowBuffedColor
        else:
            shadowColor = self.ShadowColor
        button.configure(text_shadow=shadowColor, geom_color=self.BookUnpressableGeomColor, image_image=self.flatButton, commandButtons=())
        if self._interactivePropTrackBonus == track:
            self._paintSlot(button, 'book-bonus')
        else:
            self._paintSlot(button, 'book')

    def hideTrack(self, trackIndex):
        self.trackNameLabels[trackIndex].show()
        self.trackBars[trackIndex].hide()
        if trackIndex < len(getattr(self, 'trackLockedLabels', ())):
            self.trackLockedLabels[trackIndex].show()
        for levelIndex in range(0, len(Levels[trackIndex])):
            self.buttons[trackIndex][levelIndex].hide()

    def showTrack(self, trackIndex):
        self.trackNameLabels[trackIndex].show()
        self.trackBars[trackIndex].show()
        if trackIndex < len(getattr(self, 'trackLockedLabels', ())):
            self.trackLockedLabels[trackIndex].hide()
        for levelIndex in range(0, len(Levels[trackIndex])):
            self.buttons[trackIndex][levelIndex].show()

        curExp, nextExp = self.getCurAndNextExpValues(trackIndex)
        if curExp >= UnpaidMaxSkills[trackIndex] and self.toon.getGameAccess() != OTPGlobals.AccessFull:
            self.trackBars[trackIndex]['range'] = nextExp
            self.trackBars[trackIndex]['text'] = TTLocalizer.InventoryGuestExp
        elif curExp >= regMaxSkill:
            self.trackBars[trackIndex]['range'] = UberSkill
            self.trackBars[trackIndex]['text'] = TTLocalizer.InventoryUberTrackExp % {'nextExp': MaxSkill - curExp}
        else:
            self.trackBars[trackIndex]['range'] = nextExp
            self.trackBars[trackIndex]['text'] = TTLocalizer.InventoryTrackExp % {'curExp': curExp,
             'nextExp': nextExp}

    def updateInvString(self, invString):
        InventoryBase.InventoryBase.updateInvString(self, invString)
        self.updateGUI()
        return None

    def updateButton(self, track, level):
        button = self.buttons[track][level]
        button['text'] = str(self.numItem(track, level))
        organicBonus = self.toon.checkGagBonus(track, level)
        propBonus = self.checkPropBonus(track)
        bonus = organicBonus or propBonus
        if bonus:
            textScale = 0.05
        else:
            textScale = 0.04
        if self._compactGrid:
            textScale += 0.028
        button.configure(text_scale=textScale)

    def buttonBoing(self, track, level):
        button = self.buttons[track][level]
        oldScale = button.getScale()
        s = Sequence(button.scaleInterval(0.1, oldScale * 1.333, blendType='easeOut'), button.scaleInterval(0.1, oldScale, blendType='easeIn'), name='inventoryButtonBoing-' + str(self.this))
        s.start()

    def updateGUI(self, track = None, level = None):
        self.updateTotalPropsText()
        if track == None and level == None:
            for track in range(len(Tracks)):
                curExp, nextExp = self.getCurAndNextExpValues(track)
                if curExp >= UnpaidMaxSkills[track] and self.toon.getGameAccess() != OTPGlobals.AccessFull:
                    self.trackBars[track]['range'] = nextExp
                    self.trackBars[track]['text'] = TTLocalizer.InventoryGuestExp
                elif curExp >= regMaxSkill:
                    self.trackBars[track]['text'] = TTLocalizer.InventoryUberTrackExp % {'nextExp': MaxSkill - curExp}
                    self.trackBars[track]['value'] = curExp - regMaxSkill
                else:
                    self.trackBars[track]['text'] = TTLocalizer.InventoryTrackExp % {'curExp': curExp,
                     'nextExp': nextExp}
                    self.trackBars[track]['value'] = curExp
                for level in range(0, len(Levels[track])):
                    self.updateButton(track, level)

        elif track != None and level != None:
            self.updateButton(track, level)
        else:
            self.notify.error('Invalid use of updateGUI')
        self.__activateButtons()
        return

    def getSingleGroupStr(self, track, level):
        if track == HEAL_TRACK:
            if isGroup(track, level):
                return TTLocalizer.InventoryAffectsAllToons
            else:
                return TTLocalizer.InventoryAffectsOneToon
        elif isGroup(track, level):
            return TTLocalizer.InventoryAffectsAllCogs
        else:
            return TTLocalizer.InventoryAffectsOneCog

    def getToonupDmgStr(self, track, level):
        if track == HEAL_TRACK:
            return TTLocalizer.InventoryHealString
        else:
            return TTLocalizer.InventoryDamageString

    def deleteItem(self, track, level):
        if self.numItem(track, level) > 0:
            self.useItem(track, level)
            self.updateGUI(track, level)

    def loadBattleFrame(self):
        # Toontorial still uses this frame. Same buttons and arrows, battle-bar materials.
        self.battleFrame = DirectFrame(relief=None, parent=self)
        DirectFrame(parent=self.battleFrame, relief=DGG.FLAT, frameColor=(0.78, 0.82, 0.88, 1), frameSize=(-1.28, 1.42, -0.68, 0.58))
        DirectFrame(parent=self.battleFrame, relief=DGG.FLAT, frameColor=(0.17, 0.19, 0.23, 0.96), frameSize=(-1.25, 1.39, -0.65, 0.55))
        action = (Vec4(0.28, 0.40, 0.54, 1), Vec4(0.95, 0.78, 0.28, 1), Vec4(0.40, 0.55, 0.72, 1), Vec4(0.30, 0.32, 0.36, 1))
        self.runButton = DirectButton(parent=self.battleFrame, relief=DGG.FLAT, frameSize=(-0.11, 0.11, -0.045, 0.045), frameColor=action, pos=(0.73, 0, -0.398), text=TTLocalizer.InventoryRun, text_scale=TTLocalizer.INrunButton, text_pos=(0, -0.02), text_fg=Vec4(1, 1, 1, 1), textMayChange=0, command=self.__handleRun)
        self.sosButton = DirectButton(parent=self.battleFrame, relief=DGG.FLAT, frameSize=(-0.11, 0.11, -0.045, 0.045), frameColor=action, pos=(0.96, 0, -0.398), text=TTLocalizer.InventorySOS, text_scale=0.05, text_pos=(0, -0.02), text_fg=Vec4(1, 1, 1, 1), textMayChange=0, command=self.__handleSOS)
        self.passButton = DirectButton(parent=self.battleFrame, relief=DGG.FLAT, frameSize=(-0.11, 0.11, -0.045, 0.045), frameColor=action, pos=(0.96, 0, -0.242), text=TTLocalizer.InventoryPass, text_scale=TTLocalizer.INpassButton, text_pos=(0, -0.02), text_fg=Vec4(1, 1, 1, 1), textMayChange=1, command=self.__handlePass)
        self.fireButton = DirectButton(parent=self.battleFrame, relief=DGG.FLAT, frameSize=(-0.11, 0.11, -0.045, 0.045), frameColor=(Vec4(0.55, 0.28, 0.26, 1), Vec4(0.95, 0.78, 0.28, 1), Vec4(0.72, 0.36, 0.32, 1), Vec4(0.30, 0.32, 0.36, 1)), pos=(0.73, 0, -0.242), text=TTLocalizer.InventoryFire, text_scale=TTLocalizer.INfireButton, text_pos=(0, -0.02), text_fg=Vec4(1, 1, 1, 1), textMayChange=0, command=self.__handleFire)
        self.tutText = DirectFrame(parent=self.battleFrame, relief=None, pos=(0.05, 0, -0.1133), scale=0.143, image=DGG.getDefaultDialogGeom(), image_scale=5.125, image_pos=(0, 0, -0.65), image_color=(0.16, 0.18, 0.22, 1), text_fg=(1, 1, 1, 1), text_shadow=(0, 0, 0, 1), text_scale=TTLocalizer.INclickToAttack, text=TTLocalizer.InventoryClickToAttack, textMayChange=0)
        self.tutText.hide()
        self.tutArrows = BlinkingArrows.BlinkingArrows(parent=self.battleFrame)
        self.battleFrame.hide()
        return

    def loadPurchaseFrame(self):
        purchaseModels = loader.loadModel('phase_4/models/gui/purchase_gui')
        self.purchaseFrame = DirectFrame(relief=None, image=purchaseModels.find('**/PurchasePanel'), image_pos=(-0.21, 0, 0.08), parent=self)
        self.purchaseFrame.setX(-.06)
        self.purchaseFrame.hide()
        purchaseModels.removeNode()
        return

    def loadStorePurchaseFrame(self):
        storePurchaseModels = loader.loadModel('phase_4/models/gui/gag_shop_purchase_gui')
        self.storePurchaseFrame = DirectFrame(relief=None, image=storePurchaseModels.find('**/gagShopPanel'), image_pos=(-0.21, 0, 0.18), parent=self)
        self.storePurchaseFrame.hide()
        storePurchaseModels.removeNode()
        return

    def buttonLookup(self, track, level):
        return self.invModels[track][level]

    def enterTrackFrame(self, track, guiItem):
        messenger.send('enterTrackFrame', [track])

    def exitTrackFrame(self, track, guiItem):
        messenger.send('exitTrackFrame', [track])

    def checkPropBonus(self, track):
        result = False
        if track == self._interactivePropTrackBonus:
            result = True
        return result

    def stopAndClearPropBonusIval(self):
        if self.propBonusIval and self.propBonusIval.isPlaying():
            self.propBonusIval.finish()
        self.propBonusIval = Parallel(name='dummyPropBonusIval')

    def addToPropBonusIval(self, button):
        flashObject = button
        for part in ('frame', 'image0'):
            try:
                flashObject = button.component(part)
                break
            except Exception:
                pass

        goDark = LerpColorScaleInterval(flashObject, 0.5, Point4(0.1, 0.1, 0.1, 1.0), Point4(1, 1, 1, 1), blendType='easeIn')
        goBright = LerpColorScaleInterval(flashObject, 0.5, Point4(1, 1, 1, 1), Point4(0.1, 0.1, 0.1, 1.0), blendType='easeOut')
        newSeq = Sequence(goDark, goBright, Wait(0.2))
        self.propBonusIval.append(newSeq)

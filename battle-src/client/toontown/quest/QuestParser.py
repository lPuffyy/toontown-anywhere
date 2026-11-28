
# Level-0 3D prop shown in Tom's hand during the tutorial handout, per track.
# HEAL=0 TRAP=1 LURE=2 SOUND=3 THROW=4 SQUIRT=5 DROP=6
_TTA_TRACK_PROP_MODEL = {
    0: 'phase_5/models/props/feather-mod',
    1: 'phase_5/models/props/banana-peel-mod',
    2: 'phase_5/models/props/1dollar-bill-mod',
    3: 'phase_5/models/props/bikehorn',
    4: 'phase_3.5/models/props/tart',
    5: 'phase_3.5/models/props/squirting-flower',
    6: 'phase_5/models/props/flowerpot-mod',
}

_WEB_CHAT = {'chatScButton': (0.36, 0, -0.135), 'chatNormalButton': (0.135, 0, -0.135)}
def _webChatPos(name, x, y, z):
    home = _WEB_CHAT.get(name)
    if home is None:
        return x, y, z
    if x < -1.0:
        return home
    return home[0] + 0.45, y, home[2] - 0.25
def _webChatScale(name, x, y, z):
    if name in _WEB_CHAT and abs(x - 1.179) < 0.01:
        return 2.0, 2.0, 2.0
    return x, y, z
def _webPageArrow(arrows, h1, h2):
    button = globalVarDict.get('bookNextArrow')
    if button is None:
        arrows.arrowsOn(0.85, -0.75, h1, 0.85, -0.75, h2, parent=aspect2d)
        return
    parent = button.getParent()
    p = button.getPos(parent)
    x, z = p.getX() + 0.012, p.getZ() - 0.14
    arrows.arrowsOn(x, z, h1, x, z, h2, parent=parent)
def _webChatArrows(arrows, h1, h2):
    speed = globalVarDict.get('chatScButton')
    normal = globalVarDict.get('chatNormalButton')
    if speed is None or normal is None:
        parent = base.a2dTopLeft
        sx, sz, nx, nz = 0.36, -0.135, 0.135, -0.135
    else:
        parent = speed.getParent()
        p1, p2 = speed.getPos(parent), normal.getPos(parent)
        sx, sz, nx, nz = p1.getX(), p1.getZ(), p2.getX(), p2.getZ()
    arrows.arrowsOn(sx + 0.095, sz + 0.045, h1, nx + 0.078, nz - 0.155, h2, parent=parent)
    for arrow in (arrows.arrow1, arrows.arrow2):
        arrow.setBin('gui-popup', 100)
        arrow.setDepthTest(False)
        arrow.setDepthWrite(False)
    if not getattr(arrows, '_web_chat_arrow_logged', False):
        print('QuestParser: SpeedChat arrows parent=%s speed=(%.3f, %.3f) normal=(%.3f, %.3f)' % (parent.getName(), sx, sz, nx, nz))
        arrows._web_chat_arrow_logged = True

import sys
import os
import tokenize
import copy
from direct.interval.IntervalGlobal import *
from direct.directnotify import DirectNotifyGlobal
from panda3d.core import *
from panda3d.otp import *
from direct.showbase import DirectObject
from . import BlinkingArrows
from toontown.toon import ToonHeadFrame
from toontown.char import CharDNA
from toontown.suit import SuitDNA
from toontown.char import Char
from toontown.suit import Suit
from toontown.toonbase import TTLocalizer
from toontown.toonbase import ScreenAnchors
from toontown.toonbase import ToontownBattleGlobals
from otp.speedchat import SpeedChatGlobals
from toontown.ai import DistributedBlackCatMgr
from direct.showbase import PythonUtil
from direct.interval.IntervalGlobal import *
notify = DirectNotifyGlobal.directNotify.newCategory('QuestParser')
lineDict = {}
globalVarDict = {}
curId = None

def init():
    globalVarDict.update({'render': render,
     'camera': camera,
     'hidden': hidden,
     'aspect2d': aspect2d,
     'localToon': base.localAvatar,
     'laffMeter': base.localAvatar.laffMeter,
     'inventory': base.localAvatar.inventory,
     'bFriendsList': base.localAvatar.bFriendsList,
     'book': base.localAvatar.book,
     'bookPrevArrow': base.localAvatar.book.prevArrow,
     'bookNextArrow': base.localAvatar.book.nextArrow,
     'bookOpenButton': base.localAvatar.book.bookOpenButton,
     'bookCloseButton': base.localAvatar.book.bookCloseButton,
     'chatNormalButton': base.localAvatar.chatMgr.normalButton,
     'chatScButton': base.localAvatar.chatMgr.scButton,
     'arrows': BlinkingArrows.BlinkingArrows()})


def clear():
    globalVarDict.clear()


def readFile(filename):
    global curId
    scriptFile = StreamReader(vfs.openReadFile(filename, 1), 1)
    gen = tokenize.tokenize(scriptFile.readline)
    line = getLineOfTokens(gen)
    while line is not None:
        if line == []:
            line = getLineOfTokens(gen)
            continue
        if line[0] == 'ID':
            parseId(line)
        elif curId is None:
            notify.error('Every script must begin with an ID')
        else:
            lineDict[curId].append(line)
        line = getLineOfTokens(gen)

    return


def getLineOfTokens(gen):
    tokens = []
    nextNeg = 0
    token = next(gen)
    if token[0] == tokenize.ENDMARKER:
        return None
    while token[0] != tokenize.NEWLINE and token[0] != tokenize.NL:
        if token[0] in (tokenize.COMMENT, tokenize.ENCODING):
            pass
        elif token[0] == tokenize.OP and token[1] == '-':
            nextNeg = 1
        elif token[0] == tokenize.NUMBER:
            if nextNeg:
                tokens.append(-eval(token[1]))
                nextNeg = 0
            else:
                tokens.append(eval(token[1]))
        elif token[0] == tokenize.STRING:
            tokens.append(eval(token[1]))
        elif token[0] == tokenize.NAME:
            tokens.append(token[1])
        else:
            notify.warning('Ignored token type: %s on line: %s' % (tokenize.tok_name[token[0]], token[2][0]))
        token = next(gen)

    return tokens


def parseId(line):
    global curId
    curId = line[1]
    notify.debug('Setting current scriptId to: %s' % curId)
    if questDefined(curId):
        notify.error('Already defined scriptId: %s' % curId)
    else:
        lineDict[curId] = []


def questDefined(scriptId):
    return scriptId in lineDict


class NPCMoviePlayer(DirectObject.DirectObject):

    def __init__(self, scriptId, toon, npc):
        DirectObject.DirectObject.__init__(self)
        self.scriptId = scriptId
        self.toon = toon
        self.isLocalToon = self.toon == base.localAvatar
        self.npc = npc
        self.privateVarDict = {}
        self.toonHeads = {}
        self.chars = []
        self.uniqueId = 'scriptMovie_' + str(self.scriptId) + '_' + str(toon.getDoId()) + '_' + str(npc.getDoId())
        self.setVar('toon', self.toon)
        self.setVar('npc', self.npc)
        self.chapterDict = {}
        self.timeoutTrack = None
        self.currentTrack = None
        return

    def getVar(self, varName):
        if varName in self.privateVarDict:
            return self.privateVarDict[varName]
        elif varName in globalVarDict:
            return globalVarDict[varName]
        elif varName.find('tomDialogue') > -1 or varName.find('harryDialogue') > -1:
            notify.warning('%s getting referenced. Tutorial Ack: %d                                  Place: %s' % (varName, base.localAvatar.tutorialAck, base.cr.playGame.hood))
            return None
        else:
            notify.error('Variable not defined: %s' % varName)
        return None

    def delVar(self, varName):
        if varName in self.privateVarDict:
            del self.privateVarDict[varName]
        elif varName in globalVarDict:
            del globalVarDict[varName]
        else:
            notify.warning('Variable not defined: %s' % varName)

    def setVar(self, varName, var):
        self.privateVarDict[varName] = var

    def cleanup(self):
        if self.currentTrack:
            self.currentTrack.pause()
            self.currentTrack = None
        self.ignoreAll()
        if getattr(self, 'trackSelectionGui', None) is not None:
            self.trackSelectionGui.destroy()
            self.trackSelectionGui = None
        taskMgr.remove(self.uniqueId)
        for toonHeadFrame in list(self.toonHeads.values()):
            toonHeadFrame.destroy()

        while self.chars:
            self.__unloadChar(self.chars[0])

        del self.toonHeads
        del self.privateVarDict
        del self.chapterDict
        del self.toon
        del self.npc
        del self.timeoutTrack
        return

    def __unloadChar(self, char):
        char.removeActive()
        char.delete()
        self.chars.remove(char)

    def timeout(self, fFinish = 0):
        if self.timeoutTrack:
            if fFinish:
                self.timeoutTrack.finish()
            else:
                self.timeoutTrack.start()

    def finishMovie(self):
        self.npc.finishMovie(self.toon, self.isLocalToon, 0.0)

    def playNextChapter(self, eventName, timeStamp = 0.0):
        trackList = self.chapterDict[eventName]
        if trackList:
            self.currentTrack = trackList.pop(0)
            self.currentTrack.start()
        else:
            notify.debug('Movie ended waiting for an event (%s)' % eventName)

    def play(self):
        lineNum = 0
        self.currentEvent = 'start'
        lines = lineDict.get(self.scriptId)
        if lines is None:
            notify.error('No movie defined for scriptId: %s' % self.scriptId)
        chapterList = []
        timeoutList = []
        for line in lines:
            lineNum += 1
            command = line[0]
            if command == 'UPON_TIMEOUT':
                uponTimeout = 1
                iList = timeoutList
                line = line[1:]
                command = line[0]
            else:
                uponTimeout = 0
                iList = chapterList
            if command == 'CALL':
                if uponTimeout:
                    self.notify.error('CALL not allowed in an UPON_TIMEOUT')
                iList.append(self.parseCall(line))
                continue
            elif command == 'DEBUG':
                iList.append(self.parseDebug(line))
                continue
            elif command == 'WAIT':
                if uponTimeout:
                    self.notify.error('WAIT not allowed in an UPON_TIMEOUT')
                iList.append(self.parseWait(line))
                continue
            elif command == 'CHAT':
                iList.append(self.parseChat(line))
                continue
            elif command == 'CLEAR_CHAT':
                iList.append(self.parseClearChat(line))
                continue
            elif command == 'FINISH_QUEST_MOVIE':
                chapterList.append(Func(self.finishMovie))
                continue
            elif command == 'CHAT_CONFIRM':
                if uponTimeout:
                    self.notify.error('CHAT_CONFIRM not allowed in an UPON_TIMEOUT')
                avatarName = line[1]
                avatar = self.getVar(avatarName)
                nextEvent = avatar.uniqueName('doneChatPage')
                iList.append(Func(self.acceptOnce, nextEvent, self.playNextChapter, [nextEvent]))
                iList.append(self.parseChatConfirm(line))
                self.closePreviousChapter(iList)
                chapterList = []
                self.currentEvent = nextEvent
                continue
            elif command == 'LOCAL_CHAT_CONFIRM':
                if uponTimeout:
                    self.notify.error('LOCAL_CHAT_CONFIRM not allowed in an UPON_TIMEOUT')
                avatarName = line[1]
                avatar = self.getVar(avatarName)
                nextEvent = avatar.uniqueName('doneChatPage')
                iList.append(Func(self.acceptOnce, nextEvent, self.playNextChapter, [nextEvent]))
                iList.append(self.parseLocalChatConfirm(line))
                self.closePreviousChapter(iList)
                chapterList = []
                self.currentEvent = nextEvent
                continue
            elif command == 'LOCAL_CHAT_PERSIST':
                iList.append(self.parseLocalChatPersist(line))
                continue
            elif command == 'LOCAL_CHAT_TO_CONFIRM':
                if uponTimeout:
                    self.notify.error('LOCAL_CHAT_TO_CONFIRM not allowed in an UPON_TIMEOUT')
                avatarName = line[1]
                avatar = self.getVar(avatarName)
                nextEvent = avatar.uniqueName('doneChatPage')
                iList.append(Func(self.acceptOnce, nextEvent, self.playNextChapter, [nextEvent]))
                iList.append(self.parseLocalChatToConfirm(line))
                self.closePreviousChapter(iList)
                chapterList = []
                self.currentEvent = nextEvent
                continue
            if self.isLocalToon:
                if command == 'LOAD':
                    self.parseLoad(line)
                elif command == 'LOAD_SFX':
                    self.parseLoadSfx(line)
                elif command == 'LOAD_DIALOGUE':
                    self.parseLoadDialogue(line)
                elif command == 'LOAD_CHAR':
                    self.parseLoadChar(line)
                elif command == 'UNLOAD_CHAR':
                    iList.append(self.parseUnloadChar(line))
                elif command == 'LOAD_SUIT':
                    self.parseLoadSuit(line)
                elif command == 'SET':
                    self.parseSet(line)
                elif command == 'LOCK_LOCALTOON':
                    iList.append(self.parseLockLocalToon(line))
                elif command == 'FREE_LOCALTOON':
                    iList.append(self.parseFreeLocalToon(line))
                elif command == 'REPARENTTO':
                    iList.append(self.parseReparent(line))
                elif command == 'WRTREPARENTTO':
                    iList.append(self.parseWrtReparent(line))
                elif command == 'SHOW':
                    iList.append(self.parseShow(line))
                elif command == 'HIDE':
                    iList.append(self.parseHide(line))
                elif command == 'POS':
                    iList.append(self.parsePos(line))
                elif command == 'HPR':
                    iList.append(self.parseHpr(line))
                elif command == 'SCALE':
                    iList.append(self.parseScale(line))
                elif command == 'POSHPRSCALE':
                    iList.append(self.parsePosHprScale(line))
                elif command == 'COLOR':
                    iList.append(self.parseColor(line))
                elif command == 'COLOR_SCALE':
                    iList.append(self.parseColorScale(line))
                elif command == 'ADD_LAFFMETER':
                    iList.append(self.parseAddLaffMeter(line))
                elif command == 'LAFFMETER':
                    iList.append(self.parseLaffMeter(line))
                elif command == 'OBSCURE_LAFFMETER':
                    iList.append(self.parseObscureLaffMeter(line))
                elif command == 'ARROWS_ON':
                    iList.append(self.parseArrowsOn(line))
                elif command == 'ARROWS_OFF':
                    iList.append(self.parseArrowsOff(line))
                elif command == 'START_THROB':
                    iList.append(self.parseStartThrob(line))
                elif command == 'STOP_THROB':
                    iList.append(self.parseStopThrob(line))
                elif command == 'SHOW_FRIENDS_LIST':
                    iList.append(self.parseShowFriendsList(line))
                elif command == 'HIDE_FRIENDS_LIST':
                    iList.append(self.parseHideFriendsList(line))
                elif command == 'SHOW_BOOK':
                    iList.append(self.parseShowBook(line))
                elif command == 'HIDE_BOOK':
                    iList.append(self.parseHideBook(line))
                elif command == 'ENABLE_CLOSE_BOOK':
                    iList.append(self.parseEnableCloseBook(line))
                elif command == 'OBSCURE_BOOK':
                    iList.append(self.parseObscureBook(line))
                elif command == 'OBSCURE_CHAT':
                    iList.append(self.parseObscureChat(line))
                elif command == 'ADD_INVENTORY':
                    iList.append(self.parseAddInventory(line))
                elif command == 'SET_INVENTORY':
                    iList.append(self.parseSetInventory(line))
                elif command == 'SET_INVENTORY_YPOS':
                    iList.append(self.parseSetInventoryYPos(line))
                elif command == 'SET_INVENTORY_DETAIL':
                    iList.append(self.parseSetInventoryDetail(line))
                elif command == 'PLAY_SFX':
                    iList.append(self.parsePlaySfx(line))
                elif command == 'STOP_SFX':
                    iList.append(self.parseStopSfx(line))
                elif command == 'PLAY_ANIM':
                    iList.append(self.parsePlayAnim(line))
                elif command == 'LOOP_ANIM':
                    iList.append(self.parseLoopAnim(line))
                elif command == 'LERP_POS':
                    iList.append(self.parseLerpPos(line))
                elif command == 'LERP_HPR':
                    iList.append(self.parseLerpHpr(line))
                elif command == 'LERP_SCALE':
                    iList.append(self.parseLerpScale(line))
                elif command == 'LERP_POSHPRSCALE':
                    iList.append(self.parseLerpPosHprScale(line))
                elif command == 'LERP_COLOR':
                    iList.append(self.parseLerpColor(line))
                elif command == 'LERP_COLOR_SCALE':
                    iList.append(self.parseLerpColorScale(line))
                elif command == 'DEPTH_WRITE_ON':
                    iList.append(self.parseDepthWriteOn(line))
                elif command == 'DEPTH_WRITE_OFF':
                    iList.append(self.parseDepthWriteOff(line))
                elif command == 'DEPTH_TEST_ON':
                    iList.append(self.parseDepthTestOn(line))
                elif command == 'DEPTH_TEST_OFF':
                    iList.append(self.parseDepthTestOff(line))
                elif command == 'SET_BIN':
                    iList.append(self.parseSetBin(line))
                elif command == 'CLEAR_BIN':
                    iList.append(self.parseClearBin(line))
                elif command == 'TOON_HEAD':
                    iList.append(self.parseToonHead(line))
                elif command == 'SEND_EVENT':
                    iList.append(self.parseSendEvent(line))
                elif command == 'FUNCTION':
                    iList.append(self.parseFunction(line))
                elif command == 'BLACK_CAT_LISTEN':
                    iList.append(self.parseBlackCatListen(line))
                elif command == 'STARTING_GAG_MAP':
                    iList.append(self.parseStartingGagMap(line))
                    continue
                elif command == 'SHOW_TRACK_SELECTION':
                    if uponTimeout:
                        self.notify.error('SHOW_TRACK_SELECTION not allowed in an UPON_TIMEOUT')
                    nextEvent = 'doneTrackSelection'
                    iList.append(Func(self.acceptOnce, nextEvent, self.playNextChapter, [nextEvent]))
                    iList.append(self.parseShowTrackSelection(line))
                    self.closePreviousChapter(iList)
                    chapterList = []
                    self.currentEvent = nextEvent
                elif command == 'CHAT_TRACK_REACTION':
                    if uponTimeout:
                        self.notify.error('CHAT_TRACK_REACTION not allowed in an UPON_TIMEOUT')
                    avatarName = line[1]
                    avatar = self.getVar(avatarName)
                    nextEvent = avatar.uniqueName('doneChatPage')
                    iList.append(Func(self.acceptOnce, nextEvent, self.playNextChapter, [nextEvent]))
                    iList.append(self.parseTrackReaction(line))
                    self.closePreviousChapter(iList)
                    chapterList = []
                    self.currentEvent = nextEvent
                elif command == 'SHOW_THROW_SQUIRT_PREVIEW':
                    if uponTimeout:
                        self.notify.error('SHOW_THROW_SQUIRT_PREVIEW not allowed in an UPON_TIMEOUT')
                    nextEvent = 'doneThrowSquirtPreview'
                    iList.append(Func(self.acceptOnce, nextEvent, self.playNextChapter, [nextEvent]))
                    iList.append(self.parseThrowSquirtPreview(line))
                    self.closePreviousChapter(iList)
                    chapterList = []
                    self.currentEvent = nextEvent
                elif command == 'WAIT_EVENT':
                    if uponTimeout:
                        self.notify.error('WAIT_EVENT not allowed in an UPON_TIMEOUT')
                    nextEvent = self.parseWaitEvent(line)

                    def proceed(self = self, nextEvent = nextEvent):
                        self.playNextChapter(nextEvent)

                    def handleEvent(*args):
                        proceed = args[0]
                        proceed()

                    iList.append(Func(self.acceptOnce, nextEvent, handleEvent, [proceed]))
                    self.closePreviousChapter(iList)
                    chapterList = []
                    self.currentEvent = nextEvent
                elif command == 'SET_MUSIC_VOLUME':
                    iList.append(self.parseSetMusicVolume(line))
                else:
                    notify.warning('Unknown command token: %s for scriptId: %s on line: %s' % (command, self.scriptId, lineNum))

        self.closePreviousChapter(chapterList)
        if timeoutList:
            self.timeoutTrack = Sequence(*timeoutList)
        self.playNextChapter('start')
        return

    def closePreviousChapter(self, iList):
        trackList = self.chapterDict.setdefault(self.currentEvent, [])
        trackList.append(Sequence(*iList))

    def parseLoad(self, line):
        if len(line) == 3:
            token, varName, modelPath = line
            node = loader.loadModel(modelPath)
        elif len(line) == 4:
            token, varName, modelPath, subNodeName = line
            node = loader.loadModel(modelPath).find('**/' + subNodeName)
        else:
            notify.error('invalid parseLoad command')
        self.setVar(varName, node)

    def parseLoadSfx(self, line):
        token, varName, fileName = line
        sfx = base.loader.loadSfx(fileName)
        self.setVar(varName, sfx)

    def parseLoadDialogue(self, line):
        token, varName, fileName = line
        if varName == 'tomDialogue_01':
            notify.debug('VarName tomDialogue getting added. Tutorial Ack: %d' % base.localAvatar.tutorialAck)
        if base.config.GetString('language', 'english') == 'japanese':
            dialogue = base.loader.loadSfx(fileName)
        else:
            dialogue = None
        self.setVar(varName, dialogue)
        return

    def parseLoadChar(self, line):
        token, name, charType = line
        char = Char.Char()
        dna = CharDNA.CharDNA()
        dna.newChar(charType)
        char.setDNA(dna)
        char.nametag.manage(base.marginManager)
        char.addActive()
        char.hideName()
        self.setVar(name, char)

    def parseUnloadChar(self, line):
        token, name = line
        char = self.getVar(name)
        track = Sequence()
        track.append(Func(self.__unloadChar, char))
        track.append(Func(self.delVar, name))
        return track

    def parseLoadSuit(self, line):
        token, name, suitType = line
        suit = Suit.Suit()
        dna = SuitDNA.SuitDNA()
        dna.newSuit(suitType)
        suit.setDNA(dna)
        self.setVar(name, suit)

    def parseSet(self, line):
        token, varName, value = line
        self.setVar(varName, value)

    def parseCall(self, line):
        token, scriptId = line
        nmp = NPCMoviePlayer(scriptId, self.toon, self.npc)
        return Func(nmp.play)

    def parseLockLocalToon(self, line):
        return Sequence(Func(self.toon.detachCamera), Func(self.toon.collisionsOff), Func(self.toon.disableAvatarControls), Func(self.toon.stopTrackAnimToSpeed), Func(self.toon.stopUpdateSmartCamera))

    def parseFreeLocalToon(self, line):
        return Sequence(Func(self.toon.attachCamera), Func(self.toon.startTrackAnimToSpeed), Func(self.toon.collisionsOn), Func(self.toon.enableAvatarControls), Func(self.toon.startUpdateSmartCamera))

    def parseDebug(self, line):
        token, str = line
        return Func(notify.debug, str)

    def parseReparent(self, line):
        if len(line) == 3:
            token, childNodeName, parentNodeName = line
            subNodeName = None
        elif len(line) == 4:
            token, childNodeName, parentNodeName, subNodeName = line
        childNode = self.getVar(childNodeName)
        if subNodeName:
            parentNode = self.getVar(parentNodeName).find(subNodeName)
        else:
            parentNode = self.getVar(parentNodeName)
        return ParentInterval(childNode, parentNode)

    def parseWrtReparent(self, line):
        if len(line) == 3:
            token, childNodeName, parentNodeName = line
            subNodeName = None
        elif len(line) == 4:
            token, childNodeName, parentNodeName, subNodeName = line
        childNode = self.getVar(childNodeName)
        if subNodeName:
            parentNode = self.getVar(parentNodeName).find(subNodeName)
        else:
            parentNode = self.getVar(parentNodeName)
        return WrtParentInterval(childNode, parentNode)

    def parseShow(self, line):
        token, nodeName = line
        node = self.getVar(nodeName)
        if nodeName == 'inventory' and hasattr(node, 'layoutTutorialBoard'):
            def showInventory():
                if node.getParent() == camera:
                    node.layoutTutorialBoard()
                else:
                    node.show()
            return Func(showInventory)
        return Func(node.show)

    def parseHide(self, line):
        token, nodeName = line
        node = self.getVar(nodeName)
        if nodeName == 'inventory' and hasattr(node, 'layoutTutorialBoard'):
            def _hideTutorialBoard(node=node):
                if getattr(node, '_tutorialBoard', False):
                    node._tutorialBoard = False
                    node._resetTrackRig()
                node.hide()
            return Func(_hideTutorialBoard)
        return Func(node.hide)

    def parsePos(self, line):
        token, nodeName, x, y, z = line
        node = self.getVar(nodeName)
        x, y, z = _webChatPos(nodeName, x, y, z)
        return Func(node.setPos, x, y, z)

    def parseHpr(self, line):
        token, nodeName, h, p, r = line
        node = self.getVar(nodeName)
        return Func(node.setHpr, h, p, r)

    def parseScale(self, line):
        token, nodeName, x, y, z = line
        node = self.getVar(nodeName)
        x, y, z = _webChatScale(nodeName, x, y, z)
        return Func(node.setScale, x, y, z)

    def parsePosHprScale(self, line):
        token, nodeName, x, y, z, h, p, r, sx, sy, sz = line
        node = self.getVar(nodeName)
        if nodeName == 'inventory' and hasattr(node, 'layoutTutorialBoard'):
            return Func(lambda: None)
        return Func(node.setPosHprScale, x, y, z, h, p, r, sx, sy, sz)

    def parseColor(self, line):
        token, nodeName, r, g, b, a = line
        node = self.getVar(nodeName)
        return Func(node.setColor, r, g, b, a)

    def parseColorScale(self, line):
        token, nodeName, r, g, b, a = line
        node = self.getVar(nodeName)
        return Func(node.setColorScale, r, g, b, a)

    def parseWait(self, line):
        token, waitTime = line
        return Wait(waitTime)

    def parseChat(self, line):
        toonId = self.toon.getDoId()
        avatarName = line[1]
        avatar = self.getVar(avatarName)
        chatString = eval('TTLocalizer.' + line[2])
        chatFlags = CFSpeech | CFTimeout
        quitButton, extraChatFlags, dialogueList = self.parseExtraChatArgs(line[3:])
        if extraChatFlags:
            chatFlags |= extraChatFlags
        if len(dialogueList) > 0:
            dialogue = dialogueList[0]
        else:
            dialogue = None
        return Func(avatar.setChatAbsolute, chatString, chatFlags, dialogue)

    def parseClearChat(self, line):
        toonId = self.toon.getDoId()
        avatarName = line[1]
        avatar = self.getVar(avatarName)
        chatFlags = CFSpeech | CFTimeout
        return Func(avatar.setChatAbsolute, '', chatFlags)

    def parseExtraChatArgs(self, args):
        quitButton = 0
        extraChatFlags = None
        dialogueList = []
        for arg in args:
            if type(arg) == type(0):
                quitButton = arg
            elif type(arg) == type(''):
                if len(arg) > 2 and arg[:2] == 'CF':
                    extraChatFlags = eval(arg)
                else:
                    dialogueList.append(self.getVar(arg))
            else:
                notify.error('invalid argument type')

        return (quitButton, extraChatFlags, dialogueList)

    def parseChatConfirm(self, line):
        lineLength = len(line)
        toonId = self.toon.getDoId()
        avatarName = line[1]
        avatar = self.getVar(avatarName)
        chatString = eval('TTLocalizer.' + line[2])
        quitButton, extraChatFlags, dialogueList = self.parseExtraChatArgs(line[3:])
        return Func(avatar.setPageChat, toonId, 0, chatString, quitButton, extraChatFlags, dialogueList)

    def parseLocalChatConfirm(self, line):
        lineLength = len(line)
        avatarName = line[1]
        avatar = self.getVar(avatarName)
        chatString = eval('TTLocalizer.' + line[2])
        quitButton, extraChatFlags, dialogueList = self.parseExtraChatArgs(line[3:])
        return Func(avatar.setLocalPageChat, chatString, quitButton, extraChatFlags, dialogueList)

    def parseLocalChatPersist(self, line):
        lineLength = len(line)
        avatarName = line[1]
        avatar = self.getVar(avatarName)
        chatString = eval('TTLocalizer.' + line[2])
        quitButton, extraChatFlags, dialogueList = self.parseExtraChatArgs(line[3:])
        if len(dialogueList) > 0:
            dialogue = dialogueList[0]
        else:
            dialogue = None
        return Func(avatar.setChatAbsolute, chatString, CFSpeech, dialogue)

    def parseLocalChatToConfirm(self, line):
        lineLength = len(line)
        avatarKey = line[1]
        avatar = self.getVar(avatarKey)
        toAvatarKey = line[2]
        toAvatar = self.getVar(toAvatarKey)
        localizerAvatarName = toAvatar.getName().capitalize()
        toAvatarName = eval('TTLocalizer.' + localizerAvatarName)
        chatString = eval('TTLocalizer.' + line[3])
        chatString = chatString.replace('%s', toAvatarName)
        quitButton, extraChatFlags, dialogueList = self.parseExtraChatArgs(line[4:])
        return Func(avatar.setLocalPageChat, chatString, quitButton, extraChatFlags, dialogueList)

    def parsePlaySfx(self, line):
        if len(line) == 2:
            token, sfxName = line
            looping = 0
        elif len(line) == 3:
            token, sfxName, looping = line
        else:
            notify.error('invalid number of arguments')
        sfx = self.getVar(sfxName)
        return Func(base.playSfx, sfx, looping)

    def parseStopSfx(self, line):
        token, sfxName = line
        sfx = self.getVar(sfxName)
        return Func(sfx.stop)

    def parsePlayAnim(self, line):
        if len(line) == 3:
            token, actorName, animName = line
            playRate = 1.0
        elif len(line) == 4:
            token, actorName, animName, playRate = line
        else:
            notify.error('invalid number of arguments')
        actor = self.getVar(actorName)
        return Sequence(Func(actor.setPlayRate, playRate, animName), Func(actor.play, animName))

    def parseLoopAnim(self, line):
        if len(line) == 3:
            token, actorName, animName = line
            playRate = 1.0
        elif len(line) == 4:
            token, actorName, animName, playRate = line
        else:
            notify.error('invalid number of arguments')
        actor = self.getVar(actorName)
        return Sequence(Func(actor.setPlayRate, playRate, animName), Func(actor.loop, animName))

    def parseLerpPos(self, line):
        token, nodeName, x, y, z, t = line
        node = self.getVar(nodeName)
        x, y, z = _webChatPos(nodeName, x, y, z)
        return Sequence(LerpPosInterval(node, t, Point3(x, y, z), blendType='easeInOut'), duration=0.0)

    def parseLerpHpr(self, line):
        token, nodeName, h, p, r, t = line
        node = self.getVar(nodeName)
        return Sequence(LerpHprInterval(node, t, VBase3(h, p, r), blendType='easeInOut'), duration=0.0)

    def parseLerpScale(self, line):
        token, nodeName, x, y, z, t = line
        node = self.getVar(nodeName)
        if nodeName == 'inventory' and hasattr(node, 'layoutTutorialBoard'):
            return Wait(t)
        x, y, z = _webChatScale(nodeName, x, y, z)
        return Sequence(LerpScaleInterval(node, t, VBase3(x, y, z), blendType='easeInOut'), duration=0.0)

    def parseLerpPosHprScale(self, line):
        token, nodeName, x, y, z, h, p, r, sx, sy, sz, t = line
        node = self.getVar(nodeName)
        return Sequence(LerpPosHprScaleInterval(node, t, VBase3(x, y, z), VBase3(h, p, r), VBase3(sx, sy, sz), blendType='easeInOut'), duration=0.0)

    def parseLerpColor(self, line):
        token, nodeName, sr, sg, sb, sa, er, eg, eb, ea, t = line
        node = self.getVar(nodeName)
        return Sequence(LerpColorInterval(node, t, VBase4(er, eg, eb, ea), startColorScale=VBase4(sr, sg, sb, sa), blendType='easeInOut'), duration=0.0)

    def parseLerpColorScale(self, line):
        token, nodeName, sr, sg, sb, sa, er, eg, eb, ea, t = line
        node = self.getVar(nodeName)
        return Sequence(LerpColorScaleInterval(node, t, VBase4(er, eg, eb, ea), startColorScale=VBase4(sr, sg, sb, sa), blendType='easeInOut'), duration=0.0)

    def parseDepthWriteOn(self, line):
        token, nodeName, depthWrite = line
        node = self.getVar(nodeName)
        return Sequence(Func(node.setDepthWrite, depthWrite))

    def parseDepthWriteOff(self, line):
        token, nodeName = line
        node = self.getVar(nodeName)
        return Sequence(Func(node.clearDepthWrite))

    def parseDepthTestOn(self, line):
        token, nodeName, depthTest = line
        node = self.getVar(nodeName)
        return Sequence(Func(node.setDepthTest, depthTest))

    def parseDepthTestOff(self, line):
        token, nodeName = line
        node = self.getVar(nodeName)
        return Sequence(Func(node.clearDepthTest))

    def parseSetBin(self, line):
        if len(line) == 3:
            token, nodeName, binName = line
            sortOrder = 0
        else:
            token, nodeName, binName, sortOrder = line
        node = self.getVar(nodeName)
        return Sequence(Func(node.setBin, binName, sortOrder))

    def parseClearBin(self, line):
        token, nodeName = line
        node = self.getVar(nodeName)
        return Sequence(Func(node.clearBin))

    def parseWaitEvent(self, line):
        token, eventName = line
        # Harry's book tutorial uses indices from the original tab order.
        if eventName == 'stickerBookPageChange-3':
            return 'stickerBookGagsOpened'
        if eventName == 'stickerBookPageChange-4':
            return 'stickerBookTasksOpened'
        if eventName == 'inventory-selection':
            return 'boughtGag'
        return eventName

    def parseSendEvent(self, line):
        token, eventName = line
        return Func(messenger.send, eventName)

    def parseFunction(self, line):
        token, objectName, functionName = line
        object = self.getVar(objectName)
        cfunc = compile('object' + '.' + functionName, '<string>', 'eval')
        return Func(eval(cfunc))

    def parseAddLaffMeter(self, line):
        token, maxHpDelta = line
        newMaxHp = maxHpDelta + self.toon.getMaxHp()
        newHp = newMaxHp
        laffMeter = self.getVar('laffMeter')
        return Func(laffMeter.adjustFace, newHp, newMaxHp)

    def parseLaffMeter(self, line):
        token, newHp, newMaxHp = line
        laffMeter = self.getVar('laffMeter')
        return Func(laffMeter.adjustFace, newHp, newMaxHp)

    def parseObscureLaffMeter(self, line):
        token, val = line
        return Func(self.toon.laffMeter.obscure, val)

    def _startingTracks(self):
        saved = self.toon.getChosenTracks()
        return saved if len(saved) >= 2 else getattr(self.toon, 'ttaStartingSelection', ())

    def _mapTrack(self, track):
        # The tutorial script uses the names of the two original prop slots.
        chosen = self._startingTracks()
        if len(chosen) >= 2 and track in (4, 5):
            return chosen[0] if track == 4 else chosen[1]
        return track

    def parseStartingGagMap(self, line):
        def swapProps():
            chosen = self._startingTracks()
            if len(chosen) < 2:
                return
            # The script hands the 'flower' first (paired with ADD_INVENTORY 5
            # -> chosen[1]) and the 'tart' second (ADD_INVENTORY 4 -> chosen[0]).
            for varName, tr in (('flower', chosen[1]), ('tart', chosen[0])):
                node = self.getVar(varName)
                if node is None:
                    continue
                path = _TTA_TRACK_PROP_MODEL.get(tr)
                if not path:
                    continue
                try:
                    for child in list(node.getChildren()):
                        child.removeNode()
                    model = loader.loadModel(path)
                    if model is not None:
                        model.reparentTo(node)
                    else:
                        print('web: starting gag map PROP MODEL MISSING %s' % path)
                except Exception as e:
                    print('web: starting gag map PROP SWAP FAILED %s' % e)
            print('web: starting gag map PROPS tart->%s flower->%s' % (chosen[0], chosen[1]))

        return Func(swapProps)

    def parseAddInventory(self, line):
        token, track, level, number = line
        inventory = self.getVar('inventory')
        countSound = base.loader.loadSfx('phase_3.5/audio/sfx/tick_counter.ogg')

        def doAdd():
            realTrack = self._mapTrack(track)
            print('web: starting gag map ADD %s->%s' % (track, realTrack))
            base.playSfx(countSound)
            inventory.buttonBoing(realTrack, level)
            # The AI grants the starter gags. The movie reveals the same
            # quantity, even if the authoritative update arrives mid-scene.
            if getattr(inventory, '_tutorialBoard', False):
                inventory.setItem(realTrack, level, number)
            else:
                inventory.addItems(realTrack, level, number)
            inventory.updateGUI(realTrack, level)

        return Func(doAdd)

    def parseSetInventory(self, line):
        # Handout clear lines use Throw(4)/Squirt(5) as placeholders. Remap them
        # to the chosen tracks so clearing then re-adding gives exactly 1 of each.
        token, track, level, number = line
        inventory = self.getVar('inventory')

        def setCount():
            realTrack = self._mapTrack(track)
            inventory.setItem(realTrack, level, number)
            inventory.updateGUI(realTrack, level)

        return Func(setCount)

    def parseSetInventoryYPos(self, line):
        token, track, level, yPos = line
        inventory = self.getVar('inventory')

        def doYPos():
            realTrack = self._mapTrack(track)
            button = inventory.buttons[realTrack][level].stateNodePath[0]
            text = button.find('**/+TextNode')
            if not text.isEmpty() and not getattr(inventory, '_tutorialBoard', False):
                text.setY(yPos)

        return Func(doYPos)

    def parseSetInventoryDetail(self, line):
        if len(line) == 2:
            token, val = line
        elif len(line) == 4:
            token, val, track, level = line
        else:
            notify.error('invalid line for parseSetInventoryDetail: %s' % line)
        inventory = self.getVar('inventory')
        if val == -1:
            return Func(inventory.noDetail)
        elif val == 0:
            return Func(inventory.hideDetail)
        elif val == 1:
            return Func(inventory.showDetail, track, level)
        else:
            notify.error('invalid inventory detail level: %s' % val)

    def parseShowFriendsList(self, line):
        from toontown.friends import FriendsListPanel
        return Func(FriendsListPanel.showFriendsListTutorial)

    def parseHideFriendsList(self, line):
        from toontown.friends import FriendsListPanel
        return Func(FriendsListPanel.hideFriendsListTutorial)

    def parseShowBook(self, line):
        return Sequence(Func(self.toon.book.setPage, self.toon.mapPage), Func(self.toon.book.enter), Func(self.toon.book.disableBookCloseButton))

    def parseEnableCloseBook(self, line):
        return Sequence(Func(self.toon.book.enableBookCloseButton))

    def parseHideBook(self, line):
        return Func(self.toon.book.exit)

    def parseObscureBook(self, line):
        token, val = line
        return Func(self.toon.book.obscureButton, val)

    def parseObscureChat(self, line):
        token, val0, val1 = line
        return Func(self.toon.chatMgr.obscure, val0, val1)

    def parseArrowsOn(self, line):
        arrows = self.getVar('arrows')
        token, x1, y1, h1, x2, y2, h2 = line
        if abs(x1 - 0.85) < 0.01 and abs(x2 - 0.85) < 0.01 and abs(y1 + 0.75) < 0.01 and abs(y2 + 0.75) < 0.01:
            return Func(_webPageArrow, arrows, h1, h2)
        if abs(x1 + 0.92) < 0.01 and abs(x2 + 1.12) < 0.01 and abs(y1 - 0.91) < 0.01 and abs(y2 - 0.74) < 0.01:
            return Func(_webChatArrows, arrows, h1, h2)
        if max(x1, x2) > 1.0:
            # pointing at the Shticker Book button in the bottom right corner: follow that corner, as the button does
            return Func(lambda: arrows.arrowsOn(x1, y1, h1, x2, y2, h2, parent=ScreenAnchors.bottomRight()))
        if max(x1, x2) < -0.5:
            return Func(lambda: arrows.arrowsOn(x1 + 4.0 / 3.0, y1 - 1.0, h1, x2 + 4.0 / 3.0, y2 - 1.0, h2, parent=base.a2dTopLeft))
        return Func(arrows.arrowsOn, x1, y1, h1, x2, y2, h2)

    def parseArrowsOff(self, line):
        arrows = self.getVar('arrows')
        return Func(arrows.arrowsOff)

    def parseStartThrob(self, line):
        token, nodeName, r, g, b, a, r2, g2, b2, a2, t = line
        node = self.getVar(nodeName)
        startCScale = Point4(r, g, b, a)
        destCScale = Point4(r2, g2, b2, a2)
        self.throbIval = Sequence(LerpColorScaleInterval(node, t / 2.0, destCScale, startColorScale=startCScale, blendType='easeInOut'), LerpColorScaleInterval(node, t / 2.0, startCScale, startColorScale=destCScale, blendType='easeInOut'))
        return Func(self.throbIval.loop)

    def parseStopThrob(self, line):
        return Func(self.throbIval.finish)

    def parseToonHead(self, line):
        if len(line) == 5:
            token, toonName, x, z, toggle = line
            scale = 1.0
        else:
            token, toonName, x, z, toggle, scale = line
        toon = self.getVar(toonName)
        toonId = toon.getDoId()
        toonHeadFrame = self.toonHeads.get(toonId)
        if not toonHeadFrame:
            toonHeadFrame = ToonHeadFrame.ToonHeadFrame(toon)
            toonHeadFrame.tag1Node.setActive(1)
            toonHeadFrame.hide()
            self.toonHeads[toonId] = toonHeadFrame
            self.setVar('%sToonHead' % toonName, toonHeadFrame)
        if toggle:
            return Sequence(Func(toonHeadFrame.setPos, x, 0, z), Func(toonHeadFrame.setScale, scale), Func(toonHeadFrame.show))
        else:
            return Func(toonHeadFrame.hide)

    def parseToonHeadScale(self, line):
        token, toonName, scale = line
        toon = self.getVar(toonName)
        toonId = toon.getDoId()
        toonHeadFrame = self.toonHeads.get(toonId)
        return Func(toonHeadFrame.setScale, scale)

    def parseBlackCatListen(self, line):
        token, enable = line
        if enable:

            def phraseSaid(phraseId):
                toontastic = 315
                if phraseId == toontastic:
                    messenger.send(DistributedBlackCatMgr.DistributedBlackCatMgr.ActivateEvent)

            def enableBlackCatListen():
                self.acceptOnce(SpeedChatGlobals.SCStaticTextMsgEvent, phraseSaid)

            return Func(enableBlackCatListen)
        else:

            def disableBlackCatListen():
                self.ignore(SpeedChatGlobals.SCStaticTextMsgEvent)

            return Func(disableBlackCatListen)

    def parseShowTrackSelection(self, line):
        numToPick = int(line[1]) if len(line) > 1 else 2
        doneEvent = self.uniqueId + '-trackSelectionDone'

        def runSelection():
            saved = self.toon.getChosenTracks()
            tracks = list(saved[:numToPick]) if len(saved) >= numToPick else None
            from toontown.quest.TrackSelectionGui import TrackSelectionGui
            offered = tracks if tracks else range(ToontownBattleGlobals.NUM_GAG_TRACKS)
            self.trackSelectionGui = TrackSelectionGui(offered, numToPick, doneEvent=doneEvent)
            if tracks:
                for track in tracks:
                    self.trackSelectionGui.toggle(track)

        def onDone(tracks):
            gui = getattr(self, 'trackSelectionGui', None)
            if gui:
                gui.destroy()
                self.trackSelectionGui = None
            if tracks and len(tracks) == numToPick and not self.toon.getChosenTracks():
                self.toon.ttaStartingSelection = list(tracks)
                self.toon.sendUpdate('chooseStartingTracks', [list(tracks)])
            messenger.send('doneTrackSelection')

        def start():
            self.acceptOnce(doneEvent, onDone)
            runSelection()

        return Sequence(Func(start))

    def parseTrackReaction(self, line):
        avatarName = line[1]
        avatar = self.getVar(avatarName)

        def show():
            trackList = self._startingTracks()
            message = TTLocalizer.getTrackChoiceReaction(trackList)
            avatar.setLocalPageChat(message, 0)

        return Sequence(Func(show))

    def parseThrowSquirtPreview(self, line):
        inventory = self.getVar('inventory')
        previous = []

        def start():
            previous[:] = [inventory.activateMode]
            inventory.setActivateMode('gagTutDisabled', gagTutMode=1)

        def preview(level):
            inventory.showShopPreview(int(round(level)))

        def restore():
            if previous:
                inventory.setActivateMode(previous[0], gagTutMode=1)

        return Sequence(Func(start), LerpFunctionInterval(preview, fromData=1, toData=6, duration=0.3),
                        WaitInterval(3.5), LerpFunctionInterval(preview, fromData=6, toData=1, duration=0.3),
                        Func(restore), Func(messenger.send, 'doneThrowSquirtPreview'))

    def parseSetMusicVolume(self, line):
        if base.config.GetString('language', 'english') == 'japanese':
            try:
                loader = base.cr.playGame.place.loader
                type = 'music'
                duration = 0
                fromLevel = 1.0
                if len(line) == 2:
                    token, level = line
                elif len(line) == 3:
                    token, level, type = line
                elif len(line) == 4:
                    token, level, type, duration = line
                elif len(line) == 5:
                    token, level, type, duration, fromLevel = line
                if type == 'battleMusic':
                    music = loader.battleMusic
                elif type == 'activityMusic':
                    music = loader.activityMusic
                else:
                    music = loader.music
                if duration == 0:
                    return Func(music.setVolume, level)
                else:

                    def setVolume(level):
                        music.setVolume(level)

                    return LerpFunctionInterval(setVolume, fromData=fromLevel, toData=level, duration=duration)
            except AttributeError:
                pass

        else:
            return Wait(0.0)


searchPath = DSearchPath()
if __debug__:
    searchPath.appendDirectory(Filename('resources/phase_3/etc'))
scriptFile = Filename('QuestScripts.txt')
found = vfs.resolveFilename(scriptFile, searchPath)
if not found:
    notify.error('Could not find QuestScripts.txt file')
readFile(scriptFile)

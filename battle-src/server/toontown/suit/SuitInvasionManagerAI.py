import json
import os
import random
import time
from direct.directnotify import DirectNotifyGlobal
from toontown.battle import SuitBattleGlobals
from toontown.hood import ZoneUtil
from toontown.suit import SuitDNA
from toontown.toonbase import GameConfig
from toontown.toonbase import ToontownGlobals

class SuitInvasionManagerAI:
    """One Cog invasion at a time in this district. Summoned by a Toon, or started now and then by itself, like the live game's."""
    notify = DirectNotifyGlobal.directNotify.newCategory('SuitInvasionManagerAI')
    RandomCogCount = 1000
    RandomDelay = (10 * 60, 25 * 60)       # seconds between one random invasion ending (or the server starting) and the next
    EXCLUDED = ()
    DurationMinutes = 30                     # an invasion also ends by itself after this long (gameconfig.json: invasion_minutes), so one nobody finishes does not run forever
    SAFE_DISTRICTS = ('Silly Meadow', 'Welcome Valley')       # districts that never have an invasion

    def __init__(self, air):
        self.air = air
        self.cogType = None
        self.skeleton = 0
        self.numSuits = 0
        self.total = 0
        self.nextUpdate = 0
        self.endsAt = 0.0

    def getInvadingCog(self, zoneId=None):
        if not self.getInvading(zoneId):
            return None, 0
        return self.cogType, self.skeleton

    def getInvading(self, zoneId=None):
        return (self.cogType is not None and not self.isSafeDistrict()
                and (zoneId is None or not ZoneUtil.isWelcomeValley(zoneId)))

    def isSafeDistrict(self):
        return getattr(self.air, 'districtName', '') in self.SAFE_DISTRICTS

    def scheduleRandom(self, first=True):
        if self.isSafeDistrict():
            return
        taskMgr.remove('suitInvasionRandom')
        delay = random.uniform(60, 4 * 60) if first else random.uniform(*self.RandomDelay)      # the first one comes soon after the district opens
        taskMgr.doMethodLater(delay, self.__randomInvasion, 'suitInvasionRandom')

    def __randomInvasion(self, task):
        if not self.getInvading():
            names = [n for n in SuitDNA.suitHeadTypes if n not in self.EXCLUDED]
            self.startInvasion(random.choice(names), self.RandomCogCount, random.random() < 0.1)
        self.scheduleRandom(False)
        return task.done

    def startInvasion(self, cogType, numSuits, skeleton=False):
        if self.isSafeDistrict() or self.getInvading() or cogType not in SuitDNA.suitHeadTypes:
            return False
        self.cogType = cogType
        self.skeleton = 1 if skeleton else 0
        self.numSuits = self.total = int(numSuits)
        self.nextUpdate = self.total - max(1, self.total // 10)
        self.notify.warning('invasion begins: %s x%d skeleton=%d' % (cogType, numSuits, self.skeleton))
        self.__broadcast(ToontownGlobals.SuitInvasionBegin)
        taskMgr.remove('suitInvasionTimeout')
        seconds = max(0.1, float(GameConfig.get('invasion_minutes', self.DurationMinutes))) * 60
        self.endsAt = time.time() + seconds
        taskMgr.doMethodLater(seconds, self.__timeout, 'suitInvasionTimeout')
        taskMgr.remove('suitInvasionTick')
        taskMgr.doMethodLater(60.0, self.__tick, 'suitInvasionTick')
        self.__publish()
        self.__pushNotice()
        return True

    def secondsLeft(self):
        return max(0, int(self.endsAt - time.time() + 0.999)) if self.getInvading() else 0

    def minutesLeft(self):
        return (self.secondsLeft() + 59) // 60

    def __tick(self, task):
        """Every minute the district's statistics are sent again, so every client's countdown on the Districts page stays true."""
        if not self.getInvading():
            return task.done
        self.__publish()
        return task.again

    def __pushNotice(self):
        """Ask the server's push service (docker/auth_service.py) to tell the players who turned on Cog invasion notifications. It reads this file
        every few seconds; it keeps one message per few minutes so three districts invading at once is not three messages."""
        try:
            folder = '/ot/data/push'
            if not os.path.isdir(folder):
                return
            attrs = SuitBattleGlobals.SuitAttributes.get(self.cogType)
            plural = 'Skelecogs' if self.skeleton else (attrs['pluralname'] if attrs else 'Cogs')
            district = getattr(self.air, 'districtName', '') or 'Toontown'
            text = '%s are invading %s! About %d minutes left. Join the fight!' % (plural, district, self.minutesLeft())
            with open(os.path.join(folder, 'auto.jsonl'), 'a') as f:
                f.write(json.dumps({'topic': 'invasions', 'title': 'Cog invasion!', 'text': text[:200], 'url': '/play/'}) + '\n')
        except Exception:
            self.notify.warning('could not queue the invasion notification', exc_info=True)

    def __timeout(self, task):
        self.notify.warning('invasion of %s ends: time is up with %d left' % (self.cogType, self.numSuits))
        self.stopInvasion()
        return task.done

    def stopInvasion(self):
        if not self.getInvading():
            return
        taskMgr.remove('suitInvasionTimeout')
        taskMgr.remove('suitInvasionTick')
        self.endsAt = 0.0
        self.__broadcast(ToontownGlobals.SuitInvasionEnd)
        self.cogType = None
        self.skeleton = 0
        self.numSuits = self.total = 0
        self.__publish()

    def handleSuitDefeated(self, zoneId=None):
        if not self.getInvading(zoneId):
            return
        self.numSuits -= 1
        if self.numSuits <= 0:
            self.stopInvasion()
            return
        if self.numSuits <= self.nextUpdate:
            self.nextUpdate = self.numSuits - max(1, self.total // 10)
            self.__broadcast(ToontownGlobals.SuitInvasionUpdate)
        self.__publish()

    def sendBulletin(self, avId):
        toon = self.air.doId2do.get(avId)
        if toon is not None and self.getInvading(toon.zoneId) and getattr(self.air, 'newsManager', None):
            self.air.newsManager.sendUpdateToAvatarId(avId, 'setInvasionStatus', [ToontownGlobals.SuitInvasionBulletin, self.cogType, self.numSuits, self.skeleton])

    def __broadcast(self, msgType):
        if getattr(self.air, 'newsManager', None):
            self.air.newsManager.sendUpdate('setInvasionStatus', [msgType, self.cogType, max(0, self.numSuits), self.skeleton])

    def __publish(self):
        """Let the Districts page in every district see this one's invasion."""
        stats = getattr(self.air, 'districtStats', None)
        if stats is not None:
            stats.b_setInvasion(self.cogType or '', self.skeleton, ToontownGlobals.packInvasionRemaining(max(0, self.numSuits), self.secondsLeft()))

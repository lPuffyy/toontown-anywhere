"""Check installed gag progression, battle previews and district planners."""
import ast
import builtins
from itertools import permutations
from pathlib import Path
from types import SimpleNamespace as NS

builtins.simbase = NS(config=NS())

from toontown.battle import BattleBase
from toontown.hood import ZoneUtil
from toontown.quest import Quests
from toontown.suit.SuitInvasionManagerAI import SuitInvasionManagerAI
from toontown.toonbase import ToontownBattleGlobals as G, ToontownGlobals as T

from check_starter_gags import Starter


def methods(path, class_name, names, scope=None):
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    body = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(body) == len(names)
    namespace = dict(scope or {})
    exec(compile(ast.Module(body=body, type_ignores=[]), path, 'exec'), namespace)
    return {name: namespace[name] for name in names}


def check_tracks():
    Starter.getTrackAccess = lambda toon: toon.trackArray
    Starter.getTrackProgress = lambda toon: (toon.trackProgressId, toon.trackProgress)
    Starter.b_setTrackProgress = lambda toon, track, bits: vars(toon).update(
        trackProgressId=track, trackProgress=bits)
    Starter.addTrackProgress = lambda toon, track, frame: (
        toon.b_setTrackProgress(track, toon.trackProgress | (1 << (frame - 1))))
    Starter.addTrackAccess = lambda toon, track: toon.setChosenTracks([*toon.chosenTracks, track])
    Starter.clearTrackProgress = lambda toon: toon.b_setTrackProgress(-1, 0)

    legacy = Starter()
    legacy.setChosenTracks([])
    assert legacy.trackArray == [0, 0, 0, 0, 1, 1, 0]
    deliveries = [Quests.getQuest(q) for q in Quests.QuestDict
                  if Quests.getQuestClass(q) == Quests.DeliverGagQuest]
    assert deliveries
    for tracks in permutations(range(G.NUM_GAG_TRACKS), 2):
        toon = Starter()
        toon.chooseStartingTracks(list(tracks))
        toon.clearTrackProgress()
        for delivery in deliveries:
            track, level = delivery.getGagType(toon)
            assert track in tracks and level >= 0
        available = Quests.eligibleTrainingTracks(toon)
        assert set(available) == set(range(7)) - set(tracks)
        for track in available:
            reward = Quests.getReward(Quests.getRewardIdFromTrackId(track))
            reward.sendRewardAI(toon)
            assert toon.getTrackProgress() == (track, 0)
            assert track not in Quests.eligibleTrainingTracks(toon)
            for number in range(1, 16):
                frame = Quests.getReward(Quests.transformReward(800 + number, toon))
                assert (frame.getTrack(), frame.getProgressIndex()) == (track, number)
                frame.sendRewardAI(toon)
            assert toon.getTrackProgress() == (track, (1 << 15) - 1)
            completion = Quests.getReward(Quests.transformReward(900, toon))
            completion.sendRewardAI(toon)
            assert toon.hasTrackAccess(track) and track not in Quests.eligibleTrainingTracks(toon)
            restored = Starter()
            restored.setChosenTracks(toon.chosenTracks)
            assert restored.getTrackAccess() == toon.getTrackAccess()
        assert not Quests.eligibleTrainingTracks(toon)
    print('Passed all 42 ordered starter pairs and 210 subsequent training and save/load paths.')

    # These final steps have alternate track-choice quests. Search those
    # continuations instead of sending the Toon back to a starting quest.
    npc = NS(getHq=lambda: False, getNpcId=lambda: 5000)
    for quest_id in (5250, 5258, 5259, 5260):
        quest = Quests.QuestDict[quest_id]
        candidates = quest[Quests.QuestDictNextQuestIndex]
        avatar = NS(getRewardTier=lambda: quest[Quests.QuestDictTierIndex])
        next_quest, _ = Quests.getNextQuest(quest_id, npc, avatar)
        assert next_quest in candidates
        assert Quests.getQuestClass(next_quest) is Quests.TrackChoiceQuest
    print('Passed all four alternate track-choice continuations in the Brrrgh.')


def check_previews():
    names = ('requestGagPreview', '_clearGagPreview', 'd_setGagPreviews', 'exitWaitForInput')
    scope = dict(vars(G))
    scope.update(vars(BattleBase))
    PreviewBattle = type('PreviewBattle', (), methods(
        'toontown/battle/DistributedBattleBaseAI.py', 'DistributedBattleBaseAI', names, scope))
    battle = PreviewBattle()
    sender = 10
    state = 'WaitForInput'
    battle.air = NS(getAvatarIdFromSender=lambda: sender)
    battle.fsm = NS(getCurrentState=lambda: NS(getName=lambda: state))
    battle.timer = NS(stop=lambda: None)
    battle.activeToons = [10, 11]
    battle.activeSuits = [NS(doId=20), NS(doId=21)]
    battle.responses = {}
    battle._gagPreviews = {}
    battle.sent = []
    battle.sendUpdate = lambda method, data: battle.sent.append((method, data))
    battle.getToon = lambda toon_id: NS(hasTrackAccess=lambda t: t != G.DROP_TRACK,
                                        inventory=NS(numItem=lambda t, l: l == 0))
    battle.requestGagPreview(G.THROW_TRACK, 0, -1)
    battle.requestGagPreview(G.THROW_TRACK, 0, 20)
    assert battle.sent[-1][1] == [[10], [G.THROW_TRACK], [0], [20]]
    battle.requestGagPreview(G.THROW_TRACK, 0, 21)
    assert battle.sent[-1][1][-1] == [21]
    before = len(battle.sent)
    for invalid in [(G.THROW_TRACK, 0, 999), (G.THROW_TRACK, 1, 20),
                    (G.DROP_TRACK, 0, 20), (G.HEAL_TRACK, 0, 10)]:
        battle.requestGagPreview(*invalid)
    assert len(battle.sent) == before
    sender = 11
    battle.requestGagPreview(G.HEAL_TRACK, 0, 10)
    assert battle.sent[-1][1][-1] == [21, 10]
    battle.requestGagPreview(G.SOUND_TRACK, 0, -1)
    assert battle.sent[-1][1][1] == [G.THROW_TRACK, G.SOUND_TRACK]
    battle.requestGagPreview(-1, -1, -1)
    assert battle.sent[-1][1][0] == [10]
    battle.exitWaitForInput()
    assert battle.sent[-1][1] == [[], [], [], []]
    state = 'PlayMovie'
    battle.requestGagPreview(G.THROW_TRACK, 0, 21)
    assert not battle._gagPreviews
    print('Passed two-Toon previews, single and group targets, invalid choices, cancel and round cleanup.')


def check_districts():
    air = NS(districtName='Test District', doId2do={1: NS(zoneId=22100), 2: NS(zoneId=2100)})
    manager = SuitInvasionManagerAI(air)
    manager.cogType, manager.skeleton, manager.numSuits, manager.nextUpdate = 'f', 1, 100, 50
    messages = []
    air.newsManager = NS(sendUpdateToAvatarId=lambda *args: messages.append(args))
    for zone in (T.WelcomeValleyToken, 22000, 22100, 22200, 22300, 23000):
        assert ZoneUtil.isWelcomeValley(zone)
        assert manager.getInvadingCog(zone) == (None, 0)
        assert not manager.getInvading(zone)
        manager.handleSuitDefeated(zone)
    assert manager.numSuits == 100
    assert manager.getInvadingCog(2100) == ('f', 1)
    manager.handleSuitDefeated(2100)
    assert manager.numSuits == 99
    manager.sendBulletin(1)
    manager.sendBulletin(2)
    assert len(messages) == 1 and messages[0][0] == 2
    for district in ('Welcome Valley', 'Silly Meadow'):
        air.districtName = district
        assert not manager.startInvasion('f', 100)
    planner_path = 'toontown/suit/DistributedSuitPlannerAI.py'
    names = ('calcDesiredNumFlyInSuits', 'upkeepSuitPopulation')
    Planner = type('Planner', (), methods(planner_path, 'DistributedSuitPlannerAI', names,
                                          {'Task': NS(done='done')}))
    for zone in (2100, 22100, 9100):
        planner = Planner()
        planner.zoneId = zone
        planner.streetPopulation = 9
        planner.TOTAL_MAX_SUITS = 50
        planner.SUIT_BUILDING_NUM_SUITS = 1.5
        planner.currDesired = None
        planner.buildingMgr = None
        planner.notify = NS(getDebug=lambda: False)
        planner.numFlyInSuits = planner.numBuildingSuits = 0
        planner.streetPointList = list(range(20))
        planner.suitList = []
        planner._DistributedSuitPlannerAI__waitForNextUpkeep = lambda: None
        # The extracted method compiles with a plain function name, so also supply
        # the unmangled private helper that a normal class would provide.
        planner.__waitForNextUpkeep = lambda: None

        def spawn(blocks, points):
            if not points or len(planner.suitList) >= planner.streetPopulation:
                return None
            planner.suitList.append(points.pop())
            planner.numFlyInSuits += 1
            return True

        planner.createNewSuit = spawn
        for _ in range(9):
            planner.upkeepSuitPopulation(None)
            assert len(planner.suitList) <= 9
        assert len(planner.suitList) == 9
        planner.suitList.pop()
        planner.numFlyInSuits -= 1
        planner.upkeepSuitPopulation(None)
        assert len(planner.suitList) == 9
    print('Passed zone-aware invasion and bulletin checks and simulated population/respawn checks.')


if __name__ == '__main__':
    check_tracks()
    check_previews()
    check_districts()

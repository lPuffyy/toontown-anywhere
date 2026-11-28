"""Exercise starter grant and shop rules using the installed server modules."""
from itertools import permutations
from types import SimpleNamespace
from copy import deepcopy
import ast
from pathlib import Path

from toontown.toon.InventoryBase import InventoryBase
from toontown.toonbase import ToontownBattleGlobals as g, ToontownGlobals

source = Path('toontown/toon/DistributedToonAI.py')
methods = {'chooseStartingTracks', 'setChosenTracks', 'setBlockCooldown',
           'getBlockCooldown', 'b_setBlockCooldown', 'getChosenTracks', 'fixTrackAccess'}
tree = ast.parse(source.read_text(encoding='utf-8'))
toon_ai = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == 'DistributedToonAI')
selected = ast.Module(body=[node for node in toon_ai.body
                            if isinstance(node, ast.FunctionDef) and node.name in methods],
                      type_ignores=[])
namespace = {'ToontownBattleGlobals': g}
exec(compile(selected, str(source), 'exec'), namespace)


class Starter:
    chooseStartingTracks = namespace['chooseStartingTracks']
    setChosenTracks = namespace['setChosenTracks']
    b_setBlockCooldown = namespace['b_setBlockCooldown']
    getBlockCooldown = namespace['getBlockCooldown']
    setBlockCooldown = namespace['setBlockCooldown']
    getChosenTracks = namespace['getChosenTracks']
    fixTrackAccess = namespace['fixTrackAccess']
    b_setChosenTracks = setChosenTracks
    notify = SimpleNamespace(warning=lambda *args: None, info=lambda *args: None)

    def __init__(self):
        self.chosenTracks = []
        self.tutorialAck = 0
        self.trackArray = [int(t in (g.THROW_TRACK, g.SQUIRT_TRACK)) for t in range(g.NUM_GAG_TRACKS)]
        self.experience = SimpleNamespace(getExpLevel=lambda track: 0)
        self.inventory = InventoryBase(self)
        self.sent = []
        for track in (g.THROW_TRACK, g.SQUIRT_TRACK):
            self.inventory.addItem(track, 0)

    def getTutorialAck(self):
        return self.tutorialAck

    def d_setChosenTracks(self, tracks):
        self.sent.append(('setChosenTracks', list(tracks)))

    def b_setTrackAccess(self, tracks):
        self.trackArray = tracks

    def hasTrackAccess(self, track):
        return self.trackArray[track]

    def getGameAccess(self):
        return ToontownGlobals.AccessFull

    def getMaxCarry(self):
        return 20

    def d_setInventory(self, blob):
        self.sent.append(blob)

    def sendUpdate(self, event, args):
        self.sent.append((event, args))


def main():
    tested = 0
    for tracks in permutations(range(g.NUM_GAG_TRACKS), 2):
        toon = Starter()
        assert not toon.fixTrackAccess() and not toon.getChosenTracks()
        toon.chooseStartingTracks(list(tracks))
        inv = toon.inventory
        expected = [int(t in tracks) for t in range(g.NUM_GAG_TRACKS)]
        assert [inv.numItem(t, 0) for t in range(g.NUM_GAG_TRACKS)] == expected, tracks
        restored = InventoryBase(toon, inv.makeNetString())
        assert restored.inventory == inv.inventory
        toon.chooseStartingTracks(list(reversed(tracks)))
        assert inv.totalProps == 2 and toon.chosenTracks == list(tracks)
        for track in tracks:
            proposed = deepcopy(inv.inventory)
            proposed[track][0] = inv.getMax(track, 0)
            cost = proposed[track][0] - inv.numItem(track, 0)
            assert cost > 1 and inv.validatePurchase(proposed, 20, 20 - cost), tracks
            assert inv.addItem(track, 0) < 0
            assert inv.useItem(track, 0) != -1
            assert inv.addItem(track, 0) == inv.getMax(track, 0)
        for track in set(range(g.NUM_GAG_TRACKS)) - set(tracks):
            assert inv.addItem(track, 0) == 0
        tested += 1
    legacy = Starter()
    legacy.tutorialAck = 1
    legacy.trackArray = [1, 0, 1, 0, 0, 0, 1]
    assert legacy.fixTrackAccess() and legacy.getChosenTracks() == [0, 2, 6]
    legacy.chooseStartingTracks([3, 4])
    assert legacy.getChosenTracks() == [0, 2, 6]
    toon.b_setBlockCooldown(3)
    assert toon.getBlockCooldown() == 3
    assert toon.sent[-1] == ('setBlockCooldown', [3])
    print('Passed starter grant, save format, purchase limits and delete/rebuy for %d ordered pairs.' % tested)


if __name__ == '__main__':
    main()

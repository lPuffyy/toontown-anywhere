"""Reads every ToonTask (quest) out of the game's own code and writes them to a JSON file, for build_quest_guide.py.

Run it from the root of the open-toontown-anywhere checkout, with a Python 3.9 that has Panda3D 1.11 (the game's own Python):

    cd open-toontown-anywhere
    python /path/to/tools/extract_quests.py quests.json
    python /path/to/tools/build_quest_guide.py quests.json docs/quest-guide.html

It imports toontown.quest.Quests (through otpy, so no compiled game libraries are needed) and asks the game itself for the
text, the NPC names and places, and the rewards, so the guide cannot drift from what the server does.
"""
import sys, builtins, types, json, collections
sys.path.insert(0, '.')
import otpy.install
otpy.install.install()
from direct.showbase import ShowBaseGlobal
class _Hood:
    def getFullnameFromId(self, i):
        from toontown.toonbase import ToontownGlobals as _TG
        return _TG.hoodNameMap.get(i, ('', '', str(i)))[-1]
builtins.base = types.SimpleNamespace(config=ShowBaseGlobal.config, destroy=lambda: None, cr=types.SimpleNamespace(hoodMgr=_Hood()))
builtins.simbase = builtins.base
from toontown.quest import Quests as Q
from toontown.toon import NPCToons
from toontown.toonbase import ToontownGlobals as TG, TTLocalizer as L
from toontown.hood import ZoneUtil

class _Names:
    """hood id -> the game's own name for it (Dock Harbor, Melody Meadow, ...)"""
    def get(self, i, default=None):
        return TG.hoodNameMap.get(i, ('', '', default))[-1]
    def __contains__(self, i):
        return i in TG.hoodNameMap
    def __getitem__(self, i):
        return TG.hoodNameMap[i][-1]
HOODS = _Names()

def npc(npcId):
    """name and place of an NPC id (special ids are handled by name)"""
    if npcId == Q.ToonHQ: return {'name': 'Toon HQ (any Toon HQ officer)', 'place': 'any Toon HQ', 'hq': True}
    if npcId == Q.ToonTailor: return {'name': 'a Tailor (Toon Tailor)', 'place': 'a Clothing Store'}
    if npcId == Q.Any: return {'name': 'any Toon', 'place': 'any'}
    if npcId == Q.Same: return {'name': 'the same Toon', 'place': 'same place'}
    if npcId == Q.NA or npcId is None: return None
    name = NPCToons.getNPCName(npcId)
    zone = NPCToons.getNPCZone(npcId)
    if name is None or zone is None: return {'name': 'NPC %s' % npcId, 'place': '?'}
    branch = ZoneUtil.getCanonicalBranchZone(zone)
    hood = ZoneUtil.getCanonicalHoodId(zone)
    street = TG.StreetNames.get(branch, [''])[-1]
    building = NPCToons.getBuildingTitle(zone)
    place = street if branch != hood else 'Playground'
    return {'id': npcId, 'name': name, 'hood': HOODS.get(hood, str(hood)), 'street': street, 'building': building,
            'playground': branch == hood}

def locname(loc):
    if loc in (Q.Anywhere, None): return ''
    if loc in HOODS: return HOODS[loc]
    name = TG.StreetNames.get(loc, [''])[-1]
    return name or str(loc)

def rewardinfo(rid):
    if rid in (Q.NA, None): return None
    if rid == Q.Any: return {'any': True}
    # 801-899 and 900 stand for "your chosen gag track": the game swaps in the real track when it gives the reward
    if 801 <= rid <= 899:
        return {'id': rid, 'kind': 'TrackProgressReward', 'text': 'Gag training, frame %d of your chosen track' % (rid - 800)}
    if rid == 900:
        return {'id': rid, 'kind': 'TrackCompleteReward', 'text': 'Final training for your chosen gag track'}
    cls = Q.getRewardClass(rid)
    if cls is None: return {'id': rid, 'text': 'reward %s' % rid}
    r = Q.getReward(rid)
    return {'id': rid, 'kind': cls.__name__, 'text': r.getPosterString().replace('Reward: ', ''), 'long': r.getString()}

steps = {}
for qid, e in sorted(Q.QuestDict.items()):
    tier, start, desc, frm, to, rew, nxt, dlg = e
    if nxt == Q.OBSOLETE or start == Q.OBSOLETE or rew == Q.OBSOLETE or start not in (Q.Start, Q.Cont):
        steps[qid] = {'id': qid, 'tier': tier, 'obsolete': True}
        continue
    qq = Q.getQuest(qid)
    cls = desc[0].__name__
    try: poster = qq.getPosterString()
    except Exception: poster = qq.getString()
    try: loc = locname(qq.getLocation())
    except Exception: loc = ''
    intro = None
    if isinstance(dlg, dict):
        v = dlg.get(Q.QUEST)
        if isinstance(v, (list, tuple)): v = v[0] if v else None
        intro = v
    nxtl = [] if nxt == Q.NA else (list(nxt) if isinstance(nxt, tuple) else [nxt])
    steps[qid] = {'id': qid, 'tier': tier, 'start': start == Q.Start, 'cls': cls, 'text': poster, 'headline': qq.getHeadlineString(),
                  'loc': loc, 'from': npc(frm), 'to': npc(to), 'reward': rewardinfo(rew), 'next': nxtl, 'intro': intro}
print('steps', len(steps), 'obsolete', sum(1 for s in steps.values() if s.get('obsolete')))

tiers = {}
for t in sorted(Q.RequiredRewardTrackDict):
    tiers[t] = {'tier': t, 'required': [rewardinfo(r) for r in Q.getRewardsInTier(t)], 'optional': [rewardinfo(r) for r in Q.getOptionalRewardsInTier(t)],
                'choices': Q.getNumChoices(t), 'starts': sorted(q for q, s in steps.items() if s.get('tier') == t and s.get('start')),
                'loop': Q.isLoopingFinalTier(t)}
out = {'steps': steps, 'tiers': tiers,
       'finalReward': {q: Q.Quest2RewardDict.get(q) for q in steps}}
json.dump(out, open(sys.argv[1], 'w'), indent=0, default=str)
print('tiers', len(tiers))

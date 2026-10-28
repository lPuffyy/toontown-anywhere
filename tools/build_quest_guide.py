"""Builds the quest guide (one self-contained HTML file) from the JSON that extract_quests.py writes.

    python tools/build_quest_guide.py quests.json docs/quest-guide.html
"""
import html
import json
import re
import sys

src, dst = sys.argv[1], sys.argv[2]
data = json.load(open(src, encoding='utf8'))
steps = {int(k): v for k, v in data['steps'].items() if not v.get('obsolete')}
tiers = {int(k): v for k, v in data['tiers'].items()}
final = {int(k): v for k, v in data['finalReward'].items()}

AREAS = [(0, 3, 'Toontown Central'), (4, 6, 'Dock Harbor'), (7, 7, 'Garden Grove'), (8, 10, 'Melody Meadow'),
         (11, 13, 'The Brrrgh'), (14, 17, 'Slumber Springs'), (18, 31, 'Lawbot HQ cog suit parts'),
         (32, 48, 'Bossbot HQ cog suit parts'), (49, 49, 'The final tier')]
CAT = {'CogQuest': 'fight', 'CogLevelQuest': 'fight', 'CogTrackQuest': 'fight', 'BuildingQuest': 'fight', 'FactoryQuest': 'fight',
       'MintQuest': 'fight', 'SkelecogQuest': 'fight', 'SkelecogLevelQuest': 'fight', 'SkelecogTrackQuest': 'fight',
       'SkeleReviveQuest': 'fight', 'ForemanQuest': 'fight', 'SupervisorQuest': 'fight', 'VPQuest': 'fight', 'CFOQuest': 'fight',
       'RescueQuest': 'fight', 'CogPartQuest': 'fight', 'DeliverItemQuest': 'errand', 'DeliverGagQuest': 'errand',
       'RecoverItemQuest': 'errand', 'VisitQuest': 'errand', 'FriendQuest': 'social', 'TrolleyQuest': 'social',
       'PhoneQuest': 'social', 'TrackChoiceQuest': 'choose'}


def esc(s):
    return html.escape(str(s), quote=True)


def category(s):
    c = s['cls']
    if c.endswith('NewbieQuest'):
        return 'helper'
    return CAT.get(c, 'fight')


def place(n):
    if not n or 'street' not in n:
        return ''
    where = 'Playground' if n.get('playground') else n['street']
    return '%s, %s (%s)' % (n['building'], where, n['hood'])


def who(n, start=False):
    if not n:
        return ''
    if n['name'].startswith('any Toon'):
        return 'any Toon' if start else 'whoever gave it to you'
    if n['name'].startswith('the same Toon'):
        return 'the Toon who gave you the task'
    if n['name'].startswith('Toon HQ'):
        return 'any Toon HQ'
    if n['name'].startswith('a Tailor'):
        return 'a Tailor (Clothing Store)'
    p = place(n)
    return '<b>%s</b>' % esc(n['name']) + (' <span class="muted">%s</span>' % esc(p) if p else '')


def dialogue(s):
    t = s.get('intro')
    if not t:
        return ''
    to = s.get('to') or {}
    t = t.replace('_avName_', 'Toon').replace('_toNpcName_', to.get('name', 'someone'))
    t = t.replace('_where_', ' (%s)' % place(to) if place(to) else '')
    t = t.replace('_buildingName_', to.get('building', '')).replace('_streetDesc_', to.get('street', ''))
    paras = [p.strip() for p in re.split('[\x07\n]+', t) if p.strip()]
    return '<details class="say"><summary>What they say</summary>%s</details>' % ''.join('<p>%s</p>' % esc(p) for p in paras)


def reward_text(r):
    if not r:
        return ''
    if r.get('any'):
        return ''
    return esc(r['text'])


rendered = set()


def giver_text(n):
    """Who hands the player this step. A step is handed out by the Toon the previous step was handed in to."""
    if not n:
        return ''
    name = n['name']
    if name.startswith('any Toon'):
        return 'any Toon that offers tasks (Toon HQ officers do)'
    if name.startswith('the same Toon'):
        return 'the Toon who sent you'
    return who(n, True)


def hand_in_target(to, giver):
    """The Toon this step is handed in to; "the same Toon" means whoever handed it out."""
    if to and to['name'].startswith('the same Toon') and giver:
        return giver
    return to


def render_step(qid, num=1, giver=None):
    """A step, then (flat) the steps that follow it; real branches are nested."""
    s = steps.get(qid)
    if not s:
        return ''
    if qid in rendered:
        return '<li class="again"><a href="#q%d">Continues at step %d (shown above)</a></li>' % (qid, qid)
    rendered.add(qid)
    if giver is None:
        giver = s.get('from')
    cat = category(s)
    nxt = [n for n in s['next'] if n in steps]
    to = s.get('to')
    to_eff = hand_in_target(to, giver)
    visit = s['cls'] == 'VisitQuest' and to and 'street' in to
    what = 'Visit %s' % to['name'] if visit else s['text']
    parts = ['<li class="step" id="q%d"><span class="num">%d</span><div class="sb"><span class="tag %s">%s</span> <span class="what">%s</span>' % (
        qid, num, cat, esc(s['headline'].title()), esc(what))]
    meta = ['<span class="from">Get it from %s</span>' % giver_text(giver)]
    if visit:
        meta.append('<span class="muted">%s</span>' % esc(place(to)))
    elif to_eff and not nxt:
        meta.append('Hand in to %s' % who(to_eff))
    elif to_eff:
        meta.append('Then go to %s' % who(to_eff))
    if not nxt and s.get('reward') and not s['reward'].get('any'):
        meta.append('<span class="reward">Reward: %s</span>' % reward_text(s['reward']))
    elif not nxt:
        meta.append('<span class="reward">Reward: whichever tier reward you picked</span>')
    parts.append('<div class="meta">%s</div>' % ' &middot; '.join(meta))
    parts.append(dialogue(s))
    parts.append('</div>')
    if len(nxt) > 1:
        parts.append('<ul class="next branch"><li class="branchnote">Then one of these (the game picks):</li>')
        parts.extend(render_step(n, num + 1, to_eff) for n in nxt)
        parts.append('</ul>')
    parts.append('</li>')
    if len(nxt) == 1:
        parts.append(render_step(nxt[0], num + 1, to_eff))
    return ''.join(parts)


def chain_summary(qid):
    """Single-line label for a chain: the first step's text and how long it is."""
    n, cur, seen = 1, qid, set()
    while True:
        nxt = [x for x in steps[cur]['next'] if x in steps]
        if not nxt or cur in seen:
            return n
        seen.add(cur)
        cur = nxt[0]
        n += 1


def render_tier(t):
    td = tiers[t]
    starts = [q for q in td['starts'] if q in steps]
    req = [r for r in td['required'] if r]
    opt = [r for r in td['optional'] if r]
    fixed, generic = {}, []
    for q in starts:
        f = final.get(q)
        if f is None or f == 1:
            generic.append(q)
        else:
            fixed.setdefault(f, []).append(q)
    out = ['<details class="tier" id="tier%d" data-tier="%d"><summary><span class="tn">Tier %d</span> <span class="tsum">%d required reward%s · %d task chain%s</span></summary>' % (
        t, t, t, len(req), '' if len(req) == 1 else 's', len(starts), '' if len(starts) == 1 else 's')]
    out.append('<div class="tbody">')
    if td['loop']:
        out.append('<p class="note">This is the last tier. When you finish it, it starts over, so the same kinds of task keep coming.</p>')
    n = td['choices']
    out.append('<p class="note">%s</p>' % ('Tasks are handed to you one at a time.' if n == 0 else
                                            'Each time you ask for a task you are offered up to %d to pick from.' % n))
    out.append('<div class="rewards"><h4>Rewards you must earn to finish this tier (in this order)</h4><ol>%s</ol></div>' % ''.join(
        '<li>%s</li>' % esc(r['text']) for r in req))
    if opt:
        seen, items = {}, []
        for r in opt:
            seen[r['text']] = seen.get(r['text'], 0) + 1
        for k, v in seen.items():
            items.append('%s%s' % (esc(k), ' ×%d' % v if v > 1 else ''))
        out.append('<div class="rewards just"><h4>Just for fun rewards (extra tasks, not needed to move on)</h4><p>%s</p></div>' % ' · '.join(items))

    def chain_block(q, label=None):
        text = steps[q]['text']
        length = chain_summary(q)
        vto = steps[q].get('to') or {}
        head = esc(text if steps[q]['cls'] != 'VisitQuest' or 'name' not in vto else 'Visit %s' % vto['name'])
        return '<details class="chain" data-q="%d"><summary><span class="tag %s">%s</span> %s <span class="muted">%s &middot; from %s</span></summary><ul class="tree">%s</ul></details>' % (
            q, category(steps[q]), esc(steps[q]['headline'].title()), head, ('%d steps' % length) if length > 1 else '1 step', re.sub('<.*?>', '', giver_text(steps[q].get('from'))), render_step(q))

    if fixed:
        out.append('<h4>Set task chains (each ends in a particular reward)</h4>')
        order = {r['id']: i for i, r in enumerate(req)}
        for rid in sorted(fixed, key=lambda r: (order.get(r, 999), r)):
            info = next((r for r in req + opt if r['id'] == rid), None)
            title = info['text'] if info else 'reward %s' % rid
            out.append('<div class="group"><div class="gh">Ends with: <b>%s</b></div>%s</div>' % (esc(title), ''.join(chain_block(q) for q in fixed[rid])))
    if generic:
        out.append('<h4>Open task pool (the reward is the one you picked)</h4><p class="note">These can be given for any of the tier\'s rewards. %d chains.</p>' % len(generic))
        out.append('<div class="group pool">%s</div>' % ''.join(chain_block(q) for q in generic))
    out.append('</div></details>')
    return ''.join(out)


def area_for(t):
    for a, b, n in AREAS:
        if a <= t <= b:
            return n
    return 'Other'


body, nav = [], []
for a, b, name in AREAS:
    ts = [t for t in sorted(tiers) if a <= t <= b]
    if not ts:
        continue
    aid = re.sub('[^a-z]+', '-', name.lower()).strip('-')
    label = ('Tier %d' % a) if a == b else 'Tiers %d–%d' % (a, b)
    nav.append('<a href="#%s">%s<small>%s</small></a>' % (aid, esc(name), label))
    body.append('<section class="area" id="%s"><h2>%s <span class="muted">%s</span></h2>%s</section>' % (aid, esc(name), label, ''.join(render_tier(t) for t in ts)))

total_steps, total_chains = len(steps), sum(len([q for q in t['starts'] if q in steps]) for t in tiers.values())
page = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Toontown: Anywhere Quest Guide</title>
<style>
:root{--bg:#f6f4ef;--card:#fff;--ink:#1c1b22;--muted:#6a6878;--line:#e3e0d8;--accent:#7a3bd6;--accent2:#0e8a6a;--fight:#c2403a;--errand:#2f6fd0;--social:#0e8a6a;--choose:#b5760a;--helper:#8a4fd0;--shadow:0 1px 2px rgba(0,0,0,.06)}
@media (prefers-color-scheme:dark){:root{--bg:#14131a;--card:#1d1c26;--ink:#ecebf3;--muted:#9a98ab;--line:#2d2b3a;--accent:#a678f0;--accent2:#3cc9a0;--fight:#f07a72;--errand:#7aa7f5;--social:#3cc9a0;--choose:#f0b24d;--helper:#b88cf5;--shadow:none}}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:920px;margin:0 auto;padding:0 16px 64px}
header{padding:36px 0 12px}header h1{margin:0 0 6px;font-size:clamp(26px,5vw,38px);letter-spacing:-.02em}
header p{margin:0;color:var(--muted);max-width:62ch}
.how{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:6px 18px 14px;margin:18px 0;box-shadow:var(--shadow)}
.how h3{margin:14px 0 4px;font-size:16px}.how p,.how li{margin:4px 0;color:var(--ink)}.how ul{padding-left:20px;margin:4px 0}
.bar{position:sticky;top:0;z-index:5;background:var(--bg);padding:10px 0;border-bottom:1px solid var(--line);margin:0 0 4px}
.bar input{width:100%;font:inherit;padding:11px 14px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
.bar .row{display:flex;gap:8px;margin-top:8px;align-items:center;flex-wrap:wrap}
.bar button{font:inherit;font-size:14px;padding:6px 12px;border-radius:999px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
#count{color:var(--muted);font-size:14px}
nav.toc{display:flex;gap:8px;overflow-x:auto;padding:12px 0;scrollbar-width:thin}
nav.toc a{flex:0 0 auto;text-decoration:none;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:12px;padding:8px 12px;font-weight:600;font-size:14px;display:flex;flex-direction:column}
nav.toc a small{color:var(--muted);font-weight:400}
h2{margin:34px 0 10px;font-size:24px;letter-spacing:-.01em;scroll-margin-top:110px}h2 .muted{font-size:14px;font-weight:400}
h4{margin:16px 0 6px;font-size:14px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.muted{color:var(--muted);font-size:.92em}
details.tier{background:var(--card);border:1px solid var(--line);border-radius:14px;margin:10px 0;box-shadow:var(--shadow)}
details.tier>summary{padding:14px 18px;cursor:pointer;display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;list-style:none}
details.tier>summary::-webkit-details-marker{display:none}
details.tier>summary::before{content:"▸";color:var(--muted);transition:transform .15s}details.tier[open]>summary::before{transform:rotate(90deg)}
.tn{font-weight:700;font-size:18px}.tsum{color:var(--muted);font-size:14px}
.tbody{padding:0 18px 16px}.note{color:var(--muted);margin:6px 0}
.rewards ol{margin:4px 0;padding-left:22px;columns:1}@media(min-width:700px){.rewards ol{columns:2}}
.rewards.just p{margin:4px 0;color:var(--ink)}
.group{margin:8px 0}.gh{margin:10px 0 4px;color:var(--accent);font-size:14px}
details.chain{border:1px solid var(--line);border-radius:10px;margin:6px 0;background:var(--bg)}
details.chain>summary{padding:9px 12px;cursor:pointer}
ul.tree,ul.next{list-style:none;margin:0;padding:0 12px 10px}ul.next{padding:6px 0 0 18px;border-left:2px solid var(--line);margin-left:6px}
li.step{margin:8px 0;display:flex;flex-wrap:wrap;gap:0 10px}li.step>.sb{flex:1 1 0;min-width:0}.num{flex:0 0 24px;height:24px;border-radius:50%;background:var(--line);color:var(--ink);font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center;margin-top:1px}li.step>ul.next{flex:1 0 100%}.what{font-weight:600}.meta{color:var(--ink);font-size:14.5px;margin:2px 0 0 2px}
.reward{color:var(--accent2);font-weight:600}.from{font-weight:600}
li.branchnote{color:var(--muted);font-style:italic;font-size:14px}li.again{font-size:14px}li.again a{color:var(--accent)}
.tag{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.06em;padding:2px 7px;border-radius:6px;color:#fff;vertical-align:1px}
.tag.fight{background:var(--fight)}.tag.errand{background:var(--errand)}.tag.social{background:var(--social)}.tag.choose{background:var(--choose)}.tag.helper{background:var(--helper)}
details.say{margin:4px 0 0 2px}details.say>summary{cursor:pointer;color:var(--muted);font-size:13.5px}details.say p{margin:6px 0;padding-left:10px;border-left:3px solid var(--line);font-size:14.5px}
.hidden{display:none!important}
mark{background:#ffe27a;color:#222;border-radius:3px}
footer{color:var(--muted);font-size:13.5px;margin-top:40px;border-top:1px solid var(--line);padding-top:14px}
@media print{.bar,nav.toc{display:none}details>*{display:block!important}}
</style></head><body><div class="wrap">
<header><h1>Toontown: Anywhere Quest Guide</h1>
<p>Every ToonTask in the game, in the order the game gives them: @@CHAINS@@ task chains and @@STEPS@@ steps across 50 tiers, read straight out of the game's own quest data.</p></header>

<div class="how">
<h3>How the quest line works</h3>
<ul>
<li>The game is split into <b>tiers</b>. Each tier has a list of <b>required rewards</b> (Laff boosts, gag training, pouches, cog suit parts…). Earn all of them and you move to the next tier.</li>
<li>When you ask Toon HQ or a Toon for a task, you are offered up to three. Each is tied to one of the rewards you still need, or to a bonus "just for fun" reward.</li>
<li>A <b>task chain</b> has one or more steps. You only get the reward after the <b>last</b> step; the steps in between are just errands that lead there.</li>
<li>Where a step lists several next steps, the game picks one. The open task pool is a shared list of chains that can be given for any reward in that tier.</li>
<li>Tasks marked <span class="tag helper">HELPER</span> are for helping a Toon with a low Laff meter, and are only offered to Toons who qualify.</li>
</ul>
<h3>Colours</h3>
<p><span class="tag fight">WANTED</span> / <span class="tag fight">DEFEAT</span> fight Cogs · <span class="tag errand">DELIVER</span> / <span class="tag errand">RECOVER</span> / <span class="tag errand">VISIT</span> errands · <span class="tag social">FRIEND</span> / <span class="tag social">TROLLEY</span> / <span class="tag social">CLARABELLE</span> social · <span class="tag choose">CHOOSE</span> pick a gag track</p>
</div>

<div class="bar"><input id="q" type="search" placeholder="Search tasks, Toons, places, rewards…" autocomplete="off">
<div class="row"><button id="open">Open all tiers</button><button id="close">Close all</button><span id="count"></span></div></div>
<nav class="toc">@@NAV@@</nav>
@@BODY@@
<footer>Generated from the game's quest data (<code>toontown/quest/Quests.py</code> in the open-toontown-anywhere fork). Names, places and reward text come from the game itself.</footer>
</div>
<script>
(function(){
var q=document.getElementById('q'),count=document.getElementById('count');
var chains=[].slice.call(document.querySelectorAll('details.chain')),tiers=[].slice.call(document.querySelectorAll('details.tier'));
chains.forEach(function(c){c._t=(c.textContent||'').toLowerCase();});
function run(){
 var v=q.value.trim().toLowerCase(),n=0;
 if(!v){chains.forEach(function(c){c.classList.remove('hidden');});tiers.forEach(function(t){t.classList.remove('hidden');});count.textContent='';return;}
 chains.forEach(function(c){var m=c._t.indexOf(v)>=0;c.classList.toggle('hidden',!m);if(m)n++;});
 tiers.forEach(function(t){var any=t.querySelector('details.chain:not(.hidden)');var tm=(t.querySelector('.tbody')||t).textContent.toLowerCase();var rm=t.querySelector('.rewards')&&t.querySelector('.rewards').textContent.toLowerCase().indexOf(v)>=0;
  t.classList.toggle('hidden',!any&&!rm);if(any||rm)t.open=true;});
 count.textContent=n+' matching chain'+(n==1?'':'s');
}
q.addEventListener('input',run);
document.getElementById('open').onclick=function(){tiers.forEach(function(t){t.open=true;});};
document.getElementById('close').onclick=function(){tiers.forEach(function(t){t.open=false;});chains.forEach(function(c){c.open=false;});};
if(location.hash){var el=document.querySelector(location.hash);if(el){var d=el;while(d){if(d.tagName=='DETAILS')d.open=true;d=d.parentElement;}el.scrollIntoView();}}
document.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('li.again a');if(!a)return;var el=document.querySelector(a.getAttribute('href'));if(!el)return;var d=el;while(d){if(d.tagName=='DETAILS')d.open=true;d=d.parentElement;}});
})();
</script></body></html>'''
page = page.replace('@@CHAINS@@', str(total_chains)).replace('@@STEPS@@', str(total_steps)).replace('@@NAV@@', ''.join(nav)).replace('@@BODY@@', ''.join(body))
open(dst, 'w', encoding='utf8', newline='\n').write(page)
print('wrote', dst, len(page) // 1024, 'KB;', total_chains, 'chains', total_steps, 'steps')

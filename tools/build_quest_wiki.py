"""Builds the quest guide as wiki pages (plain Markdown) from the JSON that extract_quests.py writes.

    python tools/build_quest_wiki.py quests.json docs/wiki

Writes Home.md, _Sidebar.md and one page per area (an area with a lot of tasks is split into one page per tier). The links between
pages are ordinary Markdown links to page names without ".md", which GitHub wikis and most self-hosted wikis understand.
"""
import json
import os
import re
import sys

src, outdir = sys.argv[1], sys.argv[2]
data = json.load(open(src, encoding='utf8'))
steps = {int(k): v for k, v in data['steps'].items() if not v.get('obsolete')}
tiers = {int(k): v for k, v in data['tiers'].items()}
final = {int(k): v for k, v in data['finalReward'].items()}
os.makedirs(outdir, exist_ok=True)
for old in os.listdir(outdir):
    if old.endswith('.md'):
        os.remove(os.path.join(outdir, old))

AREAS = [(0, 3, 'Toontown Central'), (4, 6, 'Dock Harbor'), (7, 7, 'Garden Grove'), (8, 10, 'Melody Meadow'),
         (11, 13, 'The Brrrgh'), (14, 17, 'Slumber Springs'), (18, 31, 'Lawbot HQ cog suit parts'),
         (32, 48, 'Bossbot HQ cog suit parts'), (49, 49, 'The final tier')]
SPLIT_OVER = 120000          # bytes: an area page bigger than this becomes one page per tier


def slug(s):
    return re.sub(r'[^A-Za-z0-9]+', '-', s).strip('-')


def md(s):
    return str(s).replace('*', '\\*').replace('_', '\\_').replace('<', '&lt;')


def place(n):
    if not n or 'street' not in n:
        return ''
    return '%s, %s (%s)' % (n['building'], 'Playground' if n.get('playground') else n['street'], n['hood'])


def who(n, start=False):
    if not n:
        return ''
    name = n['name']
    if name.startswith('any Toon'):
        return 'any Toon' if start else 'whoever gave you the task'
    if name.startswith('the same Toon'):
        return 'the Toon who gave you the task'
    if name.startswith('Toon HQ'):
        return 'any Toon HQ'
    if name.startswith('a Tailor'):
        return 'a Tailor (Clothing Store)'
    p = place(n)
    return '**%s**%s' % (md(name), (' (%s)' % md(p)) if p else '')


def category(s):
    return 'Helper' if s['cls'].endswith('NewbieQuest') else s['headline'].title()


def task(s):
    to = s.get('to')
    if s['cls'] == 'VisitQuest' and to and 'street' in to:
        return 'Visit %s' % to['name']
    return s['text']


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
    if to and to['name'].startswith('the same Toon') and giver:
        return giver
    return to


def step_line(qid, num, indent, rendered, giver):
    s = steps[qid]
    rendered.add(qid)
    nxt = [n for n in s['next'] if n in steps]
    to = s.get('to')
    to_eff = hand_in_target(to, giver)
    bits = ['get it from %s' % giver_text(giver)]
    visit = s['cls'] == 'VisitQuest' and to and 'street' in to
    if visit:
        bits.append(md(place(to)))
    elif to_eff and not nxt:
        bits.append('hand in to %s' % who(to_eff))
    elif to_eff:
        bits.append('then go to %s' % who(to_eff))
    if not nxt:
        r = s.get('reward')
        bits.append('**Reward: %s**' % (md(r['text']) if r and not r.get('any') else 'the tier reward you picked'))
    line = '%s%d. `%s` **%s** (%s)' % (indent, num, category(s), md(task(s)), '; '.join(bits))
    return line, nxt, to_eff


def render_chain(qid, rendered, num=1, indent='', giver=None):
    lines = []
    cur = qid
    while cur is not None:
        if cur in rendered:
            lines.append('%s%d. _Continues at step %d (listed above)._' % (indent, num, cur))
            break
        if giver is None:
            giver = steps[cur].get('from')
        line, nxt, to_eff = step_line(cur, num, indent, rendered, giver)
        lines.append(line)
        if len(nxt) == 1:
            cur, num, giver = nxt[0], num + 1, to_eff
        elif len(nxt) > 1:
            lines.append('%s   * _Then one of these (the game picks):_' % indent)
            for n in nxt:
                lines += render_chain(n, rendered, num + 1, indent + '     ', to_eff)
            break
        else:
            break
    return lines


def chain_len(q):
    n, cur, seen = 1, q, set()
    while True:
        nxt = [x for x in steps[cur]['next'] if x in steps]
        if not nxt or cur in seen:
            return n
        seen.add(cur)
        cur = nxt[0]
        n += 1


def tier_md(t, level='##'):
    td = tiers[t]
    starts = [q for q in td['starts'] if q in steps]
    req = [r for r in td['required'] if r]
    opt = [r for r in td['optional'] if r]
    rendered = set()
    o = ['%s Tier %d' % (level, t), '']
    if td['loop']:
        o += ['_This is the last tier. When you finish it, it starts over, so the same kinds of task keep coming._', '']
    n = td['choices']
    o += ['Tasks are handed to you one at a time.' if n == 0 else 'Each time you ask for a task you are offered up to %d to pick from.' % n, '']
    o += ['**Rewards you must earn to finish this tier (in this order):**', '']
    o += ['%d. %s' % (i + 1, md(r['text'])) for i, r in enumerate(req)] + ['']
    if opt:
        seen = {}
        for r in opt:
            seen[r['text']] = seen.get(r['text'], 0) + 1
        o += ['**Just for fun rewards** (extra tasks, not needed to move on): ' + ', '.join(md(k) + (' x%d' % v if v > 1 else '') for k, v in seen.items()), '']
    fixed, generic = {}, []
    for q in starts:
        f = final.get(q)
        (generic if f is None or f == 1 else fixed.setdefault(f, [])).append(q)
    order = {r['id']: i for i, r in enumerate(req)}
    if fixed:
        o += ['%s# Set task chains' % level, '_Each of these ends in one particular reward._', '']
        for rid in sorted(fixed, key=lambda r: (order.get(r, 999), r)):
            info = next((r for r in req + opt if r['id'] == rid), None)
            o += ['%s## Ends with: %s' % (level, md(info['text'] if info else 'reward %s' % rid)), '']
            for q in fixed[rid]:
                o += render_chain(q, rendered) + ['']
    if generic:
        o += ['%s# Open task pool' % level,
              '_These can be given for any of the tier\'s rewards (%d chains). The reward is the one you picked._' % len(generic), '']
        for q in generic:
            if chain_len(q) == 1:
                s = steps[q]
                to = s.get('to')
                tail = ' (get it from %s; hand in to %s)' % (giver_text(s.get('from')), who(hand_in_target(to, s.get('from')))) if to else ''
                o.append('* `%s` **%s**%s' % (category(s), md(task(s)), tail))
                rendered.add(q)
            else:
                o += [''] + render_chain(q, rendered) + ['']
        o.append('')
    return '\n'.join(o)


def write(name, text):
    open(os.path.join(outdir, name + '.md'), 'w', encoding='utf8', newline='\n').write(text)


links = []
for a, b, name in AREAS:
    ts = [t for t in sorted(tiers) if a <= t <= b]
    if not ts:
        continue
    label = ('Tier %d' % a) if a == b else 'Tiers %d-%d' % (a, b)
    body = {t: tier_md(t) for t in ts}
    total = sum(len(x.encode('utf8')) for x in body.values())
    page = 'Quests-' + slug(name)
    head = ['# %s quests' % name, '', '_%s. [Back to the quest guide](Home)_' % label, '']
    if total <= SPLIT_OVER or len(ts) == 1:
        write(page, '\n'.join(head) + '\n' + '\n\n'.join(body.values()) + '\n')
        links.append((name, label, page, []))
    else:
        sub = []
        for t in ts:
            tp = '%s-Tier-%d' % (page, t)
            write(tp, '# %s quests, tier %d\n\n[All %s tiers](%s) · [Back to the quest guide](Home)\n\n' % (name, t, name, page) + tier_md(t) + '\n')
            sub.append((t, tp))
        idx = head + ['This area has a lot of tasks, so each tier has its own page:', ''] + [
            '* [Tier %d](%s): %d required rewards, %d task chains' % (
                t, tp, len([r for r in tiers[t]['required'] if r]), len([q for q in tiers[t]['starts'] if q in steps])) for t, tp in sub]
        write(page, '\n'.join(idx) + '\n')
        links.append((name, label, page, sub))

home = ['# Toontown: Anywhere quest guide', '',
        'Every ToonTask in the game, in the order the game gives them: %d task chains and %d steps across %d tiers, read straight out of the game\'s own quest data.' % (
            sum(len([q for q in t['starts'] if q in steps]) for t in tiers.values()), len(steps), len(tiers)), '',
        '## How the quest line works', '',
        '* The game is split into **tiers**. Each tier has a list of **required rewards** (Laff boosts, gag training, pouches, cog suit parts and so on). Earn all of them and you move on to the next tier.',
        '* When you ask Toon HQ or a Toon for a task, you are offered up to three. Each one is tied to a reward you still need, or to a bonus "just for fun" reward.',
        '* A **task chain** has one or more steps. You only get the reward after the **last** step; the steps in between are errands that lead there.',
        '* Where a step lists several next steps, the game picks one. The **open task pool** is a shared list of chains that can be given for any reward in that tier.',
        '* `Helper` tasks are for helping a Toon with a low Laff meter, and are only offered to Toons who qualify.',
        '* The game picks tasks at random within a tier, so there is no single fixed order; this guide shows what exists.',
        '* Gag training rewards read "of your chosen track": the game fills in the real track once you have picked one.', '',
        '## Areas', '', '| Area | Tiers | Page |', '|---|---|---|']
for name, label, page, sub in links:
    home.append('| %s | %s | [%s quests](%s) |' % (md(name), label.replace('Tiers ', '').replace('Tier ', ''), md(name), page))
home += ['', '_Generated from the game\'s quest data (`toontown/quest/Quests.py`). Names, places and rewards come from the game itself._', '']
write('Home', '\n'.join(home))
side = ['**[Quest guide](Home)**', '']
for name, label, page, sub in links:
    side.append('* [%s](%s)' % (md(name), page))
    side += ['  * [Tier %d](%s)' % (t, tp) for t, tp in sub]
write('_Sidebar', '\n'.join(side) + '\n')
tot = 0
for f in sorted(os.listdir(outdir)):
    sz = os.path.getsize(os.path.join(outdir, f))
    tot += sz
    print('%-44s %7.1f KB' % (f, sz / 1024))
print('total %.0f KB in %d pages' % (tot / 1024, len(os.listdir(outdir))))

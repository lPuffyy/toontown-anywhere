"""Finds toons whose head type this game cannot draw and (only with --apply) gives them a head it can.

The accounts migrated from the old Toontown: Anywhere carry 8 head types (index 34 to 41) that Open Toontown has no model for.
A toon like that crashes the character-select screen of every toon on its account. By default this only REPORTS. Nothing is
written unless you pass --apply, and the game server must be stopped first.

    python remap_unsupported_heads.py /path/to/astron/databases/astrondb                      # report only
    python remap_unsupported_heads.py /path/to/astron/databases/astrondb --apply              # change the files (makes a backup folder)
    python remap_unsupported_heads.py ... --x h --z c                                         # pick the species used instead

A head is "species letter + ears + muzzle", for example 'xss'. The species letters this game has are d (dog), c (cat), h (horse),
m (mouse), r (rabbit), f (duck), p (monkey), b (bear) and s (pig). The two missing letters, x and z, become the species you pick,
and the toon keeps its head size and muzzle (the last two letters). Mouse only has the 'ls' and 'ss' forms, so pick another
species for a letter that has 'sl' or 'll' toons.
"""
import argparse
import os
import re
import shutil
import sys
import time

HEADS = ['dls', 'dss', 'dsl', 'dll', 'cls', 'css', 'csl', 'cll', 'hls', 'hss', 'hsl', 'hll', 'mls', 'mss', 'rls', 'rss', 'rsl', 'rll',
         'fls', 'fss', 'fsl', 'fll', 'pls', 'pss', 'psl', 'pll', 'bls', 'bss', 'bsl', 'bll', 'sls', 'sss', 'ssl', 'sll']
OLD_EXTRA = ['xls', 'xss', 'xsl', 'xll', 'zls', 'zss', 'zsl', 'zll']          # the old game's head indexes 34 to 41
NAMES = {'d': 'dog', 'c': 'cat', 'h': 'horse', 'm': 'mouse', 'r': 'rabbit', 'f': 'duck', 'p': 'monkey', 'b': 'bear', 's': 'pig'}
LINE = re.compile(r'(setDNAString: \(<)([0-9a-f]+)(>\))')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('astrondb')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--x', default='h', help='species letter to use for the old x heads (default h, horse)')
    ap.add_argument('--z', default='c', help='species letter to use for the old z heads (default c, cat)')
    a = ap.parse_args()
    swap = {'x': a.x, 'z': a.z}
    for letter, to in swap.items():
        if to not in NAMES:
            sys.exit('--%s must be one of %s' % (letter, ' '.join(NAMES)))

    owner = {}
    for f in os.listdir(a.astrondb):
        if not f.endswith('.yaml'):
            continue
        t = open(os.path.join(a.astrondb, f), encoding='utf8').read()
        if 'class: AstronAccount' in t:
            acct = re.search(r'ACCOUNT_ID: "\\"(.*?)\\""', t)
            av = re.search(r'ACCOUNT_AV_SET: "\[(.*?)\]"', t)
            for i in (av.group(1).split(',') if av else []):
                if i.strip() not in ('', '0'):
                    owner[int(i)] = acct.group(1) if acct else '?'

    changes = []
    for f in sorted(os.listdir(a.astrondb)):
        if not f.endswith('.yaml'):
            continue
        path = os.path.join(a.astrondb, f)
        text = open(path, encoding='utf8').read()
        if 'class: DistributedToon' not in text:
            continue
        m = LINE.search(text)
        if not m:
            continue
        raw = bytearray.fromhex(m.group(2))
        head = raw[3]                                        # 2 length bytes, the 't' type byte, then the head index
        if head < len(HEADS):
            continue
        name = re.search(r'setName: \("(.*?)"\)', text)
        old = OLD_EXTRA[head - 34] if 34 <= head - 0 < 34 + len(OLD_EXTRA) else '?'
        if old == '?':
            new = None
        else:
            new = swap[old[0]] + old[1:]
            if new not in HEADS:
                new = None
        changes.append((int(f[:-5]), name.group(1) if name else '?', head, old, new, path, text, m, raw))

    print('%d toon(s) with a head this game cannot draw:' % len(changes))
    for tid, name, head, old, new, path, text, m, raw in changes:
        print('  %-10d %-26s account %-12s head %d (%s) -> %s' % (
            tid, name, owner.get(tid, '?'), head, old, ('%s %s' % (new, '(' + NAMES[new[0]] + ')')) if new else 'NO MATCH, choose another species'))
    if not a.apply:
        print('Report only; nothing was changed. Use --apply (with the server stopped) to change these files.')
        return
    if any(c[4] is None for c in changes):
        sys.exit('Some toons have no valid replacement; fix --x/--z first. Nothing was changed.')
    backup = a.astrondb.rstrip('/\\') + '.before-head-remap-' + time.strftime('%Y%m%d-%H%M%S')
    shutil.copytree(a.astrondb, backup)
    print('backup copy of the database: ' + backup)
    for tid, name, head, old, new, path, text, m, raw in changes:
        raw[3] = HEADS.index(new)
        text = text[:m.start(2)] + raw.hex() + text[m.end(2):]
        open(path, 'w', encoding='utf8', newline='').write(text)
    print('changed %d toon(s)' % len(changes))


main()

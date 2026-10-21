#!/usr/bin/env python3
"""Build the download packs for TTR: Mobile: one uncompressed zip per top-level resource folder, plus packs.json.
Run on the server box after changing anything in the resources folder (after make_manifest.py):
    python3 make_packs.py /DATA/AppData/ttr-offline/resources
"""
import json
import os
import sys
import zipfile

root = sys.argv[1] if len(sys.argv) > 1 else '/DATA/AppData/ttr-offline/resources'
out = os.path.join(root, '_packs')
os.makedirs(out, exist_ok=True)
SKIP = {'_packs', '_ui', 'debug'}
packs = []
for d in sorted(os.listdir(root)):
    p = os.path.join(root, d)
    if not os.path.isdir(p) or d in SKIP or d.startswith('.'):
        continue
    zp = os.path.join(out, d + '.zip')
    n = 0
    with zipfile.ZipFile(zp, 'w', zipfile.ZIP_STORED) as z:
        for r, _, fs in os.walk(p):
            for f in fs:
                full = os.path.join(r, f)
                z.write(full, os.path.relpath(full, root).replace(os.sep, '/'))
                n += 1
    packs.append([d, os.path.getsize(zp)])
    print('%-12s %6d files %8.1f MB' % (d, n, os.path.getsize(zp) / 1e6))
json.dump(packs, open(os.path.join(root, 'packs.json'), 'w'))
print('packs.json written:', len(packs), 'packs')

"""Open WebSocket connections right now, from the bridge log.  Run inside the container:  python who_is_online.py"""
import re, collections, time
L = open('/ot/data/logs/bridge.log', errors='replace').read().splitlines()
cur = collections.Counter(); first = {}
for ln in L:
    m = re.match(r'(open|close) (\S+)', ln)
    if not m: continue
    k, ip = m.groups()
    if k == 'open': cur[ip] += 1
    else: cur[ip] -= 1
live = {ip: n for ip, n in cur.items() if n > 0}
print('open connections now:', sum(live.values()), 'from', len(live), 'addresses', live)
print('total opens since the last restart:', sum(1 for l in L if l.startswith('open')))

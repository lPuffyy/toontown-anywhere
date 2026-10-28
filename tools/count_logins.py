"""Which accounts have logged in since the migration.  Run inside the container:  python count_logins.py [migration stamp prefix]
The migration wrote each account's LAST_LOGIN as the time it ran (e.g. 'Tue Oct 27 18:2'); any other value means a real login since."""
import glob, re, json, sys
STAMP = sys.argv[1] if len(sys.argv) > 1 else 'Tue Oct 27 18:2'
D = '/ot/src/astron/databases'
acc = json.load(open(D + '/accounts.json'))
byid = {v: k for k, v in acc.items()}
rows = []
for f in glob.glob(D + '/astrondb/*.yaml'):
    s = open(f, encoding='utf8').read()
    if 'class: AstronAccount' not in s:
        continue
    i = int(re.search(r'^id: (\d+)', s, re.M).group(1))
    ll = re.search(r'LAST_LOGIN: "\\"(.*?)\\""', s).group(1)
    nm = re.search(r'ACCOUNT_ID: "\\"(.*?)\\""', s).group(1)
    rows.append((ll, nm, i))
mig = [r for r in rows if r[0].startswith(STAMP)]
new = [r for r in rows if not r[0].startswith(STAMP)]
print('accounts total', len(rows), '| migrated and not yet logged in', len(mig), '| logged in since the migration', len(new))
for r in sorted(new): print('  ', r[0], r[1])
users = json.load(open('/ot/data/users.json'))['users']
print('users.json total', len(users))

"""Turn a snapshot of the old Toontown: Anywhere server data into an Open Toontown database.
   python migrate_tta_to_open_toontown.py <snapshot dir (has astron/databases and users.json)> <out dir>"""
import glob, json, os, re, shutil, sys, time

SRC, OUT = sys.argv[1], sys.argv[2]
YIN = os.path.join(SRC, "astron", "databases", "astrondb")
YOUT = os.path.join(OUT, "astrondb")
OT_DEFAULT_SHARD = 401000001
shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(YOUT)

users = json.load(open(os.path.join(SRC, "users.json")))["users"]
bykey = {v["dbkey"]: (n, bool(v.get("admin"))) for n, v in users.items()}

accts = {}
for f in glob.glob(os.path.join(YIN, "*.yaml")):
    s = open(f, encoding="utf8").read()
    if re.search(r"^class: Account", s, re.M):
        i = int(re.search(r"^id: (\d+)", s, re.M).group(1))
        av = [int(x) for x in re.search(r'ACCOUNT_AV_SET: "\[([^\]]*)\]"', s).group(1).split(",") if int(x)]
        k = re.search(r"ACCOUNT_ID: .*?b'([^']*)'", s)
        accts[i] = (k.group(1) if k else None, av)

DROP = {"setWantBetaKeyQuest", "setMaxTokens", "setTokens", "setLastSeen", "setCatalog", "setQuests", "setNPCFriendsDict", "WishNameTimestamp"}
nxt = 100000001
accounts_json = {}
report = []
for oldId in sorted(accts):
    key, av = accts[oldId]
    if key not in bykey or not av:
        continue
    name, admin = bykey[key]
    accId = nxt
    nxt += 1
    newToons = []
    for src in av:
        path = os.path.join(YIN, "%d.yaml" % src)
        if not os.path.exists(path):
            report.append("missing toon %d for %s" % (src, name))
            newToons.append(0)
            continue
        newId = nxt
        nxt += 1
        SET = {
            "setFriendsList": "([])", "WishName": '("")', "WishNameState": '("LOCKED")', "setHouseId": "(0)", "setPetId": "(0)",
            "setNametagStyle": "(0)", "setTutorialAck": "(1)", "setDefaultShard": "(%d)" % OT_DEFAULT_SHARD,
            "setCatalogSchedule": "(0, 0)", "setCatalogNotify": "(0, 0)", "setQuests": "([])", "setGardenTutorialDone": "(0)",
            "setDISLid": "(%d)" % accId,
        }
        out, seen = [], set()
        for ln in open(path, encoding="utf8").read().splitlines():
            if ln.startswith("id:"):
                out.append("id: %d" % newId)
                continue
            m = re.match(r"  (\w+):", ln)
            if m:
                k = m.group(1)
                if k in SET:
                    out.append("  %s: %s" % (k, SET[k])); seen.add(k); continue
                if k in DROP:
                    continue
            out.append(ln)
        extra = ["  setCatalog: (<0000>, <0000>, <0000>)"] + ["  %s: %s" % (k, SET[k]) for k in ("setGardenTutorialDone", "setQuests") if k not in seen]
        open(os.path.join(YOUT, "%d.yaml" % newId), "w", encoding="utf8", newline="\n").write("\n".join(out + extra) + "\n")
        newToons.append(newId)
    slots = (newToons + [0] * 6)[:6]
    stamp = time.strftime("%a %b %d %H:%M:%S %Y")
    level = "SYSTEM_ADMIN" if admin else "NO_ACCESS"
    open(os.path.join(YOUT, "%d.yaml" % accId), "w", encoding="utf8", newline="\n").write(
        "id: %d\nclass: AstronAccount\nfields:\n  ACCOUNT_AV_SET: \"%s\"\n  ESTATE_ID: 0\n  ACCOUNT_AV_SET_DEL: \"[]\"\n  CREATED: \"\\\"%s\\\"\"\n  LAST_LOGIN: \"\\\"%s\\\"\"\n  ACCOUNT_ID: \"\\\"%s\\\"\"\n  ACCESS_LEVEL: \"\\\"%s\\\"\"\n" % (accId, slots, stamp, stamp, name, level))
    accounts_json[name] = accId
    report.append("%-20s account %d toons %s %s" % (name, accId, [t for t in newToons if t], "ADMIN" if admin else ""))
open(os.path.join(YOUT, "info.yaml"), "w").write("next: %d" % nxt)
json.dump(accounts_json, open(os.path.join(OUT, "accounts.json"), "w"), indent=2)
print("\n".join(report))
print("accounts", len(accounts_json), "next id", nxt)

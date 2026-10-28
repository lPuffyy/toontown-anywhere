"""Keeps one Discord message up to date with how many toons are playing (counts only, never names).

Reads /ot/data/online.json, which the ToonPresence service rewrites every 30 seconds, and edits a single message through
a Discord webhook, so the channel stays quiet. The webhook address is read from /ot/data/discord_webhook (one line); if
that file is missing the script does nothing. The address is a secret: it is not in this repository.

    python discord_status.py            (started by run.sh)
"""
import datetime
import json
import os
import time
import urllib.error
import urllib.request

DATA = "/ot/data"
WEBHOOK_FILE = os.path.join(DATA, "discord_webhook")
STATUS_FILE = os.path.join(DATA, "online.json")
MESSAGE_FILE = os.path.join(DATA, "discord_status_message_id")
DISTRICTS = ("Toon Valley", "Giggle Grove", "Silly Meadow")      # shown in this order, even at zero
EVERY = 60                    # seconds between checks
STALE_AFTER = 150             # seconds: an older status file means the game server is not running
BLUE = 0x2F86E8
GREY = 0x808080


def call(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json",
        "User-Agent": "ToontownAnywhere-Status (1.0)",          # Discord refuses the default Python agent
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        text = r.read().decode() or "{}"
    return json.loads(text)


def read_status():
    try:
        status = json.load(open(STATUS_FILE))
    except (OSError, ValueError):
        return None
    if time.time() - status.get("updated", 0) > STALE_AFTER:
        return None
    return status


def build(status):
    if status is None:
        return {"title": "Toontown: Anywhere", "description": "The game server is not running right now.", "color": GREY}
    total = status["total"]
    districts = status.get("districts", {})
    fields = [{"name": name, "value": str(districts.get(name, 0)), "inline": True} for name in DISTRICTS]
    for name, count in districts.items():
        if name not in DISTRICTS:
            fields.append({"name": name, "value": str(count), "inline": True})
    description = "**%d** toon%s playing now" % (total, "" if total == 1 else "s") if total else "No toons online right now"
    return {"title": "Active toons", "description": description, "color": BLUE, "fields": fields,
            "footer": {"text": "Toontown: Anywhere"}}


def main():
    try:
        url = open(WEBHOOK_FILE).read().strip()
    except OSError:
        print("discord_status: no webhook file, nothing to do", flush=True)
        return
    message_id = None
    try:
        message_id = open(MESSAGE_FILE).read().strip() or None
    except OSError:
        pass
    last = None
    while True:
        embed = build(read_status())
        key = json.dumps(embed, sort_keys=True)
        if key != last:
            embed = dict(embed, timestamp=datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"))
            try:
                if message_id:
                    try:
                        call("PATCH", "%s/messages/%s" % (url, message_id), {"embeds": [embed]})
                    except urllib.error.HTTPError as e:
                        if e.code != 404:
                            raise
                        message_id = None                      # the message was deleted: post a new one
                if not message_id:
                    reply = call("POST", url + "?wait=true", {"embeds": [embed]})
                    message_id = reply["id"]
                    open(MESSAGE_FILE, "w").write(message_id)
                last = key
            except Exception as e:
                print("discord_status: could not update (%s), will retry" % e, flush=True)
        time.sleep(EVERY)


main()

"""Keeps one Discord message up to date with whether the game server is running.

This runs in its own small container that stays up when the game container is down, so it can say "offline". It is
separate from discord_status.py (the toon count), which lives inside the game container.

It checks three things every 30 seconds:
  - the web server answers on 127.0.0.1:7380                 (the container is up)
  - /ot/data/online.json is fresh                            (the game server's UberDOG is running)
  - each district's log has finished starting ("Done.")      (the districts are open)
and edits one message through a Discord webhook. The webhook address is read from /status/discord_webhook (a secret, not in
this repository). The game's data folder is mounted read-only at /ot/data.

    docker run -d --name ot-status --restart unless-stopped --network host \\
      -v $ROOT/data:/ot/data:ro -v $ROOT/status:/status python:3.9-slim python -u /status/server_status.py
"""
import datetime
import json
import os
import time
import urllib.error
import urllib.request

WEBHOOK_FILE = "/status/discord_webhook"
MESSAGE_FILE = "/status/message_id"
STATE_FILE = "/status/state.json"                 # when the current state began
ONLINE_FILE = "/ot/data/online.json"
LOGS = "/ot/data/logs"
DISTRICTS = (("Toon Valley", "ai1.log"), ("Giggle Grove", "ai2.log"), ("Silly Meadow", "ai3.log"))
CHECK = "http://127.0.0.1:7380/play/"
EVERY = 30
STALE_AFTER = 150
GREEN, AMBER, RED = 0x3BA55D, 0xFAA61A, 0xED4245


def call(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json", "User-Agent": "ToontownAnywhere-Status (1.0)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        text = r.read().decode() or "{}"
    return json.loads(text)


def web_up():
    try:
        return urllib.request.urlopen(CHECK, timeout=5).status == 200
    except Exception:
        return False


def uberdog_up():
    try:
        return time.time() - json.load(open(ONLINE_FILE)).get("updated", 0) < STALE_AFTER
    except (OSError, ValueError):
        return False


def district_open(logname):
    """A district's log ends its start-up with 'ToontownAIRepository: Done.' and is rewritten when the container starts."""
    try:
        return "ToontownAIRepository: Done." in open(os.path.join(LOGS, logname), errors="replace").read()
    except OSError:
        return False


def check():
    if not web_up():
        return "offline", {}
    districts = {name: district_open(log) for name, log in DISTRICTS}
    if uberdog_up() and all(districts.values()):
        return "online", districts
    return "starting", districts


def build(state, districts, since):
    when = "<t:%d:R>" % int(since)            # Discord shows this as "5 minutes ago" and keeps it current by itself
    if state == "online":
        title, colour = "Server online", GREEN
        text = "The game is up and every district is open. Online since %s." % when
    elif state == "starting":
        title, colour = "Server starting", AMBER
        text = "The game server is starting up, which takes about two and a half minutes. Started %s." % when
    else:
        title, colour = "Server offline", RED
        text = "The game server is not reachable. Offline since %s." % when
    fields = [{"name": name, "value": "Open" if up else ("Starting" if state != "offline" else "Down"), "inline": True}
              for name, up in districts.items()]
    return {"title": title, "description": text, "color": colour, "fields": fields, "footer": {"text": "Toontown: Anywhere"}}


def main():
    try:
        url = open(WEBHOOK_FILE).read().strip()
    except OSError:
        print("server_status: no webhook file, nothing to do", flush=True)
        return
    message_id = None
    try:
        message_id = open(MESSAGE_FILE).read().strip() or None
    except OSError:
        pass
    try:
        saved = json.load(open(STATE_FILE))
    except (OSError, ValueError):
        saved = {}
    state, since = saved.get("state"), saved.get("since", time.time())
    last = None
    while True:
        new_state, districts = check()
        if new_state != state:
            state, since = new_state, time.time()
            json.dump({"state": state, "since": since}, open(STATE_FILE, "w"))
        embed = build(state, districts, since)
        # only send when the state or a district changes
        key = json.dumps([state, districts], sort_keys=True)
        if key != last:
            embed["timestamp"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
            try:
                if message_id:
                    try:
                        call("PATCH", "%s/messages/%s" % (url, message_id), {"embeds": [embed]})
                    except urllib.error.HTTPError as e:
                        if e.code != 404:
                            raise
                        message_id = None
                if not message_id:
                    message_id = call("POST", url + "?wait=true", {"embeds": [embed]})["id"]
                    open(MESSAGE_FILE, "w").write(message_id)
                last = key
            except Exception as e:
                print("server_status: could not update (%s), will retry" % e, flush=True)
        time.sleep(EVERY)


main()

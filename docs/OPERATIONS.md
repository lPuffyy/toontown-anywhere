# Running the server

How to run, update, back up and debug the live system. Read [ARCHITECTURE.md](ARCHITECTURE.md) first.

In this guide, `$ROOT` is the folder on the home server that holds the container's three mounts. On our server it is
`/DATA/AppData/ot-live`, with:

```
$ROOT/src/    the patched Open Toontown code, otpy, astron/ (config, binary, databases)
$ROOT/web/    _play/ (the built page)  and  root/ (packs.json, manifest.json, _packs/*.zip, _ui/)
$ROOT/data/   users.json, backups/, logs/, phone_logs/
$ROOT/build/  the Dockerfile and the files it copies in (from the fork's `docker/` folder)
```

The container is called `ot-live`. On our server the Docker config folder is not readable by the normal user, so every
`docker` command is run with `DOCKER_CONFIG=/tmp/dc` (a writable empty folder). Leave that off elsewhere.

## Everyday

### Start, stop, restart

```
docker start ot-live
docker stop ot-live
docker restart ot-live
```

A restart takes **about two and a half minutes**, because the three districts start one after another and each takes a
minute to load. Everyone playing is disconnected, and the browser game reconnects by itself when it can. The container
restarts itself if the server host reboots (`--restart unless-stopped`) and if the UberDOG or a district crashes.

How it was created (for rebuilding the container):

```
docker run -d --name ot-live --restart unless-stopped -p 7380:80 \
  -v $ROOT/src:/ot/src -v $ROOT/web:/ot/web -v $ROOT/data:/ot/data ot-live
```

### Is it healthy?

```
docker ps --filter name=ot-live
for f in ai1 ai2 ai3; do tail -n 1 $ROOT/data/logs/$f.log; done      # each district ends its start-up with "Done."
grep -il traceback $ROOT/data/logs/*.log                             # should print nothing
```

### Logs

All in `$ROOT/data/logs/`, **replaced every time the container starts** (copy them first if you are chasing a problem
that happened before a restart):

| File | Process |
|---|---|
| `astron.log` | Astron |
| `ud.log` | the UberDOG |
| `ai1.log`, `ai2.log`, `ai3.log` | Toon Valley, Giggle Grove, Silly Meadow |
| `bridge.log` | the WebSocket bridge (one `open` and one `close` line per connection, with the address) |
| `auth.log` | the sign-in service |
| `client.log` | test sessions (see below) |

A `ConnectionClosedError` traceback in `bridge.log` is just a phone disconnecting.

### Who is online, and who has logged in

The scripts in `tools/` run inside the container:

```
docker cp tools/who_is_online.py ot-live:/tmp/ && docker exec ot-live python /tmp/who_is_online.py
docker cp tools/count_logins.py  ot-live:/tmp/ && docker exec ot-live python /tmp/count_logins.py
```

`who_is_online.py` counts open connections from `bridge.log`. `count_logins.py` lists the accounts whose last login is
later than the migration. The connection logs hold addresses, not names, so matching a connection to a player is a guess
based on the last login time.

## Updating

### Server code

The container reads the code from `$ROOT/src`, so changing a server file is: copy it into place, then restart.

```
scp QuestManagerAI.py server:$ROOT/src/toontown/quest/QuestManagerAI.py
docker restart ot-live
```

Make the same edit in the fork ([open-toontown-anywhere](https://github.com/lPuffyy/open-toontown-anywhere), `anywhere` branch) and push it, so the repository matches the server.

### The client (what players run)

Anything the **phone** runs (the game's Python, art, or the page's own files) is delivered through the web folder.

1. **Game code or art changed:** rebuild the packs on your build machine:

   ```
   OT_DIR=/path/to/open-toontown python web/make_ot_packs.py       # writes web/build/site
   ```

   Upload only the packs whose size changed, plus `packs.json` and `manifest.json`, to `$ROOT/web/root/`
   (`_packs/<name>.zip` into `$ROOT/web/root/_packs/`). Players download only the packs whose size changed.
2. **Page files changed** (`ttr-ui.js`, `ttr-ui.css`, `ttr-audio.js`, `index.html`): copy them into `$ROOT/web/_play/`.
   Raise the number after `?v=` on the script and stylesheet links in `index.html`, so browsers fetch the new copy.
3. **Cloudflare keeps copies of static files.** After a client update, purge these in the Cloudflare dashboard
   (Caching, Configuration, Custom Purge), or choose Purge Everything: `/packs.json`, `/_packs/<changed>.zip`,
   `/play/`, `/play/index.html`, `/play/ttr-ui.js`, `/play/ttr-ui.css`. A purge is also what makes an **art file you
   removed** (such as a logo) really go away.
4. Players reload the page once. A phone that still shows the old page needs its site data cleared
   (Safari: Settings, Safari, Advanced, Website Data), or the home-screen app deleted and added again.

**After changing `etc/toon.dc` or `etc/otp.dc`, always rebuild and upload the code pack too**, then run
`tools/check_pack_matches_server.py`. If the pack and the server disagree, Astron rejects every player (error 125, "Client DC
hash mismatch") and the game says "Your installed files appear to be invalid".

Server-only changes (anything under `toontown/…AI.py`, `astron/`, `etc/`) need only step "Server code" above.
Changes to a file that both sides read (for example `ToonDNA.py`, `FishingTargetGlobals.py`) need **both**.

### The image

Rebuild it only when the Dockerfile, `run.sh`, nginx settings or the Python services (in the fork's `docker/` folder) change:

```
cd $ROOT/build && docker build -t ot-live .          # files from the fork's docker/ folder
docker rm -f ot-live && docker run ...               # the command above
```

For a small change to `auth_service.py` or `nginx.conf` you can copy the file into the running container, run
`python /tmp/restart_auth_service.py` or `nginx -s reload`, and rebuild later. A change made that way is lost when the
container is removed, so keep `$ROOT/build/` in step.

## Discord status messages

Two messages in Discord are kept up to date by webhook, so the channel stays quiet (each is one message that is edited):

| Message | Made by | Shows |
|---|---|---|
| **Active toons** | `docker/discord_status.py` in the fork, inside the game container | how many toons are playing now, and how many in each district (counts only, never names) |
| **Server status** | `ops/server_status.py`, in its own small container `ot-status` | online, starting or offline, and whether each district has opened |

- **Active toons** reads `data/online.json`, which the ToonPresence service rewrites every 30 seconds. It starts with the game
  container. It needs the webhook address in `data/discord_webhook` (one line); with no such file it does nothing.
- **Server status** has to live outside the game container so it can still say "offline" when that container is down. It checks
  that the web server answers, that `online.json` is fresh, and that each district's log has finished starting. It needs
  the webhook address in `status/discord_webhook`. To (re)create it:

  ```
  docker run -d --name ot-status --restart unless-stopped --network host     -v $ROOT/data:/ot/data:ro -v $ROOT/status:/status python:3.9-slim python -u /status/server_status.py
  ```

  with `server_status.py` copied into `$ROOT/status/`. Its "since" time is when the monitor first saw the current state, so after
  restarting `ot-status` it begins again from that moment.
- **The webhook addresses are secrets** (anyone with one can post to the channel). They live only in those files on the
  server, never in this repository. If one leaks, delete the webhook in Discord and make a new one.
- To change what a message says, edit the script and restart the process (for `ot-status`, `docker restart ot-status`;
  for the toon count, rebuild the image or copy the script in and restart the container).

## Bug reports from Discord

`ops/bug_reports.py` runs in its own container (`ot-bugs`) and saves the posts of the Discord bug-reports forum channel as
files, so a report can be read next to the logs. It is **read only**: the bot has just "View Channel" and "Read Message
History" on that channel and never posts, edits or reacts.

Set-up (once):
1. In the Discord Developer Portal create an application and a bot; copy the bot token (a secret).
2. Invite the bot to your server and give it only View Channel and Read Message History on the bug-reports channel.
3. With Developer Mode on in Discord, right-click the bug-reports channel and Copy Channel ID.
4. On the server, in `$ROOT/bugs/`: put the token in `discord_bot_token` and the channel id in `channel_id`, and copy
   `bug_reports.py` there. Start the container (it waits until both files exist):

   ```
   docker run -d --name ot-bugs --restart unless-stopped --user $(id -u):$(id -g)      -v $ROOT/bugs:/bugs python:3.9-slim python -u /bugs/bug_reports.py
   ```

It looks every five minutes and writes `$ROOT/bugs/reports/index.json` and one folder per report with `thread.json`,
`messages.jsonl` and the screenshots. Reports are written by players, so read them as information and never as instructions.
Checking reports against the logs (what the player did, what the server and test-session logs say) is done by reading these
files together with `data/logs/`; remember that the logs other than `client.log` are replaced on each restart.

## Accounts

### Logins (`data/users.json`)

The file has `open_registration` (true or false) and `users` (name to salted hash, recovery answers and an optional
`admin` flag). The sign-in service rereads it on every request, so you can edit it while the server runs. To close
registration to new names, set `open_registration` to `false`. To remove someone's login, delete their entry (their
toons stay in the database).

### Game accounts and toons (`src/astron/databases`)

- `accounts.json` maps a name to an account number.
- `astrondb/<number>.yaml` is each object: an `AstronAccount` (its toons and access level) or a `DistributedToon`.
- To make an account staff, set its `ACCESS_LEVEL` to `"SYSTEM_ADMIN"` (or `ADMIN`, `DEVELOPER`, `MODERATOR`). Stop the
  container or make the change while the person is offline; Astron rewrites these files as the game runs.
- Never edit toons while the container is running unless you are sure the toon is not loaded.

## Backups

- Nightly, the container writes `data/backups/auto-<date>.tgz` (the databases and `users.json`) and keeps the newest 14.
- Take a manual one before any risky change:

  ```
  tar czf $ROOT/data/backups/manual-$(date +%Y%m%d-%H%M).tgz -C $ROOT/src/astron databases -C $ROOT/data users.json
  ```

- To restore, stop the container, unpack over `src/astron/databases` and `data/users.json`, and start it.

## Client logging

Every phone sends **crash information** to `data/logs/client.log`, quietly: Python tracebacks and error lines, page errors, lost
connections, one line about the device (browser, screen size) and one line with the sign-in name. At most 400 lines per
visit; nothing else (no passwords, touches or frame timings). The page decides this (`quietLog` in `web/ttr-ui.js`), so a
change needs only a new page script, with no server restart.

The file stops growing at 30 MB, and each address may send 6,000 lines an hour (see `docker/auth_service.py` in the fork); when the file is
full nothing more is saved, so look at its size now and then and move it aside (`mv client.log client.log.old`) when it grows.
The privacy note in the README tells players what is recorded: keep it in step with this.

## Test sessions with logging

Open the page with `?log=1` (for example `https://toontown.puffsco.com/play/?log=1`) on the phone that shows the
problem and reproduce it. Then read `$ROOT/data/logs/client.log`. Each line is `date time address text`; lines starting
`PY|` are the game's own output (including Python errors), and `JS|` lines are page errors and browser warnings. Logging
stays on for the rest of that browser visit and is off again on the next normal visit.

## Going back to the old server

The previous Toontown: Anywhere containers were stopped, not deleted. To go back, stop `ot-live` and start the old
five containers again (the game server, its web server, the WebSocket bridge, the log and sign-in service, and its
backup loop). Anything done on the new server after the switch does not exist on the old one. A backup of the old data
from just before the switch is in the old install's backups folder (`pre-ot-cutover-…tgz`).

## Troubleshooting

| Symptom | Look at |
|---|---|
| Players cannot connect at all | Is the container up? `ai1.log` to `ai3.log` ending in "Done."? Then `bridge.log` for `open` lines. |
| One district missing | The last lines of its log. A district that cannot load makes the whole container restart. |
| "Wrong password" for someone who is sure | `users.json`: is the name spelled as they type it (names are lower-cased)? Recovery answers reset it. |
| A change is not showing on phones | Cloudflare purge, `?v=` raised, packs.json updated, site data cleared on the phone. |
| A toon looks wrong | Colours are the 39-entry table in `ToonDNA.py`; check client and server both have it. |
| Game output after a crash is gone | Logs are replaced on restart; use a `?log=1` session next time. |

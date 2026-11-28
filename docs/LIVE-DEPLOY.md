# Putting the Nov 16 batch on live

What is already live, what is still waiting, and the steps to finish. Nothing here changes the game's message layout (no `.dc` file changed),
so phones that are still on the old files keep connecting while this goes out.

## Already live (done by hand on the Zima, with backups)

- Code pack: Bust-a-Cog camera (no squashed screen) and win-stall fixes, mole counter position, whispers to friends through ToonPresence, the other-district
  toon details first version, Daisy flower names, map button position.
- Page (`tta-ui.js`, patched in narrowly): keyboard "Tap to type" button, movement keys released when the page loses focus, the direct
  game connection (`wss://ws.puffsco.com:4443/ws`, falls back to the tunnel), the route in the `session user` log line. CSS: no page
  text selection on the game, the button's style. `tta-audio.js`: sound recovery on iOS.
- Web glue: the one-`CLIENT_HELLO`-per-connection fix (`game_ot-1794300001.tar.gz`).
- `ws.puffsco.com` DNS (DNS only), router forward 4443 to the Zima's 8443, the `ot-direct` Caddy container (`ops/direct-ws/`).

## Waiting for live

### 1. The server image (needs a restart)

Pushing the fork's `anywhere` branch builds `ghcr.io/lpuffyy/open-toontown-anywhere:latest` (the "docker" workflow). Its changes:

- `toontown/friends/ToonGroupsUD.py`, `ToonGroupsGlobals.py`: the group tracker (Field Offices, sub options, members, friends only, locks
  while the host is inside the activity).
- `toontown/suit/SuitInvasionManagerAI.py`, `toontown/toonbase/ToontownGlobals.py`: the invasion countdown (seconds left in the district
  field) and the invasion push message queue.
- `docker/auth_service.py`: reads that queue and sends the push (at most one per 5 minutes).

Steps (see `ops/docker-compose.zima.yml` for the exact commands): wait for the workflow to finish, pull, rename the old container for a
rollback, bring the new one up, and wait until `ai1.log`, `ai2.log` and `ai3.log` each end with `Done.` (about two and a half minutes).
Everyone playing is disconnected once and reconnects by itself.

### 2. The code pack (no restart)

Files to put in `_code.zip` (compare each with the pack's copy first: they should differ only by these changes):

```
toontown/friends/ToonGroupsGlobals.py      toontown/friends/ToonPresence.py
toontown/shtiker/GroupsPage.py             toontown/shtiker/OptionsPage.py
toontown/shtiker/ShardPage.py              toontown/distributed/ToontownDistrictStats.py
toontown/toonbase/ToontownGlobals.py       toontown/toonbase/TTLocalizerEnglish.py
toontown/toon/ToonAvatarDetailPanel.py     toontown/distributed/ToontownClientRepository.py
toontown/coghq/DistributedGolfGreenGame.py
```

Use `ops/deploy/swap_pack.py <web folder> <tag> _code/<path>=<file> ...` (it keeps `_code.zip.before-<tag>` and `packs.json.before-<tag>`).
**Do the pack after the server**, so a player never has the new Groups page talking to the old group tracker.

The toon-details fix (`ToonAvatarDetailPanel.py`, `ToontownClientRepository.py`) fixes a crash that is live now (opening the details of a
toon in another district stops the game); it can go out on its own, ahead of everything else.

### 3. The page and the glue

- `web/tta-ui.js` (whole file) and `web/tta-ui.css`: the Device settings feed, the settings cog hidden in game, the keyboard button
  that checks the visible area. The live copy has only narrow patches, so replace it with the repo's file and bump the `?v=` numbers in
  `index.html`. Keep the live-only `LOGGING` rule: logging stays off on the live port.
- `web/game/webui.py` into `game_ot.tar.gz` and `game_ot.apk` (`ops/deploy/swap_glue.py`), then copy the tarball to a new
  `game_ot-<number>.tar.gz` and point `index.html` at it. Without this the sticker book has no Device tab (it shows only when the page and
  the glue both have the Device settings).

### 4. The browser away timer

- Ship `web/tta-ui.js`, `web/game/webui.py` and `web/game/webnet.py` together in the page and browser glue.
- Bind mount `ops/deploy/wsbridge.py` at `/ot/wsbridge.py` and set the Astron client agent's `heartbeat_timeout` to `660000` milliseconds in the deployment's existing configuration. Restart the game container to apply both changes.
- Keep the WebSocket route's idle timeout longer than ten minutes. The new browser opts in through the `tta-away=1` query parameter, and the relay ends an away session after 600 seconds. Older browsers can still connect.

### Gag progression overlays

Deploy the client and server files from `battle-src` with the matching DC files. Apply `battle-src/resources/phase_3/etc/QuestScripts.txt` to both the Original and Remastered phase 3 packs so the Toontorial runs the starter gag picker. Include `TutorialManagerAI.py` for the gag handout and `QuestRewardCounter.py` for saved track access.

## Checks after it is live

- Districts page during an invasion: the countdown ticks; Groups page: post a Field Office group, join it from another toon, see the
  name and the join notice; open the details of a toon in another district: no crash.
- Client log: `JS| session user: <name> route direct` appears for most players; compare the close rate (`webnet: closed code=1006`) per
  session for `route direct` against `route tunnel` after a day.

## Rolling back

Each swap leaves a `.before-<tag>` copy next to the file (`_code.zip`, `packs.json`, `tta-ui.js`, `game_ot.tar.gz`, `index.html`);
copy it back. For the server, the renamed old container.

To stop the direct game connection for everyone: `docker stop ot-direct` on the Zima. Pages fall back to the tunnel at once.

# To do

Open work, most important first. Each item says what is known. When one is finished, move it to the change notes in
[CHANGES.md](CHANGES.md) and delete it here.

## Needs fixing

- [ ] **Fish Bingo causes crashes.** It is **switched off** (`ENABLED = False` in
  `toontown/fishing/FishBingoScheduleAI.py`), so no Bingo Night starts and Toon HQ does not announce one. Not yet diagnosed.
  The schedule runs a Bingo Night for the first 20 minutes of every hour. To find the cause: turn it on in a copy,
  open the page with `?log=1`, fish during a Bingo Night, and read `client.log` and the district's log. Things to check first:
  the card and manager objects the fishing pond creates when the night starts (`startBingoNight`), what the fishing spot
  does when it joins a card, and the wide-screen changes made to the fishing screen (`DistributedFishingSpot.py`).
  Turn it back on only after a night runs without a crash.
- [ ] **The game connection does not check the password.** Only the page's sign-in does, so anyone who talks to the
  WebSocket with another player's name is let in as that player. Fix: the sign-in service issues a short-lived signed
  token, and the login manager checks it. See [ARCHITECTURE.md](ARCHITECTURE.md), section 3.
- [ ] **Furniture editing on a phone.** Fixed so far: the toon is shown again when editing ends, the clipping is gone (confirmed by a
  player), and the attic and stop-editing buttons are pinned to the screen's top-left corner so a wide screen cannot push them away.
  Still to confirm: that the attic button now stays after editing, and that furniture can be picked up and moved by touch. If
  moving by touch still fails, the page's touches may not reach the game as mouse presses and drags (see `web/game/webui.py`).
- [ ] **The phone ringing is not heard.** The sound file is in the pack. Cause not found. Some phones are silent
  because of the ring/silent switch; check that first.
- [ ] **Offline gifts** (`toontown/estate/DistributedPhoneAI.py`, `got` callback): the database query is made without the
  class argument, which the same function that crashed the districts needed. Gifting to a friend who is not playing will
  probably fail. Pass `dclass=self.air.dclassesByName['DistributedToonAI']` and test.

## Worth doing

- [ ] **Test the server on `otpy`.** The server runs our pure-Python replacement for the game's compiled libraries.
  Watch Cog movement, building takeovers and suit planning for differences. Compare against the compiled libraries on the
  Windows test machine.
- [ ] **Keep server logs across restarts.** The log files are replaced each time the container starts, so the evidence
  for a crash is gone after the restart that follows it. Append instead, or rotate with a date.
- [ ] **Friend invitations across districts.** Friends, online status, Go To and ending a friendship work across districts,
  but the invitation itself needs both toons next to each other (as in the game). Secret friends are not offered.
- [ ] **A friend who is offline when you end the friendship** keeps you on their list until they remove you.
- [ ] **Houses, furniture, gardens, Doodles and the catalog were not migrated** from the old server. See
  [MIGRATION.md](MIGRATION.md) for what players lost.
- [ ] **iPhone strip under the toolbar** in landscape on some phones: the page's overlays are sized to the large viewport
  as a fix, not confirmed everywhere.
- [ ] **Wide-screen layouts.** Some Open Toontown screens may still look stretched on very wide phones. Fix them as they
  are found (the Cog Gallery and the fishing screen are done).
- [ ] **Build the Linux Astron binary from source** and note which version it is, instead of reusing the one copied from the
  old install.
- [ ] **Add the test-session log reading to the operations notes** with an example of what a crash looks like.

## Ideas

- A server-side copy of each player's options, so sound settings follow them to another phone (today they are saved
  per phone in the browser).
- A small page for staff to see who is online and which districts have invasions.

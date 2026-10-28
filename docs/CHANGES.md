# What differs from stock Open Toontown

Everything we changed in the game, grouped by what it is for, followed by the known problems. The changes are in
`open-toontown/patches/open-toontown-anywhere.patch` (276 files; `CHANGED_FILES.txt` lists them) and are made against
upstream Open Toontown commit `2b366a2`. How to apply them is in [open-toontown/README.md](../open-toontown/README.md).

## Server

### Districts and population

- Three districts, started by `server/run.sh`: **Toon Valley**, **Giggle Grove** and **Silly Meadow**, one AI process
  each, with their own channel ranges.
- The district statistics object (`ToontownDistrictStats`) is now generated under the game's root object, which is where
  the client's interest can see it. This is what makes the Districts page show populations.
- A district's population is counted for its own streets. Toons in Welcome Valley are listed under Welcome Valley, not
  in two places.
- `ToontownDistrictStats` has a new field, `setInvasion(string, uint8, uint32)`, that tells every client which Cog is
  invading a district and how many are left (`etc/toon.dc`).

### Cog invasions (`toontown/suit/SuitInvasionManagerAI.py`, rewritten)

- Each district schedules its own invasions: the **first about one to four minutes after the district opens**, then one
  every **10 to 25 minutes**. Each is **1,000 Cogs** of one random type.
- **Silly Meadow never has invasions** (the "safe" district).
- Cogs defeated count down the invasion; it ends at zero.
- Starting or stopping an invasion publishes it on the district statistics (so the Districts page shows it), sends a Toon
  HQ bulletin to the district, and logs `invasion begins` at warning level. Toons arriving mid-invasion get the bulletin
  five seconds after they appear.

### Fishing

- **Fish Bingo is switched off.** The hourly Bingo Night (20 minutes of every hour, announced by Toon HQ) is built
  (`toontown/fishing/FishBingoScheduleAI.py`) but disabled by `ENABLED = False`. Set it to `True` to bring it back.
- Pond fish now swim to a new spot over **9 seconds** (stock: 5) and then **rest 3 to 8 seconds** before moving again
  (`FishingTargetGlobals.py`, `DistributedFishingTargetAI.py`).

### Quests

- When a toon with no tasks talks to a Toon HQ officer, the server first checks whether the toon has finished every
  required reward of its tier and, if so, moves it to the next tier (`QuestManagerAI.py`). Before this, a toon could be
  left on a finished tier and be offered only "Just For Fun" tasks.

### Friends

- **Toon-to-toon friend invitations work** (`otp/friends/FriendManagerAI.py`, written by us). Stock Open Toontown has only an
  empty stub for it, and the client was sending its friend requests to a global object (number 4501) that no server
  process ever created. Astron answers a message to a missing object by disconnecting the sender, with error code 117,
  so tapping "Add friend" dropped the player with "An unexpected problem has occurred (error code 117)".
- Now every district's AI generates its own friend manager (like its time manager), and the client uses the one it is sent
  (`ToontownStart.py` no longer creates the missing global object). The manager runs the invitation: it checks the
  invitee is in the district, is not the inviter and is not already a friend, passes the invitation on, relays the
  invitee's answer, adds both toons to each other's friends lists when it is yes (limit 50), and tells the inviter.
- **The friends list is filled by the server.** The game has no "get friends list" request on Astron, so the list window
  had no names to show. When a toon enters a district, its AI looks up each friend (name, look, pet, and whether the friend is
  in this district) and sends them to the toon's own client (`setFriendDetails`, a new field in `etc/toon.dc`); it is sent
  again when two toons become friends. Friends in the district are told when a friend arrives or leaves
  (`setFriendOnline`). "Online" therefore means "in the same district".
- **Friends in other districts, and Go To.** A new UberDOG service, `ToonPresence` (object 4730, `toontown/friends/ToonPresence*.py`,
  listed in `astrond.yml`), knows which toons are playing in every district. Each district's AI tells it when a toon arrives, leaves
  or makes a friend, and it tells that toon's friends in any district (`friendOnline`), so the friends list shows who is online
  everywhere. It also carries the **Go To** questions and answers. In the stock game a client sends those straight to the other
  toon's object; the server drops a client that sends to an object it cannot see (error 117), so Go To to anyone out of view
  would have disconnected the player. The client now sends them to `ToonPresence`, which passes them on, but only between
  toons who are both playing and are friends.
- **Ending a friendship works** (it used to crash the game: the client sent a message type Astron does not have). The client asks
  its own district to drop the friend and tells `ToonPresence`, which tells the friend's phone, which asks the friend's district
  to drop the other toon. If the friend is not playing at that moment, they keep the old friend until they remove it themselves.
- Secret friends are not offered (both secret requests answer "not available").
- Only toons in the same district can invite each other, which is also how the invitation works in the game.

### Options

- **Options are remembered in the browser** (`otp/settings/Settings.py`). The game's own options file lived in the browser's
  temporary file system and was gone on every load, so the sound and music switches had to be turned off each time. In the
  browser, options are now saved in the browser's local storage, one set for each sign-in name, and come back when that name
  plays again on that phone. (Computers still use `useropt.json`.) They are not stored on the server, so they are per device.

### Access

- A brand-new account gets `NO_ACCESS` (set in `server/live.prc`), not stock Open Toontown's `SYSTEM_ADMIN`. Staff are
  made by editing the account in the database.

### Toon colours

- `ToonDNA.py` carries the 39-entry colour table of the old server instead of the stock 27, so migrated toons keep their
  colours. The allowed-colour set and the default colour lists follow it. This file is read by both the server and the
  client.

### Content removal

- Disney characters and their code (`toontown/classicchars`, 43 files) are removed, as are a few character-art
  references elsewhere. Matching art in the resource folders was repainted or removed when the packs were prepared.

## Client (the game on the phone)

### The Shticker Book

- **Districts page** (`toontown/shtiker/ShardPage.py`): choosing a district no longer teleports at once. Tapping a name
  highlights it and shows a panel with its name, population and, if there is one, the invading Cog's head with "…are
  invading Toontown!". A **Teleport Here!** button takes you there. A district with an invasion has its name in red in the
  list (green is where you are when it has no invasion). The total population is shown at the top.
- **Cog Gallery**: the frame is narrowed so it does not stretch on wide phone screens.

### Screen size and layout

- **Wide phones** (`ToonBase.py`, `ToontownBattleGlobals.py`): the margin cells (the little arrows and name tags at the
  screen edges) are re-laid out when the aspect ratio changes, and the battle camera widens its field of view so the
  battle fits a very wide screen.
- **Fishing** (`DistributedFishingSpot.py`): the board is stretched under the interface, and the jar, bucket and exit
  button are spread out on wide screens without covering the laff meter.
- **Loading screen** (`ToontownLoadingScreen.py`): a sky backdrop sized to any screen, a scroll banner for the tip, and a
  progress bar.
- **Phone chat**: large chat buttons pinned to the screen corner (done while the packs are built, see
  `web/make_ot_packs.py`).

### Clarabelle's Cattlelog (`toontown/catalog/CatalogScreen.py`)

- Clarabelle **speaks** (greeting, goodbye and chatter clips in `phase_5.5/audio/dial/`).
- The catalog **colours the window background** while it is open, and Clarabelle's TV window now shows her room and her
  switchboard.
- The hang-up button is pinned to the screen corner.
- Gifting shows a stand-in toon (the server has no "get avatar details" message).

### Other

- Many small compatibility fixes (chat, nametags, estate, pets, minigames, hoods, and so on) that let Open Toontown run
  on Astron's current client interface and in the browser.

## The page shell (`web/`)

- Sign-in with password recovery, a server choice card, the loading and download screen, the touch controls, the rotate
  and "add to Home Screen" screens (on a sky background), an optional test-session log (`?log=1`), and the Toon font.
- Discord and Reddit buttons on the sign-in screen.

## Known problems

Honest list, most important first.

1. **The game connection does not check the password.** Only the page does (see ARCHITECTURE.md, section 3). Anyone who
   connects straight to the WebSocket with another player's name is let in as them. Planned fix: the sign-in service
   issues a short-lived signed token and the login manager verifies it.
2. **Friend invitations only work between toons in the same district** (the two toons have to be next to each other, as in
   the game). Friends, online status and Go To work across districts.
3. **The phone ringing is reported missing** (the sound file is in the pack; why it is not heard is not found). Some phones
   are also silent because of the ring/silent switch.
4. **The server runs on `otpy`**, our pure-Python replacement for the game's compiled libraries, not the compiled ones. It
   has been checked, but less than the compiled code has been used. Watch Cog movement and building behaviour.
5. **Logs are lost on every restart.**
6. **Houses, pets, friends and catalog items were not migrated** (see MIGRATION.md).
7. **Fish Bingo is disabled** because it causes crashes; see [TODO.md](TODO.md).
8. **iPhone strip:** a thin strip can show under the toolbar on some iPhones in landscape. The overlays are sized to the
   large viewport as a fix; not confirmed on every phone.
9. Some Open Toontown screens may still look stretched on very wide phones; they are fixed as they are found.

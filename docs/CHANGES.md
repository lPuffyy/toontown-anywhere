# What differs from stock Open Toontown

Everything we changed in the game, grouped by what it is for, followed by the known problems. The changes are in
`open-toontown/patches/open-toontown-anywhere.patch` (266 files; `CHANGED_FILES.txt` lists them) and are made against
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
2. **Adding a friend crashes the game** (reported on Android: a grey screen). Not reproduced yet. Use a `?log=1` session
   and read `client.log`. Suspects are the friend invitation window reading fields from the other toon's object.
3. **The phone ringing is reported missing** (the sound file is in the pack; why it is not heard is not found). Some phones
   are also silent because of the ring/silent switch.
4. **The server runs on `otpy`**, our pure-Python replacement for the game's compiled libraries, not the compiled ones. It
   has been checked, but less than the compiled code has been used. Watch Cog movement and building behaviour.
5. **Logs are lost on every restart.**
6. **Houses, pets, friends and catalog items were not migrated** (see MIGRATION.md).
7. **Fish Bingo is disabled** until it has been tested properly.
8. **iPhone strip:** a thin strip can show under the toolbar on some iPhones in landscape. The overlays are sized to the
   large viewport as a fix; not confirmed on every phone.
9. Some Open Toontown screens may still look stretched on very wide phones; they are fixed as they are found.

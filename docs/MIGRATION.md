# Moving the players over

On 27 October 2026 the live server changed from the previous Toontown: Anywhere server to the Open Toontown based
system described in [ARCHITECTURE.md](ARCHITECTURE.md). Every player who had a toon kept their login, their toons and
most of their progress. This document records what was moved, what was not, how it was done, and how to do it again.

## What players kept

| Kept | Notes |
|---|---|
| Login name and password | The same `users.json` was copied; password hashes and recovery answers are unchanged. |
| Every toon on the account | Name, look (species, head, clothes), laff, gags and gag experience, track access, beans, bank, Cog gallery and suit progress, fishing records, emotes, speedchat, and so on: everything the new game has a field for. |
| Quest progress | The quest **history** and **reward history**, so finished tasks stay finished and the player's story tier is kept. |
| Staff powers | Only the owner's account is an admin. Everyone else is an ordinary player. |

## What players lost, and why

| Not carried over | Why |
|---|---|
| Tasks in progress | The old and new games number their quests differently. Players pick up fresh tasks from Toon HQ. |
| Catalog items waiting for delivery, and the catalog schedule | The catalog data is stored differently. It starts empty. |
| Houses, furniture and gardens | The old server's estate objects are not compatible with the new server's. Toons start with no house. |
| Pets (Doodles) | Same reason. |
| Friends lists | Friend links are stored by the old server's object numbers, which do not exist any more. Players re-add friends. |
| Pending name changes | Cleared. |

Also removed from toons before the move, because the new game has no use for them: tokens, last-seen time, the NPC
friends dictionary, the beta-key quest flag, and the name-wish timestamp.

## Things that look different, on purpose

- **Toon colours.** The old game's toon colour table has 39 entries; stock Open Toontown has 27. Toons using colours 25
  and above would have changed colour (one player's light blue head turned black), so the table in `ToonDNA.py` is the
  old 39-entry one. New toons can pick the extra colours too.
- **Districts.** There are three, named after the old server's: Toon Valley, Giggle Grove and Silly Meadow. Silly Meadow
  never has a Cog invasion.

## How it works

`tools/migrate_tta_to_open_toontown.py <snapshot> <out>` reads a snapshot of the old server's data
(`astron/databases/` and `users.json`) and writes an Open Toontown database:

1. Reads every `Account` object and works out which login it belongs to (the old accounts carry a key such as
   `user:<name>`, which `users.json` maps to the name).
2. Skips logins that have no account or no toons (they get a fresh account the first time they play).
3. Gives each migrated account and each of its toons a **new object number**, starting at 100000001, in order.
4. Writes each toon with the dropped fields removed and these values reset: friends list empty, no house, no Doodle, no
   pending name, name-tag style 0, tutorial done, default district Toon Valley, catalog empty, no tasks in hand, garden
   tutorial not done, and the account number written into the toon.
5. Writes an `AstronAccount` for each, with the toon list in slot order, the login name, and the access level
   (`SYSTEM_ADMIN` for admins, `NO_ACCESS` otherwise).
6. Writes `accounts.json` (name to account number) and `astrondb/info.yaml` (the next free number).

The result is `astrondb/` and `accounts.json`, to be dropped into `src/astron/databases/`.

On 27 October: 77 logins, 62 of them with toons, became **62 accounts and 65 toons**.

## The cutover, step by step (as done)

1. Built the new container and ran it on a spare port with a migrated copy of the data. Players' real credentials
   were tried on it and their toons checked before anything live was touched.
2. Stopped the old containers (so the data stopped changing), took a backup of the old data, and took the snapshot.
3. Ran the migration on the snapshot (this is why it must run after the old server stops: anything saved afterwards
   would be missed).
4. Installed the output into the new container's `src/astron/databases`, copied the old `users.json` into `data/`, and
   started the container on the public port, where the Cloudflare tunnel already pointed.
5. Checked that all three districts finished loading, that the pages and the sign-in answered, and that a real
   connection reached the game.

## Doing it again

Use a snapshot taken **after** the old server is stopped, and keep a backup of both sides. To test without risk, install
the output into a separate copy of `src/` and a separate `data/`, and run a second container on another port. Do not run
two containers on the same `astron/databases`.

## Rolling back

See "Going back to the old server" in [OPERATIONS.md](OPERATIONS.md). The old data was never modified.

## Follow-ups found after the move

- **A toon stuck on a finished quest tier** (Toon HQ offered only "just for fun" tasks): the old server left some toons at
  the end of a tier without moving them on. The server now checks this when a toon with no tasks talks to an HQ officer.
- **The colour table** (above) was found by a player noticing a toon's head had turned black.
- **Friends lists** were reset on purpose, but a player reported that adding a friend crashes the game. That one is not
  solved yet; see [CHANGES.md](CHANGES.md#known-problems).

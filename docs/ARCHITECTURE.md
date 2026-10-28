# How Toontown: Anywhere works

This is the full write-up of the system as it runs today. It covers what the pieces are, how they fit together, and why
they were built this way. Day-to-day running is in [OPERATIONS.md](OPERATIONS.md), the move from the old server in
[MIGRATION.md](MIGRATION.md), and every difference from stock Open Toontown in [CHANGES.md](CHANGES.md).

## 1. The short version

Players open a web page on a phone. The page downloads the game (Python code and Toontown's art and sound, about 390 MB,
kept on the device) and runs it inside the browser, using Python compiled to WebAssembly. The game talks to our server
over a WebSocket. The server is the Open Toontown game server (Astron plus Python services), running in **one Docker
container** on a home server, reached from the internet through a Cloudflare tunnel.

```
 phone / tablet (browser or home-screen app)
 ┌──────────────────────────────────────────────┐
 │  page shell  (web/ttr-ui.js, ttr-ui.css)     │   sign-in, download, touch controls
 │  game        Open Toontown + otpy, in Python │   Panda3D + CPython in WebAssembly (pygbag)
 │              /Panda3D, running in the browser│
 └───────────────┬───────────────┬──────────────┘
                 │ HTTPS         │ WSS  /ws
                 ▼               ▼
            Cloudflare  ──(tunnel)──►  home server :7380
                                          │
 ┌────────────────────────────────────────▼───────────────────────────────┐
 │ Docker container "ot-live"                                             │
 │                                                                        │
 │  nginx :80 ─┬─ /play/, /packs.json, /_packs/*, /_ui/   static files    │
 │             ├─ /ws ───────────► ws bridge :7390 ──► Astron client agent│
 │             │                                         :7198 (TCP)      │
 │             └─ /auth /recover /setrecovery /__log ──► sign-in service  │
 │                                                       :7381            │
 │                                                                        │
 │  Astron (message director :7199, state server, database, client agent) │
 │  UberDOG ─ Toon Valley AI ─ Giggle Grove AI ─ Silly Meadow AI          │
 │  nightly backup loop                                                   │
 └────────────────────────────────────────────────────────────────────────┘
        volumes:  src/ (code + astron/databases)   web/ (page + packs)   data/ (users, backups, logs)
```

## 2. The parts

### 2.1 The browser client (`web/`)

Two layers run on the phone.

**The page shell** is plain JavaScript and CSS (`web/ttr-ui.js`, `web/ttr-ui.css`, `web/ttr-audio.js`). It owns
everything outside the game itself:

- the sign-in screen, password recovery, the loading screen and its progress bar;
- the "turn your phone sideways" and "add to Home Screen" screens (iPhone, iPad and Android);
- downloading and caching the game files (section 4);
- the touch controls (thumb stick, jump, camera, book) and the on-screen keyboard handling;
- sound: it plays the game's sounds through the Web Audio API (`web/ttr-audio.js`), because Panda3D has no audio
  library in the browser;
- keeping the game's window the right size on phones with notches and moving toolbars;
- the optional test-session log (`?log=1`, section 7).

**The game** is Open Toontown's Python code run by [pygbag](https://github.com/pygame-web/pygbag): CPython and Panda3D
compiled to WebAssembly, drawing with WebGL. Our glue code is in `web/game/`:

| File | Job |
|---|---|
| `main.py` | Starts the game after the shell has downloaded its files and signed in; installs `otpy`; sets the Panda3D options a browser needs; hands the game the sign-in name; keeps the window size in sync with the shell. |
| `webnet.py` | The game's network connection over WebSocket (a browser cannot open a plain TCP socket). |
| `webaudio.py` | `AudioManager` and `AudioSound` look-alikes that pass sound requests to the shell. |
| `webui.py`, `webui_core.py` | Touch controls and phone-sized versions of some game screens. |
| `xmlshim.py` | A small stand-in for `xml.sax`, which the browser's Python build lacks; it reads the game's DNA files. |

`web/patch_web.py` takes the page that pygbag builds and adds the shell, the Home Screen manifest and icons.

### 2.2 `otpy`: replacing the compiled libraries

Open Toontown needs two compiled Panda3D modules, `panda3d.otp` and `panda3d.toontown` (nametags, margin cells, the DNA
loader, Cog street paths, movement code). There is no build of them for WebAssembly, so we wrote **`otpy`**
(`otpy/` in the fork), pure Python with the same interface:

| Module | Replaces |
|---|---|
| `dna.py`, `dnaparser.py` | the DNA loader and storage (streets, buildings, Cog paths) |
| `suit.py` | Cog path legs and leg lists |
| `movement.py` | `CMover`, `CImpulse` and the pet movement helpers |
| `nametag.py` | nametags, chat balloons, margin cells, whisper popups |
| `install.py` | registers all of the above as `panda3d.otp` and `panda3d.toontown` |

`otpy` is used in two places: in the browser (`main.py` installs it), and **on the server too** (the container loads it
into every Python process through a `sitecustomize.py`, section 2.4). It was checked against the compiled versions
while it was written, but the server using it instead of the compiled library is the least-tested part of the system.

### 2.3 The edge

The home server is not exposed directly. A Cloudflare tunnel (`cloudflared`) forwards the public name
`toontown.puffsco.com` to the container's one published port, 7380. Cloudflare caches static files, which matters when
files change (see OPERATIONS.md, "Updating the client").

### 2.4 The server container (`docker/` in the fork)

Everything the game needs on the server side runs in a single container (`ot-live`, built from the fork's `docker/Dockerfile`).
`docker/run.sh` starts these, in order, and stops the whole container if the UberDOG or any district dies, so Docker
restarts everything together:

1. **nginx** (port 80 inside, 7380 published). Serves the page and game files, and proxies `/ws` and the sign-in
   paths (`docker/nginx.conf`).
2. **Sign-in service** (`docker/auth_service.py`, port 7381). Checks passwords, handles recovery, collects test-session
   logs. Section 5.
3. **WebSocket bridge** (`docker/wsbridge.py`, port 7390). Copies bytes between a browser WebSocket and Astron's TCP
   client port. It reads nothing and changes nothing. It allows 8 connections and 30 new connections a minute per
   address.
4. **Astron** (`astrond`). The message director (7199), event logger (7197), state server (4002), database server
   (4003, YAML files in `astron/databases/astrondb`), database state server, and the client agent (7198). The Linux
   settings are `astron/config/astrond-linux.yml`, made by the Dockerfile.
5. **UberDOG** (`toontown.uberdog.UDStart`, base channel 1000000). The global services: login manager, friends managers,
   delivery manager, news and the rest listed in `astrond-linux.yml`.
   The one we added is **ToonPresence** (object 4730): it knows who is playing in any district, tells friends when
   someone comes or goes, and relays the Go To messages.
6. **Three district AIs** (`toontown.ai.AIStart`), one process each: **Toon Valley** (channel base 401000000),
   **Giggle Grove** (402000000) and **Silly Meadow** (403000000). They start 25 seconds, then 15 seconds apart, and each
   takes about a minute to finish loading, so a restart takes about two and a half minutes.
7. **A backup loop** (section 6).

The image is Python 3.9 with:

- **Panda3D 1.11.0** (a development wheel from the Panda3D archive, `1.11.0.dev4085+shaderpipeline.388`), which gives
  the compiled engine and the DC (network protocol) library;
- the Python side of **Panda3D 1.11.0's `direct` package** copied over the wheel's, because the Astron classes the game
  uses (`AstronInternalRepository` and friends) are missing from the wheel's copy. That folder is in the fork
  (`docker/overlay/direct`, with Panda3D's license);
- `pytz` and `websockets`;
- a `sitecustomize.py` that loads `otpy`, so `panda3d.otp` and `panda3d.toontown` exist in every Python process.

Three folders are mounted into the container, so the image itself holds no data:

| Mount | Holds |
|---|---|
| `/ot/src` | the patched Open Toontown code, `otpy`, and `astron/databases` (the toons and accounts) |
| `/ot/web` | `_play/` (the built page) and `root/` (packs, packs.json, `_ui/`) |
| `/ot/data` | `users.json`, `backups/`, `logs/`, `phone_logs/` |

## 3. Sign-in and a play session

1. The player types a name and password. The shell lower-cases the name and sends `name:password` to `POST /auth`.
2. The sign-in service looks the name up in `users.json`. An unknown name is registered on the spot (while registration is
   open), with a salted PBKDF2-SHA256 hash (100,000 rounds). A wrong password gets "Wrong password". A first-time user is
   asked to set two recovery answers.
3. On success the shell downloads or checks the game files, then starts the game, giving it **only the name**.
4. The game opens a WebSocket to `/ws`. nginx passes it to the bridge, which opens a TCP connection to Astron's client
   agent.
5. The game sends the name as its play token. The UberDOG's login manager (`AstronLoginManagerUD`) looks the name up in
   `astron/databases/accounts.json`, which maps names to account objects:
   - a known name loads that account and its up-to-six toons;
   - an unknown name gets a new account on the spot, with the default access level `NO_ACCESS` (set in `docker/live.prc`),
     so ordinary players have no staff powers;
   - accounts that were given `SYSTEM_ADMIN` in the database (only the owner's) can use the in-game magic words.
6. The player picks a toon, the game asks for an avatar, and the toon appears in the default district. From there it is
   normal Open Toontown: the district's AI creates the toon's objects, and the state server and client agent keep the
   phone's view up to date through interest.

**Important limitation:** step 5 trusts the name. Only the page checks the password (step 2); the game connection
itself does not. Someone who talks to `/ws` directly and sends another player's name as the token would be let in as
that player. This is inherited from how the old server worked. Fixing it means having the sign-in service issue a
short-lived signed token that the login manager checks. It is the most important open security item
(see [CHANGES.md](CHANGES.md#known-problems)).

## 4. Getting the game files to the phone

The files are served as a handful of zip "packs" listed in `packs.json` (name and size). The shell:

- fetches `packs.json`, then each `/_packs/<name>.zip?s=<size>`; the size in the address means a changed pack is never
  mistaken for the cached one;
- stores the packs in the browser's Cache API (or IndexedDB where that is unavailable) and unpacks them into the game's
  virtual file system;
- deletes cached packs that are no longer listed.

`web/make_ot_packs.py` builds the packs:

- **`_code.zip`**: the Python of the `otp` and `toontown` packages from the patched checkout, our `otpy`, `pytz`, the
  `etc/` config files and the licence notices. While it is packed, two kinds of changes are made to the code:
  browser fixes (the game's see-through modes become plain alpha blending, because WebGL has no alpha test), and
  phone-friendly chat (large chat buttons pinned to the screen corner).
- **`models.zip` and one zip per `phase_*` folder**: the game's art, sound and data, taken as they are from the
  checkout's `resources/` folder.

The resources are not in this repository. You supply them in your own Open Toontown checkout.

## 5. Accounts

There are two separate stores, deliberately:

| Store | File | What it holds |
|---|---|---|
| Logins | `data/users.json` | name, salted password hash, recovery answers (also hashed), an admin flag, a registration switch |
| Game | `src/astron/databases/accounts.json` and `astrondb/*.yaml` | which account belongs to which name; each account's toons and every toon's fields |

The sign-in service is the only thing that touches `users.json`. Password recovery asks for two answers the player chose
(their nickname and their toon's name), hashes them the same way, and throttles repeated failures per name and per address.

## 6. Data and backups

- **Toons and accounts** are YAML files, one per object, written by Astron's database server. No other database runs.
- **A nightly backup** (inside `run.sh`) tars `astron/databases` and `users.json` into `data/backups/`, and keeps 14.
- **Logs** are in `data/logs/` (see OPERATIONS.md). They are replaced each time the container starts.

## 7. Seeing what happens

- **Server logs:** one file per process in `data/logs/` (`astron.log`, `ud.log`, `ai1.log` to `ai3.log`, `bridge.log`,
  `auth.log`).
- **Test sessions:** open the page with `?log=1`. For the rest of that visit the page sends everything the game prints
  (including Python errors), page errors and browser console warnings and errors to `POST /__log`. The sign-in service
  appends them to `data/logs/client.log` with the time and the device's address. It stops at 30 MB and 6,000 lines per
  device per hour. Nothing is logged unless the page was opened with `?log=1`.
- **Who is online:** `tools/who_is_online.py` and `tools/count_logins.py` (run inside the container).

## 8. What runs where, in one table

| Thing | Where | Port |
|---|---|---|
| Public site | Cloudflare tunnel to the container | 7380 |
| nginx | container | 80 |
| Sign-in service | container | 7381 |
| WebSocket bridge | container | 7390 |
| Astron client agent | container | 7198 |
| Astron message director | container | 7199 |
| Astron event logger | container | 7197 |
| State server (control channel) | container, inside Astron | 4002 |
| Database server (control channel) | container, inside Astron | 4003 |

Only 7380 is reachable from outside the container.

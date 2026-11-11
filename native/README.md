# Toontown: Anywhere, native desktop client

A desktop client that runs the same game code as the browser version, as plain Python on Panda3D. **No WebAssembly.**
It is the first of the native clients (Windows now; Linux and Steam Deck, Mac and Android use the same shell later).

## What it does

1. **Launcher** (`tta_native/app.py`, `ui.py`): a window in the web app's look (cloud sky, Toon Display lettering, white rounded fields,
   yellow PLAY button). It first shows a loading screen while it checks the server's `/packs.json` and downloads whatever changed,
   then the sign-in screen, then the recovery-answers card (skippable twice per computer, as on the web), then the game.
2. **Updates** (`packs.py`): the same pack list the browser version uses. The code pack (`_code`) goes into
   `%LOCALAPPDATA%\TTAnywhere\game`, the resource packs (`phase_3`, `phase_4`, ...) into `game\resources`. A pack is fetched again when
   its size on the server changes. If the server can't be reached, the files already on the computer are used.
3. **Sign-in** (`auth.py`): the server's own `/auth`, `/setrecovery` and `/recover`. The saved password is kept protected with the
   Windows account's key (`securestore.py`, DPAPI), never as plain text.
4. **Game** (`game.py`): the game's own `ToontownStart`, with the pure-Python `otpy` (from the code pack) standing in for libotp and
   libtoontown, so **stock Panda3D wheels** work (no custom Panda build). The connection to the server is `netlayer.py`: the same
   `CConnectionRepository` replacement the browser uses, but with a Python WebSocket instead of the browser's. It connects to
   `wss://<server>/ws`, so nothing but the normal web port is needed.

## Run it

```
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m tta_native
```

Useful switches:

- `--server http://192.168.40.134:7381` the dev server (or "Change server" on the sign-in screen).
- `--selftest-ui DIR` draws every launcher screen offscreen into DIR as pictures.
- `--autologin USER:PASSWORD` skips the screens (files are still checked), for testing.
- Environment `TTA_HIDDEN=1` parks the game window off screen; `TTA_TEST_SHOT="file.png,seconds"` saves a picture after that long and quits.

Everything the game prints is also written to `%LOCALAPPDATA%\TTAnywhere\logs\client.log`.

## Verified so far (2026-11-11, Windows, Python 3.13, panda3d 1.10.16)

Download and install of all 15 packs (393 MB) from the dev server; the launcher screens render like the web app; sign-in against the
server; the game starts, connects over WebSocket and reaches **Pick a Toon**. Not tried yet: making a toon, entering the world,
sound, controls, full-screen.

## Known gaps (next)

- Window size: the game's own display options take over once it starts (800x600); the launcher's 1280x720 is not carried over. Needs a
  settings screen (window size, full screen) and the widescreen HUD anchoring the web version does (`_anchor_hud` in `web/game/main.py`).
- Controls: keyboard and mouse only so far; no controller support (Steam Deck needs it).
- The launcher is a separate step from the game window (the launcher window closes and the game opens its own).
- Packaging: no installer yet (PyInstaller or Briefcase), and no self-update of the app itself; the game files do update. The update
  design is in the project notes: signed pack list, minimum app version, then a launcher that replaces its own files.
- The server still accepts a bare user name as the play token (also true for the browser version): the sign-in step is not yet tied to the
  game connection.

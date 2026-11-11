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

## Controls and window

- Keyboard and mouse as in the original game. **F11** (or Alt+Enter) switches full screen. The first start opens a 1280x720 window; the
  in-game Options page changes the resolution afterwards. The side HUD buttons are moved to the window's edges on wide windows.
- **Controllers** (`gamepad.py`, uses the same control code as the browser's touch buttons, `controls.py`): left stick or D-pad walks,
  A jumps, B is the action button, X changes the camera, Y or Start opens the sticker book, shoulder buttons are the tug-of-war pads.

## Install

Players get the app from GitHub: `https://github.com/lPuffyy/toontown-anywhere/releases/latest/download/TTAnywhere-Setup.exe`. Setup installs for
the current user (no administrator needed) into `%LOCALAPPDATA%\Programs\TTAnywhere`, adds Start menu and desktop shortcuts and an entry in
Windows' app list; Uninstall there (or `TTAnywhere.exe --uninstall`) removes the app and asks whether to keep the downloaded game files.
Setup options for scripts: `--silent --dir FOLDER --no-shortcuts --no-launch --desktop-shortcut`. Releases and updates all go through
GitHub: see [RELEASING.md](RELEASING.md).

F11 (or Alt+Enter) switches full screen in both the launcher and the game; the choice and window size are remembered.

## Build and update the Windows app

```
.venv\Scripts\pip install pyinstaller
.venv\Scripts\python build_windows.py          ->  dist\TTAnywhere\TTAnywhere.exe  and  dist\TTAnywhere-<version>-windows.zip (about 60 MB)
```

The app carries only Python, Panda3D and the launcher (the whole standard library is included, because the downloaded game code imports it).
The game code and files are downloaded on first start. Updating the **app itself** (`shell_update.py`):

1. `python tools/sign_tool.py keygen KEYFILE` once. Keep KEYFILE out of the repo and backed up in two places; put the printed public key in
   `tta_native/updatekey.py` (the one in the repo is a test key).
2. Raise `__version__` in `tta_native/__init__.py`, build, then `python tools/sign_tool.py publish KEYFILE dist\TTAnywhere-X.Y.Z-windows.zip OUTDIR`.
3. Normally the GitHub workflow does all of this on a tag (see RELEASING.md); by hand, attach OUTDIR's files to a GitHub release.

At start the app downloads `windows.json` and its signature from the newest GitHub release, checks the signature with the built-in public key, and if the version is newer
downloads the zip, checks its size and SHA-256, unpacks it beside the app and swaps the files in after it closes (`robocopy`), then
restarts. An altered list or zip is refused. The app folder must be writable (not Program Files). `min_version` in the list is for forcing an
update later (not enforced yet).

## Verified so far (2026-11-11, Windows, Python 3.13, panda3d 1.10.16)

Download and install of all 15 packs (393 MB) from the dev server; the launcher screens render like the web app; sign-in against the
server; the game starts, connects over WebSocket, picks a toon and **enters Toontown Central** in a 16:9 window with the HUD at the edges.
The packaged app does the same. A 0.1.0 app updated itself to a signed 0.1.1. Not tried yet: sound, controller and F11 on real hardware, making a toon.

## Known gaps (next)

- Sound is untested, and so are controllers and F11 on real hardware (written to Panda's documented input API, not tried with a pad).
- The launcher is a separate step from the game window (the launcher window closes and the game opens its own).
- The executable is not code-signed: SmartScreen will warn, and Windows Defender flagged one build as a generic trojan guess
  (false alarm; see RELEASING.md). Steam Deck, Linux and Mac builds use the same code and still need to be built and tried.
- `min_version` forcing is not enforced; there is no "what's new" screen.
- The server still accepts a bare user name as the play token (also true for the browser version): the sign-in step is not yet tied to the
  game connection.

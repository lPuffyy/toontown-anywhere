# TTR: Mobile (iOS build scripts)

Build scripts for an iOS app that runs a **TTR-Offline** client natively: Panda3D 1.10 and CPython 3.10,
cross-compiled for iPhone, with a small UIKit shell (loading screen, touch controls).

**This repository contains no game files.** No models, textures, sounds, or game code. The app downloads
the game's code and resources at first launch from **your own file server**, and talks to **your own game
server**. You supply both.

## What the build does
1. Clones the Panda3D fork used by TTR-Offline and applies small patches (`panda_ios/patch_sources.py`).
2. Builds OpenSSL, libpng, libjpeg, FreeType, Ogg/Vorbis for iOS, and Panda3D with an OpenGL ES 1 iPhone display.
3. Embeds Python (BeeWare Python-Apple-support) and produces an **unsigned** `.ipa` (sign it yourself, e.g. with Feather).

## Run it
GitHub, Actions, **panda-ios**, Run workflow. Inputs: `resource_server` (URL of your file server, for example
`http://192.168.1.10:7380`) and `game_server` (`host:port`). Download the `TTRPanda-ipa` artifact.
After the first full run, **panda-ios-app** rebuilds just the app shell from that run's saved libraries (about a minute).

## Your file server
A static HTTP server whose root contains the TTR-Offline `resources` folders (`phase_3` ... `phase_14`), a
`_code/` folder with the game's Python code (`toontown/`, `otp/`, `config/`), and a `manifest.json` produced by
`python3 panda_ios/make_manifest.py /path/to/served/folder` (for the resource list and md5s of the code files).

## Status / notes
- Experimental. Works on an iPhone 15 Pro Max (iOS 26) with a dev-signed build; graphics use the deprecated OpenGL ES 1 API.
- The game code and assets belong to their authors; this project is not affiliated with Disney or Toontown Rewritten.
  Check the licensing of whatever you host before sharing it.

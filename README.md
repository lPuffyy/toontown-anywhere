# Toontown: Anywhere (unofficial iOS client for TTR-Offline)

An **unofficial** iPhone and iPad client for **self-hosted TTR-Offline servers**. It is not affiliated with,
endorsed by, or connected to Toontown Rewritten, its team, or Disney, and it **cannot connect to the official
Toontown Rewritten servers**.

> **Credit:** the game client this app runs is [TTR-Offline](https://github.com/RegDogg/TTR-Offline) by
> **RegDogg**, used under the Apache License 2.0. Thank you for a great project.

**This repository contains no game files.** No game code, models, textures, or audio. The app downloads the
client code and resources at first launch from the **file server it was built for**, and connects to the **game
server it was built for**.

Native iOS: Panda3D 1.10 (the TTR-Offline fork) and CPython 3.10 are cross-compiled for iPhone and iPad, with a
UIKit shell (loading screen, sign-in, touch controls, keyboard bridge for chat). Graphics use OpenGL ES 1.

## Build your own app for your own server

The server addresses are baked in at build time, so each person builds an app for their own server.

1. **Fork this repository** on GitHub and enable Actions on the fork.
2. Run the **panda-ios** workflow (Actions, Run workflow). Inputs:
   - `resource_server`: URL of your file server, for example `https://files.example.com` or `http://192.168.1.10:7380`
   - `game_server`: `host:port` of your game server, for example `play.example.com:7298`
3. Download the **TTRPanda-ipa** artifact. It is an **unsigned** `.ipa`.
4. Sign and install it yourself (for example with SideStore, AltStore or Feather).

After the first full run, **panda-ios-app** rebuilds just the app shell from that run's saved libraries (about a minute).
It takes the saved run's id as an input.

## What your servers need to provide

**Game server:** a running [TTR-Offline](https://github.com/RegDogg/TTR-Offline) server (Astron, UberDOG and an AI).
The app connects with a play cookie of the form `name:password`. A plain TTR-Offline server accepts any cookie. If
you want real passwords, your account service has to check them.

**File server** (static HTTP or HTTPS), whose root contains:
- the TTR-Offline `resources` folders (`phase_3` and so on), and a `_code/` folder with the game's Python code
  (`toontown/`, `otp/`, `config/`)
- `manifest.json`, made with `python3 panda_ios/make_manifest.py /path/to/served/folder`
- optional, but much faster first installs: `packs.json` and `_packs/*.zip`, made with
  `python3 panda_ios/make_packs.py /path/to/served/folder` (run it after the manifest)
- optional: `_ui/background.jpg` and `_ui/logo.png` for the start screen
- optional: `POST /auth` taking the body `name:password`, answering `200` for ok or `403` with a message. If the
  path doesn't exist (404) the app treats the sign-in as accepted.

You are responsible for having the right to host whatever you serve. Check the licenses of the TTR-Offline code and
the resources repository before you share anything.

## What the build does
1. Clones the Panda3D fork used by TTR-Offline and applies small patches (`panda_ios/patch_sources.py`).
2. Builds OpenSSL, libpng, libjpeg, FreeType, Ogg/Vorbis for iOS, and Panda3D with an OpenGL ES 1 display.
3. Embeds Python (BeeWare Python-Apple-support) and produces the unsigned `.ipa`.

## Status
Experimental. Developed and tested on iPhone and iPad with dev-signed builds. The OpenGL ES 1 API it uses is
deprecated by Apple.

## License and notices
Apache License 2.0, see [LICENSE](LICENSE). Third-party components and credits are listed in
[THIRD_PARTY_NOTICES.md](panda_ios/THIRD_PARTY_NOTICES.md), which is also bundled inside the app.

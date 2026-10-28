# Toontown: Anywhere

An **unofficial, fan-made** way to play Toontown on your phone: in your browser, as an installable web app for iPhone, iPad
and Android. It is not affiliated with, endorsed by, or connected to Disney or Toontown Rewritten.

The game is built on **[Open Toontown](https://github.com/open-toontown/open-toontown)** (the open-source Toontown
Online code) with our own changes, and it runs on our own server. The browser client is Python running in WebAssembly
([pygbag](https://github.com/pygame-web/pygbag) with Panda3D).

## Play

Open **<https://toontown.puffsco.com/play/>** on your phone or tablet, then add it to your Home Screen so it opens full
screen in landscape.

**iPhone or iPad (Safari):** open the address, tap **Share** (tap the **...** button first if you don't see it), then
**View More** if it is shown, then **Add to Home Screen**, then **Add**. Open **TT: Anywhere** from your Home Screen.

**Android (Chrome works best):** open the address in the browser app itself, tap the **...** menu, then **Install app**
(or **Add to Home screen**), and open **TT: Anywhere** from your Home screen.

Good to know:

- The first start downloads the game files (about 390 MB). Use Wi-Fi. They are kept on the device afterwards. Keep the
  app installed to the Home Screen: Safari can clear the saved files of a normal browser tab after about a week without use.
- Phones drop the connection when you switch to another app. Coming back, the game tries to reconnect by itself.
- Pick a name and a password and tap **Play**. If you have been here before, use the same ones. Passwords can be
  recovered with the two answers you set up (**Forgot password?**).

## Community

- **Discord:** <https://discord.gg/NxdkuR2aCp>, for help, bug reports and chat.
- **Reddit:** <https://www.reddit.com/r/ToontownAnywhere/s/p7FFnl9jGJ>, r/ToontownAnywhere.

## What is in this repository

This repository holds everything we wrote to run the game, but **no game files**: no models, textures, sounds or
Disney content. The game's own code comes from Open Toontown, and our changes to it are a patch.

| Folder | What it is |
|---|---|
| [`web/`](web) | The browser client: the page's screens (sign-in, loading, controls), the Python glue that runs Open Toontown in the browser, and the scripts that build the download packs and the page. |
| [`server/`](server) | The all-in-one server container: Dockerfile, start-up script, web server settings, the WebSocket bridge and the sign-in service. |
| [`open-toontown/`](open-toontown) | Our changes to Open Toontown (a patch against a known upstream commit) and `otpy`, our pure-Python replacement for the game's compiled libraries. |
| [`tools/`](tools) | Migration of the old Toontown: Anywhere accounts, and small operations scripts. |
| [`docs/`](docs) | The full write-up of the system. |

Start with **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**. The other documents:

- [docs/OPERATIONS.md](docs/OPERATIONS.md): running, updating, backing up and debugging the live server.
- [docs/MIGRATION.md](docs/MIGRATION.md): how the old server's players were moved over, and what changed for them.
- [docs/CHANGES.md](docs/CHANGES.md): everything that differs from stock Open Toontown, and the known problems.
- [docs/TODO.md](docs/TODO.md): open work, with Fish Bingo (switched off because it causes crashes) at the top.

## Status

Live and under active development. Known problems are listed in [docs/CHANGES.md](docs/CHANGES.md#known-problems).

## License and notices

Our own code is under the Apache License 2.0, see [LICENSE](LICENSE). Open Toontown is under the BSD 3-Clause
License and Panda3D under a modified BSD license. Third-party components and credits are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Toontown is a trademark of Disney. This is a fan project with no commercial purpose.

# Credits and third-party notices

**Toontown: Anywhere is an unofficial client for self-hosted TTR-Offline servers.** It is not affiliated with,
endorsed by, or connected to Toontown Rewritten, its team, or Disney, and it cannot connect to the official
Toontown Rewritten servers.

## Based on TTR-Offline

The game client this app runs is **TTR-Offline** by **RegDogg**, licensed under the **Apache License 2.0**:
https://github.com/RegDogg/TTR-Offline

The app downloads the client code and game files at first launch from the server it is configured for; none of
them are part of this app. The Apache License 2.0 text is in `LICENSE.txt` (bundled in the app) and in the
repository root. Changes made by this project to TTR-Offline's code are applied on the server side and are
marked in the changed files.

## Components included in the app

| Component | License | Project |
|---|---|---|
| Panda3D (TTR-Offline fork, 1.10.11) | Modified BSD (BSD-3-Clause) | https://github.com/RegDogg/TTR-Offline-panda3d , https://www.panda3d.org |
| CPython 3.10 | PSF License | https://www.python.org |
| Python-Apple-support (BeeWare) | BSD-3-Clause and PSF | https://github.com/beeware/Python-Apple-support |
| OpenSSL 3 | Apache License 2.0 | https://www.openssl.org |
| libpng | libpng license | http://www.libpng.org |
| libjpeg (IJG) | IJG license | https://www.ijg.org |
| FreeType | FreeType License | https://freetype.org |
| libogg, libvorbis | BSD-3-Clause (Xiph.Org) | https://xiph.org |
| CA certificate bundle (`cacert.pem`) | Mozilla Public License 2.0 | https://curl.se/docs/caextract.html |

Each component is used under its own license; see the linked projects for the full terms and copyright notices.
OpenAL is Apple's system framework.

## This project's own code

The build scripts and the app shell in this repository are licensed under the Apache License 2.0 (see `LICENSE`).

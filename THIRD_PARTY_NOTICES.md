# Credits and third-party notices

**Toontown: Anywhere is an unofficial, fan-made project.** It is not affiliated with, endorsed by, or connected to Disney or
Toontown Rewritten. Toontown is a trademark of Disney. There is no commercial purpose.

This repository contains **no game files**: no models, textures, sounds or other Disney content.

## Open Toontown

The game's code (the `otp` and `toontown` packages and its server) comes from the **Open Toontown** project,
<https://github.com/open-toontown/open-toontown>. Our changes to it are in
[open-toontown/patches/](open-toontown/patches), and the patch contains parts of Open Toontown's code. Open Toontown is
licensed under the BSD 3-Clause License:

```
BSD 3-Clause License

Copyright (c) 2019, Open Toontown
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## Other components

| Component | Used for | Licence |
|---|---|---|
| [Panda3D](https://www.panda3d.org) | the 3D engine, on the server and in the browser | Modified BSD (BSD-3-Clause) |
| [pygbag](https://github.com/pygame-web/pygbag) and the pygame-web project | CPython and Panda3D compiled to WebAssembly, which runs the game in the browser | see the project |
| [Astron](https://github.com/Astron/Astron) | the game's message director, state server, database server and client agent | see the project |
| [nginx](https://nginx.org), [websockets](https://github.com/python-websockets/websockets), [pytz](https://pythonhosted.org/pytz/) | web server, WebSocket bridge, time zones | their own licences |
| Python 3.9 | the server and browser language | PSF licence |

The full text of each licence is in its own project. If you redistribute a build of this system, include the notices
those projects require.

## Our own code

Everything else in this repository (the web page, the glue code, `otpy`, the server container and the tools) is under the
Apache License 2.0, see [LICENSE](LICENSE).

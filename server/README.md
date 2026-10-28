# The server container

Everything the game needs on the server side, in one container. How it fits together is in
[../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md); how to run it is in [../docs/OPERATIONS.md](../docs/OPERATIONS.md).

| File | Job |
|---|---|
| `Dockerfile` | Python 3.9, Panda3D 1.11, nginx, and the loader that installs `otpy` into every Python process |
| `run.sh` | Starts nginx, the sign-in service, the WebSocket bridge, Astron, the UberDOG and the three districts; exits if one dies |
| `nginx.conf` | Serves the page and packs; proxies `/ws`, `/auth`, `/recover`, `/setrecovery`, `/__log` |
| `auth_service.py` | Password sign-in and recovery (`users.json`), and the test-session log receiver |
| `wsbridge.py` | WebSocket to Astron client agent TCP bridge, with per-address limits |
| `discord_status.py` | Edits one Discord message with the number of toons playing (counts only); needs `data/discord_webhook` |
| `server_status.py` | Runs in its own container and edits one Discord message with online, starting or offline; see the operations notes |
| `bug_reports.py` | Read-only: saves the Discord bug-reports forum as files (own container, needs a bot token); see the operations notes |
| `restart_auth_service.py` | Restarts the sign-in service inside a running container (after copying in a new `auth_service.py`) |
| `astrond-linux.yml` | Astron's configuration for the container (the client agent listens on all interfaces, inside the container) |
| `live.prc` | Server settings for the live game (new accounts get `NO_ACCESS`) |

## Setting up from nothing

You need a patched Open Toontown checkout ([../open-toontown/README.md](../open-toontown/README.md)) with its game
resources, plus a Linux x86-64 `astrond` binary (build Astron from <https://github.com/Astron/Astron>).

1. Lay out the three folders the container mounts (call the parent `$ROOT`):

   ```
   $ROOT/src/                      the patched checkout, with ../otpy copied in next to toontown/
   $ROOT/src/astron/linux/astrond  the Linux Astron binary
   $ROOT/src/astron/config/astrond-linux.yml    (from this folder)
   $ROOT/src/etc/live.prc                       (from this folder)
   $ROOT/web/                      _play/ (the built page) and root/ (packs, see ../web)
   $ROOT/data/                     empty; the container creates users.json and the rest
   $ROOT/build/                    this folder's files, plus overlay/direct (below)
   ```

2. Make `overlay/direct`: take the `direct` folder from the **Panda3D 1.11.0 SDK** (the pure-Python files; leave out
   compiled `.pyd`/`.dll` files and `__pycache__`) and put it at `$ROOT/build/overlay/direct`. The Panda3D wheel the
   image installs does not contain the Astron classes the game imports, so this folder supplies them.

3. Build and run:

   ```
   cd $ROOT/build && docker build -t ot-live .
   docker run -d --name ot-live --restart unless-stopped -p 7380:80 \
     -v $ROOT/src:/ot/src -v $ROOT/web:/ot/web -v $ROOT/data:/ot/data ot-live
   ```

4. Wait about two and a half minutes. Each of `$ROOT/data/logs/ai1.log` to `ai3.log` should end with `Done.`.

5. Point your tunnel or reverse proxy at port 7380.

Then migrate players (or start fresh): [../docs/MIGRATION.md](../docs/MIGRATION.md).

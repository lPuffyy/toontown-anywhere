# Beside the game server

Two small services that run in their own containers next to the game server (how to start them is in
[../docs/OPERATIONS.md](../docs/OPERATIONS.md)):

| File | Job |
|---|---|
| `server_status.py` | Edits one Discord message with whether the game is online, starting or offline, and whether each district has opened. Needs a webhook address (a secret, not in this repository). |
| `bug_reports.py` | Read-only: saves the posts of the Discord bug-reports forum as files so they can be read and checked against the logs. Needs a bot token (a secret, not in this repository). |

The game server itself (its Docker image, start-up script, web server settings, WebSocket bridge and sign-in service) is in the
fork, [open-toontown-anywhere](https://github.com/lPuffyy/open-toontown-anywhere), under `docker/`. A ready image is at
`ghcr.io/lpuffyy/open-toontown-anywhere:latest`.

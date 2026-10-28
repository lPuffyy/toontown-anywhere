"""WebSocket <-> game server bridge for the browser version. A browser cannot open the game's plain TCP port, so the page connects to
wss://<site>/ws (nginx passes that here) and this copies the bytes both ways to the game server. Nothing is read or changed.
Runs on the Zima next to the game server:  python wsbridge.py"""
import asyncio
import collections
import os
import time

from websockets.asyncio.server import serve

LISTEN_HOST = os.environ.get("WS_LISTEN", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("WS_PORT", "7390"))
GAME_HOST = os.environ.get("GAME_HOST", "127.0.0.1")
GAME_PORT = int(os.environ.get("GAME_PORT", "7198"))
MAX_PER_IP = 8
MAX_NEW_PER_MIN = 30
_open = collections.Counter()
_recent = collections.defaultdict(collections.deque)


def client_ip(ws):
    h = ws.request.headers
    ip = h.get("X-Forwarded-For") or h.get("CF-Connecting-IP") or ""
    if not ip:
        ip = str(ws.remote_address[0]) if ws.remote_address else "?"
    return ip.split(",")[0].strip()


async def pump_ws_to_tcp(ws, writer):
    async for msg in ws:
        if isinstance(msg, str):
            msg = msg.encode()
        writer.write(msg)
        await writer.drain()


async def pump_tcp_to_ws(reader, ws):
    while True:
        data = await reader.read(65536)
        if not data:
            break
        await ws.send(data)


async def handler(ws):
    ip = client_ip(ws)
    now = time.time()
    q = _recent[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if _open[ip] >= MAX_PER_IP or len(q) >= MAX_NEW_PER_MIN:
        print("refused", ip, flush=True)
        await ws.close(1013, "too many connections")
        return
    q.append(now)
    _open[ip] += 1
    print("open", ip, "now", _open[ip], flush=True)
    writer = None
    try:
        reader, writer = await asyncio.open_connection(GAME_HOST, GAME_PORT)
        tasks = [asyncio.create_task(pump_ws_to_tcp(ws, writer)), asyncio.create_task(pump_tcp_to_ws(reader, ws))]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
    except OSError as e:
        print("could not reach the game server:", e, flush=True)
        await ws.close(1011, "game server unreachable")
    except Exception as e:
        print("bridge error", type(e).__name__, e, flush=True)
    finally:
        if writer is not None:
            writer.close()
        _open[ip] -= 1
        if _open[ip] <= 0:
            del _open[ip]
        print("close", ip, flush=True)


async def main():
    async with serve(handler, LISTEN_HOST, LISTEN_PORT, max_size=2 ** 20, ping_interval=30, ping_timeout=60):
        print("ws bridge on %s:%d -> %s:%d" % (LISTEN_HOST, LISTEN_PORT, GAME_HOST, GAME_PORT), flush=True)
        await asyncio.Future()


asyncio.run(main())

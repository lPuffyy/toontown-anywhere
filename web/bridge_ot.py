"""WebSocket (from the browser page) <-> the local Open Toontown Astron client port.   venv python bridge_ot.py"""
import asyncio

import websockets

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 8766
GAME_HOST = "127.0.0.1"
GAME_PORT = 7198


async def pump_ws_to_tcp(ws, writer):
    async for msg in ws:
        writer.write(msg.encode() if isinstance(msg, str) else msg)
        await writer.drain()


async def pump_tcp_to_ws(reader, ws):
    while True:
        data = await reader.read(65536)
        if not data:
            break
        await ws.send(data)


async def handler(ws):
    print("browser connected", ws.remote_address, flush=True)
    try:
        reader, writer = await asyncio.open_connection(GAME_HOST, GAME_PORT)
    except OSError as e:
        print("could not reach the game server:", e, flush=True)
        await ws.close(1011, "game server unreachable")
        return
    tasks = [asyncio.create_task(pump_ws_to_tcp(ws, writer)), asyncio.create_task(pump_tcp_to_ws(reader, ws))]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    writer.close()
    print("closed", ws.remote_address, flush=True)


async def main():
    async with websockets.serve(handler, LISTEN_HOST, LISTEN_PORT, max_size=2 ** 22):
        print("bridge listening on ws://%s:%d -> %s:%d" % (LISTEN_HOST, LISTEN_PORT, GAME_HOST, GAME_PORT), flush=True)
        await asyncio.Future()


asyncio.run(main())

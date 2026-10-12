import socket
import urllib.request
import asyncio
import json
import aiohttp
from tabletspeed.obs_server import ObsServer

def test_obs_server_local_page_and_shutdown():
    with socket.socket() as s:
        s.bind(("127.0.0.1",0)); port=s.getsockname()[1]
    values={"speed":1}
    server=ObsServer(lambda:dict(values),port)
    server.start()
    try:
        body=urllib.request.urlopen(f"http://127.0.0.1:{port}/",timeout=2).read().decode()
        assert "Connecting" in body and "WebSocket" in body
        async def get_update():
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"http://127.0.0.1:{port}/ws",timeout=aiohttp.ClientWSTimeout(ws_close=2,ws_receive=2)) as ws:
                    first=await ws.receive(timeout=2)
                    values["speed"]=9
                    second=await ws.receive(timeout=2)
                    return json.loads(first.data),json.loads(second.data)
        first,second=asyncio.run(get_update())
        assert first["speed"]==1 and second["speed"]==9
    finally:
        server.stop()
    assert not server.thread.is_alive()


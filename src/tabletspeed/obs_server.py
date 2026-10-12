"""Optional localhost-only JSON/WebSocket source for OBS Browser Source."""
from __future__ import annotations
import asyncio, json, threading
from aiohttp import web

_HTML = """<!doctype html><html><head><meta charset=utf-8><style>html,body{margin:0;background:transparent;color:#f4f7ff;font:700 20px Segoe UI}#box{display:inline-block;padding:14px 18px;border:1px solid #33eaff;border-radius:10px;background:rgba(16,16,32,.90);box-shadow:0 0 18px #33eaff55}#speed{color:#33eaff}</style></head><body><div id=box>TabletSpeed<br><b id=speed>Connecting…</b><div id=distance></div></div><script>const box=document.getElementById('box'),speed=document.getElementById('speed'),distance=document.getElementById('distance');let w=new WebSocket(`ws://${location.host}/ws`);w.onmessage=e=>{let x=JSON.parse(e.data);speed.textContent=`${x.speed.toFixed(1)} ${x.unit}`;distance.textContent=`Distance: ${x.distance.toFixed(1)} ${x.distance_unit} · ${x.source}`;box.style.color=x.foreground||'#f4f7ff';box.style.backgroundColor=x.background||'rgba(16,16,32,.9)';box.style.borderColor=x.accent||'#33eaff';box.style.fontSize=`${x.font_size||20}px`;box.style.opacity=x.opacity??1;speed.style.color=x.accent||'#33eaff'}</script></body></html>"""
class ObsServer:
    def __init__(self, snapshot, port=8765): self.snapshot=snapshot; self.port=port; self.loop=None; self.thread=None; self.runner=None; self._ready=threading.Event(); self._startup_error=None
    async def _handler(self, request): return web.Response(text=_HTML, content_type="text/html")
    async def _ws(self, request):
        ws=web.WebSocketResponse(); await ws.prepare(request)
        async def consume_client_frames():
            async for _message in ws: pass
        reader=asyncio.create_task(consume_client_frames())
        try:
            while not ws.closed and not reader.done():
                await ws.send_str(json.dumps(self.snapshot())); await asyncio.sleep(.1)
        except (ConnectionError, asyncio.CancelledError): pass
        finally:
            reader.cancel(); await asyncio.gather(reader,return_exceptions=True)
        return ws
    async def _start(self):
        app=web.Application(); app.router.add_get("/",self._handler); app.router.add_get("/ws",self._ws)
        self.runner=web.AppRunner(app); await self.runner.setup(); site=web.TCPSite(self.runner,"127.0.0.1",self.port); await site.start()
    def start(self):
        if self.thread and self.thread.is_alive(): return
        self.loop=asyncio.new_event_loop()
        def run():
            asyncio.set_event_loop(self.loop)
            try: self.loop.run_until_complete(self._start())
            except Exception as exc: self._startup_error=exc; self._ready.set(); return
            self._ready.set(); self.loop.run_forever()
        self._ready.clear(); self._startup_error=None
        self.thread=threading.Thread(target=run,name="TabletSpeed-OBS",daemon=True); self.thread.start()
        if not self._ready.wait(3): raise RuntimeError("Timed out starting the OBS source server")
        if self._startup_error: raise RuntimeError(f"OBS source could not bind localhost:{self.port}: {self._startup_error}")
    def stop(self):
        if self.loop and self.thread and self.thread.is_alive():
            if self.runner:
                future=asyncio.run_coroutine_threadsafe(self.runner.cleanup(),self.loop)
                try: future.result(2)
                except Exception: pass
            self.loop.call_soon_threadsafe(self.loop.stop); self.thread.join(2)

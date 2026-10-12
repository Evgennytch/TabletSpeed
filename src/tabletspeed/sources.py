"""Windows cursor and optional OpenTabletDriver IPC v2 coordinate sources."""
from __future__ import annotations
import ctypes, ctypes.wintypes, os, socket, struct, sys, threading, time, math
from collections import deque
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Point:
    x: float
    y: float
    timestamp: float

class CoordinateSource(ABC):
    name = "Unknown"
    @abstractmethod
    def read(self) -> Point | None: ...
    def start(self): pass
    def stop(self): pass

class CursorSource(CoordinateSource):
    """60 Hz cursor sampler; Windows API polling runs off the GUI thread."""
    name = "Windows cursor"
    def __init__(self): self._stop=threading.Event(); self._lock=threading.Lock(); self._points=deque(maxlen=512); self.thread=None; self.error=""
    @staticmethod
    def _read_cursor() -> Point:
        if sys.platform != "win32": raise OSError("Windows cursor source is available on Windows only")
        pt = ctypes.wintypes.POINT()
        get_cursor_pos = ctypes.windll.user32.GetCursorPos
        get_cursor_pos.argtypes = (ctypes.POINTER(ctypes.wintypes.POINT),)
        get_cursor_pos.restype = ctypes.wintypes.BOOL
        if not get_cursor_pos(ctypes.byref(pt)): raise OSError("GetCursorPos failed in the current Windows session")
        return Point(pt.x, pt.y, time.perf_counter())
    def start(self):
        if self.thread and self.thread.is_alive(): return
        self.error=""; self._stop.clear()
        with self._lock: self._points.clear()
        def poll():
            while not self._stop.is_set():
                try:
                    point=self._read_cursor()
                    with self._lock: self._points.append(point)
                except Exception as exc:
                    self.error=str(exc); self._stop.wait(.1)
                self._stop.wait(1/60)
        self.thread=threading.Thread(target=poll,name="TabletSpeed-Cursor",daemon=True); self.thread.start()
    def read(self) -> Point | None:
        with self._lock: return self._points.popleft() if self._points else None
    def stop(self):
        self._stop.set()
        if self.thread and self.thread.is_alive(): self.thread.join(1.5)
        self.thread=None

class OTDProtocolError(RuntimeError): pass

def parse_otd_message(header: bytes, payload: bytes):
    """Return (type, parsed-fields); rejects malformed/oversized IPC frames."""
    if len(header) != 12: raise OTDProtocolError("Incomplete OTD IPC header")
    message_type, size, tablet_id = struct.unpack("<III", header)
    if size < 12 or size > 1_000_000 or len(payload) != size - 12: raise OTDProtocolError("Invalid OTD IPC frame size")
    if message_type == 1:  # DeviceInfo: header, maxX, maxY, pressure, IDs, name
        if size < 536: raise OTDProtocolError("Truncated OTD DeviceInfo message")
        max_x, max_y = struct.unpack_from("<ff", payload, 0)
        if not math.isfinite(max_x) or not math.isfinite(max_y) or max_x<=0 or max_y<=0: raise OTDProtocolError("Invalid OTD device coordinate bounds")
        name = payload[268:524].split(b"\0",1)[0].decode("utf-8",errors="replace")
        return message_type, {"tablet_id":tablet_id,"max_x":max_x,"max_y":max_y,"name":name}
    if message_type == 2:  # State: header, validBits, x, y, ...
        if size < 41: raise OTDProtocolError("Truncated OTD State message")
        valid_bits = struct.unpack_from("<I",payload,0)[0]
        x,y = struct.unpack_from("<ff",payload,4)
        if valid_bits & 0x3 != 0x3: return message_type, None
        return message_type, {"tablet_id":tablet_id,"x":x,"y":y,"timestamp":time.perf_counter()}
    return message_type, None

def build_otd_hello() -> bytes:
    """Build the fixed-layout OTD-IPC v2 Hello frame (800 bytes)."""
    def fixed(value: str) -> bytes: return value.encode("utf-8")[:255].ljust(256,b"\0")
    size=800
    return struct.pack("<III4xQ256s256s256sB7x",6,size,0,0x022026020501,fixed("TabletSpeed"),fixed("0.1.0"),fixed("tabletspeed.local"),1)

def connect_unix_socket(path: str | Path) -> socket.socket:
    """Connect to an OTD-IPC Unix socket, including Python builds without AF_UNIX."""
    if hasattr(socket, "AF_UNIX"):
        sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        try: sock.connect(str(path)); return sock
        except Exception: sock.close(); raise
    if os.name!="nt": raise OSError("Unix domain sockets are unavailable in this Python build")
    encoded=os.fsencode(str(path))
    if len(encoded)>107: raise OSError("OTD-IPC socket path is too long for Windows AF_UNIX")
    # Python's _socket module can omit AF_UNIX on some Windows builds even
    # though Winsock and the OTD plugin support it. Create family 1 and call
    # Winsock directly with sockaddr_un, then use the normal Python socket API.
    sock=socket.socket(1,socket.SOCK_STREAM)
    try:
        address=ctypes.create_string_buffer(b"\x01\x00"+encoded+b"\0")
        connect=ctypes.windll.ws2_32.connect
        connect.argtypes=(ctypes.c_size_t,ctypes.c_void_p,ctypes.c_int)
        connect.restype=ctypes.c_int
        if connect(sock.fileno(),address,len(address)-1)==-1:
            error=ctypes.windll.ws2_32.WSAGetLastError()
            raise OSError(error,f"Could not connect to OTD-IPC socket {path}")
        return sock
    except Exception:
        sock.close(); raise

class TabletSource(CoordinateSource):
    """OTD-IPC v2 consumer. This exclusive IPC connection can suspend OTD output mode."""
    name = "OpenTabletDriver IPC v2"
    def __init__(self):
        self.sock=None; self.thread=None; self._stop=threading.Event(); self._lock=threading.Lock(); self._latest=None
        self.error=""; self.device_name="Unknown tablet"; self.max_x=0.0; self.max_y=0.0
    @staticmethod
    def discover_socket(local_app_data: str | Path | None = None) -> Path:
        root=Path(local_app_data or os.environ.get("LOCALAPPDATA",Path.home()/"AppData"/"Local"))
        base=root/"otd-ipc"/"servers"/"v2"
        implementation=(base/"default.txt").read_text(encoding="utf-8").strip()
        if not implementation or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for c in implementation):
            raise OTDProtocolError("OpenTabletDriver IPC discovery ID is invalid")
        metadata=(base/"available"/f"{implementation}.txt").read_text(encoding="utf-8")
        for line in metadata.splitlines():
            if line.startswith("SOCKET="):
                path=Path(line[7:].strip())
                if not path.is_absolute(): raise OTDProtocolError("OTD IPC socket path must be absolute")
                return path
        raise OTDProtocolError("OTD IPC metadata has no SOCKET entry")
    def start(self):
        if sys.platform!="win32": raise OSError("OTD-IPC v2 integration is currently supported here on Windows only")
        self.stop(); self.error=""; path=self.discover_socket()
        sock=connect_unix_socket(path); sock.settimeout(1.0); sock.settimeout(.5); self.sock=sock
        sock.sendall(build_otd_hello())
        self._stop.clear(); self.thread=threading.Thread(target=self._reader,name="TabletSpeed-OTD",daemon=True); self.thread.start()
    def _read_exact(self,count):
        chunks=[]; remaining=count
        while remaining and not self._stop.is_set():
            try: part=self.sock.recv(remaining)
            except socket.timeout: continue
            if not part: raise ConnectionError("OpenTabletDriver IPC disconnected")
            chunks.append(part); remaining-=len(part)
        if remaining: return None
        return b"".join(chunks)
    def _reader(self):
        try:
            while not self._stop.is_set():
                header=self._read_exact(12)
                if header is None: break
                _,size,_=struct.unpack("<III",header)
                if size<12 or size>1_000_000: raise OTDProtocolError("Invalid OTD IPC frame size")
                payload=self._read_exact(size-12)
                if payload is None: break
                typ,data=parse_otd_message(header,payload)
                if typ==1 and data:
                    self.max_x,self.max_y=data["max_x"],data["max_y"]; self.device_name=data["name"] or "Unknown tablet"
                elif typ==2 and data:
                    with self._lock: self._latest=Point(data["x"],data["y"],data["timestamp"])
        except Exception as exc:
            if not self._stop.is_set(): self.error=str(exc)
        finally:
            try: self.sock.close()
            except Exception: pass
    def read(self) -> Point | None:
        with self._lock:
            point=self._latest; self._latest=None
            return point
    def stop(self):
        self._stop.set()
        if self.sock:
            try: self.sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            try: self.sock.close()
            except OSError: pass
            self.sock=None
        if self.thread and self.thread.is_alive(): self.thread.join(1.5)
        self.thread=None

"""Per-user Windows single-instance guard with a named activation event."""
import ctypes
import sys

class SingleInstance:
    def __init__(self,name="Local\\TabletSpeed.SingleInstance"):
        self.name=name; self.event_name=name+".Activate"; self.handle=None; self.event=None; self._kernel=None
    def acquire(self) -> bool:
        if sys.platform!="win32": raise OSError("Single-instance guard is implemented for Windows")
        kernel=ctypes.WinDLL("kernel32",use_last_error=True)
        kernel.CreateMutexW.argtypes=(ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p); kernel.CreateMutexW.restype=ctypes.c_void_p
        kernel.CreateEventW.argtypes=(ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_wchar_p); kernel.CreateEventW.restype=ctypes.c_void_p
        kernel.OpenEventW.argtypes=(ctypes.c_uint,ctypes.c_int,ctypes.c_wchar_p); kernel.OpenEventW.restype=ctypes.c_void_p
        kernel.SetEvent.argtypes=(ctypes.c_void_p,); kernel.SetEvent.restype=ctypes.c_int
        kernel.WaitForSingleObject.argtypes=(ctypes.c_void_p,ctypes.c_uint); kernel.WaitForSingleObject.restype=ctypes.c_uint
        kernel.CloseHandle.argtypes=(ctypes.c_void_p,); kernel.CloseHandle.restype=ctypes.c_int
        mutex=kernel.CreateMutexW(None,0,self.name)
        if not mutex: raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error()==183:
            kernel.CloseHandle(mutex)
            event=kernel.OpenEventW(0x0002,0,self.event_name)
            if event: kernel.SetEvent(event); kernel.CloseHandle(event)
            return False
        self._kernel=kernel; self.handle=mutex
        self.event=kernel.CreateEventW(None,0,0,self.event_name)
        if not self.event:
            error=ctypes.WinError(ctypes.get_last_error()); self.close(); raise error
        return True
    def consume_activation(self) -> bool:
        return bool(self.event and self._kernel.WaitForSingleObject(self.event,0)==0)
    def close(self):
        if self.event and self._kernel: self._kernel.CloseHandle(self.event); self.event=None
        if self.handle and self._kernel: self._kernel.CloseHandle(self.handle); self.handle=None

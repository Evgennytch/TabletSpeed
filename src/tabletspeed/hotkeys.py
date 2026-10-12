"""Small Win32 RegisterHotKey helper; callbacks run on the Qt GUI thread."""
import ctypes
import sys
from ctypes import wintypes

MOD_CONTROL=0x0002; MOD_SHIFT=0x0004; WM_HOTKEY=0x0312; PM_REMOVE=0x0001

class Hotkeys:
    def __init__(self): self.registered={}; self.user32=None
    def start(self, actions):
        if sys.platform != "win32": return ["Global hotkeys are available only on Windows."]
        self.user32=ctypes.windll.user32
        self.user32.RegisterHotKey.argtypes=(wintypes.HWND,wintypes.INT,wintypes.UINT,wintypes.UINT)
        self.user32.RegisterHotKey.restype=wintypes.BOOL
        self.user32.UnregisterHotKey.argtypes=(wintypes.HWND,wintypes.INT)
        self.user32.PeekMessageW.argtypes=(ctypes.POINTER(wintypes.MSG),wintypes.HWND,wintypes.UINT,wintypes.UINT,wintypes.UINT)
        self.user32.PeekMessageW.restype=wintypes.BOOL
        errors=[]
        for hotkey_id,(key,callback) in enumerate(actions.items(),start=1):
            if self.user32.RegisterHotKey(None,hotkey_id,MOD_CONTROL|MOD_SHIFT,ord(key)):
                self.registered[hotkey_id]=callback
            else: errors.append(f"Ctrl+Shift+{key} is already in use or could not be registered")
        return errors
    def poll(self):
        if not self.user32: return
        msg=wintypes.MSG()
        while self.user32.PeekMessageW(ctypes.byref(msg),None,WM_HOTKEY,WM_HOTKEY,PM_REMOVE):
            callback=self.registered.get(int(msg.wParam))
            if callback: callback()
    def stop(self):
        if self.user32:
            for hotkey_id in self.registered: self.user32.UnregisterHotKey(None,hotkey_id)
        self.registered.clear()

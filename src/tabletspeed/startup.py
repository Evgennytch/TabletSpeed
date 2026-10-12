"""Explicit per-user Windows startup registration."""
import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "TabletSpeed"

def command_line() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    entry = Path(__file__).resolve().parents[2] / "main.py"
    return f'"{sys.executable}" "{entry}"'

def set_autostart(enabled: bool) -> None:
    if sys.platform != "win32":
        raise OSError("Windows startup registration is available only on Windows")
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command_line())
        else:
            try: winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError: pass

def is_autostart_enabled() -> bool:
    if sys.platform != "win32": return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return value == command_line()
    except FileNotFoundError: return False

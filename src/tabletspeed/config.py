"""Versioned per-user settings and profile persistence."""
from __future__ import annotations
import json, logging, os, shutil, sys, math, re
from pathlib import Path
from typing import Any
APP_NAME = "TabletSpeed"
DEFAULTS: dict[str, Any] = {"schema": 1, "active_profile": "Default", "source": "cursor", "overlay_visible": True, "graph_visible": True, "show_current": True, "show_average": True, "show_max": True, "show_map_distance": True, "show_session_distance": True, "show_source": True, "compact": False, "overlay_topmost": True, "click_through": True, "opacity": 0.92, "font_size": 15, "accent": "#33eaff", "background": "#101020", "foreground": "#f4f7ff", "font_family": "Segoe UI", "font_file": "", "layout_orientation": "vertical", "current_color": "#33eaff", "average_color": "#a9b5c9", "max_color": "#ff64d8", "distance_color": "#80ffb0", "overlay_x": 40, "overlay_y": 40, "overlay_width": 300, "overlay_height": 150, "settings_x": 0, "settings_y": 0, "settings_width": 620, "settings_height": 560, "smoothing": 0.3, "average_window": 2.0, "noise_threshold": 0.0, "autostart": False, "obs_enabled": False, "obs_port": 8765, "units": "px/s", "physical_speed_unit": "cm/s", "distance_display_unit": "cm", "active_width_cm": 0.0, "active_height_cm": 0.0, "mapped_width_px": 0.0, "mapped_height_px": 0.0}

def data_dir() -> Path:
    root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    p = root / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p

def safe_settings(values: dict[str, Any]) -> dict[str, Any]:
    """Merge defaults and discard malformed or out-of-range JSON values."""
    result=dict(DEFAULTS)
    if not isinstance(values,dict): return result
    numeric_ranges={"opacity":(.2,1.0),"font_size":(8,48),"overlay_width":(180,1200),"overlay_height":(100,900),"overlay_x":(-100000,100000),"overlay_y":(-100000,100000),"settings_x":(-100000,100000),"settings_y":(-100000,100000),"settings_width":(300,2000),"settings_height":(300,2000),"smoothing":(0,1),"average_window":(.25,30),"noise_threshold":(0,1_000_000),"obs_port":(1024,65535),"active_width_cm":(0,1000),"active_height_cm":(0,1000),"mapped_width_px":(0,100000),"mapped_height_px":(0,100000),"tablet_diagonal_cm":(.1,1000),"tablet_aspect":(.1,10)}
    bools={k for k,v in DEFAULTS.items() if isinstance(v,bool)}
    colors={"accent","background","foreground","current_color","average_color","max_color","distance_color"}
    for key,default in DEFAULTS.items():
        value=values.get(key,default)
        if key in bools:
            if type(value) is bool: result[key]=value
        elif key in numeric_ranges:
            if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and numeric_ranges[key][0] <= value <= numeric_ranges[key][1]: result[key]=value
        elif key in colors:
            if isinstance(value,str) and re.fullmatch(r"#[0-9A-Fa-f]{6}",value): result[key]=value
        elif isinstance(value,type(default)):
            result[key]=value
    if result.get("source") not in {"cursor","tablet"}: result["source"]="cursor"
    if result.get("physical_speed_unit") not in {"cm/s","mm/s"}: result["physical_speed_unit"]="cm/s"
    if result.get("distance_display_unit") not in {"mm","cm","m","km"}: result["distance_display_unit"]="cm"
    if result.get("layout_orientation") not in {"vertical","horizontal"}: result["layout_orientation"]="vertical"
    if len(result.get("font_family", "")) > 100: result["font_family"]="Segoe UI"
    font_path=result.get("font_file","")
    if font_path:
        try: valid_font=Path(font_path).suffix.lower() in {".ttf",".otf"} and Path(font_path).is_file()
        except (OSError,ValueError): valid_font=False
        if not valid_font: result["font_file"]=""
    return result

class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "settings.json"
        self.backup = self.path.with_suffix(".json.bak")

    def load(self) -> dict[str, Any]:
        for candidate in (self.path, self.backup):
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                if not isinstance(data, dict): raise ValueError("Settings root must be an object")
                version = int(data.get("schema", 0))
                if version > 1: raise ValueError(f"Unsupported settings schema {version}")
                data = safe_settings(data); data["schema"] = 1
                return data
            except FileNotFoundError:
                continue
            except Exception:
                logging.exception("Could not load settings from %s", candidate)
                if candidate == self.path:
                    try: shutil.copy2(self.path, self.path.with_suffix(".json.corrupt"))
                    except OSError: pass
        return dict(DEFAULTS)

    def save(self, settings: dict[str, Any]) -> None:
        data = safe_settings(settings); data["schema"] = 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        if self.path.exists(): shutil.copy2(self.path, self.backup)
        temp.replace(self.path)

class Profiles:
    def __init__(self, path: Path | None = None): self.path = path or data_dir() / "profiles.json"; self.backup=self.path.with_suffix(".json.bak")
    def load(self) -> dict[str, dict]:
        for candidate in (self.path,self.backup):
            try:
                obj = json.loads(candidate.read_text(encoding="utf-8"))
                if not isinstance(obj, dict) or any(not isinstance(v, dict) for v in obj.values()): raise ValueError("Invalid profiles")
                return {str(name):safe_settings(values) for name,values in obj.items()}
            except FileNotFoundError: continue
            except Exception:
                logging.exception("Could not load profiles from %s",candidate)
                if candidate==self.path:
                    try: shutil.copy2(self.path,self.path.with_suffix(".json.corrupt"))
                    except OSError: pass
        return {"Default":dict(DEFAULTS)}
    def save(self, profiles: dict[str, dict]):
        self.path.parent.mkdir(parents=True,exist_ok=True); temp=self.path.with_suffix(".json.tmp")
        clean={str(name):safe_settings(values) for name,values in profiles.items() if str(name).strip() and len(str(name))<=80}
        temp.write_text(json.dumps(clean,indent=2),encoding="utf-8")
        if self.path.exists(): shutil.copy2(self.path,self.backup)
        temp.replace(self.path)
    def export_profile(self, name: str, target: Path):
        data = self.load()
        if name not in data: raise KeyError(name)
        target.write_text(json.dumps({"schema": 1, "name": name, "settings": data[name]}, indent=2), encoding="utf-8")
    def import_profile(self, source: Path, name: str | None = None):
        obj = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(obj, dict) or not isinstance(obj.get("settings"), dict) or obj.get("schema") != 1: raise ValueError("Unsupported profile file")
        safe = safe_settings(obj["settings"])
        profile_name=name or obj.get("name", "Imported")
        if not isinstance(profile_name,str) or not profile_name.strip() or len(profile_name)>80: raise ValueError("Invalid profile name")
        profiles = self.load(); profiles[profile_name.strip()] = safe; self.save(profiles)

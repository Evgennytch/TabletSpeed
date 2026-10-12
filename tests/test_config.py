import json
from pathlib import Path
from tabletspeed.config import SettingsStore, Profiles, DEFAULTS

def test_save_load_and_schema_migration(tmp_path):
    p=tmp_path/"settings.json"; p.write_text(json.dumps({"schema":0,"font_size":20}))
    data=SettingsStore(p).load(); assert data["schema"]==1 and data["font_size"]==20 and data["source"]=="cursor"
    store=SettingsStore(p); store.save(data); assert store.load()["font_size"]==20

def test_corrupt_backup_recovery(tmp_path):
    p=tmp_path/"settings.json"; p.write_text("{"); p.with_suffix(".json.bak").write_text(json.dumps({"schema":1,"font_size":25}))
    assert SettingsStore(p).load()["font_size"]==25
    assert p.with_suffix(".json.corrupt").exists()

def test_profile_export_import(tmp_path):
    prof=Profiles(tmp_path/"profiles.json"); prof.save({"Test":{**DEFAULTS,"font_size":21}})
    out=tmp_path/"profile.json"; prof.export_profile("Test",out); prof.import_profile(out,"Copy")
    assert prof.load()["Copy"]["font_size"]==21


def test_bad_profile_values_are_sanitized(tmp_path):
    prof=Profiles(tmp_path/"profiles.json")
    incoming=tmp_path/"bad.json"
    incoming.write_text(json.dumps({"schema":1,"name":"Imported","settings":{"opacity":99,"overlay_visible":"yes","accent":"not-a-color","font_file":"C:/bad.exe"}}))
    prof.import_profile(incoming)
    settings=prof.load()["Imported"]
    assert settings["opacity"]==DEFAULTS["opacity"]
    assert settings["overlay_visible"] is True
    assert settings["accent"]==DEFAULTS["accent"]
    assert settings["font_file"]==""

def test_corrupt_profiles_preserve_file_and_use_defaults(tmp_path):
    path=tmp_path/"profiles.json"; path.write_text("not json")
    assert Profiles(path).load()["Default"]["source"]=="cursor"
    assert path.with_suffix(".json.corrupt").exists()

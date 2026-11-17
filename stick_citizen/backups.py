"""Backups of Star Citizen's live bindings file (actionmaps.xml).

SC can lose custom binds (a crash resets them to the defaults), and it only ever keeps one copy.
Stick Citizen keeps dated copies in %APPDATA%\\StickCitizen\\backups\\sc-bindings:
  - automatic: every time it sees actionmaps.xml change (on launch and while running), the last KEEP kept
  - saved:     "Save my current config", never pruned
Identical content is stored once. A backup goes back into SC as an *exported layout* in controls\\mappings
(pick it in Options -> Keybindings -> Control Profiles). The live actionmaps.xml is only ever read.
"""
from __future__ import annotations

import hashlib
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from .paths import user_dir

KEEP = 20
_NAME = re.compile(r"^actionmaps_(?P<ch>[A-Za-z-]+)_(?P<ts>\d{4}-\d{2}-\d{2}_\d{6})(?:-(?P<n>\d+))?(?P<saved>_saved)?\.xml$")
_CHANNELS = ("LIVE", "PTU", "EPTU", "HOTFIX", "TECH-PREVIEW")


def backups_dir() -> Path:
    d = user_dir() / "backups" / "sc-bindings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def channel_of(live) -> str:
    parts = [p.upper() for p in Path(live).parts]
    return next((c for c in _CHANNELS if c in parts), "SC")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _valid(data: bytes) -> bool:
    """A whole bindings file, not one SC is halfway through writing."""
    try:
        return ET.fromstring(data).tag == "ActionMaps"
    except ET.ParseError:
        return False


def bind_count(data: bytes) -> int:
    """Every rebind with an input (keyboard, mouse, sticks, gamepad) in the file's default profile."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return 0
    return sum(1 for rb in _scope(root).iter("rebind") if (rb.get("input") or "").split("_", 1)[-1].strip())


def _scope(root):
    profiles = root.findall(".//ActionProfiles")
    if not profiles:
        return root
    return next((p for p in profiles if p.get("profileName") == "default"), profiles[0])


def _entries(d=None):
    d = d or backups_dir()
    out = []
    for f in d.glob("actionmaps_*.xml"):
        m = _NAME.match(f.name)
        if m:
            out.append((m.group("ts"), int(m.group("n") or 0), f, m))
    out.sort(key=lambda e: (e[0], e[1]), reverse=True)        # newest first
    return out


def info(f: Path, m=None) -> dict:
    m = m or _NAME.match(f.name)
    data = f.read_bytes()
    ts = time.strptime(m.group("ts"), "%Y-%m-%d_%H%M%S")
    return {"id": f.name, "when": time.strftime("%Y-%m-%d %H:%M:%S", ts), "channel": m.group("ch"),
            "kind": "saved" if m.group("saved") else "auto", "size": len(data), "binds": bind_count(data)}


def list_backups() -> list[dict]:
    return [info(f, m) for _ts, _n, f, m in _entries()]


def snapshot(live, saved=False, keep=KEEP, now=None) -> dict:
    """Copy the live bindings file into backups (reads it, never writes it).
    Returns {"ok", "created", "backup", "msg"}; ok False if the file is missing or half-written (try again later).
    Same content as an existing backup: no new file (a "saved" request marks that one saved so it's kept)."""
    live = Path(live)
    try:
        data = live.read_bytes()
    except OSError:
        return {"ok": False, "created": False, "backup": None, "msg": "Couldn't read Star Citizen's bindings file"}
    if not _valid(data):
        return {"ok": False, "created": False, "backup": None, "msg": "Star Citizen's bindings file looks half-written. Try again in a moment."}
    d = backups_dir()
    h = _digest(data)
    for _ts, _n, f, m in _entries(d):
        try:
            same = _digest(f.read_bytes()) == h
        except OSError:
            continue
        if same:
            if saved and not m.group("saved"):
                f = f.rename(f.with_name(f.stem + "_saved.xml"))
            return {"ok": True, "created": False, "backup": info(f), "msg": "Already backed up"}
    stamp = time.strftime("%Y-%m-%d_%H%M%S", time.localtime(now))
    taken = {(ts, n) for ts, n, _f, _m in _entries(d)}
    n = 0
    while (stamp, n) in taken:                    # two backups in one second
        n = 2 if n == 0 else n + 1
    f = d / f"actionmaps_{channel_of(live)}_{stamp}{f'-{n}' if n else ''}{'_saved' if saved else ''}.xml"
    f.write_bytes(data)
    prune(keep)
    return {"ok": True, "created": True, "backup": info(f), "msg": "Backed up"}


def prune(keep=KEEP) -> int:
    """Keep the newest `keep` automatic backups. Saved ones are never deleted."""
    autos = [f for _ts, _n, f, m in _entries() if not m.group("saved")]
    for f in autos[keep:]:
        f.unlink(missing_ok=True)
    return max(0, len(autos) - keep)


def get(backup_id: str):
    """A backup file by its id (file name). Only names in the backups folder, nothing else."""
    if not backup_id or "/" in backup_id or "\\" in backup_id or not _NAME.match(backup_id):
        return None
    f = backups_dir() / backup_id
    return f if f.is_file() else None


def to_layout_xml(data: bytes, name: str, note: str = "") -> str:
    """The whole backup (keyboard, mouse, sticks, options) as an exported layout SC can load from Control Profiles."""
    root = ET.fromstring(data)
    scope = _scope(root)
    out = ET.Element("ActionMaps", {"version": scope.get("version", "1"), "optionsVersion": scope.get("optionsVersion", "2"),
                                    "rebindVersion": scope.get("rebindVersion", "2"), "profileName": name})
    head = ET.SubElement(out, "CustomisationUIHeader", {"label": name, "description": note or "Restored by Stick Citizen", "image": ""})
    devs = ET.SubElement(head, "devices")
    seen = set()
    for opt in scope.iter("options"):
        t, i = (opt.get("type") or "").lower(), opt.get("instance") or ""
        if t in ("keyboard", "mouse", "joystick", "gamepad") and i and (t, i) not in seen:
            seen.add((t, i))
            ET.SubElement(devs, t, {"instance": i})
    for child in scope:
        if child.tag != "CustomisationUIHeader":
            out.append(child)
    ET.indent(out, " ")
    return ET.tostring(out, encoding="unicode") + "\n"

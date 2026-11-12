"""Where Stick Citizen keeps your stuff: a per-user folder that survives updating the exe.

Windows: %APPDATA%\\StickCitizen   Others: ~/.config/stick-citizen
v2.x kept templates and settings next to the exe; those are copied over once.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def user_dir() -> Path:
    override = os.environ.get("STICK_CITIZEN_HOME")
    if override:
        d = Path(override)
    elif os.name == "nt" and os.environ.get("APPDATA"):
        d = Path(os.environ["APPDATA"]) / "StickCitizen"
    else:
        d = Path.home() / ".config" / "stick-citizen"
    d.mkdir(parents=True, exist_ok=True)
    return d


def legacy_dir() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()


DATA_REV = 2      # bump to give everyone a clean set of stick maps (old ones are backed up, never deleted)


def migrate_legacy():
    """Copy v2.x settings from beside the exe into the user folder (never overwrites)."""
    src, dst = legacy_dir(), user_dir()
    if src.resolve() == dst.resolve():
        return
    old_cfg = src / "stick_citizen.json"
    if old_cfg.is_file() and not (dst / "stick_citizen.json").exists():
        shutil.copy2(old_cfg, dst / "stick_citizen.json")


def backup_dir() -> Path:
    import time
    d = user_dir() / "backups" / time.strftime("%Y%m%d-%H%M%S")
    d.mkdir(parents=True, exist_ok=True)
    return d


def fresh_start() -> bool:
    """Stick maps saved by an older version can carry stale control lists and half-learned buttons.
    Once per DATA_REV, move them to backups/ so the built-in profiles start clean. True if it did."""
    d = user_dir()
    mark = d / "data_rev"
    try:
        rev = int(mark.read_text().strip())
    except (OSError, ValueError):
        rev = 0
    if rev >= DATA_REV:
        return False
    moved = False
    for name in ("templates", "images"):
        src = d / name
        if src.is_dir() and any(src.iterdir()):
            shutil.move(str(src), str(backup_dir() / name))
            moved = True
    mark.write_text(str(DATA_REV))
    return moved

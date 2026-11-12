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


def migrate_legacy():
    """Copy v2.x files from beside the exe into the user folder (never overwrites)."""
    src, dst = legacy_dir(), user_dir()
    if src.resolve() == dst.resolve():
        return
    old_cfg = src / "stick_citizen.json"
    if old_cfg.is_file() and not (dst / "stick_citizen.json").exists():
        shutil.copy2(old_cfg, dst / "stick_citizen.json")
    old_t = src / "templates"
    if old_t.is_dir():
        (dst / "templates").mkdir(exist_ok=True)
        for f in old_t.iterdir():
            if f.is_file() and not (dst / "templates" / f.name).exists():
                shutil.copy2(f, dst / "templates" / f.name)

"""Settings saved next to the .exe (or the working folder when run from source)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULTS = {
    "actionmaps_path": None,   # None = auto-find SC's live actionmaps.xml
    "instances": {},           # {"1": device_index} manual js -> device overrides
    "axis_order": [0, 1, 2, 3, 4, 5, 6, 7],  # SC x,y,z,rotx,roty,rotz,slider1,slider2 -> pygame axis
    "invert": [],              # action names to invert, e.g. ["v_pitch"]
    "deadzone": 0.04,
    "speech": True,
}


def config_path() -> Path:
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
    return base / "stick_citizen.json"


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(config_path().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return cfg


def save(cfg: dict):
    try:
        config_path().write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except OSError:
        pass

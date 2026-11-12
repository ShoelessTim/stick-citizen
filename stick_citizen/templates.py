"""Device templates: where each control sits on screen, plus an optional photo behind them.

A template is JSON saved in a `templates` folder next to the exe:
{"name": "VKBsim Gladiator EVO R", "image": "evo_r.png", "tiles": {"b1": [x, y], "a0": [x, y], "h1u": [x, y]}}
Tile keys: b<n> = button n, a<slot> = SC axis slot (0=x .. 7=slider2), h<n><u|d|l|r> = hat direction.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

TILE_W, TILE_H = 168, 44
GAP = 8
HAT_DIRS = {"u": "up", "d": "down", "l": "left", "r": "right"}


def templates_dir() -> Path:
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
    return base / "templates"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "device").lower()).strip("-") or "device"


def tile_key(kind: str, index: int, direction: str = "") -> str:
    if kind == "button":
        return f"b{index}"
    if kind == "axis":
        return f"a{index}"
    return f"h{index}{direction[:1]}"


def parse_tile_key(k: str):
    if k[0] == "b":
        return "button", int(k[1:]), ""
    if k[0] == "a":
        return "axis", int(k[1:]), ""
    return "hat", int(k[1:-1]), HAT_DIRS[k[-1]]


def auto_layout(num_axes: int, num_hats: int, num_buttons: int) -> dict:
    """Plain grid: axes on top, hats as crosses, then buttons."""
    tiles = {}
    cols = 4
    y = 0
    for i in range(min(num_axes, 8)):
        tiles[f"a{i}"] = [(i % cols) * (TILE_W + GAP), y + (i // cols) * (TILE_H + GAP)]
    if num_axes:
        y += ((min(num_axes, 8) - 1) // cols + 1) * (TILE_H + GAP) + GAP * 2
    cross_w = 3 * TILE_W * 0.62
    for h in range(num_hats):
        ox = (h % 2) * (cross_w + GAP * 4)
        oy = y + (h // 2) * (3 * (TILE_H + 4) + GAP * 2)
        w = TILE_W * 0.62
        tiles[f"h{h + 1}u"] = [ox + w, oy]
        tiles[f"h{h + 1}l"] = [ox, oy + TILE_H + 4]
        tiles[f"h{h + 1}r"] = [ox + 2 * w, oy + TILE_H + 4]
        tiles[f"h{h + 1}d"] = [ox + w, oy + 2 * (TILE_H + 4)]
    if num_hats:
        y += ((num_hats - 1) // 2 + 1) * (3 * (TILE_H + 4) + GAP * 2) + GAP
    for b in range(num_buttons):
        tiles[f"b{b + 1}"] = [(b % cols) * (TILE_W + GAP), y + (b // cols) * (TILE_H + GAP)]
    return tiles


class Template:
    def __init__(self, name: str, tiles: dict, image: str = "", path: Path | None = None):
        self.name = name
        self.tiles = tiles
        self.image = image
        self.path = path

    def image_path(self):
        if not self.image:
            return None
        p = Path(self.image)
        if not p.is_absolute():
            p = templates_dir() / p
        return p if p.is_file() else None

    def save(self):
        d = templates_dir()
        d.mkdir(parents=True, exist_ok=True)
        self.path = self.path or d / f"{_slug(self.name)}.json"
        self.path.write_text(json.dumps({"name": self.name, "image": self.image, "tiles": self.tiles}, indent=1),
                             encoding="utf-8")


def load_template(device_name: str, num_axes: int, num_hats: int, num_buttons: int) -> Template:
    p = templates_dir() / f"{_slug(device_name)}.json"
    tiles = auto_layout(num_axes, num_hats, num_buttons)
    image = ""
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        tiles.update({k: v for k, v in raw.get("tiles", {}).items()})
        image = raw.get("image", "")
    except (OSError, ValueError):
        p = None
    return Template(device_name, tiles, image, p)

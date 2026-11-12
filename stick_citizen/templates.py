"""Device templates: the physical controls on a stick, where they sit on screen, plus an optional photo.

VKB-style firmware reports a fixed block of button numbers (often 128) no matter how many
physical buttons the stick has; the spare numbers are shift layers, hat-as-buttons, tempo
pulses or simply unused. So the template lists the *physical* controls, and each control owns
the button numbers it can send, one per layer:

{"name": "VKBsim Gladiator EVO R", "image": "evo_r.png",
 "controls": [{"id": "trigger", "label": "Trigger", "pos": [x, y], "inputs": {"base": 1, "shift": 33}}],
 "tiles": {"a0": [x, y], "h1u": [x, y]}}

`tiles` keeps positions for axes (a<slot>) and hat directions (h<n><u|d|l|r>), which the device
reports honestly. Button numbers no control owns are "other inputs": shown in a collapsed drawer,
and only once they are bound or have actually fired.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

TILE_W, TILE_H = 168, 44
CONTROL_H = 62          # a control tile with a shift layer
GAP = 8
COLS = 4
HAT_DIRS = {"u": "up", "d": "down", "l": "left", "r": "right"}
LAYERS = ("base", "shift")


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


def auto_layout(num_axes: int, num_hats: int, num_buttons: int = 0) -> dict:
    """Plain grid: axes on top, hats as crosses, then (legacy) buttons."""
    tiles = {}
    y = 0
    for i in range(min(num_axes, 8)):
        tiles[f"a{i}"] = [(i % COLS) * (TILE_W + GAP), y + (i // COLS) * (TILE_H + GAP)]
    if num_axes:
        y += ((min(num_axes, 8) - 1) // COLS + 1) * (TILE_H + GAP) + GAP * 2
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
        tiles[f"b{b + 1}"] = [(b % COLS) * (TILE_W + GAP), y + (b // COLS) * (TILE_H + GAP)]
    return tiles


class Control:
    """One physical control (a button, a trigger stage, a hat push...) and the button numbers it sends."""

    def __init__(self, cid: str, label: str, pos=None, inputs: dict | None = None):
        self.id = cid
        self.label = label
        self.pos = list(pos) if pos else None
        self.inputs = {k: int(v) for k, v in (inputs or {}).items() if k in LAYERS and v}

    def layer_of(self, button: int):
        return next((layer for layer, n in self.inputs.items() if n == button), None)

    def to_json(self):
        return {"id": self.id, "label": self.label, "pos": self.pos, "inputs": self.inputs}


class Template:
    def __init__(self, name: str, tiles: dict, image: str = "", path: Path | None = None,
                 controls: list[Control] | None = None):
        self.name = name
        self.tiles = tiles
        self.image = image
        self.path = path
        self.controls: list[Control] = controls or []

    # ----- controls -----
    def claimed(self) -> set[int]:
        return {n for c in self.controls for n in c.inputs.values()}

    def control_for(self, button: int):
        """(control, layer) owning this button number, or (None, None)."""
        for c in self.controls:
            layer = c.layer_of(button)
            if layer:
                return c, layer
        return None, None

    def control(self, cid: str):
        return next((c for c in self.controls if c.id == cid), None)

    def _new_id(self, label: str) -> str:
        base = _slug(label) or "control"
        cid, i = base, 2
        while self.control(cid):
            cid, i = f"{base}-{i}", i + 1
        return cid

    def controls_top(self) -> float:
        """Where button controls start: under the axis and hat tiles."""
        bottoms = [y + TILE_H for _x, y in self.tiles.values()]
        return (max(bottoms) + GAP * 3) if bottoms else 0

    def next_free_pos(self):
        taken = {tuple(c.pos) for c in self.controls if c.pos}
        top = self.controls_top()
        i = 0
        while True:
            pos = ((i % COLS) * (TILE_W + GAP), top + (i // COLS) * (CONTROL_H + GAP))
            if pos not in taken:
                return list(pos)
            i += 1

    def add_control(self, label: str, button: int) -> Control:
        self.release(button)
        c = Control(self._new_id(label), label.strip() or f"Button {button}", self.next_free_pos(), {"base": button})
        self.controls.append(c)
        return c

    def set_layer(self, control: Control, layer: str, button: int):
        self.release(button)
        control.inputs[layer] = int(button)

    def release(self, button: int):
        """Take a button number away from whichever control owns it."""
        c, layer = self.control_for(button)
        if c:
            del c.inputs[layer]
            if not c.inputs:
                self.controls.remove(c)

    def remove_control(self, control: Control):
        if control in self.controls:
            self.controls.remove(control)

    # ----- files -----
    def image_path(self):
        if not self.image:
            return None
        p = Path(self.image)
        if not p.is_absolute():
            p = templates_dir() / p
        return p if p.is_file() else None

    def to_json(self):
        tiles = {k: v for k, v in self.tiles.items() if not k.startswith("b")}
        return {"name": self.name, "image": self.image,
                "controls": [c.to_json() for c in self.controls], "tiles": tiles}

    def save(self):
        d = templates_dir()
        d.mkdir(parents=True, exist_ok=True)
        self.path = self.path or d / f"{_slug(self.name)}.json"
        self.path.write_text(json.dumps(self.to_json(), indent=1), encoding="utf-8")


def from_json(raw: dict, device_name: str, num_axes: int, num_hats: int, path=None) -> Template:
    tiles = auto_layout(num_axes, num_hats)
    tiles.update({k: v for k, v in raw.get("tiles", {}).items() if not k.startswith("b")})
    controls = [Control(c.get("id") or f"c{i}", c.get("label") or "Control", c.get("pos"), c.get("inputs"))
                for i, c in enumerate(raw.get("controls", []))]
    controls = [c for c in controls if c.inputs]
    if "controls" not in raw:
        # v2.1 templates saved a tile per button number. Keep only the ones the user actually moved
        # off the default grid: those are the real controls they laid out over their stick.
        old = raw.get("tiles", {})
        bkeys = [k for k in old if k.startswith("b")]
        if bkeys:
            nb = max(int(k[1:]) for k in bkeys)
            default = auto_layout(num_axes, num_hats, nb)
            for k in sorted(bkeys, key=lambda k: int(k[1:])):
                if [round(v) for v in old[k]] != [round(v) for v in default.get(k, [None, None])]:
                    n = int(k[1:])
                    controls.append(Control(f"button-{n}", f"Button {n}", old[k], {"base": n}))
    t = Template(raw.get("name") or device_name, tiles, raw.get("image", ""), path, controls)
    for c in t.controls:
        if not c.pos:
            c.pos = t.next_free_pos()
    return t


def load_template(device_name: str, num_axes: int, num_hats: int) -> Template:
    p = templates_dir() / f"{_slug(device_name)}.json"
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Template(device_name, auto_layout(num_axes, num_hats))
    return from_json(raw, device_name, num_axes, num_hats, p)


def other_inputs(template: Template, bound: set[int], seen: set[int], num_buttons: int | None = None) -> list[int]:
    """Button numbers for the drawer: not owned by a control, and either bound or seen firing."""
    out = (set(bound) | set(seen)) - template.claimed()
    if num_buttons is not None:
        out = {n for n in out if 0 < n <= num_buttons}
    return sorted(out)

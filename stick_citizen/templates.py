"""Stick maps: the physical controls on a stick, which inputs each sends, and where it sits on the photo.

A stick reports a block of inputs (VKB: 128 button numbers, a few hats, axes), far more than it
physically has. A stick map lists the *physical* controls:

{"name": "VKBsim Gladiator EVO R", "image": "evo_r.png",
 "controls": [
   {"id": "trigger", "label": "Main trigger", "group": "", "dir": "",
    "dot": [0.25, 0.22], "inputs": {"base": "b1", "shift": "b33"}},
   {"id": "a1-up", "label": "Up", "group": "8-way hat A1", "dir": "up",
    "dot": [0.36, 0.06], "inputs": {"base": "h1u"}}]}

- Input keys: b<n> button, h<n><u|d|l|r> hat direction, a<slot> SC axis slot.
- Layers: "base", and "shift" for the stick firmware's shift layer (a different button number).
- dot: where the control sits on the stick picture, as fractions of its width and height.
- group/dir: hat directions (or any set of related inputs) share one label on screen.

Maps live in the per-user folder, so updating the exe never loses them.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HAT_DIRS = {"u": "up", "d": "down", "l": "left", "r": "right"}
LAYERS = ("base", "shift")


def templates_dir() -> Path:
    from .paths import user_dir
    return user_dir() / "templates"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "device").lower()).strip("-") or "device"


# ----- input keys <-> binding keys (instance, kind, index, direction) -----
def key_of(kind: str, index: int, direction: str = "") -> str:
    if kind == "button":
        return f"b{index}"
    if kind == "axis":
        return f"a{index}"
    return f"h{index}{direction[:1]}"


def parse_key(k: str):
    if k[0] == "b":
        return "button", int(k[1:]), ""
    if k[0] == "a":
        return "axis", int(k[1:]), ""
    return "hat", int(k[1:-1]), HAT_DIRS[k[-1]]


def bind_key(instance: int, k: str):
    return (instance, *parse_key(k))


def short_label(k: str) -> str:
    kind, i, d = parse_key(k)
    if kind == "button":
        return f"B{i}"
    if kind == "axis":
        return ("X", "Y", "Z", "RotX", "RotY", "RotZ", "Slider 1", "Slider 2")[i]
    return f"H{i} {d}"


def _norm_key(v):
    if isinstance(v, int) or (isinstance(v, str) and v.isdigit()):
        return f"b{int(v)}"
    return v if isinstance(v, str) and re.fullmatch(r"b\d+|a\d|h\d+[udlr]", v) else None


class Control:
    def __init__(self, cid, label, inputs=None, group="", direction="", dot=None, kind="", how=""):
        self.id = cid
        self.kind = kind or ""          # "" = button/hat, "axis" = a wheel or lever the setup learns by movement
        self.how = how or ""            # what the setup walkthrough tells you to do
        self.label = label
        self.group = group or ""
        self.dir = direction or ""
        self.dot = [float(dot[0]), float(dot[1])] if dot else None
        self.inputs = {}
        for layer, v in (inputs or {}).items():
            k = _norm_key(v)
            if layer in LAYERS and k:
                self.inputs[layer] = k

    def layer_of(self, key: str):
        return next((layer for layer, k in self.inputs.items() if k == key), None)

    def to_json(self):
        return {"id": self.id, "label": self.label, "group": self.group, "dir": self.dir,
                "dot": self.dot, "inputs": self.inputs, "kind": self.kind, "how": self.how}


class Template:
    def __init__(self, name: str, image: str = "", controls=None, path: Path | None = None):
        self.name = name
        self.image = image
        self.starter_image = None       # built-in profile photo, used when the user hasn't set one
        self.controls: list[Control] = controls or []
        self.path = path
        self.starter_rev = 1            # which built-in profile revision this map has already taken in

    def claimed(self) -> set[str]:
        return {k for c in self.controls for k in c.inputs.values()}

    def control_for(self, key: str):
        for c in self.controls:
            layer = c.layer_of(key)
            if layer:
                return c, layer
        return None, None

    def control(self, cid: str):
        return next((c for c in self.controls if c.id == cid), None)

    def group_members(self, c: Control) -> list[Control]:
        if not c.group:
            return [c]
        return [x for x in self.controls if x.group == c.group]

    def _new_id(self, label: str) -> str:
        base = _slug(label) or "control"
        cid, i = base, 2
        while self.control(cid):
            cid, i = f"{base}-{i}", i + 1
        return cid

    def add_control(self, label: str, key: str, group: str = "", direction: str = "", dot=None) -> Control:
        self.release(key)
        if dot is None and group:
            sib = next((x for x in self.controls if x.group == group and x.dot), None)
            dot = sib.dot if sib else None
        c = Control(self._new_id(f"{group} {label}" if group else label), label.strip() or short_label(key),
                    {"base": key}, group, direction, dot or [0.5, 0.5])
        self.controls.append(c)
        return c

    def set_layer(self, control: Control, layer: str, key: str):
        self.release(key)
        control.inputs[layer] = key

    def release(self, key: str):
        """Take an input off whichever control has it (the control stays, waiting for a press)."""
        c, layer = self.control_for(key)
        if c:
            del c.inputs[layer]

    def unassigned(self) -> list[Control]:
        return [c for c in self.controls if "base" not in c.inputs]

    def remove_control(self, control: Control):
        if control in self.controls:
            self.controls.remove(control)

    def set_dot(self, control: Control, fx: float, fy: float):
        """Move a control (and the rest of its group) on the picture."""
        dot = [min(1.0, max(0.0, float(fx))), min(1.0, max(0.0, float(fy)))]
        for c in self.group_members(control):
            c.dot = list(dot)

    def to_json(self):
        return {"name": self.name, "image": self.image, "starter_rev": self.starter_rev,
                "controls": [c.to_json() for c in self.controls]}

    def save(self):
        d = templates_dir()
        d.mkdir(parents=True, exist_ok=True)
        self.path = self.path or d / f"{_slug(self.name)}.json"
        self.path.write_text(json.dumps(self.to_json(), indent=1), encoding="utf-8")


def from_json(raw: dict, device_name: str, path=None) -> Template:
    controls = []
    for i, c in enumerate(raw.get("controls", [])):
        ctl = Control(c.get("id") or f"c{i}", c.get("label") or "Control", c.get("inputs"),
                      c.get("group", ""), c.get("dir", ""), c.get("dot"), c.get("kind", ""), c.get("how", ""))
        controls.append(ctl)
    # v2 files ("tiles") carry nothing over: the built-in profile replaces their grid and photo.
    image = "" if "tiles" in raw else raw.get("image", "")
    t = Template(raw.get("name") or device_name, image, controls, path)
    t.starter_rev = int(raw.get("starter_rev", 1))
    return t


def starter_for(device_name: str):
    """A bundled starter map (labels + positions, no button numbers) for a known stick, if any."""
    d = Path(__file__).parent / "data" / "starters"
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if raw.get("match") and re.search(raw["match"], (device_name or "").lower()):
            return raw
    return None


def load_template(device_name: str) -> Template:
    p = templates_dir() / f"{_slug(device_name)}.json"
    try:
        t = from_json(json.loads(p.read_text(encoding="utf-8")), device_name, p)
    except (OSError, ValueError):
        t = Template(device_name, path=p)
    st = starter_for(device_name)
    if st:
        rev = int(st.get("starter_rev", 1))
        if not t.controls:                   # new stick, or a v2 file
            t.controls = from_json(st, device_name).controls
            t.starter_rev = rev
        elif rev > t.starter_rev:            # controls added to the built-in profile since this map was made
            have = {c.id for c in t.controls}
            for c in st.get("controls", []):
                if c.get("added", 1) > t.starter_rev and c.get("id") not in have:
                    t.controls.append(from_json({"controls": [c]}, device_name).controls[0])
            t.starter_rev = rev
            if t.path:
                t.save()
        img = Path(__file__).parent / "data" / "starters" / st.get("image", "")
        if st.get("image") and img.is_file():
            t.starter_image = img
    return t


def other_inputs(template: Template, bound: set[str], seen: set[str]) -> list[str]:
    """Input keys for the "unmapped" strip: not on a control, and either bound or seen firing."""
    out = (set(bound) | set(seen)) - template.claimed()
    out = {k for k in out if not k.startswith("a")}

    def order(k):
        kind, i, d = parse_key(k)
        return (kind != "button", i, d)
    return sorted(out, key=order)

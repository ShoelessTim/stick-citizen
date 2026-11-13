"""Parse Star Citizen bindings: the live actionmaps.xml or an exported layout XML."""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

AXIS_NAMES = ("x", "y", "z", "rotx", "roty", "rotz", "slider1", "slider2")

_JS_RE = re.compile(r"^js(\d+)_(.*)$")
_HAT_RE = re.compile(r"^hat(\d+)_(up|down|left|right)$")


@dataclass(frozen=True)
class Input:
    instance: int      # SC joystick instance (js1, js2, ...)
    kind: str          # "button" | "axis" | "hat"
    index: int         # button number (1-based) | axis slot | hat number (1-based)
    direction: str = ""  # hat direction

    @property
    def key(self):
        return (self.instance, self.kind, self.index, self.direction)

    def label(self) -> str:
        if self.kind == "button":
            return f"js{self.instance} button {self.index}"
        if self.kind == "axis":
            return f"js{self.instance} {AXIS_NAMES[self.index]}"
        return f"js{self.instance} hat{self.index} {self.direction}"


@dataclass(frozen=True)
class Binding:
    actionmap: str
    action: str
    input: Input
    modifiers: tuple = ()
    activation: str = ""


# SC keeps axis inversion per joystick in <options type="joystick" instance="N"><flight_move_yaw invert="1"/></options>
INVERT_OPTION = {
    "v_pitch": "flight_move_pitch", "v_yaw": "flight_move_yaw", "v_roll": "flight_move_roll",
    "v_strafe_lateral": "flight_move_strafe_lateral", "v_strafe_vertical": "flight_move_strafe_vertical",
    "v_strafe_longitudinal": "flight_move_strafe_longitudinal",
}


@dataclass
class Profile:
    path: str | None
    name: str
    devices: dict            # instance -> product string from the file
    bindings: list
    by_input: dict = field(default_factory=dict)
    inverts: set = field(default_factory=set)   # {(instance, option name)}, e.g. (2, "flight_move_yaw")

    def __post_init__(self):
        for b in self.bindings:
            self.by_input.setdefault(b.input.key, []).append(b)

    def lookup(self, key):
        return self.by_input.get(key, [])

    @property
    def instances(self):
        return sorted(set(self.devices) | {b.input.instance for b in self.bindings})


def parse_input(raw):
    """'js1_button3' -> Input. Handles axes, hats and '+' modifier combos."""
    text = (raw or "").strip().lower()
    m = _JS_RE.match(text)
    if not m:
        return None, ()
    inst = int(m.group(1))
    tokens = [t.strip() for t in m.group(2).split("+") if t.strip()]
    if not tokens:
        return None, ()
    main = tokens[-1]
    mm = _JS_RE.match(main)
    if mm:
        inst, main = int(mm.group(1)), mm.group(2)
    mods = tuple(tokens[:-1])
    if main.startswith("button") and main[6:].isdigit():
        return Input(inst, "button", int(main[6:])), mods
    if main in AXIS_NAMES:
        return Input(inst, "axis", AXIS_NAMES.index(main)), mods
    h = _HAT_RE.match(main)
    if h:
        return Input(inst, "hat", int(h.group(1)), h.group(2)), mods
    return None, mods


def parse_actionmaps(text: str, path: str | None = None) -> Profile:
    root = ET.fromstring(text)
    name = root.get("profileName") or ""
    scope = root
    profiles = root.findall(".//ActionProfiles")
    if profiles:
        scope = next((p for p in profiles if p.get("profileName") == "default"), profiles[0])
        name = scope.get("profileName") or name

    devices, inverts = {}, set()
    for opt in scope.iter("options"):
        if (opt.get("type") or "").lower() != "joystick":
            continue
        try:
            inst = int(opt.get("instance", "0"))
        except ValueError:
            continue
        if inst and inst not in devices:
            devices[inst] = (opt.get("Product") or opt.get("product") or "").strip()
        for o in opt:
            if inst and o.get("invert") == "1":
                inverts.add((inst, o.tag))

    bindings = []
    for am in scope.iter("actionmap"):
        for action in am.iter("action"):
            for rb in action.iter("rebind"):
                inp, mods = parse_input(rb.get("input"))
                if inp is None:
                    continue
                act = rb.get("activationMode") or ""
                if not act and rb.get("multiTap"):
                    act = f"multitap {rb.get('multiTap')}"
                bindings.append(Binding(am.get("name", ""), action.get("name", ""), inp, mods, act))

    if not name and path:
        name = Path(path).stem
    return Profile(path, name, devices, bindings, inverts=inverts)


def load_profile(path) -> Profile:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return parse_actionmaps(text, str(path))


_SC_ROOTS = (
    r"Program Files\Roberts Space Industries\StarCitizen",
    r"Roberts Space Industries\StarCitizen",
    r"Games\Roberts Space Industries\StarCitizen",
    r"RSI\StarCitizen",
    r"StarCitizen",
)
_CHANNELS = ("LIVE", "PTU", "EPTU", "HOTFIX", "TECH-PREVIEW")


def find_actionmaps():
    """Most recently saved actionmaps.xml from a Star Citizen install, or None."""
    if os.name != "nt":
        return None
    found = []
    for drive in "CDEFGH":
        for base in _SC_ROOTS:
            for ch in _CHANNELS:
                p = Path(f"{drive}:\\") / base / ch / "user" / "client" / "0" / "Profiles" / "default" / "actionmaps.xml"
                try:
                    if p.is_file():
                        found.append(p)
                except OSError:
                    pass
    return str(max(found, key=lambda p: p.stat().st_mtime)) if found else None

"""Editable joystick bindings: load from SC XML, change, export as an SC layout file."""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import quoteattr

from .actionmaps import AXIS_NAMES, Input, Profile
from .callouts import humanize

DATA = Path(__file__).parent / "data"

ACTIVATION_MODES = (
    "", "press", "tap", "double_tap", "hold", "delayed_press", "delayed_press_medium",
    "delayed_press_long", "delayed_hold", "delayed_hold_long", "hold_toggle", "smart_toggle", "all",
)


@dataclass
class Bound:
    map: str
    action: str
    activation: str = ""
    modifiers: tuple = ()


@dataclass
class Catalog:
    actions: list
    by_key: dict = field(default_factory=dict)
    sc_version: str = ""

    def __post_init__(self):
        self.by_action = {}
        for a in self.actions:
            self.by_key.setdefault((a["map"], a["action"]), a)
            self.by_action.setdefault(a["action"], a)

    def get(self, mapname, action):
        return self.by_key.get((mapname, action)) or self.by_action.get(action)

    def label(self, mapname, action) -> str:
        a = self.get(mapname, action)
        return a["label"] if a else humanize(action)

    def is_axis(self, mapname, action) -> bool:
        a = self.get(mapname, action)
        return bool(a and a["axis"])

    def default_activation(self, mapname, action) -> str:
        a = self.get(mapname, action)
        return a["activation"] if a else ""


def load_catalog() -> Catalog:
    try:
        raw = json.loads((DATA / "sc_actions.json").read_text(encoding="utf-8"))
        try:   # friendlier names for the actions people bind most
            names = json.loads((DATA / "label_overrides.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            names = {}
        for a in raw["actions"]:
            a["label"] = names.get(a["action"], a["label"])
        return Catalog(raw["actions"], sc_version=raw.get("sc_version", ""))
    except (OSError, ValueError, KeyError):
        return Catalog([])


def input_string(inp: Input, modifiers=()) -> str:
    if inp.kind == "button":
        main = f"button{inp.index}"
    elif inp.kind == "axis":
        main = AXIS_NAMES[inp.index]
    else:
        main = f"hat{inp.index}_{inp.direction}"
    return f"js{inp.instance}_" + "".join(m + "+" for m in modifiers) + main


class BindingSet:
    """Joystick bindings keyed by input. One joystick input per action, like SC."""

    def __init__(self, name="Stick Citizen"):
        self.name = name
        self.devices: dict[int, str] = {}       # SC js instance -> product string
        self.binds: dict[tuple, list] = {}      # Input.key -> [Bound]
        self.inverts: set = set()               # {(js instance, SC option name)}, e.g. (2, "flight_move_yaw")
        self._undo: list = []
        self.dirty = False

    # ----- load -----
    @classmethod
    def from_profile(cls, prof: Profile) -> "BindingSet":
        bs = cls(prof.name or "Stick Citizen")
        bs.devices = dict(prof.devices)
        bs.inverts = set(getattr(prof, "inverts", set()))
        for b in prof.bindings:
            bs.binds.setdefault(b.input.key, []).append(Bound(b.actionmap, b.action, b.activation, b.modifiers))
        return bs

    # ----- queries -----
    def at(self, key) -> list:
        return self.binds.get(key, [])

    def where(self, mapname, action):
        for key, lst in self.binds.items():
            if any(b.map == mapname and b.action == action for b in lst):
                return key
        return None

    def bound_actions(self) -> set:
        return {(b.map, b.action) for lst in self.binds.values() for b in lst}

    def count(self) -> int:
        return sum(len(v) for v in self.binds.values())

    # ----- edits -----
    def _snapshot(self):
        self._undo.append((copy.deepcopy(self.binds), self.dirty))
        self._undo = self._undo[-100:]
        self.dirty = True

    def undo(self) -> bool:
        if not self._undo:
            return False
        self.binds, self.dirty = self._undo.pop()
        return True

    def assign(self, key, mapname, action, activation=""):
        """Bind action to input `key`, moving it off any other input."""
        self._snapshot()
        self._remove(mapname, action)
        self.binds.setdefault(key, []).append(Bound(mapname, action, activation))

    def remove(self, key, mapname, action):
        self._snapshot()
        lst = self.binds.get(key, [])
        self.binds[key] = [b for b in lst if not (b.map == mapname and b.action == action)]
        if not self.binds[key]:
            del self.binds[key]

    def clear(self, key):
        if key in self.binds:
            self._snapshot()
            del self.binds[key]

    def set_activation(self, key, mapname, action, mode):
        self._snapshot()
        for b in self.binds.get(key, []):
            if b.map == mapname and b.action == action:
                b.activation = mode

    def _remove(self, mapname, action):
        for key in list(self.binds):
            self.binds[key] = [b for b in self.binds[key] if not (b.map == mapname and b.action == action)]
            if not self.binds[key]:
                del self.binds[key]

    # ----- export -----
    def to_xml(self, profile_name: str | None = None) -> str:
        name = re.sub(r"[^A-Za-z0-9_-]+", "-", profile_name or self.name).strip("-") or "StickCitizen"
        instances = sorted(set(self.devices) | {k[0] for k in self.binds} | {i for i, _ in self.inverts})
        by_map: dict[str, dict[str, list]] = {}
        for key, lst in self.binds.items():
            inp = Input(*key)
            for b in lst:
                by_map.setdefault(b.map, {}).setdefault(b.action, []).append((input_string(inp, b.modifiers), b.activation))
        out = [f'<ActionMaps version="1" optionsVersion="2" rebindVersion="2" profileName={quoteattr(name)}>',
               f' <CustomisationUIHeader label={quoteattr(name)} description="Made with Stick Citizen" image="">',
               "  <devices>"]
        out += [f'   <joystick instance="{i}"/>' for i in instances]
        out += ["  </devices>", " </CustomisationUIHeader>"]
        for i in instances:
            prod = self.devices.get(i, "")
            head = f' <options type="joystick" instance="{i}"' + (f" Product={quoteattr(prod)}" if prod else "")
            inv = sorted(o for inst, o in self.inverts if inst == i)
            if inv:
                out.append(head + ">")
                out += [f"  <{o} invert=\"1\"/>" for o in inv]
                out.append(" </options>")
            else:
                out.append(head + "/>")
        for mapname in sorted(by_map):
            out.append(f" <actionmap name={quoteattr(mapname)}>")
            for action in sorted(by_map[mapname]):
                out.append(f"  <action name={quoteattr(action)}>")
                for inp_s, act in by_map[mapname][action]:
                    extra = f" activationMode={quoteattr(act)}" if act else ""
                    out.append(f"   <rebind input={quoteattr(inp_s)}{extra}/>")
                out.append("  </action>")
            out.append(" </actionmap>")
        out.append("</ActionMaps>")
        return "\n".join(out) + "\n"


def mappings_dir(actionmaps_path: str | None):
    """SC's controls/mappings folder next to a live actionmaps.xml, if it exists."""
    if not actionmaps_path:
        return None
    p = Path(actionmaps_path)
    try:
        d = p.parents[2] / "controls" / "mappings"
    except IndexError:
        return None
    return d if d.parent.is_dir() else None

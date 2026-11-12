"""The bridge between the Python core and the v3 screen (stick_citizen/web).

`InputHub` owns pygame on its own thread and turns stick input into events.
`Api` is what the page calls (window.pywebview.api.*): every public method returns plain JSON.
"""
from __future__ import annotations

import base64
import collections
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from . import __version__, config as configmod
from .actionmaps import find_actionmaps, load_profile
from .bindings import ACTIVATION_MODES, BindingSet, Bound, load_catalog, mappings_dir
from .callouts import spoken
from .paths import backup_dir, fresh_start, migrate_legacy, user_dir
from .templates import bind_key, key_of, load_template, other_inputs, parse_key, short_label

MODES = [("all", "All"), ("flight", "Flight"), ("mining", "Mining"), ("salvage", "Salvage"),
         ("turret", "Turret"), ("foot", "On foot"), ("ground", "Ground")]


def mode_of(mapname: str) -> str:
    m = mapname.lower()
    if "mining" in m:
        return "mining"
    if "salvage" in m:
        return "salvage"
    if m.startswith("turret") or m == "remoterigidentitycontroller":
        return "turret"
    if m in ("vehicle_driver", "vehicle_general"):
        return "ground"
    if m.startswith(("player", "zero_gravity", "prone", "incapacitated", "tractor_beam")):
        return "foot"
    if m.startswith(("spaceship", "seat_", "vehicle_mfd", "lights")):
        return "flight"
    return "general"     # shown in every mode


def stick_side(name: str) -> str:
    n = (name or "").strip().lower()
    if n.endswith(" l") or "left" in n:
        return "L"
    if n.endswith(" r") or "right" in n:
        return "R"
    return ""


# ---------------------------------------------------------------- input
class InputHub(threading.Thread):
    """Reads every stick on a background thread. Events: (device uid, input key, on)."""

    def __init__(self):
        super().__init__(daemon=True, name="stick-input")
        self.lock = threading.Lock()
        self.devices: list[dict] = []      # {uid, name, axes, buttons, hats}
        self.axes: dict[str, list] = {}
        self.events = collections.deque(maxlen=512)
        self.generation = 0
        self.error = ""
        self._stop = threading.Event()

    def run(self):
        os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        try:
            import pygame
            pygame.display.init()
            pygame.joystick.init()
        except Exception as e:  # noqa: BLE001
            self.error = f"Couldn't start joystick input: {e}"
            return
        sticks, prev = {}, {}

        def refresh():
            sticks.clear()
            for i in range(pygame.joystick.get_count()):
                js = pygame.joystick.Joystick(i)
                sticks[str(js.get_instance_id())] = js
            with self.lock:
                self.devices = [{"uid": uid, "name": js.get_name() or "Unknown device", "axes": js.get_numaxes(),
                                 "buttons": js.get_numbuttons(), "hats": js.get_numhats()}
                                for uid, js in sticks.items()]
                self.generation += 1

        refresh()
        while not self._stop.is_set():
            try:
                changed = any(ev.type in (pygame.JOYDEVICEADDED, pygame.JOYDEVICEREMOVED) for ev in pygame.event.get())
            except pygame.error:
                changed = False
            if changed:
                refresh()
            out = []
            axes = {}
            for uid, js in list(sticks.items()):
                try:
                    for n in range(js.get_numbuttons()):
                        on = bool(js.get_button(n))
                        k = f"b{n + 1}"
                        if prev.get((uid, k), False) != on:
                            prev[(uid, k)] = on
                            out.append((uid, k, on))
                    for h in range(js.get_numhats()):
                        x, y = js.get_hat(h)
                        for d, on in (("u", y > 0), ("d", y < 0), ("l", x < 0), ("r", x > 0)):
                            k = f"h{h + 1}{d}"
                            if prev.get((uid, k), False) != on:
                                prev[(uid, k)] = on
                                out.append((uid, k, on))
                    axes[uid] = [round(js.get_axis(a), 3) for a in range(js.get_numaxes())]
                except pygame.error:
                    continue
            with self.lock:
                self.events.extend(out)
                self.axes = axes
            time.sleep(0.005)

    def stop(self):
        self._stop.set()

    def snapshot(self):
        with self.lock:
            return list(self.devices), dict(self.axes), self.generation

    def drain(self):
        with self.lock:
            out = list(self.events)
            self.events.clear()
        return out


class FakeHub:
    """Stand-in for tests and for machines with no sticks."""

    def __init__(self, devices=None):
        self.devices = devices or []
        self.events = []
        self.axes = {}
        self.generation = 1
        self.error = ""

    def start(self):
        pass

    def snapshot(self):
        return list(self.devices), dict(self.axes), self.generation

    def drain(self):
        out, self.events = self.events, []
        return out

    def press(self, uid, key, on=True):
        self.events.append((uid, key, on))


# ---------------------------------------------------------------- api
class Api:
    def __init__(self, hub=None, actionmaps=None):
        migrate_legacy()
        self._fresh = fresh_start()
        self._cfg = configmod.load()
        self._catalog = load_catalog()
        self._bset = BindingSet()
        self._path = None
        self._mtime = 0.0
        self._hub = hub if hub is not None else InputHub()
        self._hub.start()
        self._gen = -1
        self._slots: list[dict] = []
        self._templates: dict[str, object] = {}
        self._seen: dict[int, set] = {}
        self._capture = None          # slot number (or 0 = any) waiting for a press
        self._capture_want = "button"  # "button" (buttons + hats) or "axis"
        self._capture_base = {}        # axis positions when an axis capture was armed
        self._capture_cid = ""         # control being set up (its own axis may be re-learned)
        self._capture_keys = []        # inputs seen during the press being captured
        self._capture_down = set()
        self._capture_t0 = 0.0
        self._captured = None
        self._last_reload_check = 0.0
        self._window = None
        self._speaker = None
        path = actionmaps if actionmaps is not None else (self._cfg.get("actionmaps_path") or find_actionmaps())
        if path:
            self._load(path)
        self._sync_slots(force=True)

    # ----- internals -----
    def _load(self, path):
        prof = load_profile(path)
        self._bset = BindingSet.from_profile(prof)
        self._path = str(path)
        self._mtime = os.path.getmtime(path)
        self._cfg["actionmaps_path"] = self._path
        configmod.save(self._cfg)

    def _sync_slots(self, force=False):
        devices, _axes, gen = self._hub.snapshot()
        if gen == self._gen and not force:
            return False
        self._gen = gen
        wanted = dict(self._bset.devices)                       # SC instance -> product name
        instances = sorted(set(wanted) | {k[0] for k in self._bset.binds}) or [1, 2]
        overrides = {int(k): v for k, v in self._cfg.get("slot_devices", {}).items()}
        free = list(devices)
        slots = {}

        def take(pred):
            d = next((d for d in free if pred(d)), None)
            if d:
                free.remove(d)
            return d

        for inst in instances:                                   # 1. manual choice, 2. product name
            o = overrides.get(inst)
            d = take(lambda d, o=o: o and d["name"] == o)
            if not d and wanted.get(inst):
                base = wanted[inst].split("{")[0].strip().lower()
                d = take(lambda d, b=base: b and b in d["name"].lower())
            if d:
                slots[inst] = d
        for inst in instances:                                   # 3. whatever is left, in order
            if inst not in slots and free:
                slots[inst] = free.pop(0)
        n = max(instances) if instances else 0
        for d in free:                                           # extra sticks get new instances
            n += 1
            slots[n] = d
        connected = [i for i in sorted(slots)]
        shown = connected if connected else instances            # no sticks: show what the file uses
        self._slots = []
        for inst in shown:
            d = slots.get(inst)
            name = d["name"] if d else (wanted.get(inst, "").split("{")[0].strip() or f"js{inst}")
            self._slots.append({"slot": inst, "uid": d["uid"] if d else None, "name": name,
                                "connected": bool(d), "buttons": d["buttons"] if d else None,
                                "side": stick_side(name)})
        sides = [s["side"] for s in self._slots]
        if len(self._slots) == 2 and sides[0] == sides[1]:       # unknown sides: first is left
            self._slots[0]["side"], self._slots[1]["side"] = "L", "R"
        self._slots.sort(key=lambda s: {"L": 0, "": 1, "R": 2}[s["side"]])
        for s in self._slots:
            if s["connected"] and s["slot"] not in self._bset.devices:
                self._bset.devices[s["slot"]] = s["name"]
        return True

    def _slot(self, slot):
        return next((s for s in self._slots if s["slot"] == int(slot)), None)

    def _tpl(self, slot):
        s = self._slot(slot)
        name = s["name"] if s else f"js{slot}"
        if name not in self._templates:
            t = load_template(name)
            self._templates[name] = t
            self._fix_photo(t)
        return self._templates[name]

    def _fix_photo(self, t):
        """v2 photos kept their white background: cut them out once."""
        p = self._image_path(t)
        if p is None:
            return
        from .photo import cutout, needs_cutout
        if not needs_cutout(p):
            return
        d = user_dir() / "images"
        d.mkdir(exist_ok=True)
        name = f"{Path(t.name).stem or 'stick'}-{int(time.time())}.png".replace(" ", "_")
        try:
            cutout(p, d / name)
        except Exception:  # noqa: BLE001 - keep the original photo if it can't be processed
            return
        t.image = name
        t.save()

    def _bound_keys(self, slot):
        return {key_of(k[1], k[2], k[3]) for k, v in self._bset.binds.items() if v and k[0] == int(slot)}

    def _binds_json(self, slot):
        out = {}
        for k, lst in self._bset.binds.items():
            if k[0] != int(slot) or not lst:
                continue
            out[key_of(k[1], k[2], k[3])] = [
                {"map": b.map, "action": b.action, "label": self._catalog.label(b.map, b.action),
                 "activation": b.activation, "mode": mode_of(b.map), "axis": self._catalog.is_axis(b.map, b.action)}
                for b in lst]
        return out

    def _ok(self, msg="", **extra):
        return {"ok": True, "msg": msg, "state": self.get_state(), **extra}

    # ----- reads -----
    def get_state(self):
        self._sync_slots()
        sticks = []
        for s in self._slots:
            t = self._tpl(s["slot"])
            sticks.append({
                **{k: s[k] for k in ("slot", "name", "connected", "side", "buttons")},
                "has_image": self._image_path(t) is not None,
                "controls": [c.to_json() for c in t.controls],
                "unassigned": [c.id for c in t.unassigned()],
                "others": other_inputs(t, self._bound_keys(s["slot"]), self._seen.get(s["slot"], set())),
                "binds": self._binds_json(s["slot"]),
            })
        return {
            "version": __version__,
            "modes": [{"id": m, "label": lbl} for m, lbl in MODES],
            "activations": list(ACTIVATION_MODES),
            "layout": {"path": self._path, "name": Path(self._path).name if self._path else "New layout",
                       "dirty": self._bset.dirty, "count": self._bset.count()},
            "catalog": {"sc_version": self._catalog.sc_version, "actions": len(self._catalog.actions)},
            "sticks": sticks,
            "speech": bool(self._cfg.get("speech", True)),
            "input_error": getattr(self._hub, "error", ""),
            "fresh": self._fresh,
        }

    def poll(self):
        """Called by the page ~60 times a second: stick events, axes, and whether to re-read state."""
        reload = self._sync_slots()
        now = time.time()
        if now - self._last_reload_check > 1.0:
            self._last_reload_check = now
            if self._path and not self._bset.dirty:
                try:
                    m = os.path.getmtime(self._path)
                except OSError:
                    m = self._mtime
                if m != self._mtime:
                    self._load(self._path)
                    reload = True
        by_uid = {s["uid"]: s["slot"] for s in self._slots if s["uid"]}
        events = []
        for uid, key, on in self._hub.drain():
            slot = by_uid.get(uid)
            if slot is None:
                continue
            events.append({"slot": slot, "key": key, "on": on})
            if self._capture is not None and self._capture_want == "button" and self._capture in (0, slot):
                if on:
                    if not self._capture_keys:
                        self._capture_t0 = time.time()
                        self._capture = slot                 # stick to the stick that was pressed
                    if key not in self._capture_keys:
                        self._capture_keys.append(key)
                    self._capture_down.add(key)
                else:
                    self._capture_down.discard(key)
            if on:
                t = self._tpl(slot)
                if key not in t.claimed():
                    seen = self._seen.setdefault(slot, set())
                    if key not in seen:
                        seen.add(key)
                        reload = True
        # a press is done when everything it fired is released (or after 1.5 s held)
        if self._capture_keys and (not self._capture_down or time.time() - self._capture_t0 > 1.5):
            self._captured = {"slot": self._capture, "key": self._capture_keys[0], "keys": list(self._capture_keys)}
            self._capture, self._capture_keys, self._capture_down = None, [], set()
        _d, axes, _g = self._hub.snapshot()
        if self._capture is not None and self._capture_want == "axis" and not self._captured:
            order = self._cfg.get("axis_order") or list(range(8))
            for s in self._slots:
                if not s["uid"] or self._capture not in (0, s["slot"]):
                    continue
                base = self._capture_base.get(s["uid"], [])
                t = self._tpl(s["slot"])
                taken = {k for c in t.controls if c.id != self._capture_cid for k in c.inputs.values()}
                for i, v in enumerate(axes.get(s["uid"], [])):
                    if i < len(base) and abs(v - base[i]) > 0.5:
                        sc = order.index(i) if i in order else i
                        if f"a{sc}" in taken:
                            continue
                        if sc < 8:
                            self._captured = {"slot": s["slot"], "key": f"a{sc}", "keys": [f"a{sc}"]}
                            self._capture = None
                        break
                if self._captured:
                    break
        out = {"events": events, "axes": {s["slot"]: axes.get(s["uid"], []) for s in self._slots if s["uid"]},
               "reload": reload}
        if self._captured:
            out["captured"], self._captured = self._captured, None
        return out

    @staticmethod
    def _image_path(t):
        if not t.image:
            return t.starter_image
        p = Path(t.image).expanduser()
        if not p.is_absolute():
            p = user_dir() / "images" / p
        return p if p.is_file() else None

    def get_image(self, slot):
        p = self._image_path(self._tpl(slot))
        if p is None:
            return None
        mime = {".png": "image/png", ".webp": "image/webp"}.get(p.suffix.lower(), "image/jpeg")
        return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()

    def search(self, query="", mode="all", limit=80):
        q = (query or "").strip().lower().replace("_", " ")
        out = []
        for a in self._catalog.actions:
            m = mode_of(a["map"])
            if mode not in ("all", None) and m not in (mode, "general"):
                continue
            hay = f"{a['label']} {a['action']} {a['group']}".lower().replace("_", " ")
            if q and not all(w in hay for w in q.split()):
                continue
            where = self._bset.where(a["map"], a["action"])
            out.append({"map": a["map"], "action": a["action"], "label": a["label"], "group": a["group"],
                        "axis": a["axis"], "mode": m,
                        "bound": f"js{where[0]} {short_label(key_of(*where[1:]))}" if where else ""})
            if len(out) >= limit:
                break
        return out

    # ----- binding edits -----
    def assign(self, slot, key, mapname, action):
        k = bind_key(int(slot), key)
        old = self._bset.where(mapname, action)
        self._bset.assign(k, mapname, action, "" if k[1] == "axis" else self._catalog.default_activation(mapname, action))
        msg = f"{self._catalog.label(mapname, action)} → {self.input_name(slot, key)}"
        if old and old != k:
            msg += f" (moved from js{old[0]} {short_label(key_of(*old[1:]))})"
        return self._ok(msg)

    def remove(self, slot, key, mapname, action):
        self._bset.remove(bind_key(int(slot), key), mapname, action)
        return self._ok()

    def set_activation(self, slot, key, mapname, action, mode):
        self._bset.set_activation(bind_key(int(slot), key), mapname, action, mode)
        return self._ok()

    def undo(self):
        return self._ok("Undone" if self._bset.undo() else "Nothing to undo")

    def input_name(self, slot, key):
        t = self._tpl(slot)
        c, layer = t.control_for(key)
        if c:
            name = f"{c.group} {c.label}".strip() if c.group else c.label
            return name + (" ⇧" if layer == "shift" else "")
        return short_label(key)

    # ----- stick map edits -----
    def arm_capture(self, slot=0, want="button", cid=""):
        """The next press (or, with want="axis", the next big axis move) on `slot` (0 = any stick)
        comes back from poll() as `captured`. For an axis, axes already learned by another control
        (`cid` = the one being set up) are ignored, so a stick springing back to center after the
        last step doesn't count as this one."""
        self._capture = int(slot)
        self._capture_want = "axis" if want == "axis" else "button"
        self._capture_cid = cid or ""
        self._capture_base = {uid: list(v) for uid, v in self._hub.snapshot()[1].items()}
        self._capture_keys, self._capture_down = [], set()
        self._captured = None
        return {"ok": True}

    def cancel_capture(self):
        self._capture, self._capture_keys, self._capture_down = None, [], set()
        return {"ok": True}

    def learn(self, slot, cid, keys):
        """Setup step: the control was pressed and these inputs fired. One input: that's the control.
        Several (a two-stage or rapid-fire trigger): they become its stages, in the order they fired."""
        t = self._tpl(slot)
        c = t.control(cid)
        if not c or not keys:
            return {"ok": False, "msg": "Nothing to learn"}
        keys = list(dict.fromkeys(keys))
        if c.dir or c.kind == "axis" or len(keys) == 1:          # hat directions and axes take one input
            t.set_layer(c, "base", keys[0])
            t.save()
            return self._ok(f"{self.input_name(slot, keys[0])} = {short_label(keys[0])}")
        group = c.group or c.label
        siblings = [x for x in t.controls if x.group == group and not x.dir] if c.group else []
        if not c.group:
            c.group, c.label = group, "stage 1"
            siblings = [c]
        siblings.sort(key=lambda x: x.label)
        for i, k in enumerate(keys):
            target = siblings[i] if i < len(siblings) else None
            if target is None:
                target = t.add_control(f"stage {i + 1}", k, group, "", c.dot)
                target.how = c.how
            else:
                t.set_layer(target, "base", k)
        t.save()
        return self._ok(f"{group}: {len(keys)} stages = " + ", ".join(short_label(k) for k in keys))

    def map_control(self, slot, key, label, group="", direction="", target_id=""):
        t = self._tpl(slot)
        if target_id:
            c = t.control(target_id)
            if not c:
                return {"ok": False, "msg": "That control is gone"}
            t.set_layer(c, "shift", key)
            msg = f"{c.label} ⇧ = {short_label(key)}"
        else:
            c = t.add_control(label, key, group, direction)
            msg = f"{(group + ' ') if group else ''}{c.label} = {short_label(key)}"
        t.save()
        return self._ok(msg, control=c.id)

    def assign_input(self, slot, cid, layer, key):
        """Give a control (from the starter map) the input that was just pressed."""
        t = self._tpl(slot)
        c = t.control(cid)
        if not c:
            return {"ok": False, "msg": "That control is gone"}
        t.set_layer(c, layer, key)
        t.save()
        name = f"{c.group} {c.label}".strip() if c.group else c.label
        return self._ok(f"{name}{' ⇧' if layer == 'shift' else ''} = {short_label(key)}")

    def reset_stick(self, slot):
        """Start a stick's map over from the built-in profile. The old map goes to backups/."""
        s = self._slot(slot)
        t = self._tpl(slot)
        if not s or t is None:
            return {"ok": False, "msg": "No such stick"}
        if t.path and Path(t.path).is_file():
            import shutil
            shutil.move(str(t.path), str(backup_dir() / Path(t.path).name))
        self._templates.pop(s["name"], None)
        self._seen.pop(s["slot"], None)
        return self._ok("Started over. Your old map is in the backups folder.")

    def set_dot(self, slot, cid, fx, fy):
        t = self._tpl(slot)
        c = t.control(cid)
        if c:
            t.set_dot(c, fx, fy)
            t.save()
        return {"ok": bool(c)}

    def edit_control(self, slot, cid, label=None, group=None, direction=None, drop_shift=False, delete=False):
        t = self._tpl(slot)
        c = t.control(cid)
        if not c:
            return {"ok": False, "msg": "That control is gone"}
        if delete:
            t.remove_control(c)
        else:
            if label is not None:
                c.label = label.strip() or c.label
            if group is not None:
                c.group = group.strip()
            if direction is not None:
                c.dir = direction
            if drop_shift:
                c.inputs.pop("shift", None)
        t.save()
        return self._ok()

    def choose_photo(self, slot):
        path = self._dialog("open", ("Images (*.png;*.jpg;*.jpeg;*.webp)",))
        if not path:
            return {"ok": False}
        return self.set_photo(slot, path)

    def set_photo(self, slot, path):
        from .photo import cutout
        t = self._tpl(slot)
        d = user_dir() / "images"
        d.mkdir(exist_ok=True)
        name = f"{Path(t.name).stem or 'stick'}-{int(time.time())}.png".replace(" ", "_")
        try:
            cutout(path, d / name)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"Couldn't read that image: {e}"}
        t.image = name
        t.save()
        return self._ok("Photo set: background removed")

    # ----- files -----
    def _dialog(self, kind, types=(), save_name=""):
        if self._window is None:
            return None
        import webview
        fd = getattr(webview, "FileDialog", None)
        dtype = (fd.SAVE if kind == "save" else fd.OPEN) if fd else (webview.SAVE_DIALOG if kind == "save" else webview.OPEN_DIALOG)
        start = ""
        if kind == "save":
            d = mappings_dir(self._cfg.get("actionmaps_path") or find_actionmaps())
            start = str(d) if d else ""
        r = self._window.create_file_dialog(dtype, directory=start, save_filename=save_name, file_types=types)
        if not r:
            return None
        return r if isinstance(r, str) else r[0]

    def open_layout(self):
        path = self._dialog("open", ("Star Citizen bindings (*.xml)", "All files (*.*)"))
        if not path:
            return {"ok": False}
        try:
            self._load(path)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"Couldn't open that file: {e}"}
        self._sync_slots(force=True)
        return self._ok(f"Loaded {self._bset.count()} bindings")

    # ----- starting layouts -----
    @staticmethod
    def _layouts_dir():
        return Path(__file__).parent / "data" / "layouts"

    def list_layouts(self):
        out = [{"id": "blank", "name": "Blank", "description": "No joystick bindings. Build your own from scratch.", "credit": "", "for": "Any sticks"}]
        for f in sorted(self._layouts_dir().glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            out.append({k: d.get(k, "") for k in ("id", "name", "description", "credit", "for")})
        return out

    def apply_layout(self, layout_id):
        """Start from a built-in layout. Bindings land on your learned controls; undo brings the old ones back."""
        self._bset._snapshot()
        self._bset.binds = {}
        if layout_id == "blank":
            self._bset.name = "MyHOSAS"
            return self._ok("Blank layout. Click any label to bind.")
        f = self._layouts_dir() / f"{layout_id}.json"
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"ok": False, "msg": "That layout is missing"}
        self._bset.name = d.get("name", layout_id)
        done = waiting = 0
        for s in self._slots:
            side = s["side"]
            t = self._tpl(s["slot"])
            for cid, layers in d.get("sides", {}).get(side, {}).items():
                c = t.control(cid)
                if c is None:            # a control this stick doesn't have (removed in setup): nothing to wait for
                    continue
                for layer, v in layers.items():
                    key = c.inputs.get(layer)
                    if key and self._catalog.get(v[0], v[1]):
                        self._bset.binds.setdefault(bind_key(s["slot"], key), []).append(
                            Bound(v[0], v[1], v[2] if len(v) > 2 else self._catalog.default_activation(v[0], v[1])))
                        done += 1
                    else:
                        waiting += 1
            for slot_axis, v in d.get("axes", {}).get(side, {}).items():
                self._bset.binds.setdefault((s["slot"], "axis", int(slot_axis), ""), []).append(Bound(v[0], v[1], ""))
                done += 1
        msg = f"{self._bset.name}: {done} bindings placed"
        if waiting:
            msg += f" · {waiting} more land once those controls are set up (run Set up, add ⇧ layers, then apply again)"
        return self._ok(msg)

    def new_layout(self):
        devs = dict(self._bset.devices)
        self._bset = BindingSet("MyHOSAS")
        self._bset.devices = devs
        self._path = None
        return self._ok("Blank layout")

    def save_layout(self, path=None):
        name = self._bset.name if self._bset.name not in ("", "default") else "MyHOSAS"
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in name).strip("-") or "MyHOSAS"
        path = path or self._dialog("save", ("Star Citizen layout (*.xml)",), f"layout_{safe}_exported.xml")
        if not path:
            return {"ok": False}
        profile = Path(path).stem.removeprefix("layout_").removesuffix("_exported")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(self._bset.to_xml(profile), encoding="utf-8")
        self._bset.dirty = False
        return self._ok(f"Saved. In Star Citizen: Options → Keybindings → Control Profiles → “{profile}”")

    def fly_test(self):
        tmp = Path(tempfile.gettempdir()) / "stick_citizen_flytest.xml"
        tmp.write_text(self._bset.to_xml("FlyTest"), encoding="utf-8")
        cmd = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "stick_citizen"]
        subprocess.Popen(cmd + ["--fly", str(tmp)])
        return {"ok": True, "msg": "Ring course launched. Esc to come back."}

    # ----- voice -----
    def say(self, action):
        if not self._cfg.get("speech", True) or os.name != "nt":
            return {"ok": False}
        if self._speaker is None:
            from .speech import Speaker
            self._speaker = Speaker(enabled=True)
        self._speaker.say(spoken(action))
        return {"ok": True}

    def set_speech(self, on):
        self._cfg["speech"] = bool(on)
        configmod.save(self._cfg)
        return {"ok": True}

    def is_dirty(self):
        return self._bset.dirty


__all__ = ["Api", "InputHub", "FakeHub", "mode_of", "parse_key"]

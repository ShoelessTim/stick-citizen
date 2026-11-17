"""Fix it: why does this control do nothing in Star Citizen?

Two readouts, kept apart on purpose (a later troubleshooter compares them):
  raw_readout  what the stick sent to Windows during the press (from the input thread's events)
  sc_readout   what the loaded SC bindings do with those inputs (from the BindingSet only)
`diagnose` turns the two into four checks, each a light (True green, False red, None not checked)
and one plain-English line on what to do.

Nothing here reads the stick or writes files. Fixes go out as an exported layout XML (webapi.Api.fixit_fix);
SC's live actionmaps.xml is never written.
"""
from __future__ import annotations

import os
import subprocess
import time

from .templates import bind_key, short_label

CHECKS = ("sent", "bound", "wrong_stick", "mode")
MODE_NAMES = {"flight": "Flight", "mining": "Mining", "salvage": "Salvage", "turret": "Turret",
              "foot": "On foot", "ground": "Ground", "general": "any mode", "all": "any mode"}


# ---------------------------------------------------------------- readouts
def raw_readout(events, slot=None, mouse_moved=False, devices=0) -> dict:
    """What reached Windows. events: [(slot, key, on)] seen while Fix it was listening.
    slot: the stick the press landed on (first press wins), or None if nothing came in."""
    keys = []
    for s, key, on in events:
        if not on:
            continue
        if slot is None:
            slot = s
        if s == slot and key not in keys:
            keys.append(key)
    return {"slot": slot if keys else None, "keys": keys, "mouse_moved": bool(mouse_moved), "devices": devices}


def sc_readout(bset, slot, keys, catalog=None, mode_of=None, twins=()) -> dict:
    """What the loaded bindings do with `keys` on js<slot>, and with the same keys on every other js.
    twins: the other layer's number of each pressed control (base <-> shift), looked up on js<slot> only."""
    def describe(inst, key):
        return [{"map": b.map, "action": b.action, "activation": b.activation,
                 "label": catalog.label(b.map, b.action) if catalog else b.action,
                 "mode": mode_of(b.map) if mode_of else "general"}
                for b in bset.at(bind_key(inst, key))]

    others = sorted({k[0] for k in bset.binds} | set(bset.devices)) if slot is not None else []
    here = {k: describe(slot, k) for k in keys} if slot is not None else {}
    layers = {k: describe(slot, k) for k in twins if k not in here} if slot is not None else {}
    elsewhere = {}
    for inst in others:
        if inst == slot:
            continue
        hits = {k: describe(inst, k) for k in keys}
        hits = {k: v for k, v in hits.items() if v}
        if hits:
            elsewhere[inst] = hits
    return {"slot": slot, "here": here, "twins": layers, "elsewhere": elsewhere}


# ---------------------------------------------------------------- checks
def _row(cid, ok, title, fix="", can_fix=False):
    return {"id": cid, "ok": ok, "title": title, "fix": fix, "can_fix": bool(can_fix and ok is False)}


def diagnose(raw: dict, sc: dict, *, mode="flight", controls=None, stick_name=None, match="product") -> dict:
    """controls: {key: (control name, layer, {layer: key})} for the pressed stick's map (layer base/shift).
    stick_name(inst) -> "left stick" etc.  match: how this js number was paired with the stick
    ("product" = SC's file names this stick, "order" = guessed by order, "manual" = the user picked)."""
    controls = controls or {}
    name = stick_name or (lambda i: f"js{i}")
    keys, slot = raw["keys"], raw["slot"]
    shown = ", ".join(short_label(k) for k in keys)
    rows = []

    # 1. did anything reach Windows?
    if keys:
        rows.append(_row("sent", True, f"Your stick sent {shown}", "The stick and cable are fine."))
    elif raw["mouse_moved"]:
        rows.append(_row("sent", True, "Your stick moved the mouse pointer, not a button",
                         "The stick is working. See the mode check below."))
    elif not raw["devices"]:
        rows.append(_row("sent", False, "Windows can't see any sticks",
                         "Plug the sticks in (try another USB port). If HidHide is installed, allow Stick Citizen and Star Citizen in it."))
    else:
        rows.append(_row("sent", False, "Your stick sent nothing",
                         "Check the cable and USB port, then VKBDevCfg: the button may be turned off in the firmware. "
                         "If you use HidHide, make sure it isn't hiding this stick."))

    if not keys:
        rows.append(_row("bound", None, "Not checked", "Press the control again once the stick sends something."))
        rows.append(_row("wrong_stick", None, "Not checked", ""))
        if raw["mouse_moved"]:
            rows.append(_row("mode", False, "The mini-stick is in Mouse mode",
                             "Press the mini-stick straight in to switch it to Hat mode, then try again."))
        else:
            rows.append(_row("mode", None, "Not checked", ""))
        return {"slot": slot, "keys": keys, "checks": rows}

    here = sc["here"]
    bound_here = {k: v for k, v in here.items() if v}

    # 2. does SC have an action on this input?
    if bound_here:
        acts = sorted({b["label"] for v in bound_here.values() for b in v})
        rows.append(_row("bound", True, "Bound to " + ", ".join(acts[:3]) + (f" +{len(acts) - 3}" if len(acts) > 3 else ""),
                         "SC has an action on this input."))
    else:
        rows.append(_row("bound", False, f"{shown} has no action in your layout",
                         "Pick an action for it, then import the layout in SC.", can_fix=True))

    # 3. is the bind sitting on the other stick (SC's js1/js2 the other way round)?
    other = sc["elsewhere"]
    if bound_here or not other:
        rows.append(_row("wrong_stick", True, f"Bind is on this stick (js{slot})" if bound_here else "Not on your other stick either",
                         "SC's number for this stick matches." if bound_here else "So it isn't a js1/js2 mix-up."))
    else:
        inst, hits = next(iter(other.items()))
        acts = sorted({b["label"] for v in hits.values() for b in v})
        why = ("Stick Citizen guessed which stick is js1 by plug-in order, so SC may number them the other way round. "
               if match != "product" else "")
        rows.append(_row("wrong_stick", False, f"{', '.join(acts[:2])} is on the {name(inst)} (js{inst}) instead",
                         why + f"Move it to this stick (js{slot}) and import the layout in SC.", can_fix=True))

    # 4. right mode, right layer?
    mode_row = None
    for k in keys:
        cname, layer, inputs = controls.get(k, (None, None, {}))
        twin = inputs.get("base" if layer == "shift" else "shift") if layer else None
        if not here.get(k) and twin and (here.get(twin) or sc.get("twins", {}).get(twin)):
            if layer == "shift":
                mode_row = _row("mode", False, "Shift layer was on",
                                f"With shift on, {cname} sends {short_label(k)}, which has nothing on it. "
                                "Let go of your shift button (or bind the ⇧ layer too).")
            else:
                mode_row = _row("mode", False, "That action is on the ⇧ layer",
                                f"{cname}'s action is on its shift number ({short_label(twin)}). Hold your shift button and press it.")
            break
    if mode_row is None and bound_here and mode not in ("all", "general"):
        modes = {b["mode"] for v in bound_here.values() for b in v}
        if mode not in modes and "general" not in modes:
            where = ", ".join(MODE_NAMES.get(m, m) for m in sorted(modes))
            want = MODE_NAMES.get(mode, mode).lower()
            mode_row = _row("mode", False, f"Only bound for {where}",
                            f"In SC that bind only works {'on foot' if where == 'On foot' else 'in ' + where.lower()}, "
                            f"not {'on foot' if mode == 'foot' else 'in ' + want}. Bind a {want} action to it too.")
    if mode_row is None:
        mode_row = _row("mode", True, f"Works in {MODE_NAMES.get(mode, mode)}" if bound_here else "No mode or shift problem",
                        "Mode, shift layer and mini-stick mode look right.")
    rows.append(mode_row)
    return {"slot": slot, "keys": keys, "checks": rows}


# ---------------------------------------------------------------- freshness (open question: soft note only)
def sc_running() -> bool:
    if os.name != "nt":
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq StarCitizen.exe", "/NH"], capture_output=True,
                             text=True, timeout=3, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "starcitizen.exe" in out.lower()


def freshness_note(path, running: bool, now=None) -> str:
    """SC only rewrites actionmaps.xml when binds change or it quits, so while it runs the file can be behind."""
    if not path:
        return "No SC bindings file loaded. Open your actionmaps.xml or a layout to check binds."
    try:
        age = (now or time.time()) - os.path.getmtime(path)
    except OSError:
        return ""
    when = "just now" if age < 90 else f"{int(age // 60)} min ago" if age < 3600 else \
        f"{int(age // 3600)} h ago" if age < 86400 else f"{int(age // 86400)} days ago"
    if running:
        return (f"Star Citizen is running. Its bindings file was saved {when}; if you changed binds in SC since, "
                "restart SC (or quit to desktop) so Stick Citizen sees them.")
    return f"Bindings from {os.path.basename(path)}, saved {when}."

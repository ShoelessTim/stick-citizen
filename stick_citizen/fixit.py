"""Fix it: why does this control do nothing in Star Citizen?

Two readouts, kept apart on purpose (a later troubleshooter compares them):
  raw_readout  what the stick sent to Windows during the press (from the input thread's events)
  sc_readout   what the loaded SC bindings do with those inputs (from the BindingSet only)
`diagnose` turns the two into four checks, each a light (True green, False red, None not checked)
and one plain-English line on what to do.

Slice 2, the whole-layout scan, keeps the same split without a live press:
  stick_readout   what each stick can send (its learned stick map, what Windows reports, inputs seen firing)
  layout_readout  what the loaded SC bindings do on every input (BindingSet + SC's action list only)
`scan` joins them into findings that reuse the slice-1 checks (not bound, wrong stick, mode/category)
plus two only a scan can see (two actions on one input, binds on an input the stick never sends).

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


# ---------------------------------------------------------------- slice 2: whole-layout scan
def stick_readout(slot, *, name="", side="", connected=True, buttons=None, hats=None, controls=(), seen=()) -> dict:
    """What one stick can send, from the learned stick map and Windows (never from the bindings).
    controls: [(control id, display name, {layer: key})] from the stick map; a control with no inputs isn't set up.
    buttons/hats: the counts Windows reports for a connected stick (None = unknown)."""
    sends, names, unset = {}, {}, []
    for cid, cname, inputs in controls:
        if not inputs:
            unset.append(cname)
            continue
        names[cid] = cname
        for layer, k in inputs.items():
            sends[k] = (cid, cname + (" ⇧" if layer == "shift" else ""), layer)
    return {"slot": slot, "name": name, "side": side, "connected": bool(connected), "buttons": buttons, "hats": hats,
            "sends": sends, "controls": [(cid, cname, dict(inputs)) for cid, cname, inputs in controls if inputs],
            "unset": unset, "seen": set(seen)}


def layout_readout(bset, catalog=None, mode_of=None) -> dict:
    """What the loaded SC bindings do, input by input (never looks at the sticks).
    {(inst, key): [{map, action, label, mode, activation, known}]}; known: "yes", "map" (the action is in SC's
    list but under another category), "no" (not in SC's list at all), or "" (no list loaded)."""
    from .templates import key_of
    by_key = getattr(catalog, "by_key", {}) or {}
    by_action = getattr(catalog, "by_action", {}) or {}
    out = {}
    for (inst, kind, idx, d), lst in bset.binds.items():
        if not lst:
            continue
        rows = []
        for b in lst:
            if not by_key:
                known = ""
            elif (b.map, b.action) in by_key:
                known = "yes"
            else:
                known = "map" if b.action in by_action else "no"
            rows.append({"map": b.map, "action": b.action,
                         "label": catalog.label(b.map, b.action) if catalog else b.action,
                         "mode": mode_of(b.map) if mode_of else "general",
                         "activation": b.activation or (catalog.default_activation(b.map, b.action) if catalog else ""),
                         "known": known,
                         "right_map": by_action[b.action]["map"] if known == "map" else ""})
        out[(inst, key_of(kind, idx, d))] = rows
    return out


def _finding(fid, check, level, slot, key, where, title, fix, can_fix=False, **extra):
    return {"id": fid, "check": check, "level": level, "slot": slot, "key": key, "where": where,
            "title": title, "fix": fix, "can_fix": bool(can_fix), **extra}


def _sends(stick, key):
    """Does this stick send `key`? True (its map or a press says so), False (Windows says it can't),
    None (not on the map and not seen: unknown, the stick just isn't set up for it)."""
    if key in stick["sends"] or key in stick["seen"]:
        return True
    if stick["connected"]:
        kind, idx = key[0], key[1:-1] if key[0] == "h" else key[1:]
        try:
            n = int(idx)
        except ValueError:
            return None
        if kind == "b" and stick["buttons"] is not None and n > stick["buttons"]:
            return False
        if kind == "h" and stick["hats"] is not None and n > stick["hats"]:
            return False
    return None


def _key_order(k):
    from .templates import parse_key
    kind, i, d = parse_key(k)
    return ({"button": 0, "hat": 1, "axis": 2}[kind], i, d)


def scan(sticks: dict, sc: dict, *, match=None, sc_version="") -> dict:
    """Whole-layout scan. sticks: {inst: stick_readout(...)}; sc: layout_readout(...).
    match: {inst: "product" | "manual" | "order"} as in Api._match. Returns {"findings": [...], "summary": {...}}.
    Levels: "bad" (SC will do nothing / the wrong thing), "warn" (worth a look), "info" (spare controls)."""
    match = match or {}
    found, n = [], 0
    any_connected = any(s["connected"] for s in sticks.values())

    def where(inst, key):
        s = sticks.get(inst)
        side = {"L": "left stick", "R": "right stick"}.get(s["side"], "") if s else ""
        ctl = s["sends"].get(key, (None, None, None))[1] if s else None
        return {"stick": side or f"js{inst}", "js": inst, "control": ctl or short_label(key)}

    def acts(rows):
        names = sorted({r["label"] for r in rows})
        return ", ".join(names[:3]) + (f" +{len(names) - 3}" if len(names) > 3 else "")

    ver = f"SC {sc_version}" if sc_version else "SC"
    for (inst, key), rows in sorted(sc.items(), key=lambda kv: (kv[0][0], _key_order(kv[0][1]))):
        n += len(rows)
        w = where(inst, key)
        here = f"{w['control']} on your {w['stick']}" if w["stick"].endswith("stick") else f"{short_label(key)} on js{inst}"

        # dead input / wrong stick: buttons and hats only (axes are learned per stick and not all on the map)
        if key[0] in "bh" and any_connected:
            s = sticks.get(inst)
            sends = _sends(s, key) if s and s["connected"] else False
            if sends is not True:
                # slice-1 check 3 without a press: another stick sends this input and has nothing on it
                other = [o for i, o in sticks.items() if i != inst and o["connected"] and _sends(o, key) is True
                         and not sc.get((i, key))]
                firm = s is None or not s["connected"] or sends is False or not s["unset"]
                if len(other) == 1 and firm:
                    o = other[0]
                    oname = {"L": "left stick", "R": "right stick"}.get(o["side"], f"js{o['slot']}")
                    guess = (" Stick Citizen guessed which stick is js1 by plug-in order, so SC may number them the other way round."
                             if match.get(inst, "order") != "product" or match.get(o["slot"], "order") != "product" else "")
                    found.append(_finding(f"wrong_stick:{inst}:{key}", "wrong_stick", "bad", inst, key, w,
                                          f"{acts(rows)} is on js{inst} {short_label(key)}, but only your {oname} (js{o['slot']}) sends that",
                                          f"Move it to the {oname} (js{o['slot']}) and import the layout in SC." + guess,
                                          can_fix=True, to=o["slot"], acts=rows))
                    continue
                if s is None or not s["connected"]:
                    found.append(_finding(f"dead:{inst}:{key}", "dead", "bad", inst, key, w,
                                          f"{acts(rows)} is bound on js{inst}, but no stick is connected as js{inst}",
                                          "Plug that stick in, or move the action onto a stick you have (Edit).", acts=rows))
                    continue
                if sends is False:
                    lim = s["buttons"] if key[0] == "b" else s["hats"]
                    what = "buttons" if key[0] == "b" else "hats"
                    found.append(_finding(f"dead:{inst}:{key}", "dead", "bad", inst, key, w,
                                          f"{acts(rows)} is on {short_label(key)}, but your {w['stick']} only has {lim} {what}",
                                          "Windows says this stick can't send it, so it never fires. Move the action to a control you use (Edit).",
                                          acts=rows))
                    continue
                if s["unset"]:
                    fix = (f"No control on your {w['stick']}'s map sends {short_label(key)} yet. "
                           f"Run Set up ({len(s['unset'])} control{'s' if len(s['unset']) != 1 else ''} not learned), "
                           "or press it in Fix it to see if the stick sends it.")
                    found.append(_finding(f"dead:{inst}:{key}", "dead", "warn", inst, key, w,
                                          f"{acts(rows)} is on {short_label(key)}, which isn't on your stick map", fix, acts=rows))
                else:
                    found.append(_finding(f"dead:{inst}:{key}", "dead", "bad", inst, key, w,
                                          f"{acts(rows)} is on {short_label(key)}, which no control on your {w['stick']} sends",
                                          "Your stick map has every control learned and none sends it. Move the action to a control "
                                          "you use (Edit), or press the control in Fix it if you think it does.", acts=rows))
                    continue

        # mode or category: the action isn't where SC looks for it
        for r in rows:
            if r["known"] == "map":
                found.append(_finding(f"mode:{inst}:{key}:{r['map']}:{r['action']}", "mode", "bad", inst, key, w,
                                      f"{r['label']} on {here} is filed under the wrong category",
                                      f"{ver} files it under “{r['right_map']}”, not “{r['map']}”, so SC won't pick it up there. "
                                      + "Bind it again from Edit so it lands in the right place, then import the layout.",
                                      acts=[r]))
            elif r["known"] == "no":
                found.append(_finding(f"mode:{inst}:{key}:{r['map']}:{r['action']}", "mode", "warn", inst, key, w,
                                      f"{r['label']} on {here} isn't in SC's action list",
                                      f"Stick Citizen's list of {ver} actions has no “{r['action']}”. "
                                      + "It may have been renamed or removed in an SC update: find it again in Edit and bind it.",
                                      acts=[r]))

        # two actions on one input that fire together (same mode, same press type)
        clash = []
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if (a["mode"] == b["mode"] or "general" in (a["mode"], b["mode"])) and a["activation"] == b["activation"]:
                    clash += [x for x in (a, b) if x not in clash]
        if clash:
            m = next((x["mode"] for x in clash if x["mode"] != "general"), "general")
            found.append(_finding(f"conflict:{inst}:{key}", "conflict", "warn", inst, key, w,
                                  f"{' and '.join(sorted({x['label'] for x in clash}))} both fire on {here}",
                                  f"Same press, same mode ({MODE_NAMES.get(m, m)}), so SC does them together. If you only want one, "
                                  "open the control in Edit and remove the other (or give one a tap/hold).", acts=clash))

    # not bound: learned controls with no action on any layer (spare buttons are normal, so these are info)
    spare = 0
    for inst, s in sorted(sticks.items()):
        if not s["connected"]:
            continue
        side = {"L": "left stick", "R": "right stick"}.get(s["side"], f"js{inst}")
        for cid, cname, inputs in s["controls"]:
            if any(sc.get((inst, k)) for k in inputs.values()):
                continue
            key = inputs.get("base") or next(iter(inputs.values()))
            if key[0] == "a":
                continue           # axes: the scan doesn't judge which ones you fly with
            spare += 1
            found.append(_finding(f"bound:{inst}:{key}", "bound", "info", inst, key,
                                  {"stick": side, "js": inst, "control": cname, "cid": cid},
                                  f"{cname} on your {side} has no action", "Pick an action for it, then import the layout in SC.",
                                  can_fix=True))

    order = {"bad": 0, "warn": 1, "info": 2}
    first = {"wrong_stick": 0, "dead": 1, "mode": 2, "conflict": 3, "bound": 4}
    found.sort(key=lambda f: (order[f["level"]], first[f["check"]]))     # stable: stick order within a check
    guessed = sorted(i for i, s in sticks.items() if s["connected"] and match.get(i, "order") != "product")
    summary = {"binds": n, "sticks": sum(1 for s in sticks.values() if s["connected"]),
               "bad": sum(f["level"] == "bad" for f in found), "warn": sum(f["level"] == "warn" for f in found),
               "spare": spare,
               "guess": ("Stick Citizen guessed which stick is js1 by plug-in order (SC's file doesn't name each stick), "
                         "so a whole stick's binds could be on the other one. Press a control in Fix it to check."
                         if len(guessed) > 1 else ""),
               "unplugged": "" if any_connected else
               "No sticks connected, so the scan can't check which inputs your sticks send. Plug them in and scan again."}
    return {"findings": found, "summary": summary}


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

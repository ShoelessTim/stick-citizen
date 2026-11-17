"""Setup helper: suggest where a sequence of SC actions goes on one stick, and sanity-check the axes.

Pure functions, like fixit.py: nothing here reads the sticks or writes files. webapi.Api gathers the
stick map and bindings, calls in here, and applies an accepted plan to the bindings in memory (one Undo
step). The plan only reaches Star Citizen through an exported layout (Save for Star Citizen);
SC's live actionmaps.xml is never written.

Data (hand-made, edit freely; see docs/SETUP-HELPER.md):
  data/reach.json       reach rank + zone per built-in control id, axis centering, scoring weights
  data/action_use.json  how often an action gets used (often / sometimes / rare), and ready-made sequences

How a plan is chosen
  Each control has a reach r from 0 (rank 1, easiest) to 1 (rank 10). Each action wants the r for how often
  it's used (weights.use_targets: often wants the best reach, rare wants the base buttons). A placement costs
  |r - target|, plus weights.displace per bind it would replace (same mode, or "general"), plus weights.share
  per bind it would sit next to in another mode (flight + on foot on one input is fine in SC).
  Two plans are scored: the whole sequence on one hat (directions in weights.hat_order) and each action on its
  own best control (most-used first). The hat plan wins unless it costs more than the spread plan plus
  weights.sequence_bonus per action. keep_together=False always spreads.

Axis checks are a list (AXIS_CHECKS): each is a function(ctx) -> [finding]. Add one by writing a function
and appending it.
"""
from __future__ import annotations

import json
from pathlib import Path

from .actionmaps import AXIS_NAMES

DATA = Path(__file__).parent / "data"
USES = ("often", "sometimes", "rare")
MAX_RANK = 10
CALIBRATE_NOTE = ("New sensor or adapter (an Omni throttle swap, a new grip)? Calibrate it in VKBDevCfg before "
                  "binding: until you do, an axis can read dead or off-centre.")


def load_data():
    """(reach, use) from data/. Missing or broken files fall back to empty tables (everything rank 10)."""
    def read(name):
        try:
            return json.loads((DATA / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    reach, use = read("reach.json"), read("action_use.json")
    w = reach.setdefault("weights", {})
    w.setdefault("use_targets", {"often": 0.0, "sometimes": 0.45, "rare": 0.8})
    w.setdefault("displace", 0.6)
    w.setdefault("share", 0.15)
    w.setdefault("sequence_bonus", 0.5)
    w.setdefault("hat_order", ["up", "right", "down", "left", "push"])
    reach.setdefault("controls", {})
    reach.setdefault("main_axes", {})
    use.setdefault("use", {})
    use.setdefault("presets", [])
    return reach, use


def default_use(action, use_table) -> str:
    u = use_table.get("use", {}).get(action, "sometimes")
    return u if u in USES else "sometimes"


def _reach(cid, reach):
    e = reach["controls"].get(cid) or {}
    rank = max(1, min(MAX_RANK, int(e.get("rank", MAX_RANK))))
    return (rank - 1) / (MAX_RANK - 1), e.get("zone", "other")


def _overlaps(m1, m2):
    return m1 == m2 or "general" in (m1, m2)


def _place_cost(row, ctl, binds_at, reach, mode_of):
    """Cost of putting one action on one control, and what it would replace / sit next to."""
    w = reach["weights"]
    r, _zone = _reach(ctl["id"], reach)
    target = w["use_targets"].get(row["use"], w["use_targets"].get("sometimes", 0.45))
    mode = mode_of(row["map"])
    here = [b for b in binds_at(ctl["key"]) if not (b["map"] == row["map"] and b["action"] == row["action"])]
    displaces = [b for b in here if _overlaps(mode_of(b["map"]), mode)]
    keeps = [b for b in here if not _overlaps(mode_of(b["map"]), mode)]
    cost = abs(r - target) + w["displace"] * len(displaces) + w["share"] * len(keeps)
    return round(cost, 4), displaces, keeps


def _placement(i, row, ctl, cost, displaces, keeps, reach, where):
    r, zone = _reach(ctl["id"], reach)
    return {"i": i, "map": row["map"], "action": row["action"], "label": row.get("label", row["action"]),
            "use": row["use"], "cid": ctl["id"], "key": ctl["key"], "control": ctl["name"], "group": ctl.get("group", ""),
            "dir": ctl.get("dir", ""), "zone": zone, "rank": round(r * (MAX_RANK - 1)) + 1, "cost": cost,
            "displaces": displaces, "keeps": keeps, "moves_from": where(row["map"], row["action"], ctl["key"]) if where else "",
            "free": not displaces and not keeps}


def _spread(rows, cands, binds_at, reach, mode_of, where, only=None):
    """Each action on its own best control, most-used first (ties: sequence order). only: row indices to place."""
    used = set()
    out, total, skipped = {}, 0.0, []
    idx = range(len(rows)) if only is None else only
    order = sorted(idx, key=lambda i: (USES.index(rows[i]["use"]), i))
    for i in order:
        row = rows[i]
        best = None
        for c in cands:
            if c["key"] in used or bool(c["axis"]) != bool(row.get("axis")):
                continue
            cost, d, k = _place_cost(row, c, binds_at, reach, mode_of)
            if best is None or cost < best[0]:
                best = (cost, c, d, k)
        if best is None:
            skipped.append({"i": i, "label": row.get("label", row["action"]),
                            "why": "no free axis on this stick" if row.get("axis") else "no control left on this stick"})
            continue
        cost, c, d, k = best
        used.add(c["key"])
        total += cost
        out[i] = _placement(i, row, c, cost, d, k, reach, where)
    return out, total, skipped


def _hats(cands, reach):
    """Hat groups with their usable directions in weights.hat_order (diagonals left out)."""
    order = reach["weights"]["hat_order"]
    groups = {}
    for c in cands:
        if c["group"] and c["dir"] in order and not c["axis"]:
            groups.setdefault(c["group"], {})[c["dir"]] = c
    return {g: [d[k] for k in order if k in d] for g, d in groups.items()}


def suggest(rows, controls, binds_at, *, reach, mode_of, keep_together=True, where=None) -> dict:
    """Plan for an ordered sequence of actions on one stick.

    rows:      [{"map", "action", "label", "use": often|sometimes|rare, "axis": bool}] in the order wanted
    controls:  [{"id", "name", "group", "dir", "key", "axis": bool}] the stick's learned controls (base layer)
    binds_at:  key -> [{"map", "action", "label"}] what's on that input now
    where:     (map, action, key) -> "" or a name of where the action sits now if it would move
    Returns {"placements": [...] in sequence order, "skipped": [...], "together": group name or "", "notes": [...]}.
    """
    rows = [{**r, "use": r.get("use") if r.get("use") in USES else "sometimes"} for r in rows]
    cands = [c for c in controls if c.get("key")]
    notes = []
    spread, spread_cost, spread_skip = _spread(rows, cands, binds_at, reach, mode_of, where)
    plan, skipped, together = spread, spread_skip, ""
    buttons = [i for i, r in enumerate(rows) if not r.get("axis")]
    if keep_together and len(buttons) > 1:
        best = None
        for g, dirs in _hats(cands, reach).items():
            if len(dirs) < len(buttons):
                continue
            cost, placed = 0.0, {}
            for i, c in zip(buttons, dirs):
                cst, d, k = _place_cost(rows[i], c, binds_at, reach, mode_of)
                cost += cst
                placed[i] = _placement(i, rows[i], c, cst, d, k, reach, where)
            if best is None or cost < best[0]:
                best = (cost, g, placed)
        if best is None:
            notes.append(f"No hat has {len(buttons)} free directions, so the sequence is spread out.")
        else:
            ax, _ax_cost, ax_skip = _spread(rows, cands, binds_at, reach, mode_of, where,
                                            only=[i for i, r in enumerate(rows) if r.get("axis")])
            spread_btn_cost = sum(p["cost"] for i, p in spread.items() if i in buttons)
            if best[0] <= spread_btn_cost + reach["weights"]["sequence_bonus"] * len(buttons):
                plan, skipped, together = {**ax, **best[2]}, ax_skip, best[1]
            else:
                notes.append(f"Spread out: the best hat ({best[1]}) is a much worse reach for these actions than single buttons.")
    placements = [plan[i] for i in sorted(plan)]
    return {"placements": placements, "skipped": sorted(skipped, key=lambda s: s["i"]), "together": together,
            "notes": notes, "cost": round(sum(p["cost"] for p in placements), 3)}


# ---------------------------------------------------------------- axis sanity checks
def centering_of(key, control, kind, reach) -> str:
    """'spring' or 'free' (absolute: stays where you leave it) for an axis input on a stick of this kind."""
    if control is not None:
        e = reach["controls"].get(control["id"]) or {}
        if e.get("centering"):
            return e["centering"]
    name = AXIS_NAMES[int(key[1:])] if key[1:].isdigit() and int(key[1:]) < len(AXIS_NAMES) else key
    return (reach["main_axes"].get(kind) or {}).get(name, "spring")


def _axis_finding(fid, level, title, fix, **extra):
    return {"id": fid, "level": level, "title": title, "fix": fix, **extra}


def check_vertical_lift(ctx) -> list:
    """Vertical lift (v_strafe_vertical) wants a centred axis: let go and the ship stops climbing.
    Flags it when it isn't on an axis at all, or when it's on an absolute / throttle-style axis (one that stays
    where you leave it: a base wheel, a slider, an Omni stick's forward/back) of a spring-centred or Omni stick."""
    out = []
    lift = [a for a in ctx["axes"] if a["action"] == "v_strafe_vertical"]
    if not lift:
        on_buttons = [b for b in ctx["buttons"] if b in ("v_strafe_up", "v_strafe_down")]
        out.append(_axis_finding(
            "vertical_lift:none", "warn",
            "Vertical lift isn't on an axis" + (" (only on buttons: strafe up / down)" if on_buttons else ""),
            "Put Strafe up down (v_strafe_vertical) on a centred axis, like the twist or a mini-stick in analog mode, "
            "so letting go stops the climb.", action="v_strafe_vertical"))
        return out
    for a in lift:
        st = ctx["sticks"].get(a["slot"]) or {}
        kind = st.get("kind", "spring")
        if kind not in ("spring", "omni"):
            continue
        cen = centering_of(a["key"], a.get("control"), kind, ctx["reach"])
        if cen != "free":
            continue
        where = f"{st.get('stick', 'stick')} {a['name']}"
        why = "an Omni stick's forward/back stays where you leave it" if kind == "omni" and a.get("control") is None \
            else f"{a['name']} stays where you leave it"
        out.append(_axis_finding(
            f"vertical_lift:{a['slot']}:{a['key']}", "bad",
            f"Vertical lift is on an absolute (throttle-style) axis: {where}",
            f"The ship keeps climbing or sinking until you bring it back to the exact middle ({why}). "
            "Move Strafe up down to a spring-centred axis, like the twist or a mini-stick in analog mode.",
            action="v_strafe_vertical", slot=a["slot"], key=a["key"]))
    return out


AXIS_CHECKS = [check_vertical_lift]


def axis_checks(sticks: dict, axes: list, buttons, *, reach, checks=None) -> dict:
    """sticks: {slot: {"stick": "left stick", "kind": spring|omni|other}}
    axes: [{"slot", "key", "map", "action", "name", "control": {"id"} or None}] every axis bind
    buttons: actions bound to any button/hat. Returns {"findings": [...], "note": calibration note}."""
    ctx = {"sticks": sticks, "axes": axes, "buttons": set(buttons), "reach": reach}
    findings = [f for chk in (checks or AXIS_CHECKS) for f in chk(ctx)]
    findings.sort(key=lambda f: {"bad": 0, "warn": 1}.get(f["level"], 2))
    return {"findings": findings, "note": CALIBRATE_NOTE}

"""Build stick_citizen/data/sc_actions.json from SC's defaultProfile.xml.

Usage: python tools/make_catalog.py path/to/defaultProfile.xml [sc_version]
defaultProfile.xml lives inside Data.p4k (Data/Libs/Config/defaultProfile.xml).
Only action names, groups and default activation modes are kept.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from stick_citizen.callouts import humanize  # noqa: E402

AXIS_HINTS = ("x", "y", "z", "rotx", "roty", "rotz", "slider1", "slider2")
SKIP_MAPS = {"server_renderer", "spectator", "view_director_mode", "player_emotes", "stopwatch"}


def label_from_key(key: str) -> str:
    k = (key or "").lstrip("@")
    if k.lower().startswith("ui_"):
        k = k[3:]
    k = re.sub(r"^(CI|CG|CC|CO)(_|(?=[A-Z]))", "", k).replace("MFDs", "MFD")
    if "_" in k and k.lower() == k:
        words = k.split("_")
    else:
        words = re.findall(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+", k)
    words = [w for w in words if w.lower() not in ("cg", "ci", "cc", "desc")]
    text = " ".join(words).strip()
    if not text:
        return ""
    out = []
    for i, w in enumerate(text.split(" ")):
        out.append(w if (w.isupper() and len(w) > 1) else (w.capitalize() if i == 0 else w.lower()))
    return " ".join(out)


def _label(key: str, name: str) -> str:
    text = label_from_key(key)
    if not text or text.lower().startswith(("v ", "pc ", "eva ")) and "_" in key:
        text = humanize(name)
    return re.sub(r"(attack1|group)(\d)", r"\1 \2", text).replace("Attack1", "Fire")


def main(src: str, version: str = ""):
    root = ET.parse(src).getroot()
    actions = []
    for am in root.findall("actionmap"):
        mname = am.get("name", "")
        if mname in SKIP_MAPS:
            continue
        group = label_from_key(am.get("UILabel", "")) or mname
        for a in am.findall("action"):
            js = a.find("joystick")
            if "joystick" not in a.attrib and js is None:
                continue
            default = (a.get("joystick") or (js.get("input") if js is not None else "") or "").strip()
            act = a.get("activationMode") or (js.get("activationMode") if js is not None else "") or ""
            name = a.get("name", "")
            axis = not act and (default in AXIS_HINTS or bool(re.search(
                r"(_abs$|_rel$|axis|^v_(pitch|yaw|roll)$|strafe_(lateral|vertical|longitudinal)$)", name)))
            actions.append({
                "map": mname,
                "group": group,
                "action": name,
                "label": _label(a.get("UILabel", ""), name),
                "activation": act,
                "axis": axis,
            })
    out = Path(__file__).resolve().parent.parent / "stick_citizen" / "data" / "sc_actions.json"
    out.write_text(json.dumps({"sc_version": version, "actions": actions}, indent=0), encoding="utf-8")
    print(f"{len(actions)} actions -> {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "")

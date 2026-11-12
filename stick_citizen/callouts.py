"""Turn SC action names into on-screen text and a short spoken callout."""
from __future__ import annotations

# Ordered substring rules: first match wins for the spoken phrase.
_SPOKEN_RULES = (
    ("atc", "Call A T C"),
    ("landing_system", "Gear"),
    ("attack1", "Guns, guns"),
    ("missile", "Missile"),
    ("decoy", "Flares"),
    ("noise", "Chaff"),
    ("eject", "Eject, eject"),
    ("emergency_exit", "Exit seat"),
    ("exit_seat", "Exit seat"),
    ("v_exit", "Exit seat"),
    ("door", "Doors"),
    ("lock_all", "Lock"),
    ("unlock_all", "Unlock"),
    ("qdrive", "Quantum"),
    ("quantum", "Quantum"),
    ("afterburner", "Boost"),
    ("boost", "Boost"),
    ("brake", "Brake"),
    ("decoupl", "Decoupled"),
    ("gforce_safety", "G safe"),
    ("esp", "E S P"),
    ("flightready", "Flight ready"),
    ("power", "Power"),
    ("shield", "Shields"),
    ("cycle", "Cycle target"),
    ("target", "Target"),
    ("lights", "Lights"),
    ("headlight", "Lights"),
    ("scan", "Scan"),
    ("ping", "Ping"),
    ("mining", "Mining mode"),
    ("salvage", "Salvage mode"),
    ("cruise", "Cruise"),
    ("speed_limiter", "Speed limiter"),
    ("look_behind", "Check six"),
    ("freelook", "Free look"),
    ("free_look", "Free look"),
    ("zoom", "Zoom"),
    ("mfd", "M F D"),
    ("map", "Map"),
    ("mobiglas", "MobiGlas"),
    ("interact", "Interact"),
    ("vtol", "V tol"),
)

_ABBREV = {
    "ifcs": "IFCS", "qdrive": "quantum drive", "mfd": "MFD", "atc": "ATC", "esp": "ESP",
    "vtol": "VTOL", "scm": "SCM", "abs": "absolute", "fwd": "forward", "rel": "relative",
}
_PREFIXES = ("v_", "pc_", "ui_", "foip_", "player_", "spaceship_")


def humanize(name: str) -> str:
    n = name
    for p in _PREFIXES:
        if n.startswith(p):
            n = n[len(p):]
            break
    words = [_ABBREV.get(w, w) for w in n.split("_") if w]
    text = " ".join(words)
    return text[:1].upper() + text[1:] if text else name


def spoken(action: str) -> str:
    low = action.lower()
    for needle, phrase in _SPOKEN_RULES:
        if needle in low:
            return phrase
    return humanize(action)


def describe(binding) -> str:
    """On-screen text for one binding, e.g. 'Toggle landing system (double tap)'."""
    text = humanize(binding.action)
    extras = []
    if binding.activation:
        extras.append(binding.activation.replace("_", " "))
    if binding.modifiers:
        extras.append("with " + "+".join(binding.modifiers))
    if extras:
        text += " (" + ", ".join(extras) + ")"
    return text

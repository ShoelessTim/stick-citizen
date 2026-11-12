# Stick Citizen

Test your Star Citizen HOSAS setup (stick → Joystick Gremlin → vJoy → SC) without booting Star Citizen.

Fly a little ship through a ring course using your real SC bindings. Every button press shows and speaks the SC action it triggers ("Guns, guns", "Gear", "Call ATC", "Exit seat"), so you learn your layout in a sandbox.

## Run it

Download `StickCitizen.exe` from the latest build (Actions tab, or Releases) and double-click it. No install.

It finds SC's live `actionmaps.xml` automatically. Press **L** to load a different file, such as an exported layout or Subliminal's bindings. Save a change in SC or Gremlin and the app reloads it within a second.

## What you see

- **Flight view**: crosshair, velocity marker (green), next ring in yellow with an arrow when it's off screen.
- **Callouts**: big text plus voice on each press. Orange means more than one action is bound to that input.
- **Device panel**: every controller. Devices SC reads are labeled `SC js1`, `SC js2`; others (your physical NXT behind Gremlin) are `raw`. If a raw button lights but the vJoy one doesn't, the problem is in your Gremlin profile.

## Keys

| Key | Does |
| --- | --- |
| L | Load bindings file |
| F1–F4 | Point SC js1–js4 at a different device (if left and right are crossed) |
| R | Reset ship and course |
| M | Mute voice |
| H | Help |
| Esc | Quit |

## Settings

`stick_citizen.json` is saved next to the exe. Useful fields:

- `invert`: action names to flip, e.g. `["v_pitch"]`
- `axis_order`: pygame axis index for SC's x, y, z, rotx, roty, rotz, slider1, slider2, if a vJoy device has axes disabled
- `deadzone`, `speech`

## Build from source

```
pip install -r requirements.txt pyinstaller
pyinstaller --onefile --windowed --name StickCitizen run_stick_citizen.py
```

Or just `python run_stick_citizen.py`.

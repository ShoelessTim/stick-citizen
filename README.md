# Stick Citizen

See your HOSAS on screen, drag Star Citizen actions onto it, fly-test it, and save a layout SC can import. No Joystick Gremlin required.

## ⬇ Download

**[Download StickCitizen.exe](https://github.com/shoelesstim/stick-citizen/releases/latest/download/StickCitizen.exe)** (Windows) and double-click it. No install.

All versions and the zip package: [Releases](https://github.com/shoelesstim/stick-citizen/releases).

## Build your bindings

1. **Your sticks show up side by side** as SC `js1` and `js2`. If left and right are crossed, pick the right device in the dropdown above each one.
2. **Press anything** on a stick and its tile lights up, with the bound action shown big and spoken.
3. **Drag an action** from the list on the left onto a tile. Search finds actions by name or plain words ("gear", "quantum", "missile"). Dropping an action that's already bound somewhere moves it.
4. **Bind by pressing** (toolbar): select an action on the left, then press the stick input.
5. **Right-click a tile** to set tap, hold or double-tap, remove an action, or clear the input. An orange border means two or more actions share that input.
6. **Fly test ▶** (F5) opens the ring course with your current bindings.
7. **Save layout…** (Ctrl+S) writes `layout_<name>_exported.xml` into SC's `controls\mappings` folder. In SC: Options → Keybindings → Control Profiles → pick it.

It never edits SC's live `actionmaps.xml`; SC overwrites that file anyway.

## Make it look like your stick

Stick Citizen draws your real sticks with a label on every physical control, wired to the button it sits on.

1. Click **Edit**, then **Set stick photo**. Any product photo on a white background works; the background is removed for you.
2. Click **+ Map a control** and press a control on your stick. Name it (Main trigger, Red button...). For a hat, give each direction the same group name (e.g. "8-way hat A1"); a real hat fills in its direction for you.
3. Drag the numbered dot onto that button in the photo.
4. Click a label to bind actions. Each control has a **base** row and a **⇧ shift** row: click *Add a shift layer* and press the control with your shift button held.

The **Mode** chips (Flight, Mining, Salvage, Turret, On foot, Ground) show only the bindings for that kind of play. Inputs your stick reports that aren't on your map show in **Unmapped inputs** only once they're bound or pressed, so the 100+ spare button numbers a VKB stick reports stay out of the way.

Your stick maps, photos and settings live in `%APPDATA%\StickCitizen`, so downloading a new version never loses them.

## Shift layers and the mini-stick

Star Citizen can't do joystick shift layers or stick-to-mouse on its own. Set those up in your stick's firmware (VKB: VKBDevCfg). A shifted button reports as a higher button number; map it as the shift layer of its control and bind it there. Dropping an action on the lower (⇧) half of a control binds the shift layer.

## Files

- `stick_citizen.json` (next to the exe): settings such as `axis_order`, `deadzone`, `speech`, and device picks.
- `templates\`: your device layouts.
- `stick_citizen\data\sc_actions.json`: the SC action list (built from SC 4.7's default profile by `tools/make_catalog.py`).

## Build from source

```
pip install -r requirements.txt pyinstaller
pyinstaller --onefile --windowed --name StickCitizen --add-data "stick_citizen/data;stick_citizen/data" run_stick_citizen.py
```

Or `python run_stick_citizen.py` (editor) / `python run_stick_citizen.py --fly bindings.xml` (ring course).

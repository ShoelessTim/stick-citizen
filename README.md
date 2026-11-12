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

Turn on **Edit layout** and drag tiles to where the buttons sit on your stick. **Set stick photo…** puts your own photo behind them. Each stick's layout saves to `templates\<device name>.json` next to the exe. Share that file and anyone with the same stick gets your layout.

## Shift layers and the mini-stick

Star Citizen can't do joystick shift layers or stick-to-mouse on its own. Set those up in your stick's firmware (VKB: VKBDevCfg). A shifted button just shows up as a higher button number, so bind it like any other.

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

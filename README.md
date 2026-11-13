<p align="center"><img src="assets/logo-lockup.png" alt="Stick Citizen" width="520"></p>

# Stick Citizen

See your HOSAS on screen, drag Star Citizen actions onto it, fly-test it, and save a layout SC can import. No Joystick Gremlin required.

## ⬇ Download

**[Download the latest StickCitizen-vX.Y.Z.exe](https://github.com/ShoelessTim/stick-citizen/releases/latest)** (Windows) and double-click it. No install. The version is in the file name, the window title, and the exe's Properties → Details.

All versions and the zip package: [Releases](https://github.com/ShoelessTim/stick-citizen/releases).

## Build your bindings

1. **Your sticks show up side by side** as SC `js1` and `js2`. If left and right are crossed, pick the right device in the dropdown above each one.
2. **Press anything** on a stick and its tile lights up, with the bound action shown big and spoken.
3. **Drag an action** from the list on the left onto a tile. Search finds actions by name or plain words ("gear", "quantum", "missile"). Dropping an action that's already bound somewhere moves it.
4. **Bind by pressing** (toolbar): select an action on the left, then press the stick input.
5. **Right-click a tile** to set tap, hold or double-tap, remove an action, or clear the input. An orange border means two or more actions share that input.
6. **Fly test ▶** (F5) opens the ring course with your current bindings.
7. **Save layout…** (Ctrl+S) writes `layout_<name>_exported.xml` into SC's `controls\mappings` folder. In SC: Options → Keybindings → Control Profiles → pick it.

It never edits SC's live `actionmaps.xml`; SC overwrites that file anyway.

## Your sticks, ready to go

The VKB Gladiator NXT EVO (left and right, SCG grip) is built in: photo, every control labeled with VKB's names, placed on the stick. Plug in and they show up.

The first time, click **Set up left stick** (and right): each control lights up in turn and you press it, so Stick Citizen learns your stick's button numbers. Takes about two minutes per stick; **Skip** anything your grip doesn't have. The trigger's two stages are already known, and anything that sends more than one button is learned as stages automatically. The rapid trigger is set up as two positions, up and down.

Then click the **layouts** button (four squares) to start from **Sublight** (a combat-ready dual-stick layout, inspired by Subliminal's) or from any exported layout file, or click any label to bind actions yourself. Each control has a **base** row and a **⇧ shift** row (press the control with your shift button held to add it).

The **Mode** chips (Flight, Mining, Salvage, Turret, On foot, Ground) show only the bindings for that kind of play. Spare button numbers your stick reports stay out of the way in **Unmapped inputs**.

Your setup lives in `%APPDATA%\StickCitizen`, so a new version never loses it.

## Shift layers and the mini-stick

Star Citizen can't do joystick shift layers or stick-to-mouse on its own. Set those up in your stick's firmware (VKB: VKBDevCfg). A shifted button reports as a higher button number; map it as the shift layer of its control and bind it there. Dropping an action on the lower (⇧) half of a control binds the shift layer.

## Where it's going

Stick Citizen started as a quick binding tester. The goal now is a polished visual binding app, what stick software should feel like: graphical, drag and drop, and smooth enough that nobody has to dig through menus.

**Next up**
- Built-in VKB Gladiator NXT EVO profiles that work out of the box, with no setup step for stock firmware.
- Starting layouts to pick from: Sublight now, and the creator's own layout next. Others, such as Subliminal's originals, only with their creators' permission.
- A mini-stick mode indicator showing mouse vs 8-way hat.

**Planned**
- **Setup sheet export:** build a config with the picker, then export a PDF or Markdown checklist of exactly what to change in VKBDevCfg and in Star Citizen.
- **Troubleshooter:** "my stick won't do X". It tells you which setting to change and where.
- **Firmware-aware modes:** use both NXT mini-sticks as analog sticks for gamepad-style on-foot play, and have modes change the stick status LEDs.
- **LED test mode:** one LED lights on a button press, the other on axis movement.
- **More hardware:** device profiles beyond VKB.
- A YouTube explainer once it's ready for other people.

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

## Disclaimer and credits

Stick Citizen is an unofficial, fan-made Star Citizen tool. It is not affiliated with or endorsed by the Cloud Imperium group of companies. Star Citizen® is a registered trademark of Cloud Imperium Rights LLC.

VKB and Gladiator are trademarks of VKB. The stick photos in `stick_citizen/data/starters/` are VKB's product images and are **not** covered by this repo's MIT license.

The Sublight layout is inspired by Subliminal's Enhanced dual VKB Gladiator NXT layout ([subliminal.gg](https://subliminal.gg)). It was rebuilt from scratch and is not their file.

The exe isn't code-signed, so Windows SmartScreen may warn on first run. Click **More info**, then **Run anyway**.

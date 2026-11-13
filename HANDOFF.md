# Stick Citizen — Handoff

**State (2026-11-12): v3.5.2 (PR): new logo — hex crest mark in the app header, app/exe icon (`assets/icon.ico` from `assets/logo-mark.svg`), installer wizard images, README banner (`assets/logo-lockup.png`). v3.5.1 shipped: fresh start (stick maps from older versions are moved to `%APPDATA%\StickCitizen\backups\` once, via `paths.DATA_REV`), "Start a stick over" in the Edit bar, page assets carry `?v=<version>` and the window runs in private mode so no stale screen, app icon (`assets/icon.ico`), and an Inno Setup installer (`installer/stick-citizen.iss`, built in CI as `StickCitizen-vX.Y.Z-Setup.exe`, per-user, Start Menu + desktop icon). Tim's v3.5.0 run came up "half-assed": old learned maps from 3.1-3.4 were being reused. v3.5.0: Set up is now a one-control-at-a-time wizard (photo zooms to the control, compass shows the direction, raw "stick is sending" readout, mouse-mode hint on the mini-stick, duplicate-press check, Back / Skip / "not on my stick", diagonals that are just two directions get dropped automatically). Picking a layout before setup now offers Set up first. "Copy my stick maps" (wizard end screen and Edit bar) puts the learned numbers on the clipboard. Tim's v3.4.0 run: setup never finished because the hats were hard to tell apart on the map, so Sublight had nothing to land on. Tim confirmed both sticks are on VKB's stock profile, so his run becomes the baked default.**

Plan and decisions live in the *Stick Citizen — Base Conditions* Claude Doc. This file is the engineering state. The public roadmap is in README → "Where it's going"; keep the two in step.

**Direction (Nov 2026):** move from a toy tester to a polished visual binding app (drag and drop, Apple-smooth, not limited to VKB). Planned beyond the current next steps: setup sheet export (PDF/MD of VKBDevCfg + SC changes), a "which setting do I change?" troubleshooter, analog mini-sticks for on-foot play, LEDs that follow modes, an LED test mode, and more device profiles.

## What exists

| Piece | Where | Notes |
|---|---|---|
| Screen | `stick_citizen/web/` (index.html, app.css, app.js) | Vanilla JS, no build step. Cockpit look: Bahnschrift / Cascadia Mono, cyan live, amber shift |
| Window | `webui.py` | pywebview (Edge WebView2 on Windows), js_api = `webapi.Api` |
| Bridge | `webapi.py` | `Api` (every public method returns JSON), `InputHub` (pygame on its own thread), `FakeHub` for tests |
| Stick maps | `templates.py` | Controls = physical controls; inputs per layer (`base`, `shift`); hats grouped by `group`/`dir`; `dot` = position on the photo (0–1) |
| Built-in profiles | `data/starters/*.json` + `.png` | VKB Gladiator NXT EVO SCG L/R. Names from VKB's SCG templates. Only trigger stage 1/2 (b1/b2) have numbers |
| Photo cutout | `photo.py` | Flood-fills a light background from the edges, keeps the biggest shape (drops logos) |
| User data | `paths.py` | `%APPDATA%\StickCitizen` (templates, images, settings); v2 files copied once |
| Ring course | `app.py`, `sim.py` | pygame; launched by the Fly tab as `--fly <layout.xml>` |
| Starting layouts | `data/layouts/*.json` | Bindings keyed by built-in control id + layer, plus axes by SC slot; `Api.apply_layout` places what's learned and reports the rest. Sublight = inspired by Subliminal's Enhanced (credited), base + ⇧ only |
| Action names | `data/label_overrides.json` | Plain-English names over SC's labels |
| Visual QA | `tools/preview.py` | Real Api + fake sticks → browser copy with a mock API → Playwright screenshots. **Run it and look before every UI release.** |

## Start here (next session)

**Tim's first real run of v3.5.1 (2026-11-12): setup and Sublight both worked end to end.** What he hit:

1. **Wrong grip.** Tim's sticks are the **Premium** grips; the built-in profiles and photos are the SCG Standard. Need grip detection (Premium vs Standard; device name or button/axis count) and a Premium profile + photo per hand. The picture didn't match his stick.
2. **4-way hats behaved strangely** in the wizard. Get specifics from Tim (wrong direction order? diagonals asked for on a 4-way?).
3. **8-way mini-stick only appeared on the left stick.** The right-hand Premium has one too (right profile lists Hat A1 there). Add it to the right Premium profile.
4. **Mini-stick secondary (analog) mode sends two axes**, but the wizard asks for 8 hat directions in that mode and never sees the axes. Wizard needs an axis step for it: "move the mini-stick left-right, then up-down" → learn 2 axes, and treat hat mode and analog mode as two layers of one control.
5. **Sublight: something was upside-down / inverted** (likely an axis). Ask Tim which one; fix in `data/layouts/sublight.json` or add an invert flag.

Still to do after those: Tim pastes **Copy stick maps** → bake numbers into the (Premium) built-in profiles.

**Process change (Tim, 2026-11-12):** never push to main. Feature branch + PR per slice; PR is done when it builds, new behavior has tests, plain-English description, and UI screenshots. Keep ≤3 unreviewed PRs open.

**Parked, Tim's call:** more "inspired by" layouts (BuzZz Killer etc.). Sublight was built from the Subliminal chart Tim shared; we have no BuzZz chart, so one would be guesswork. Tim plans to ask both creators for permission once the app works; don't add more look-alikes before that.

**Not yet verified on real hardware:** everything since v3.0.0 (built-in profiles, setup wizard, multi-input learn, axis capture for T1, layouts picker, mouse-mode hint, clipboard copy in WebView2). Unknown until Tim's run: whether the mini-stick's hat mode sends 8 separate buttons, 4 buttons with diagonals as pairs, or a POV hat. The wizard handles all three. Only checked with fake sticks via `tools/preview.py` and tests.

## Principle

Don't encode hardware facts from chat. The stick is the source of truth: setup records every input each press fires, and Tim's learned map gets baked into the built-in profile. Names and dot positions are the only hand-made parts.

## Next steps (in order)

1. **Tim: run Set up on both sticks** (v3.1.0). Watch for: dots that sit off their button, controls the SCG Standard grip doesn't have, hats that report as POV hats (h1u…) vs buttons.
2. **Bake defaults:** copy Tim's learned `inputs` from `%APPDATA%\StickCitizen\templates\vkbsim-gladiator-evo-*.json` into `data/starters/*.json` (keep labels and dots). Then setup is only for people who changed their VKB config. Add a "Use VKB defaults / Re-learn" choice.
3. **Fix dot positions and names** from Tim's screenshots (head hats are best guesses; C1 especially). Known from Tim: T1 (center base wheel) is an axis, EN1 is an encoder, SW1 a switch; on the left stick A2 is the switchable 8-way hat / mouse mini-stick. Check whether the right stick's equivalent is also A2.
   - Mini-stick in mouse mode sends mouse, not joystick input; the planned mode label/toast (Base Conditions) still to build.
4. **Action catalog gaps:** `data/sc_actions.json` lacks some 4.x actions (e.g. `v_attack1_group1` weapon-group fire), so they show humanized names. Regenerate with `tools/make_catalog.py` from a current SC install.
5. **Real Windows check of packaging:** pywebview + PyInstaller onefile (`--collect-all webview`) built in CI but only v3.0.0 has run on a real machine. Confirm WebView2, file dialogs, speech, and the Fly tab subprocess.
6. **Layouts:** add "Tim's layout" once his is built (export from the app → `data/layouts/`). Subliminal / BuzZz Killer originals only with their permission (Tim will ask once the app works).
7. Later: mini-stick mode label (mouse vs hat), print chart export, ring course as a tab, more device profiles.

## Going public (target: v3.7)

Repo stays private until Tim's CI and dev rules are in place. Before flipping it public: VKB photo permission (or own art), Subliminal permission for Sublight, BuzZz Killer permission if we add one. Permission emails drafted 2026-11-12.

## Open risk (Tim decided, logged)

The built-in photos are VKB's product images. Shipping them in a public repo/release risks a takedown request. Mitigation options: ask VKB for permission, or replace with our own art before public launch.

## How to work on it

- Tests: `SDL_VIDEODRIVER=dummy python -m pytest -q` (no Qt, no window needed)
- Look at it: `python tools/preview.py --out shots/` then open the PNGs
- Release: bump `stick_citizen/__init__.py` `__version__` AND the `?v=` on app.css/app.js in `web/index.html` (a test checks they match), push to main → CI tests, builds `StickCitizen-vX.Y.Z.exe` (version also in Properties → Details via `tools/make_version_file.py`), cuts release `vX.Y.Z` with the exe and `StickCitizen-vX.Y.Z.zip`; the rolling `latest` pre-release gets `StickCitizen-vX.Y.Z-dev-<sha>.exe`
- Repo: github.com/ShoelessTim/stick-citizen (moved from lowercase `shoelesstim`)

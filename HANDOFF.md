# Stick Citizen — Handoff

**State (2026-11-12, evening): v3.6.0 is merged and released.** Tim's real button numbers (VKB stock profile; both sticks number identically, T1 = `a2`) are built into `data/starters/*.json`, so on a stock VKB setup Set up only asks for the mini-stick. Also in 3.6.0: mini-stick analog mode learned as two axes, rapid trigger as up/down, "No diagonals (4-way hat)", axis capture ignores axes another control owns (fixed spring-back bug), corrected dots (grey thumb knob = Thumb hat C1; Side button B1 hidden on the outside of the head), and saved maps upgrade via `starter_rev` / `added` / `moved`. v3.5.2: hex-crest logo (icon, header, installer, README).

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

1. **Right stick A1 = mini-stick.** Branch `wip/right-mini-stick` (no PR yet) turns the right profile's Hat A1 into "Mini-stick A1": 8 directions + push + 2 analog axes, ids stay `hat-a1-*` so Sublight keeps working, plus a merge rule that refreshes group/label/how in saved maps. It was cut before v3.6.0 merged: rebuild it on main (starter_rev 5, not 4), run tests + `tools/wizard_check.py`, open the PR. Then L and R have equal control counts.
2. **Mini-stick didn't register.** Tim's pasted maps (v3.6.0) had NO mini-stick inputs on either stick. Ask: skipped, or did it send nothing? If nothing: check VKB mode (mouse mode sends mouse, not joystick) — this is the first case for the fix-it tool.
3. **Premium grip profiles.** Tim's sticks are the Premium grip, not SCG Standard. His markups: `docs/hardware/premium-left-tim-markup.png`, `premium-right-tim-markup.png`. Names (both hands, mirrored): A4 = top hat; B4 = button by it; mini-stick (left A2, right A1; 8-way / mouse / analog "controller" mode); Side = side button, hidden on the outside of the head above the index finger; C4 = grey thumb knob (the app calls it Thumb hat C1); Pinky = lever on the back; rapid trigger rocks up/down; 4-way hats have no diagonals. **Waiting on Tim's own clean photos** (plain light background, 3/4 front, no flash, one stick per shot) — these also replace VKB's product photos before going public.
4. **Fix-it tool ("how do I unbreak my layout").** Tim's next big want. Proposed first slice: press anything → three columns: what the stick sent (raw, or nothing → VKB/hardware), what SC does with it (binding, or nothing → SC), plain-English diagnosis (unbound / two actions on one input / mini-stick in mouse mode / bound to an input the stick never sends); plus a one-click layout scan for conflicts and dead bindings. **Open question to Tim:** when a layout breaks, is it usually "does nothing", "does the wrong thing", or "feels wrong" (inverted/drift/twitchy)?
5. **Sublight:** one input is upside-down / inverted (likely an axis). Tim to name which.

**Parked, Tim's call:** more "inspired by" layouts (BuzZz Killer etc.); ask creators for permission first.

**Offered, not answered:** have CI build every PR (installer included) so Tim can test without a manual Actions run. Today PR builds were started by hand (Actions → Build Windows exe → Run workflow → branch).

**Verified on Tim's hardware (v3.5.1–3.6.0):** setup wizard end to end, Sublight, all buttons/hats/triggers/base controls/T1 on both sticks. **Not yet:** mini-stick (any mode), right A1 mini-stick, Premium profiles.

## Principle

Don't encode hardware facts from chat. The stick is the source of truth: setup records every input each press fires, and Tim's learned map gets baked into the built-in profile. Names and dot positions are the only hand-made parts.

## Later (after Start here)

- Mini-stick mode label + toast (mouse vs hat vs analog), per Base Conditions.
- Action catalog gaps: `data/sc_actions.json` lacks some 4.x actions (e.g. `v_attack1_group1`); regenerate with `tools/make_catalog.py` from a current SC install.
- "Tim's layout" in `data/layouts/` once he builds it in the app.
- Roadmap items (LEDs, on-foot analog play, export checklist) live in Base Conditions.

## Going public (target: v3.7)

Repo stays private until Tim's CI and dev rules are in place. Tim wanted it public for his buddy (2026-11-12); held because of the two items below, and the buddy can use the installer file instead. Before flipping it public: VKB photo permission (or own art), Subliminal permission for Sublight, BuzZz Killer permission if we add one. Permission emails drafted 2026-11-12.

## Open risk (Tim decided, logged)

The built-in photos are VKB's product images. Shipping them in a public repo/release risks a takedown request. Mitigation options: ask VKB for permission, or replace with our own art before public launch.

## How to work on it

- Tests: `SDL_VIDEODRIVER=dummy python -m pytest -q` (no Qt, no window needed)
- Look at it: `python tools/preview.py --out shots/` then open the PNGs (fake presses use b60+, clear of the built-in VKB numbers)
- Walk the Set up wizard end to end (real Api, fake sticks, every step pressed): `python tools/wizard_check.py . shots/wizard` (and `SCEN=pairs ...`). **Run before any wizard change ships.**
- Release: bump `stick_citizen/__init__.py` `__version__` AND the `?v=` on app.css/app.js in `web/index.html` (a test checks they match), push to main → CI tests, builds `StickCitizen-vX.Y.Z.exe` (version also in Properties → Details via `tools/make_version_file.py`), cuts release `vX.Y.Z` with the exe and `StickCitizen-vX.Y.Z.zip`; the rolling `latest` pre-release gets `StickCitizen-vX.Y.Z-dev-<sha>.exe`
- Merging a branch: never take one side of HANDOFF.md wholesale (`checkout --ours` lost PR #1's notes once); merge it by hand.
- Repo: github.com/ShoelessTim/stick-citizen (moved from lowercase `shoelesstim`)

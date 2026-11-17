# Stick Citizen — Handoff

**State (2026-11-17): v3.9.0 (PR) = Fix it, slice 2: whole-layout scan.** Slice 1 (v3.8.0, PR #14) is merged. The Fix it panel now has **Scan whole layout** (also offered while it listens for a press, and as "Scan again"): one click, no press, findings in plain English, worst first. Code: `fixit.py` gains `stick_readout` (stick side: learned map + Windows button/hat counts + inputs seen firing; never reads bindings), `layout_readout` (SC side: binds per input + whether SC's action list has them; never reads sticks) and `scan` (joins them). Checks: **wrong stick** (bind on an input this stick's map doesn't send, exactly one other stick sends it and it's free there; only "firm" when the stick is fully learned, the js isn't connected, or Windows says it can't send it; has **Fix in layout** = move + export, like slice 1 check 3), **never sends** (button/hat beyond Windows' count, no stick as that js, or not on a fully learned map; "check this" only if Set up isn't finished; axes skipped), **wrong category** (action is in the SC 4.7 list under another actionmap → red; not in the list at all → amber "renamed or removed?"), **two actions on one input** (same mode or one "general", same activation; flight + on-foot on one input like Sublight's mini-stick is fine; tap vs hold is fine), **not bound** (learned controls with nothing on any layer, folded away as info, each with Fix in layout… = pick action, then export). Summary repeats the js1/js2 "guessed by plug-in order" note and the freshness note. `Api.fixit_scan()` / `Api.fixit_scan_fix(id)`; exports go through `save_layout` (still refuses `actionmaps.xml`). **Open, test on Tim's PC:** (a) are the wrong-category findings right on his real 4.7 file (any false alarms = the catalog is missing a map/action, regenerate it with `tools/make_catalog.py`); (b) does "wrong stick" ever fire on his VKBs (both grips use the same b1–b29 numbers, so it mostly catches hats and a missing js3); (c) is the spare-controls list useful or noise. Slice 1's open questions (actionmaps freshness while SC runs; distinct L/R product names) are still open.

**State (2026-11-16): v3.8.0 (merged, PR #14) = Fix it, slice 1.** A "Fix it: a control does nothing" chip in the bar (Sticks view) opens a panel over the stage: press the dead control, get four checks (green/red + one-line fix): 1 stick sent anything (nothing → cable / VKB firmware / HidHide; mouse moved → mini-stick in Mouse mode), 2 SC action on that input, 3 bind sitting on the other js (js1/js2 swapped), 4 wrong mode (e.g. On foot only vs the Mode chip), shift layer on/off, mini-stick Mouse mode. Checks 2 and 3 have **Fix in layout** (3 moves the bind to this js; 2 opens the bind search; both then save an exported layout XML). Code: `fixit.py` (pure: `raw_readout` and `sc_readout` are separate on purpose, `diagnose` joins them), `Api.fixit_arm/fixit_mouse/fixit_cancel/fixit_fix`, result comes back from `poll()` as `fixit`. `save_layout` now refuses any `actionmaps.xml` path. `Api._match` records how each js number was paired with a stick (`product` only when SC's file names it uniquely; `manual`; else `order` = a guess), which check 3 reports. **Open, test on Tim's PC:** (a) is actionmaps.xml fresh while SC runs? Fix it shows a soft "restart SC" note when StarCitizen.exe is running; drop or harden it after testing. (b) do the L/R sticks show distinct product names in actionmaps.xml? If yes, `_match` = `product` and js1/js2 is known; if both read the same, it stays a guess. Next slice: whole-layout scan reusing `diagnose`.

**State (2026-11-12, 9:30pm): v3.7.2 (PR).** Tim tried 3.7.1 in game: yaw was right before (invert removed), the throttle (left stick forward/back, `v_strafe_longitudinal`) was backwards (now inverted), and he wants the mini-sticks to work on foot like a controller's thumbsticks. Layout files can now put several actions on one control (`[["map","action"], ["map","action"]]`), so Sublight's left mini-stick keeps its flight binds and adds `player` moveforward/moveback/moveleft/moveright (8-way from POV diagonals). **On-foot look has no joystick-button action in SC 4.7's catalog** (only gamepad `gp_rotateyaw/pitch`), so right mini-stick look = VKB mouse mode; Tim confirmed that's OK (2026-11-12). Still open: is his left stick spring-centered or an Omni throttle (decides throttle mode), Tim wants a plain throttle (stick position = throttle; center = stop coupled / coast decoupled), so `v_ifcs_throttle_swap_mode` moved off the left mini-stick push (also VKB's mode toggle) to left Thumb hat C4 down; pressing it once gets out of hold-speed mode if SC is stuck in it.

**State (2026-11-12, late): v3.7.1 (PR).** Tim's v3.7.0 maps showed the right mini-stick's hat mode is a **POV hat** (h1u/r/d/l), analog = a4 (x) / a3 (y); built into the right profile (`starter_rev` 6, right diagonals removed). Set up now learns a POV hat in one press (`Api.learn` → all four directions, diagonals dropped) and `templates.fix_pov_hats` repairs saved maps where a diagonal holds one POV direction. Left mini-stick: Tim's re-run ended after up/down/left/right in v3.7.0 (no push/analog steps); `tools/wizard_check.py` with `SCEN=pov` now walks that path and asks push + analog — confirm on his stick. Sublight yaw was inverted for Tim: layouts can mark an axis `"invert"` (3rd element), exported as SC's `<options type="joystick"><flight_move_yaw invert="1"/>` and honored by the Fly tab. **Verify in SC** that the invert option element name is right (Options → Keybindings should show Yaw inverted on the right stick).

**State (2026-11-12, night): v3.7.0 = the public-release build (PR open; Tim merges, then flips the repo public himself).** VKB's product photos are gone: the built-in profiles use Tim's own photos of his Premium-grip sticks (cut out with a dark + neutral-grey threshold against the cardboard), every dot re-placed, `starter_rev` 5 with `moved: 5` on every control so saved maps take the new dots (unless the user set their own photo: `templates.load_template` skips dot moves when `t.image` is set). Names now follow what's printed on the stick: both sticks' mini-stick is **A1** (left ids stay `mini-stick-a2-*`, right `hat-a1-*`, so Sublight keeps working), red button A2, hats A3/A4; Tim's names for unlabeled ones: Thumb hat C4 (ids `thumb-hat-c1-*`), Side button (`side-button-b1`), Pinky lever (`pinky-d1`). Saved maps pick up new names/how-tos through the merge rule. Right A1 is now a full mini-stick (from `wip/right-mini-stick`, rebuilt on main; PR #4 superseded). README rewritten for the public; SECURITY.md added. v3.6.0 notes follow.

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
| Built-in profiles | `data/starters/*.json` + `.png` | VKB Gladiator NXT EVO Premium L/R. Tim's photos; names as printed on the stick; VKB stock button numbers built in, only the mini-stick needs Set up |
| Photo cutout | `photo.py` | Flood-fills a light background from the edges, keeps the biggest shape (drops logos) |
| User data | `paths.py` | `%APPDATA%\StickCitizen` (templates, images, settings); v2 files copied once |
| Ring course | `app.py`, `sim.py` | pygame; launched by the Fly tab as `--fly <layout.xml>` |
| Starting layouts | `data/layouts/*.json` | Bindings keyed by built-in control id + layer, plus axes by SC slot; `Api.apply_layout` places what's learned and reports the rest. Sublight = inspired by Subliminal's Enhanced (credited), base + ⇧ only |
| Action names | `data/label_overrides.json` | Plain-English names over SC's labels |
| Visual QA | `tools/preview.py` | Real Api + fake sticks → browser copy with a mock API → Playwright screenshots. **Run it and look before every UI release.** |

## Start here (next session)

1. **Tim's v3.7.0 run:** check the new photos' dots on both sticks, and that the mini-stick (A1, both sticks) registers in hat and analog mode. If it sent nothing in v3.6.0, it was probably in mouse mode: that's the first case for the fix-it tool.
2. **Going public:** Tim flips visibility (Settings → General → Danger Zone). Git history still contains VKB's product photos (starter PNGs before v3.7.0, `docs/screens/v3.6.0-*`, the markups in the old handoff branch). Tim decides: accept, or publish a fresh-history repo.
3. **Fix it.** Slice 1 (v3.8.0, "does nothing") is built; Tim to test it on his sticks and answer the two open questions above. Slice 2: whole-layout scan with the same checks. "Does the wrong thing" / "feels wrong" come after.
4. **Sublight:** one input is upside-down / inverted (likely an axis). Tim to name which.

**Parked, Tim's call:** more "inspired by" layouts (BuzZz Killer etc.); ask creators for permission first.

**CI on PRs:** in the repo-hardening PR (security kit + builds on every PR).

**Verified on Tim's hardware (v3.5.1–3.6.0):** setup wizard end to end, Sublight, all buttons/hats/triggers/base controls/T1 on both sticks. **Not yet:** mini-stick (any mode), right A1 mini-stick, Premium profiles.

## Principle

Don't encode hardware facts from chat. The stick is the source of truth: setup records every input each press fires, and Tim's learned map gets baked into the built-in profile. Names and dot positions are the only hand-made parts.

## Later (after Start here)

- Mini-stick mode label + toast (mouse vs hat vs analog), per Base Conditions.
- Action catalog gaps: `data/sc_actions.json` lacks some 4.x actions (e.g. `v_attack1_group1`); regenerate with `tools/make_catalog.py` from a current SC install.
- "Tim's layout" in `data/layouts/` once he builds it in the app.
- Roadmap items (LEDs, on-foot analog play, export checklist) live in Base Conditions.

## Going public (target: v3.7)

v3.7.0 clears the blockers: own photos (no VKB art in the app), Sublight kept and credited (Tim's call), security kit + PR builds in the hardening PR. Still before flipping: Tim's decision on VKB images in git history. BuzZz Killer only with permission.

## Open risk (Tim decided, logged)

Resolved in v3.7.0: built-in photos are Tim's own. Remaining: VKB images in git history (see Start here 2). Sublight ships credited without a reply from Subliminal (Tim's call, 2026-11-12); pull it if they object.

## How to work on it

- Tests: `SDL_VIDEODRIVER=dummy python -m pytest -q` (no Qt, no window needed)
- Look at it: `python tools/preview.py --out shots/` then open the PNGs (fake presses use b60+, clear of the built-in VKB numbers)
- Walk the Set up wizard end to end (real Api, fake sticks, every step pressed): `python tools/wizard_check.py . shots/wizard` (and `SCEN=pairs ...`). **Run before any wizard change ships.**
- Release: bump `stick_citizen/__init__.py` `__version__` AND the `?v=` on app.css/app.js in `web/index.html` (a test checks they match), push to main → CI tests, builds `StickCitizen-vX.Y.Z.exe` (version also in Properties → Details via `tools/make_version_file.py`), cuts release `vX.Y.Z` with the exe and `StickCitizen-vX.Y.Z.zip`; the rolling `latest` pre-release gets `StickCitizen-vX.Y.Z-dev-<sha>.exe`
- Merging a branch: never take one side of HANDOFF.md wholesale (`checkout --ours` lost PR #1's notes once); merge it by hand.
- Repo: github.com/ShoelessTim/stick-citizen (moved from lowercase `shoelesstim`)

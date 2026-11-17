# Setup helper (v3.11.0)

A second mode next to **Fix it**. You list the Star Citizen actions you want on one hand, in the order you
use them, and pick the stick. The helper suggests where each one goes, shows it on the stick photo, and
changes nothing until you press **Accept**. Accepting changes your bindings in Stick Citizen (one **Undo**
puts everything back); they reach Star Citizen only when you **Save for Star Citizen**, as an exported
layout. SC's live `actionmaps.xml` is never written.

## How it picks

- **Reach** comes from `stick_citizen/data/reach.json`: a hand-made rank per built-in control id
  (1 = easiest with your hand on the grip, 10 = hardest) and a zone (thumb, index, pinky, base).
  Controls you mapped yourself, and anything not in the table, count as rank 10.
- **How often** each action gets used is a starting guess from `stick_citizen/data/action_use.json`
  (`often`, `sometimes`, `rare`; anything unlisted starts as `sometimes`). You change it per action in the panel.
- Often-used actions want the best reach (thumb hats, trigger, red button); rare ones want the base buttons.
  A placement costs the gap between the control's reach and what the action wants, plus a penalty for each
  bind it would replace in the same mode. A bind in another mode (for example on foot) stays and costs a little,
  because flight + on foot on one input is fine in SC.
- **Keep the sequence on one hat** (on by default): the whole sequence goes on one hat in the order
  up, right, down, left, push, if a hat has enough set-up directions. The helper still spreads it out when
  the best hat is a much worse reach than single buttons (`weights.sequence_bonus`). Untick it to always spread.
- Each row shows what it would **replace**, what it **keeps** (other modes), and whether the action **moves**
  from somewhere else (SC allows one input per action).
- Controls that aren't set up yet (for example the left mini-stick before Set up) are left out, with a note.

All the numbers live in `reach.json` → `weights`; edit them without touching code. `tests/test_core.py`
checks that every built-in control has a rank, so a new built-in control needs a row in `reach.json`.

## Axis checks

A list in `stick_citizen/helper.py` (`AXIS_CHECKS`). Each check is a function `check(ctx) -> [finding]`;
add one by writing a function and appending it. Each stick's kind (spring-centred, Omni throttle, other) is
picked in the panel and saved per side in the settings (`stick_kinds`).

1. **Vertical lift** (`v_strafe_vertical`):
   - *warn* when it isn't bound to an axis at all (or only to the strafe up / down buttons);
   - *problem* when it sits on an absolute, throttle-style axis (one that stays where you leave it) on a
     spring-centred or Omni stick: the base wheel T1, a slider, or an Omni stick's forward/back.
     Which axes stay put comes from `reach.json` (`centering` on axis controls, `main_axes` per stick kind).

The panel always shows: *calibrate a new sensor or adapter in VKBDevCfg first.* Tim's left twist read dead
after an Omni throttle swap until he calibrated it.

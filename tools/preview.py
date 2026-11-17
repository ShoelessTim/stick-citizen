"""Visual check of the v3 screen without Windows or sticks.

Runs the real Api with fake VKB sticks (built-in profiles), writes a browser copy of the screen
whose window.MOCK_API replays that state, and screenshots it with Playwright:
  0-*  a brand-new user: built-in profile, nothing learned yet, and the setup walkthrough
  1-*  after setup: learned buttons and some bindings, live presses, shift, edit drawer, Fix it (press + scan)

  python tools/preview.py --out shots/
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Sample bindings on built-in profile controls (by control id), after a fake setup run.
BINDS = {
    "R": {"main-trigger-stage1": ("spaceship_weapons", "v_weapon_staggered_fire_toggle"),
          "red-button-a2": ("spaceship_missiles", "v_weapon_launch_missile"),
          "side-button-b1": ("spaceship_movement", "v_toggle_landing_system"),
          "hat-a4-up": ("spaceship_targeting_advanced", "v_target_cycle_hostile_fwd"),
          "hat-a4-down": ("spaceship_targeting_advanced", "v_target_cycle_hostile_back"),
          "hat-a1-up": ("spaceship_power", "v_power_toggle"),
          "base-f1": ("lights_controller", "v_lights"), "base-f2": ("seat_general", "v_emergency_exit"),
          "base-f3": ("spaceship_general", "v_toggle_all_doorlocks"),
          "encoder-en1-up": ("spaceship_mining", "v_increase_mining_throttle"),
          "pinky-d1": ("spaceship_movement", "v_ifcs_vector_decoupling_toggle")},
    "L": {"main-trigger-stage1": ("spaceship_movement", "v_afterburner"),
          "red-button": ("spaceship_movement", "v_space_brake"),
          "side-button-b1": ("spaceship_movement", "v_atc_request"),
          "hat-a4-up": ("spaceship_movement", "v_ifcs_speed_limiter_up"),
          "hat-a4-down": ("spaceship_movement", "v_ifcs_speed_limiter_down"),
          "base-f1": ("spaceship_quantum", "v_toggle_qdrive_engagement"),
          "base-f2": ("spaceship_general", "v_toggle_all_doors")},
}


def build(workdir: Path, learned=True):
    os.environ["STICK_CITIZEN_HOME"] = str(workdir / "home")
    from stick_citizen.webapi import Api, FakeHub
    hub = FakeHub([{"uid": "L", "name": "VKBsim Gladiator EVO L", "axes": 6, "buttons": 128, "hats": 1},
                   {"uid": "R", "name": "VKBsim Gladiator EVO R", "axes": 6, "buttons": 128, "hats": 1}])
    api = Api(hub, actionmaps=str(ROOT / "samples" / "demo_actionmaps.xml"))
    by_side = {s["side"]: s["slot"] for s in api.get_state()["sticks"]}
    if learned:   # what the one-time "Set up" walkthrough produces
        for side, slot in by_side.items():
            stick = next(x for x in api.get_state()["sticks"] if x["slot"] == slot)
            n = 60   # clear of the built-in VKB numbers
            for cid in stick["unassigned"]:
                api.assign_input(slot, cid, "base", f"b{n}")
                n += 1
            st = next(x for x in api.get_state()["sticks"] if x["slot"] == slot)
            ids = {c["id"]: c["inputs"].get("base") for c in st["controls"]}
            api.assign_input(slot, "main-trigger-stage1", "shift", "b60")
            for cid, (m, a) in BINDS[side].items():
                if ids.get(cid) and api._catalog.get(m, a):
                    api.assign(slot, ids[cid], m, a)
            api.assign(slot, "b60", "spaceship_missiles", "v_weapon_launch_missile")
    fixes = {}
    if learned:   # real Fix it results from the real Api: js1/js2 mix-up, on-foot-only bind, mini-stick in mouse mode
        def run(uid=None, key=None, mouse=False):
            api.FIX_WAIT = 0 if key is None else 6.0
            api.fixit_arm("flight")
            if mouse:
                api.fixit_mouse()
            if key:
                hub.press(uid, key)
                hub.press(uid, key, False)
            return api.poll()["fixit"]
        fixes["wrong"] = run("L", "b6")                  # demo file: landing gear is on js2 b6 (the other stick)
        api.assign(by_side["R"], "b70", "player", "jump")
        fixes["foot"] = run("R", "b70")
        fixes["mouse"] = run(mouse=True)
        api.undo()
        # slice 2: the whole-layout scan on the same state (demo file + a bind on a number the left stick never sends)
        # and two actions on one right-stick input; the left mini-stick fully learned (so its H1 binds are firm findings)
        api.assign_input(by_side["L"], "mini-stick-a2-up", "base", "b99")
        api.assign(by_side["L"], "b100", "spaceship_targeting_advanced", "v_target_cycle_hostile_back")
        from stick_citizen.bindings import Bound
        api._bset.binds.setdefault((by_side["R"], "button", 29, ""), []).append(Bound("spaceship_general", "v_toggle_all_doors"))
        fixes["scan"] = api.fixit_scan()
        api._bset.binds[(by_side["R"], "button", 29, "")].pop()
        api.undo()
    hub.press("R", "b120")
    api.poll()
    state = api.get_state()
    images = {s["name"]: api.get_image(s["slot"]) for s in state["sticks"]}
    search = api.search("", "all", 400)
    api.apply_layout("sublight")
    state = api.get_state()
    state["layouts"] = api.list_layouts()
    state["fixes"] = fixes
    state["backups"] = fake_backups(workdir)
    state["helper"] = fake_helper(api, by_side) if learned else {}
    return state, images, search


def fake_helper(api, by_side):
    """Real Setup helper results on the Sublight state shown: the ship start-up sequence on the right stick
    (kept on one hat, and spread), and the axis checks for a layout with vertical lift on the left base wheel."""
    from stick_citizen.bindings import Bound
    start = api.helper_start()
    rows = start["presets"][0]["rows"]
    out = {"start": start, "plan": api.helper_suggest(by_side["R"], rows, True),
           "spread": api.helper_suggest(by_side["R"], rows, False)}
    lift = api._bset.where("spaceship_movement", "v_strafe_vertical")
    api._bset.binds[lift] = [b for b in api._bset.binds[lift] if b.action != "v_strafe_vertical"]
    api._bset.binds.setdefault((by_side["L"], "axis", 2, ""), []).append(Bound("spaceship_movement", "v_strafe_vertical"))
    out["wheel"] = api.helper_checks()
    api._bset.binds[(by_side["L"], "axis", 2, "")].pop()
    api._bset.binds[lift].append(Bound("spaceship_movement", "v_strafe_vertical"))
    api.helper_suggest(by_side["R"], rows, True)
    out["accepted"] = api.helper_accept()["msg"]      # the real message for the plan shown, then put it back
    api.undo()
    return out


def fake_backups(workdir: Path):
    """Real backups (stick_citizen.backups) of a fake SC install: a saved copy, edits, then a crash reset."""
    import time as _t
    from stick_citizen import backups
    base = workdir / "StarCitizen" / "LIVE" / "user" / "client" / "0"
    (base / "controls" / "mappings").mkdir(parents=True, exist_ok=True)
    live = base / "Profiles" / "default" / "actionmaps.xml"
    live.parent.mkdir(parents=True, exist_ok=True)
    demo = (ROOT / "samples" / "demo_actionmaps.xml").read_text()
    t0 = _t.mktime((2026, 11, 17, 9, 12, 5, 0, 0, -1))
    steps = [(demo, True, 0), (demo.replace("js2_button6", "js2_button16"), False, 2400),
             (demo.replace("js2_button7", "js2_button17").replace("</actionmap>", '<action name="v_lights"><rebind input="js1_button9"/></action></actionmap>', 1), False, 4100),
             ('<ActionMaps><ActionProfiles profileName="default"></ActionProfiles></ActionMaps>', False, 5520)]
    for text, saved, dt in steps:
        live.write_text(text)
        backups.snapshot(live, saved=saved, now=t0 + dt)
    return {"live": "C:\\Program Files\\Roberts Space Industries\\StarCitizen\\LIVE\\user\\client\\0\\Profiles\\default\\actionmaps.xml",
            "channel": "LIVE", "items": backups.list_backups(), "keep": backups.KEEP, "folder": "", "mappings": ""}


MOCK = r"""
window.__events = [];
window.MOCK_API = (() => {
  const F = window.FIXTURE;
  const ok = (msg) => Promise.resolve({ ok: true, msg: msg || "", state: F.state });
  return {
    get_state: () => Promise.resolve(F.state),
    get_image: (slot) => Promise.resolve(F.images[F.state.sticks.find(s => s.slot === slot).name]),
    poll: () => Promise.resolve({ events: window.__events.splice(0), axes: F.axes, reload: false }),
    search: (q) => Promise.resolve(F.search.filter(a => !q || (a.label + a.group).toLowerCase().includes(q.toLowerCase())).slice(0, 80)),
    assign: () => ok("Bound"), remove: () => ok(), set_activation: () => ok(), undo: () => ok("Undone"),
    arm_capture: () => Promise.resolve({ ok: true }), cancel_capture: () => Promise.resolve({ ok: true }),
    map_control: () => ok("Mapped"), assign_input: () => ok("Learned"), learn: () => ok("Learned"), reset_stick: () => ok("Started over"), set_dot: () => Promise.resolve({ ok: true }),
    edit_control: () => ok(), choose_photo: () => Promise.resolve({ ok: false }), open_layout: () => Promise.resolve({ ok: false }),
    save_layout: () => ok("Saved"), fly_test: () => ok("Ring course launched"), say: () => Promise.resolve({}),
    set_speech: () => Promise.resolve({ ok: true }),
    list_layouts: () => Promise.resolve(F.layouts), apply_layout: () => ok("Applied"),
    fixit_arm: () => Promise.resolve({ ok: true, wait: 6 }), fixit_mouse: () => Promise.resolve({ ok: true }),
    fixit_cancel: () => Promise.resolve({ ok: true }), fixit_fix: () => ok("Moved 1 bind to this stick. Saved."),
    backup_list: () => Promise.resolve(F.backups),
    backup_now: () => Promise.resolve({ ok: true, msg: "Saved a copy of your LIVE bindings (19 binds)", backup: F.backups.items[1], suggest: "MyBinds-2026-11-17" }),
    backup_export: () => Promise.resolve({ ok: true, msg: "Saved as “Restored-2026-11-17-1052”. In Star Citizen: Options → Keybindings → Control Profiles → “Restored-2026-11-17-1052”" }),
    fixit_scan: () => Promise.resolve(F.fixes.scan), fixit_scan_fix: () => ok("Moved 1 bind to js2. Saved."),
    helper_start: () => Promise.resolve(F.helper.start), helper_checks: () => Promise.resolve(F.helper.start.checks),
    helper_row: (m, a) => Promise.resolve({ ok: true, row: { map: m, action: a, label: a, axis: false, use: "sometimes" } }),
    helper_suggest: (slot, rows, keep) => Promise.resolve(keep ? F.helper.plan : F.helper.spread),
    helper_accept: () => Promise.resolve({ ok: true, msg: F.helper.accepted, placed: 5, state: F.state }),
    helper_set_kind: () => Promise.resolve({ ok: true, checks: F.helper.wheel }),
  };
})();
"""


def write_site(state, images, search, site: Path):
    web = ROOT / "stick_citizen" / "web"
    if site.exists():
        shutil.rmtree(site)
    shutil.copytree(web, site)
    axes = {s["slot"]: [0.35, -0.2, 0, 0, 0, 0.1] for s in state["sticks"]}
    (site / "fixture.js").write_text("window.FIXTURE = " + json.dumps(
        {"state": state, "images": images, "search": search, "axes": axes, "layouts": state.pop("layouts"), "fixes": state.pop("fixes"), "backups": state.pop("backups"), "helper": state.pop("helper")}) + ";\n" + MOCK, encoding="utf-8")
    html = (site / "index.html").read_text(encoding="utf-8")
    (site / "index.html").write_text(html.replace('<script src="app.js', '<script src="fixture.js"></script>\n<script src="app.js'), encoding="utf-8")


def shoot(site: Path, out: Path, size=(1600, 940), fresh=False):
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=True)
    shots, errors = [], []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": size[0], "height": size[1]})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
        pg.goto((site / "index.html").as_uri())
        pg.wait_for_timeout(900)

        def snap(name, js=None, wait=500):
            if js:
                pg.evaluate(js)
            pg.wait_for_timeout(wait)
            f = out / f"{name}.png"
            pg.screenshot(path=str(f))
            shots.append(f)

        r = "S.state.sticks.find(s => s.side === 'R').slot"
        if fresh:
            snap("0-fresh-both", "S.stick='both'; render();")
            l = "S.state.sticks.find(s => s.side === 'L')"
            snap("0-fresh-layout-needs-setup", "layoutsFlow().then(() => document.querySelectorAll('.lay')[1].click())", 700)
            snap("0-wizard-hat-up", "closeModal(); setTimeout(() => setupFlow(%s), 0)" % l, 900)
            # (stock VKB numbers are built in, so setup starts at the mini-stick) learn up/right/down/left, leaving push; then fake a mouse move
            for k in ("b60", "b61", "b62", "b63"):   # clear of the built-in VKB numbers
                pg.evaluate("(() => { const m = %s.controls.find(c => c.id === S.wiz.todo[S.wiz.i].id); m.inputs.base = '%s'; const f = S.capture; S.capture = null; f({slot: S.wiz.slot, key: '%s', keys: ['%s']}); })()" % (l, k, k, k))
                pg.wait_for_timeout(150)
            snap("0-wizard-mini-stick", "window.dispatchEvent(new MouseEvent('mousemove', {movementX: 9, movementY: 3})); window.__events.push({slot: S.wiz.slot, key: 'b61', on: true}, {slot: S.wiz.slot, key: 'b61', on: false})", 500)
            snap("0-wizard-duplicate", "(() => { const f = S.capture; S.capture = null; f({slot: S.wiz.slot, key: 'b60', keys: ['b60']}); })()", 500)
            # a diagonal step on a regular hat offers "No diagonals (4-way hat)"
            snap("0-wizard-diagonal", "S.wiz.i = S.wiz.todo.findIndex(t => t.id === 'mini-stick-a2-up-right'); document.querySelector('#wizard .wz-btns .btn').click()", 700)
            # jump to the mini-stick's analog step ("Try again" on the duplicate prompt re-enters the loop at W.i)
            snap("0-wizard-analog", "S.wiz.i = S.wiz.todo.findIndex(t => t.id === 'mini-stick-a2-analog-x'); document.querySelector('#wizard .wz-btns .btn').click(); setTimeout(() => window.dispatchEvent(new MouseEvent('mousemove', {movementX: 9, movementY: 3})), 300)", 700)
        else:
            snap("1-both", "S.stick='both'; S.othersOpen=true; render(); window.__events.push({slot:%s,key:'b1',on:true})" % r)
            snap("2-right", "S.stick=%s; render();" % r)
            snap("3-right-shift", "window.__events.push({slot:%s,key:'b1',on:false},{slot:%s,key:'b60',on:true})" % (r, r))
            snap("4-edit-drawer", "setView('edit'); openDrawer(%s, 'Main trigger')" % r)
            snap("5-layouts", "closeDrawer(); setView('sticks'); S.stick='both'; render(); layoutsFlow()", 700)
            snap("6-fixit-listening", "closeModal(); fixitFlow()", 600)
            snap("7-fixit-wrong-stick", "fixGot(FIXTURE.fixes.wrong)")
            snap("8-fixit-on-foot-only", "fixGot(FIXTURE.fixes.foot)")
            snap("9-fixit-mouse-mode", "fixGot(FIXTURE.fixes.mouse)")
            snap("10-fixit-scan", "fixitScan()", 600)
            snap("11-fixit-scan-spare", "document.querySelector('.fixit').scrollTop = 1e6; document.querySelector('.fx-spare').open = true; setTimeout(() => { document.querySelector('.fixit').scrollTop = document.querySelector('.fx-spare').offsetTop - 20; }, 50)", 600)
            snap("12-backups", "fixClose(); backupsFlow().then(() => document.querySelectorAll('.bk-row .btn')[1].click())", 600)
            snap("13-backups-saved", "document.querySelector('#modal .btn.go').click()", 600)
            snap("14-backups-restored", "backupsFlow({msg: 'Saved as “Restored-2026-11-17-1052”. In Star Citizen: Options → Keybindings → Control Profiles → “Restored-2026-11-17-1052”'})", 600)
            # Setup helper: the ship start-up sequence on the right stick, its preview on the photo, spread, accepted
            snap("15-helper-sequence", "closeModal(); S.live = {}; window.__events.push({slot:%s,key:'b60',on:false}); helperFlow().then(() => { S.help.slot = %s; S.stick = S.help.slot; render(); document.querySelector('.hp-empty .btn').click(); })" % (r, r), 700)
            snap("16-helper-preview", "helperSuggest()", 700)
            snap("17-helper-spread", "document.querySelector('.hp-keep input').click(); helperSuggest().then(() => { const b = document.querySelector('#helper'); b.scrollTop = 1e6; })", 700)
            snap("18-helper-axis-check", "const sel = document.querySelector('.hp-kind select'); sel.value = 'omni'; sel.dispatchEvent(new Event('change')); setTimeout(() => { document.querySelector('#helper').scrollTop = 1e6; }, 100)", 700)
            snap("19-helper-accepted", "document.querySelector('.hp-keep input').click(); helperSuggest().then(() => helperAccept()).then(() => { document.querySelector('#helper').scrollTop = 0; })", 700)
        b.close()
    return shots, errors


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="shots")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=940)
    a = ap.parse_args()
    allfiles, allerrs = [], []
    for fresh in (True, False):
        work = Path(tempfile.mkdtemp(prefix="sc-preview-"))
        st, im, se = build(work, learned=not fresh)
        write_site(st, im, se, work / "site")
        files, errs = shoot(work / "site", Path(a.out), (a.width, a.height), fresh)
        allfiles += files
        allerrs += errs
    print("\n".join(map(str, allfiles)))
    if allerrs:
        print("PAGE ERRORS:\n" + "\n".join(allerrs))
        sys.exit(1)

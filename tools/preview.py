"""Visual check of the v3 screen without Windows or sticks.

Runs the real Api with fake VKB sticks (built-in profiles), writes a browser copy of the screen
whose window.MOCK_API replays that state, and screenshots it with Playwright:
  0-*  a brand-new user: built-in profile, nothing learned yet, and the setup walkthrough
  1-*  after setup: learned buttons and some bindings, live presses, shift, edit drawer

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
            n = 3
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
    hub.press("R", "b120")
    api.poll()
    state = api.get_state()
    images = {s["name"]: api.get_image(s["slot"]) for s in state["sticks"]}
    search = api.search("", "all", 400)
    api.apply_layout("sublight")
    state = api.get_state()
    state["layouts"] = api.list_layouts()
    return state, images, search


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
        {"state": state, "images": images, "search": search, "axes": axes, "layouts": state.pop("layouts")}) + ";\n" + MOCK, encoding="utf-8")
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
            # learn up/right/down/left, leaving the mini-stick push step; then fake a mouse move
            for k in ("b20", "b21", "b22", "b23"):
                pg.evaluate("(() => { const m = %s.controls.find(c => c.id === S.wiz.todo[S.wiz.i].id); m.inputs.base = '%s'; const f = S.capture; S.capture = null; f({slot: S.wiz.slot, key: '%s', keys: ['%s']}); })()" % (l, k, k, k))
                pg.wait_for_timeout(150)
            snap("0-wizard-mini-stick", "window.dispatchEvent(new MouseEvent('mousemove', {movementX: 9, movementY: 3})); window.__events.push({slot: S.wiz.slot, key: 'b21', on: true}, {slot: S.wiz.slot, key: 'b21', on: false})", 500)
            snap("0-wizard-duplicate", "(() => { const f = S.capture; S.capture = null; f({slot: S.wiz.slot, key: 'b20', keys: ['b20']}); })()", 500)
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

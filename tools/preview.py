"""Visual check of the v3 screen without Windows or sticks.

Runs the real Api with fake sticks, writes a browser copy of the screen whose window.MOCK_API
replays that state, and screenshots it with Playwright.

  python tools/preview.py --photos L.jpg R.jpg --out shots/
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

# Sample map for a VKB Gladiator NXT EVO (R); the L stick mirrors it. Dots are fractions of the photo.
R_MAP = [
    ("8-way hat A1", [("up", "b12"), ("down", "b14"), ("left", "b15"), ("right", "b13")], (0.365, 0.056)),
    ("4-way hat A4", [("up", "h1u"), ("down", "h1d"), ("left", "h1l"), ("right", "h1r")], (0.265, 0.083)),
    ("Mini-stick C1", [("push", "b20")], (0.336, 0.133)),
    ("Red button", [("", "b2")], (0.265, 0.178)),
    ("Main trigger", [("", "b1")], (0.255, 0.256)),
    ("Button A2", [("", "b3")], (0.369, 0.336)),
    ("Button D1", [("", "b5")], (0.608, 0.506)),
    ("Base F1", [("", "b6")], (0.680, 0.691)),
    ("Base F3", [("", "b8")], (0.751, 0.672)),
    ("Base F2", [("", "b7")], (0.608, 0.728)),
    ("Encoder EN1", [("up", "b9"), ("down", "b10")], (0.837, 0.756)),
    ("Switch SW1", [("up", "b16"), ("down", "b17")], (0.687, 0.817)),
]
L_DOTS = {g: (x / 696, y / 900) for g, (x, y) in {
    "8-way hat A1": (425, 45), "4-way hat A4": (495, 75), "Mini-stick C1": (440, 120), "Red button": (490, 150),
    "Main trigger": (510, 230), "Button A2": (425, 298), "Button D1": (270, 455), "Base F1": (220, 622),
    "Base F3": (270, 652), "Base F2": (170, 605), "Encoder EN1": (215, 740), "Switch SW1": (110, 700)}.items()}
SHIFT = {"b1": "b33", "b2": "b34", "b6": "b38", "b7": "b39"}
BINDS = {  # (stick side, key): (map, action)
    ("R", "b1"): ("spaceship_weapons", "v_weapon_staggered_fire_toggle"),
    ("R", "b33"): ("spaceship_missiles", "v_weapon_launch_missile"),
    ("R", "b2"): ("spaceship_movement", "v_ifcs_vector_decoupling_toggle"),
    ("R", "h1u"): ("spaceship_targeting_advanced", "v_target_cycle_hostile_fwd"),
    ("R", "h1d"): ("spaceship_targeting_advanced", "v_target_cycle_hostile_back"),
    ("R", "b12"): ("spaceship_power", "v_power_toggle"),
    ("R", "b3"): ("spaceship_movement", "v_toggle_landing_system"),
    ("R", "b6"): ("lights_controller", "v_lights"),
    ("R", "b7"): ("seat_general", "v_emergency_exit"),
    ("R", "b8"): ("spaceship_general", "v_toggle_all_doorlocks"),
    ("R", "b9"): ("spaceship_mining", "v_increase_mining_throttle"),
    ("R", "b10"): ("spaceship_mining", "v_decrease_mining_throttle"),
    ("R", "b20"): ("spaceship_view", "v_view_cycle_fwd"),
    ("L", "b1"): ("spaceship_movement", "v_afterburner"),
    ("L", "b2"): ("spaceship_movement", "v_space_brake"),
    ("L", "b3"): ("spaceship_movement", "v_atc_request"),
    ("L", "b6"): ("spaceship_quantum", "v_toggle_qdrive_engagement"),
    ("L", "b7"): ("spaceship_general", "v_toggle_all_doors"),
    ("L", "h1u"): ("spaceship_movement", "v_ifcs_speed_limiter_up"),
    ("L", "h1d"): ("spaceship_movement", "v_ifcs_speed_limiter_down"),
    ("L", "b12"): ("spaceship_movement", "v_ifcs_throttle_swap_mode"),
}


def build(photos, workdir: Path):
    os.environ["STICK_CITIZEN_HOME"] = str(workdir / "home")
    from stick_citizen.webapi import Api, FakeHub
    hub = FakeHub([{"uid": "L", "name": "VKBsim Gladiator EVO L", "axes": 6, "buttons": 128, "hats": 1},
                   {"uid": "R", "name": "VKBsim Gladiator EVO R", "axes": 6, "buttons": 128, "hats": 1}])
    api = Api(hub, actionmaps=str(ROOT / "samples" / "demo_actionmaps.xml"))
    by_side = {s["side"]: s["slot"] for s in api.get_state()["sticks"]}
    for side, photo in zip("LR", photos or []):
        if photo:
            api.set_photo(by_side[side], photo)
    for side in "LR":
        slot = by_side[side]
        for group, members, (fx, fy) in R_MAP:
            if side == "L":
                fx, fy = L_DOTS[group]
            for d, key in members:
                if len(members) > 1:
                    r = api.map_control(slot, key, d, group, d)
                else:
                    r = api.map_control(slot, key, group)
                api.set_dot(slot, r["control"], fx, fy)
                if key in SHIFT:
                    api.map_control(slot, SHIFT[key], "", "", "", r["control"])
    for (side, key), (m, a) in BINDS.items():
        if api._catalog.get(m, a):
            api.assign(by_side[side], key, m, a)
    hub.press("R", "b77")      # a spare number firing: lands in "Unmapped inputs"
    api.poll()
    state = api.get_state()
    images = {s["name"]: api.get_image(s["slot"]) for s in state["sticks"]}
    search = api.search("", "all", 400)
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
    map_control: () => ok("Mapped"), set_dot: () => Promise.resolve({ ok: true }), edit_control: () => ok(),
    choose_photo: () => Promise.resolve({ ok: false }), open_layout: () => Promise.resolve({ ok: false }),
    save_layout: () => ok("Saved"), fly_test: () => ok("Ring course launched"), say: () => Promise.resolve({}),
    set_speech: () => Promise.resolve({ ok: true }),
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
        {"state": state, "images": images, "search": search, "axes": axes}) + ";\n" + MOCK, encoding="utf-8")
    html = (site / "index.html").read_text(encoding="utf-8")
    (site / "index.html").write_text(html.replace('<script src="app.js">', '<script src="fixture.js"></script>\n<script src="app.js">'), encoding="utf-8")


def shoot(site: Path, out: Path, size=(1600, 940)):
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=True)
    shots = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": size[0], "height": size[1]})
        errors = []
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
        snap("1-both", "S.stick='both'; S.othersOpen=true; render(); window.__events.push({slot:%s,key:'b1',on:true})" % r)
        snap("2-right", "S.stick=%s; render();" % r)
        snap("3-right-shift", "window.__events.push({slot:%s,key:'b1',on:false},{slot:%s,key:'b33',on:true})" % (r, r))
        snap("4-mining", "S.mode='mining'; render();")
        snap("5-edit-drawer", "S.mode='flight'; setView('edit'); openDrawer(%s, '#' + S.state.sticks.find(s=>s.side==='R').controls.find(c=>c.label==='Main trigger').id)" % r)
        snap("6-hat-drawer", "openDrawer(%s, '8-way hat A1'); S.sel.adding = S.state.sticks.find(s=>s.side==='R').controls.find(c=>c.group==='8-way hat A1' && c.dir==='left').inputs.base; renderDrawer();" % r)
        b.close()
    return shots, errors


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos", nargs=2, default=None, help="left and right stick photos")
    ap.add_argument("--out", default="shots")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=940)
    a = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="sc-preview-"))
    st, im, se = build(a.photos, work)
    write_site(st, im, se, work / "site")
    files, errs = shoot(work / "site", Path(a.out), (a.width, a.height))
    print("\n".join(map(str, files)))
    if errs:
        print("PAGE ERRORS:\n" + "\n".join(errs))
        sys.exit(1)

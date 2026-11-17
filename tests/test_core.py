import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from stick_citizen.actionmaps import load_profile, parse_input
from stick_citizen.callouts import describe, humanize, spoken
from stick_citizen.sim import Controls, Course, Ship

DEMO = Path(__file__).parent.parent / "samples" / "demo_actionmaps.xml"


def test_parse_inputs():
    assert parse_input("js1_button3")[0].key == (1, "button", 3, "")
    assert parse_input("js2_rotz")[0].key == (2, "axis", 5, "")
    assert parse_input("js1_hat1_up")[0].key == (1, "hat", 1, "up")
    inp, mods = parse_input("js2_lalt+button9")
    assert inp.key == (2, "button", 9, "") and mods == ("lalt",)
    assert parse_input("js1_ ")[0] is None
    assert parse_input("kb1_space")[0] is None


def test_profile():
    p = load_profile(DEMO)
    assert set(p.devices) == {1, 2}
    assert p.instances == [1, 2]
    gear = p.lookup((2, "button", 6, ""))
    assert gear[0].action == "v_toggle_landing_system"
    assert len(p.lookup((2, "button", 8, ""))) == 2      # conflict surfaced
    assert all(b.action != "v_weapon_countermeasure_noise_launch" for b in p.bindings)  # blank skipped


def test_callouts():
    assert spoken("v_attack1_group1") == "Guns, guns"
    assert spoken("v_atc_request") == "Call A T C"
    assert spoken("v_toggle_landing_system") == "Gear"
    assert humanize("v_ifcs_toggle_vector_decoupling") == "IFCS toggle vector decoupling"
    p = load_profile(DEMO)
    assert describe(p.lookup((2, "button", 5, ""))[0]).endswith("(double tap)")


def test_ship_and_course():
    s, c = Ship(), Course(count=3, seed=1)
    ctl = Controls(strafe_z=1.0)
    for _ in range(600):
        prev = s.pos
        s.update(ctl, 1 / 60)
        c.update(prev, s.pos, 0)
    assert s.speed > 100
    assert c.next >= 1   # first ring sits dead ahead


def test_app_smoke(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from stick_citizen.app import App
    app = App(headless=True)
    app.load_bindings(str(DEMO), announce=False)
    app.run(max_frames=30)


def test_bindingset_roundtrip(tmp_path):
    from stick_citizen.actionmaps import parse_actionmaps
    from stick_citizen.bindings import BindingSet, load_catalog

    bs = BindingSet.from_profile(load_profile(DEMO))
    n = bs.count()
    # moving an action takes it off its old input
    bs.assign((1, "button", 9, ""), "spaceship_general", "v_toggle_landing_system", "tap")
    assert bs.at((2, "button", 6, "")) == []
    assert bs.where("spaceship_general", "v_toggle_landing_system") == (1, "button", 9, "")
    assert bs.count() == n and bs.dirty
    bs.undo()
    assert bs.where("spaceship_general", "v_toggle_landing_system") == (2, "button", 6, "")
    xml = bs.to_xml("My HOSAS")
    again = parse_actionmaps(xml)
    assert again.name == "My-HOSAS"
    assert len(again.bindings) == n
    assert again.lookup((2, "button", 9, ""))[0].modifiers == ("lalt",)
    assert again.lookup((2, "button", 5, ""))[0].activation == "double_tap"
    cat = load_catalog()
    assert len(cat.actions) > 500 and cat.is_axis("spaceship_movement", "v_pitch")


def test_templates(tmp_path, monkeypatch):
    monkeypatch.setenv("STICK_CITIZEN_HOME", str(tmp_path))
    from stick_citizen import templates
    t = templates.load_template("Test Stick R2")
    trig = t.add_control("Trigger", "b1")
    t.set_layer(trig, "shift", "b33")
    up = t.add_control("up", "h1u", "Hat A1", "up")
    t.set_dot(up, 0.3, 0.1)
    down = t.add_control("down", "b14", "Hat A1", "down")
    assert down.dot == [0.3, 0.1]                          # new direction joins its group's spot
    t.save()
    again = templates.load_template("Test Stick R2")
    assert again.control("trigger").inputs == {"base": "b1", "shift": "b33"}
    assert again.control_for("b33")[1] == "shift"
    assert {c.dir for c in again.group_members(again.control_for("h1u")[0])} == {"up", "down"}
    again.set_dot(again.control_for("b14")[0], 0.5, 0.5)
    assert again.control_for("h1u")[0].dot == [0.5, 0.5]   # the whole hat moves together
    # v2.2 maps used plain button numbers
    old = templates.from_json({"controls": [{"id": "x", "label": "X", "inputs": {"base": 5, "shift": 37}}]}, "dev")
    assert old.controls[0].inputs == {"base": "b5", "shift": "b37"}
    assert templates.parse_key("h12l") == ("hat", 12, "left")
    assert templates.other_inputs(again, bound={"b1", "b40", "a0"}, seen={"b77"}) == ["b40", "b77"]


def _api(tmp_path, monkeypatch, devices=None):
    monkeypatch.setenv("STICK_CITIZEN_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    from stick_citizen.webapi import Api, FakeHub
    hub = FakeHub(devices if devices is not None else [
        {"uid": "u1", "name": "VKBsim Gladiator EVO L", "axes": 6, "buttons": 128, "hats": 1},
        {"uid": "u2", "name": "VKBsim Gladiator EVO R", "axes": 6, "buttons": 128, "hats": 1}])
    return Api(hub, actionmaps=str(DEMO)), hub


def test_api_sticks_and_live_input(tmp_path, monkeypatch):
    api, hub = _api(tmp_path, monkeypatch)
    st = api.get_state()
    assert [s["side"] for s in st["sticks"]] == ["L", "R"]          # only connected sticks, left first
    assert all(s["connected"] for s in st["sticks"])
    r = next(s for s in st["sticks"] if s["side"] == "R")
    hub.press("u2", "b77")                                       # a spare number nobody mapped
    out = api.poll()
    assert out["events"] == [{"slot": r["slot"], "key": "b77", "on": True}] and out["reload"]
    assert "b77" in next(s for s in api.get_state()["sticks"] if s["side"] == "R")["others"]


def test_api_map_bind_save(tmp_path, monkeypatch):
    api, hub = _api(tmp_path, monkeypatch)
    slot = next(s["slot"] for s in api.get_state()["sticks"] if s["side"] == "R")
    api.arm_capture(slot)
    hub.press("u2", "b1")
    hub.press("u2", "b1", False)
    assert api.poll()["captured"] == {"slot": slot, "key": "b1", "keys": ["b1"]}
    res = api.map_control(slot, "b1", "My trigger")
    cid = res["control"]
    api.map_control(slot, "b33", "", "", "", cid)                # shift layer
    api.set_dot(slot, cid, 0.25, 0.26)
    res = api.assign(slot, "b33", "spaceship_missiles", "v_weapon_launch_missile")
    assert "My trigger ⇧" in res["msg"]
    stick = next(s for s in res["state"]["sticks"] if s["slot"] == slot)
    assert next(c for c in stick["controls"] if c["id"] == cid)["inputs"] == {"base": "b1", "shift": "b33"}
    assert stick["binds"]["b33"][0]["mode"] == "flight"
    assert "b1" not in stick["others"] and "b33" not in stick["others"]
    hits = api.search("launch missile", "flight")
    assert any(h["action"] == "v_weapon_launch_missile" and h["bound"] for h in hits)
    assert all(h["mode"] in ("flight", "general") for h in api.search("", "flight", 400))
    out = tmp_path / "layout_Test_exported.xml"
    api.save_layout(str(out))
    assert 'input="js%d_button33"' % slot in out.read_text() and not api.is_dirty()


def test_api_no_sticks_shows_file_instances(tmp_path, monkeypatch):
    api, _ = _api(tmp_path, monkeypatch, devices=[])
    st = api.get_state()
    assert [s["slot"] for s in st["sticks"]] == [1, 2] and not any(s["connected"] for s in st["sticks"])


def test_builtin_vkb_profile(tmp_path, monkeypatch):
    api, hub = _api(tmp_path, monkeypatch)
    st = api.get_state()
    r = next(s for s in st["sticks"] if s["side"] == "R")
    assert r["has_image"] and api.get_image(r["slot"]).startswith("data:image/png")   # bundled photo
    groups = {c["group"] or c["label"] for c in r["controls"]}
    assert {"Main trigger", "Mini-stick A1", "Red button A2", "Pinky lever", "Base F1"} <= groups
    trig = [c for c in r["controls"] if c["group"] == "Main trigger"]
    assert [c["inputs"].get("base") for c in trig] == ["b1", "b2"]                  # VKB default stages
    # VKB stock numbers are built in (read off Tim's sticks); only the mini-stick / A1 hat is left to learn
    assert r["unassigned"] == ["hat-a1-push"]                                         # right mini-stick: POV + analog built in
    ids = {c["id"]: c["inputs"].get("base") for c in r["controls"]}
    assert ids["red-button-a2"] == "b3" and ids["rapid-trigger-down"] == "b22" and ids["wheel-t1"] == "a2"
    cid = r["unassigned"][0]
    res = api.assign_input(r["slot"], cid, "base", "b30")
    r2 = next(s for s in res["state"]["sticks"] if s["slot"] == r["slot"])
    assert cid not in r2["unassigned"]
    # learning persists across restarts
    api2, _ = _api(tmp_path, monkeypatch)
    r3 = next(s for s in api2.get_state()["sticks"] if s["side"] == "R")
    assert cid not in r3["unassigned"]


def test_axis_capture_for_t1_wheel(tmp_path, monkeypatch):
    api, hub = _api(tmp_path, monkeypatch)
    r = next(s for s in api.get_state()["sticks"] if s["side"] == "R")
    t1 = next(c for c in r["controls"] if c["id"] == "wheel-t1")
    en1 = [c for c in r["controls"] if c["group"] == "Encoder EN1"]
    assert t1["kind"] == "axis" and {c["dir"] for c in en1} == {"up", "down"}
    hub.axes = {"u2": [0, 0, 0, 0, 0, 0, -1.0]}
    api.arm_capture(r["slot"], "axis")
    hub.press("u2", "b5")                                   # a button press doesn't count for an axis
    assert "captured" not in api.poll()
    hub.axes = {"u2": [0, 0, 0, 0, 0, 0, 0.4]}
    assert api.poll()["captured"]["key"] == "a6"


def test_setup_learns_multi_button_controls(tmp_path, monkeypatch):
    api, hub = _api(tmp_path, monkeypatch)
    r = next(s for s in api.get_state()["sticks"] if s["side"] == "R")
    api.arm_capture(r["slot"])
    hub.press("u2", "b4")
    hub.press("u2", "b5")                                   # a button that fires two numbers (stages)
    assert "captured" not in api.poll()                    # still held: keep listening
    hub.press("u2", "b4", False)
    hub.press("u2", "b5", False)
    got = api.poll()["captured"]
    assert got["keys"] == ["b4", "b5"]
    res = api.learn(r["slot"], "side-button-b1", got["keys"])
    st = next(s for s in res["state"]["sticks"] if s["slot"] == r["slot"])
    stages = [c for c in st["controls"] if c["group"] == "Side button"]
    assert [c["inputs"]["base"] for c in stages] == ["b4", "b5"] and [c["label"] for c in stages] == ["stage 1", "stage 2"]
    # a hat direction that sends a POV hat learns the whole hat (diagonals fire two directions)
    api.learn(r["slot"], "hat-a4-up", ["h2u", "h2r"])
    st = next(s for s in api.get_state()["sticks"] if s["slot"] == r["slot"])
    assert next(c for c in st["controls"] if c["id"] == "hat-a4-right")["inputs"] == {"base": "h2r"}


def test_sublight_layout(tmp_path, monkeypatch):
    api, hub = _api(tmp_path, monkeypatch)
    names = [x["name"] for x in api.list_layouts()]
    assert names[0] == "Blank" and "Sublight" in names
    r = next(s for s in api.get_state()["sticks"] if s["side"] == "R")
    api.learn(r["slot"], "red-button-a2", ["b3"])
    res = api.apply_layout("sublight")
    assert "Sublight" in res["msg"] and "more land once" in res["msg"]
    stick = next(s for s in res["state"]["sticks"] if s["slot"] == r["slot"])
    assert stick["binds"]["b1"][0]["action"] == "v_weapon_preset_fire_guns0"     # trigger: VKB default b1
    assert stick["binds"]["b3"][0]["action"] == "v_master_mode_cycle"            # learned red button
    assert stick["binds"]["a5"][0]["action"] == "v_roll"
    api.undo()
    assert api.get_state()["layout"]["count"] > 0                                # the demo file is back


def test_mode_of():
    from stick_citizen.webapi import mode_of
    assert mode_of("spaceship_weapons") == "flight" and mode_of("spaceship_mining") == "mining"
    assert mode_of("turret_movement") == "turret" and mode_of("zero_gravity_eva") == "foot"
    assert mode_of("default") == "general"


def test_photo_cutout(tmp_path):
    from PIL import Image, ImageDraw
    from stick_citizen.photo import cutout
    im = Image.new("RGB", (400, 500), "white")
    d = ImageDraw.Draw(im)
    d.rectangle((150, 100, 250, 450), fill=(30, 30, 30))      # the "stick"
    d.rectangle((10, 10, 40, 30), fill=(0, 0, 0))             # a logo in the corner
    im.save(tmp_path / "s.jpg")
    res = Image.open(cutout(tmp_path / "s.jpg", tmp_path / "s.png"))
    assert res.mode == "RGBA" and abs(res.size[0] - 100) < 25 and res.size[1] > 300   # cropped to the stick, logo gone


def test_web_assets_carry_the_version():
    """The page asks for app.js?v=<version> so a cached copy from an older build is never used."""
    import stick_citizen
    html = (Path(stick_citizen.__file__).parent / "web" / "index.html").read_text(encoding="utf-8")
    assert f'app.js?v={stick_citizen.__version__}' in html and f'app.css?v={stick_citizen.__version__}' in html


def test_fresh_start_backs_up_old_maps_once(tmp_path, monkeypatch):
    monkeypatch.setenv("STICK_CITIZEN_HOME", str(tmp_path))
    from stick_citizen import paths
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "old.json").write_text("{}")
    assert paths.fresh_start() is True
    assert not (tmp_path / "templates").exists()
    assert list((tmp_path / "backups").glob("*/templates/old.json"))
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "new.json").write_text("{}")
    assert paths.fresh_start() is False                     # only once
    assert (tmp_path / "templates" / "new.json").exists()


def test_mini_stick_analog_mode_learns_two_axes(tmp_path, monkeypatch):
    api, hub = _api(tmp_path, monkeypatch)
    left = next(s for s in api.get_state()["sticks"] if s["side"] == "L")
    mini = [c for c in left["controls"] if c["group"] == "Mini-stick A1"]
    analog = [c for c in mini if c["kind"] == "axis"]
    assert [c["id"] for c in analog] == ["mini-stick-a2-analog-x", "mini-stick-a2-analog-y"]
    assert len([c for c in mini if c["dir"]]) == 9                       # hat mode: 8 directions + push
    slot = left["slot"]
    for cid, idx in (("mini-stick-a2-analog-x", 3), ("mini-stick-a2-analog-y", 4)):
        hub.axes = {"u1": [0.0] * 6}
        api.arm_capture(slot, "axis")
        hub.axes = {"u1": [0.9 if i == idx else 0.0 for i in range(6)]}   # push it all the way one way
        cap = api.poll()["captured"]
        assert cap["key"] == f"a{idx}"
        res = api.learn(slot, cid, cap["keys"])
    l2 = next(s for s in res["state"]["sticks"] if s["slot"] == slot)
    got = {c["id"]: c["inputs"].get("base") for c in l2["controls"] if c["kind"] == "axis" and c["group"] == "Mini-stick A1"}
    assert got == {"mini-stick-a2-analog-x": "a3", "mini-stick-a2-analog-y": "a4"}


def test_old_stick_maps_pick_up_new_builtin_controls(tmp_path, monkeypatch):
    import json
    from stick_citizen import templates
    monkeypatch.setattr(templates, "templates_dir", lambda: tmp_path)
    name = "VKBsim Gladiator EVO L"
    starter = templates.starter_for(name)
    old = {"name": name, "image": "", "controls": [c for c in starter["controls"] if c.get("added", 1) == 1
                                                   and c["id"] != "base-f1"]}    # user took F1 off ("not on my stick")
    old["controls"][0] = dict(old["controls"][0], inputs={"base": "b20"})          # and learned something
    (tmp_path / f"{templates._slug(name)}.json").write_text(json.dumps(old), encoding="utf-8")
    t = templates.load_template(name)
    ids = [c.id for c in t.controls]
    assert "mini-stick-a2-analog-x" in ids and "mini-stick-a2-analog-y" in ids   # new in rev 2
    assert "base-f1" not in ids                                                   # removals stay removed
    assert t.controls[0].inputs == {"base": "b20"}                                # learning kept
    assert "rapid-trigger-down" in ids                                          # new in rev 3
    assert t.starter_rev == 6
    assert templates.load_template(name).starter_rev == 6                         # saved, not re-added


def test_rapid_trigger_rocks_up_and_down(tmp_path, monkeypatch):
    api, hub = _api(tmp_path, monkeypatch)
    for st in api.get_state()["sticks"]:
        rt = {c["dir"]: c["id"] for c in st["controls"] if c["group"] == "Rapid trigger"}
        assert rt == {"up": "rapid-trigger", "down": "rapid-trigger-down"}


def test_axis_springing_back_doesnt_count_for_the_next_step(tmp_path, monkeypatch):
    """Learn the mini-stick's left-right axis, then arm up-down while it's still pushed:
    the spring back to center must not be taken as up-down."""
    api, hub = _api(tmp_path, monkeypatch)
    slot = next(s for s in api.get_state()["sticks"] if s["side"] == "L")["slot"]
    hub.axes = {"u1": [0.0] * 6}
    api.arm_capture(slot, "axis", "mini-stick-a2-analog-x")
    hub.axes = {"u1": [0, 0, 0, 0.95, 0, 0]}
    cap = api.poll()["captured"]
    api.learn(slot, "mini-stick-a2-analog-x", cap["keys"])
    api.arm_capture(slot, "axis", "mini-stick-a2-analog-y")       # still held at 0.95
    hub.axes = {"u1": [0.0] * 6}                                     # springs back to center
    assert "captured" not in api.poll()
    hub.axes = {"u1": [0, 0, 0, 0, 0.9, 0]}                          # now up-down
    assert api.poll()["captured"]["key"] == "a4"
    # re-learning the same control may take its own axis again
    api.arm_capture(slot, "axis", "mini-stick-a2-analog-x")
    hub.axes = {"u1": [0, 0, 0, 0.95, 0.9, 0]}
    assert api.poll()["captured"]["key"] == "a3"


def test_side_button_and_thumb_hat_dots_follow_the_fix(tmp_path, monkeypatch):
    """Tim 2026-11-12: the grey thumb knob is Thumb hat C1; Side button B1 is hidden on the outside of the head.
    Saved maps from before the fix get the corrected dots and keep their numbers."""
    import json
    from stick_citizen import templates
    monkeypatch.setattr(templates, "templates_dir", lambda: tmp_path)
    for name in ("VKBsim Gladiator EVO L", "VKBsim Gladiator EVO R"):
        st = templates.starter_for(name)
        c1 = next(c for c in st["controls"] if c["id"] == "thumb-hat-c1-up")
        sb = next(c for c in st["controls"] if c["id"] == "side-button-b1")
        assert c1["dot"][1] > 0.3 and sb["dot"][1] < 0.2                       # knob low on the grip, button up on the head
        old = [dict(c, dot=[0.5, 0.5], inputs={"base": "b4"} if c["id"] == "side-button-b1" else c["inputs"])
               for c in st["controls"] if c.get("added", 1) == 1]
        (tmp_path / f"{templates._slug(name)}.json").write_text(json.dumps({"name": name, "starter_rev": 3, "controls": old}), encoding="utf-8")
        t = templates.load_template(name)
        assert t.control("side-button-b1").dot == sb["dot"] and t.control("side-button-b1").inputs == {"base": "b4"}
        assert t.control("thumb-hat-c1-up").dot == c1["dot"]
        a4 = next(c for c in st["controls"] if c["id"] == "hat-a4-up")
        assert t.control("hat-a4-up").dot == a4["dot"]                           # v3.7.0 new photos: every dot follows


def test_own_photo_keeps_its_dots(tmp_path, monkeypatch):
    """A user who set their own stick photo keeps their dots when the built-in photo changes."""
    import json
    from stick_citizen import templates
    monkeypatch.setattr(templates, "templates_dir", lambda: tmp_path)
    name = "VKBsim Gladiator EVO L"
    st = templates.starter_for(name)
    old = [dict(c, dot=[0.5, 0.5]) for c in st["controls"] if c.get("added", 1) == 1]
    (tmp_path / f"{templates._slug(name)}.json").write_text(
        json.dumps({"name": name, "image": "mine.png", "starter_rev": 4, "controls": old}), encoding="utf-8")
    t = templates.load_template(name)
    assert t.control("hat-a4-up").dot == [0.5, 0.5]
    assert t.control("pinky-d1").label == "Pinky lever"                         # names still follow the profile


def test_both_sticks_have_a_mini_stick_and_match(tmp_path, monkeypatch):
    api, hub = _api(tmp_path, monkeypatch)
    st = {s["side"]: s for s in api.get_state()["sticks"]}
    for side, dirs in (("L", 9), ("R", 5)):          # right is a POV hat on stock VKB: 4 directions + push
        mini = [c for c in st[side]["controls"] if c["group"] == "Mini-stick A1"]
        assert len([c for c in mini if c["dir"]]) == dirs and len([c for c in mini if c["kind"] == "axis"]) == 2


def test_old_right_map_becomes_mini_stick_keeping_learned_numbers(tmp_path, monkeypatch):
    import json
    from stick_citizen import templates
    monkeypatch.setattr(templates, "templates_dir", lambda: tmp_path)
    name = "VKBsim Gladiator EVO R"
    old = [dict(c, group="Hat A1") if c["id"].startswith("hat-a1-") else c
           for c in templates.starter_for(name)["controls"] if c.get("added", 1) == 1]
    for c in old:
        if c["id"] == "hat-a1-up":
            c["inputs"] = {"base": "b9"}
    (tmp_path / f"{templates._slug(name)}.json").write_text(json.dumps({"name": name, "controls": old}), encoding="utf-8")
    t = templates.load_template(name)
    a1 = [c for c in t.controls if c.id.startswith("hat-a1-")]
    assert {c.group for c in a1} == {"Mini-stick A1"} and len(a1) == 7              # 4 dirs + push + 2 axes
    assert t.control("hat-a1-up").inputs == {"base": "b9"}


def test_pov_mini_stick_map_from_v370_is_repaired(tmp_path, monkeypatch):
    """Tim's v3.7.0 run: the right mini-stick is a POV hat; Set up stored one POV direction per diagonal and left
    the four directions empty. Loading the map fills the four directions and drops the diagonals."""
    import json
    from stick_citizen import templates
    monkeypatch.setattr(templates, "templates_dir", lambda: tmp_path)
    name = "VKBsim Gladiator EVO R"
    ctrls = [dict(c) for c in templates.starter_for(name)["controls"]]
    for c in ctrls:
        if c["id"].startswith("hat-a1-"):
            c["inputs"] = {}
    ctrls += [{"id": f"hat-a1-{d}", "label": d, "group": "Mini-stick A1", "dir": d, "dot": [0.1, 0.1], "inputs": {"base": k}}
              for d, k in (("up-right", "h1r"), ("down-right", "h1d"), ("down-left", "h1l"), ("up-left", "h1u"))]
    (tmp_path / f"{templates._slug(name)}.json").write_text(json.dumps({"name": name, "starter_rev": 6, "controls": ctrls}), encoding="utf-8")
    t = templates.load_template(name)
    a1 = {c.dir: c.inputs.get("base") for c in t.controls if c.group == "Mini-stick A1" and c.dir}
    assert a1 == {"up": "h1u", "right": "h1r", "down": "h1d", "left": "h1l", "push": None}


def test_setup_learns_a_pov_hat_in_one_press(tmp_path, monkeypatch):
    api, hub = _api(tmp_path, monkeypatch)
    l = next(s for s in api.get_state()["sticks"] if s["side"] == "L")
    res = api.learn(l["slot"], "mini-stick-a2-up", ["h1u"])
    assert res["pov"]
    mini = {c["dir"]: c["inputs"].get("base") for c in next(s for s in res["state"]["sticks"] if s["side"] == "L")["controls"]
            if c["group"] == "Mini-stick A1" and c["dir"]}
    assert mini == {"up": "h1u", "right": "h1r", "down": "h1d", "left": "h1l", "push": None}   # no diagonals left


def test_builtin_right_mini_stick_is_pov(tmp_path, monkeypatch):
    api, hub = _api(tmp_path, monkeypatch)
    r = next(s for s in api.get_state()["sticks"] if s["side"] == "R")
    ids = {c["id"]: c["inputs"].get("base") for c in r["controls"]}
    assert ids["hat-a1-up"] == "h1u" and ids["hat-a1-analog-x"] == "a4" and "hat-a1-up-right" not in ids
    assert r["unassigned"] == ["hat-a1-push"]


def templates_input(api, slot, cid):
    from stick_citizen.templates import bind_key
    k = api._tpl(slot).control(cid).inputs.get("base")
    return bind_key(slot, k) if k else None


def test_sublight_axes_and_on_foot(tmp_path, monkeypatch):
    """Tim 2026-11-12: yaw back to normal, throttle (left stick forward/back) inverted, and on foot the left
    mini-stick walks like a controller thumbstick, alongside its flight binds."""
    from stick_citizen.actionmaps import parse_actionmaps
    api, hub = _api(tmp_path, monkeypatch)
    l, r = (next(s for s in api.get_state()["sticks"] if s["side"] == x) for x in "LR")
    api.learn(l["slot"], "mini-stick-a2-up", ["h1u"])            # left mini-stick set up as a POV hat
    api.learn(l["slot"], "mini-stick-a2-push", ["b60"])
    api.apply_layout("sublight")
    xml = api._bset.to_xml("T")
    assert parse_actionmaps(xml).inverts == {(l["slot"], "flight_move_strafe_longitudinal")}   # SC options round-trip
    assert "flight_move_yaw" not in xml
    up = api._bset.at((l["slot"], "hat", 1, "up"))
    assert {(b.map, b.action) for b in up} == {("spaceship_movement", "v_ifcs_speed_limiter_up"), ("player", "moveforward")}
    assert {b.action for b in api._bset.at((l["slot"], "hat", 1, "right"))} >= {"moveright"}
    # hold-speed (sticky) throttle toggle is off the mini-stick push, which is also VKB's mode switch
    swap = [k for k, v in api._bset.binds.items() for b in v if b.action == "v_ifcs_throttle_swap_mode"]
    mini_push = templates_input(api, l["slot"], "mini-stick-a2-push")
    assert mini_push and swap and all(k != mini_push for k in swap) and not api._bset.at(mini_push)
    api.apply_layout("blank")
    assert "invert" not in api._bset.to_xml("T")


# ---------------------------------------------------------------- Fix it
def _fix(api, hub, uid=None, key=None, mouse=False, mode="flight"):
    """One Fix it run: press `key` on stick `uid` (or nothing) and return the result poll() hands back."""
    api.FIX_WAIT = 0 if key is None else api.FIX_WAIT
    api.fixit_arm(mode)
    if mouse:
        api.fixit_mouse()
    if key:
        hub.press(uid, key)
        hub.press(uid, key, False)
    res = api.poll().get("fixit")
    assert res, "Fix it should finish once the press is released (or nothing came)"
    return res, {c["id"]: c for c in res["checks"]}


def test_fixit_stick_sent_nothing(tmp_path, monkeypatch):
    api, hub = _api(tmp_path, monkeypatch)
    _res, c = _fix(api, hub)
    assert c["sent"]["ok"] is False and "HidHide" in c["sent"]["fix"]
    assert c["bound"]["ok"] is None and c["wrong_stick"]["ok"] is None     # nothing to check yet
    api2, hub2 = _api(tmp_path, monkeypatch, devices=[])
    _res, c = _fix(api2, hub2)
    assert c["sent"]["ok"] is False and "can't see any sticks" in c["sent"]["title"]


def test_fixit_mini_stick_in_mouse_mode(tmp_path, monkeypatch):
    api, hub = _api(tmp_path, monkeypatch)
    _res, c = _fix(api, hub, mouse=True)
    assert c["sent"]["ok"] is True and c["mode"]["ok"] is False and "Hat mode" in c["mode"]["fix"]


def test_fixit_bound_and_working(tmp_path, monkeypatch):
    api, hub = _api(tmp_path, monkeypatch)
    res, c = _fix(api, hub, "u2", "b6")                     # demo: js2 button 6 = landing gear (flight)
    assert res["raw"]["keys"] == ["b6"] and res["slot"] == 2
    assert res["sc"]["here"]["b6"][0]["action"] == "v_toggle_landing_system"
    assert [c[k]["ok"] for k in ("sent", "bound", "wrong_stick", "mode")] == [True, True, True, True]


def test_fixit_not_bound_anywhere(tmp_path, monkeypatch):
    api, hub = _api(tmp_path, monkeypatch)
    _res, c = _fix(api, hub, "u2", "b77")
    assert c["bound"]["ok"] is False and c["bound"]["can_fix"]
    assert c["wrong_stick"]["ok"] is True and not c["wrong_stick"]["can_fix"]
    assert api.fixit_fix("bound", str(tmp_path / "layout_X_exported.xml"))["ok"] is False   # pick an action first
    api.assign(2, "b77", "spaceship_general", "v_toggle_all_doors")
    out = tmp_path / "layout_Fixed_exported.xml"
    assert api.fixit_fix("bound", str(out))["ok"] and 'input="js2_button77"' in out.read_text()


def test_fixit_wrong_stick_moves_bind_into_exported_layout(tmp_path, monkeypatch):
    from stick_citizen.actionmaps import load_profile as lp
    live = DEMO.read_bytes()
    api, hub = _api(tmp_path, monkeypatch)
    _res, c = _fix(api, hub, "u1", "b6")                    # js1 b6: nothing here, landing gear sits on js2 b6
    assert c["bound"]["ok"] is False
    assert c["wrong_stick"]["ok"] is False and c["wrong_stick"]["can_fix"] and "js2" in c["wrong_stick"]["title"]
    assert "plug-in order" in c["wrong_stick"]["fix"]       # demo file names both sticks "vJoy": a guess
    out = tmp_path / "mappings" / "layout_FixIt_exported.xml"
    res = api.fixit_fix("wrong_stick", str(out))
    assert res["ok"] and "Moved 1 bind" in res["msg"]
    again = lp(out)
    assert again.lookup((1, "button", 6, ""))[0].action == "v_toggle_landing_system"
    assert again.lookup((2, "button", 6, "")) == []
    assert DEMO.read_bytes() == live                         # SC's live file is never written
    api.undo()
    assert api._bset.where("spaceship_general", "v_toggle_landing_system") == (2, "button", 6, "")


def test_fixit_bound_only_on_foot(tmp_path, monkeypatch):
    from stick_citizen.webapi import mode_of
    api, hub = _api(tmp_path, monkeypatch)
    foot = next(a for a in api._catalog.actions if mode_of(a["map"]) == "foot" and not a["axis"])
    api.assign(2, "b70", foot["map"], foot["action"])
    _res, c = _fix(api, hub, "u2", "b70")
    assert c["bound"]["ok"] is True and c["mode"]["ok"] is False and "On foot" in c["mode"]["title"]
    _res, c = _fix(api, hub, "u2", "b70", mode="foot")      # in the on-foot mode it's fine
    assert c["mode"]["ok"] is True


def test_fixit_shift_layer_on(tmp_path, monkeypatch):
    api, hub = _api(tmp_path, monkeypatch)
    cid = api.map_control(2, "b90", "Test button")["control"]
    api.map_control(2, "b91", "", "", "", cid)              # its shift-layer number
    api.assign(2, "b90", "spaceship_general", "v_toggle_all_doors")
    _res, c = _fix(api, hub, "u2", "b91")
    assert c["mode"]["ok"] is False and c["mode"]["title"] == "Shift layer was on"
    api.remove(2, "b90", "spaceship_general", "v_toggle_all_doors")
    api.assign(2, "b91", "spaceship_general", "v_toggle_all_doors")
    _res, c = _fix(api, hub, "u2", "b90")
    assert c["mode"]["ok"] is False and "⇧ layer" in c["mode"]["title"]


def test_never_writes_live_actionmaps(tmp_path, monkeypatch):
    api, _hub = _api(tmp_path, monkeypatch)
    live = tmp_path / "LIVE" / "actionmaps.xml"
    res = api.save_layout(str(live))
    assert res["ok"] is False and not live.exists()


def test_fixit_freshness_note(tmp_path):
    from stick_citizen.fixit import freshness_note
    f = tmp_path / "actionmaps.xml"
    f.write_text("<ActionMaps/>")
    assert "restart SC" in freshness_note(str(f), running=True)
    assert "saved just now" in freshness_note(str(f), running=False)
    assert "No SC bindings" in freshness_note(None, running=False)


# ---------------------------------------------------------------- Fix it, slice 2: whole-layout scan
def _scan(api):
    res = api.fixit_scan()
    return res, {f["id"]: f for f in res["findings"]}


def _learn_all(api, slot, start=60):
    """What the Set up walkthrough leaves behind: every control on the stick map has an input."""
    st = next(s for s in api.get_state()["sticks"] if s["slot"] == slot)
    for i, cid in enumerate(st["unassigned"]):
        api.assign_input(slot, cid, "base", f"b{start + i}")


def test_scan_two_actions_on_one_input(tmp_path, monkeypatch):
    api, _hub = _api(tmp_path, monkeypatch)
    _res, f = _scan(api)
    c = f["conflict:2:b8"]                                   # demo: doors and door locks both on js2 b8
    assert c["level"] == "warn" and "both fire" in c["title"] and not c["can_fix"]
    assert {a["action"] for a in c["acts"]} == {"v_toggle_all_doors", "v_toggle_all_doorlocks"}
    api.set_activation(2, "b8", "spaceship_general", "v_toggle_all_doorlocks", "hold")   # tap vs hold: not a clash
    _res, f = _scan(api)
    assert "conflict:2:b8" not in f


def test_scan_flight_and_on_foot_on_one_input_is_fine(tmp_path, monkeypatch):
    """Sublight puts flight and on-foot actions on the left mini-stick on purpose: different modes, no clash."""
    api, _hub = _api(tmp_path, monkeypatch)
    l = next(s for s in api.get_state()["sticks"] if s["side"] == "L")
    api.learn(l["slot"], "mini-stick-a2-up", ["h1u"])
    api.apply_layout("sublight")
    _res, f = _scan(api)
    assert not [x for x in f.values() if x["check"] == "conflict" and x["slot"] == l["slot"] and x["key"].startswith("h1")]


def test_scan_wrong_category_and_unknown_action(tmp_path, monkeypatch):
    api, _hub = _api(tmp_path, monkeypatch)
    _res, f = _scan(api)
    brake = f["mode:2:b3:spaceship_movement:v_brake"]       # demo: v_brake filed under spaceship flight; SC has it for ground
    assert brake["level"] == "bad" and "vehicle_driver" in brake["fix"]
    old = f["mode:1:b1:spaceship_weapons:v_attack1_group1"]  # an old action name SC's list doesn't have
    assert old["level"] == "warn" and "renamed or removed" in old["fix"]
    assert "mode:2:b6:spaceship_general:v_toggle_landing_system" in f
    api.remove(2, "b6", "spaceship_general", "v_toggle_landing_system")      # bound again from the list: fine
    api.assign(2, "b6", "spaceship_movement", "v_toggle_landing_system")
    _res, f = _scan(api)
    assert not [x for x in f.values() if x["check"] == "mode" and x["key"] == "b6"]


def test_scan_wrong_stick_moves_bind_into_exported_layout(tmp_path, monkeypatch):
    from stick_citizen.actionmaps import load_profile as lp
    live = DEMO.read_bytes()
    api, _hub = _api(tmp_path, monkeypatch)
    l, r = (next(s for s in api.get_state()["sticks"] if s["side"] == x)["slot"] for x in "LR")
    _res, f = _scan(api)
    # demo: js1 (left) H1 right, but the left stick still has controls to learn: only a "check this"
    assert f[f"dead:{l}:h1r"]["level"] == "warn" and "Run Set up" in f[f"dead:{l}:h1r"]["fix"]
    _learn_all(api, l)
    res, f = _scan(api)
    w = f[f"wrong_stick:{l}:h1r"]                            # every left control learned, none sends H1: only the right stick does
    assert w["level"] == "bad" and w["can_fix"] and w["to"] == r and "plug-in order" in w["fix"]
    assert res["findings"][0]["id"] == w["id"]               # worst first
    out = tmp_path / "mappings" / "layout_Scan_exported.xml"
    done = api.fixit_scan_fix(w["id"], str(out))
    assert done["ok"] and "Moved 1 bind" in done["msg"]
    again = lp(out)
    assert again.lookup((r, "hat", 1, "right"))[0].action == "v_target_cycle_hostile_fwd"
    assert again.lookup((l, "hat", 1, "right")) == []
    assert DEMO.read_bytes() == live                         # SC's live file is never written
    assert api.fixit_scan_fix(w["id"], str(out))["ok"] is False      # used up: scan again
    api.undo()
    assert api._bset.at((l, "hat", 1, "right"))


def test_scan_input_the_stick_never_sends(tmp_path, monkeypatch):
    devs = [{"uid": "u1", "name": "VKBsim Gladiator EVO L", "axes": 6, "buttons": 32, "hats": 1},
            {"uid": "u2", "name": "VKBsim Gladiator EVO R", "axes": 6, "buttons": 32, "hats": 1}]
    api, hub = _api(tmp_path, monkeypatch, devices=devs)
    api.assign(2, "b77", "spaceship_general", "v_toggle_all_doors")
    from stick_citizen.bindings import Bound
    api._bset.binds[(3, "button", 2, "")] = [Bound("spaceship_general", "v_toggle_all_doorlocks")]   # an old third stick
    _res, f = _scan(api)
    d = f["dead:2:b77"]
    assert d["level"] == "bad" and "only has 32 buttons" in d["title"]
    assert "no stick is connected as js3" in f["dead:3:b2"]["title"]
    hub.press("u2", "b30")                                   # a number seen firing is never "never sends"
    api.poll()
    api.assign(2, "b30", "spaceship_general", "v_toggle_all_doors")
    _res, f = _scan(api)
    assert "dead:2:b30" not in f


def test_scan_spare_controls_fix_in_layout(tmp_path, monkeypatch):
    api, _hub = _api(tmp_path, monkeypatch)
    res, f = _scan(api)
    spare = [x for x in res["findings"] if x["check"] == "bound"]
    assert spare and all(x["level"] == "info" and x["can_fix"] for x in spare) and res["summary"]["spare"] == len(spare)
    one = next(x for x in spare if x["slot"] == 2 and x["key"].startswith("b"))
    out = tmp_path / "layout_Spare_exported.xml"
    assert api.fixit_scan_fix(one["id"], str(out))["ok"] is False and not out.exists()     # pick an action first
    api.assign(2, one["key"], "spaceship_general", "v_toggle_all_doors")
    assert api.fixit_scan_fix(one["id"], str(out))["ok"] and f'input="js2_button{one["key"][1:]}"' in out.read_text()


def test_scan_notes_guess_and_no_sticks(tmp_path, monkeypatch):
    api, _hub = _api(tmp_path, monkeypatch)
    res, _f = _scan(api)
    assert "plug-in order" in res["summary"]["guess"]       # demo names both sticks "vJoy": js1/js2 is a guess
    api2, _hub2 = _api(tmp_path, monkeypatch, devices=[])
    res, f = _scan(api2)
    assert "No sticks connected" in res["summary"]["unplugged"]
    assert not [x for x in f.values() if x["check"] in ("dead", "wrong_stick", "bound")]


def test_scan_readouts_stay_separate():
    """The stick side never reads bindings and the SC side never reads sticks; scan joins them."""
    from stick_citizen.bindings import BindingSet, Bound
    from stick_citizen.fixit import layout_readout, scan, stick_readout
    stick = stick_readout(1, side="R", buttons=128, hats=1, controls=[("trig", "Main trigger", {"base": "b1"})])
    assert scan({1: stick}, {})["findings"][0]["check"] == "bound"
    bs = BindingSet()
    bs.binds[(1, "button", 1, "")] = [Bound("spaceship_general", "v_toggle_all_doors", "")]
    sc = layout_readout(bs)
    assert sc[(1, "b1")][0]["known"] == ""                   # no SC list given: category not judged
    assert scan({1: stick}, sc)["findings"] == []


# ---------------------------------------------------------------- backups of SC's live bindings
def _live_sc(tmp_path, text=None):
    """A fake SC install: LIVE\\user\\client\\0\\Profiles\\default\\actionmaps.xml plus its controls folder."""
    base = tmp_path / "StarCitizen" / "LIVE" / "user" / "client" / "0"
    (base / "controls").mkdir(parents=True)
    live = base / "Profiles" / "default" / "actionmaps.xml"
    live.parent.mkdir(parents=True)
    live.write_text(text or DEMO.read_text())
    return live


def _backups(api):
    return api.backup_list()["items"]


def test_backup_on_launch_and_when_sc_changes_binds(tmp_path, monkeypatch):
    live = _live_sc(tmp_path)
    monkeypatch.setenv("STICK_CITIZEN_HOME", str(tmp_path / "home"))
    from stick_citizen.webapi import Api, FakeHub
    api = Api(FakeHub([]), actionmaps=str(live))
    items = _backups(api)
    assert len(items) == 1 and items[0]["kind"] == "auto" and items[0]["channel"] == "LIVE"
    assert items[0]["binds"] == 19 and items[0]["size"] == live.stat().st_size
    assert api._backup_tick() is None                       # nothing changed: nothing new
    live.write_text(DEMO.read_text().replace("js2_button6", "js2_button16"))
    os.utime(live, (live.stat().st_mtime + 5,) * 2)
    assert api._backup_tick()["created"] and len(_backups(api)) == 2
    api.BACKUP_EVERY, api._live_check = 0, 0               # and from poll() while running
    live.write_text(DEMO.read_text().replace("js2_button7", "js2_button17"))
    os.utime(live, (live.stat().st_mtime + 10,) * 2)
    assert "backed up" in api.poll()["backup"] and len(_backups(api)) == 3


def test_backup_dedupes_identical_content_and_skips_half_written(tmp_path, monkeypatch):
    from stick_citizen import backups
    live = _live_sc(tmp_path)
    monkeypatch.setenv("STICK_CITIZEN_HOME", str(tmp_path / "home"))
    assert backups.snapshot(live, now=1_700_000_000)["created"]
    os.utime(live, (live.stat().st_mtime + 5,) * 2)        # SC touched the file, same content
    r = backups.snapshot(live, now=1_700_000_100)
    assert r["ok"] and not r["created"] and len(backups.list_backups()) == 1
    r = backups.snapshot(live, saved=True)                  # "Save my current config" on the same content: kept for good
    assert not r["created"] and r["backup"]["kind"] == "saved" and len(backups.list_backups()) == 1
    live.write_text(DEMO.read_text()[:400])                 # SC halfway through writing it
    r = backups.snapshot(live)
    assert r["ok"] is False and len(backups.list_backups()) == 1


def test_backup_prunes_to_last_20_automatic_keeps_saved(tmp_path, monkeypatch):
    from stick_citizen import backups
    live = _live_sc(tmp_path)
    monkeypatch.setenv("STICK_CITIZEN_HOME", str(tmp_path / "home"))
    backups.snapshot(live, saved=True, now=1_600_000_000)
    for i in range(25):
        live.write_text(DEMO.read_text().replace("js2_button6", f"js2_button{30 + i}"))
        backups.snapshot(live, now=1_700_000_000 + i)
    items = backups.list_backups()
    autos = [b for b in items if b["kind"] == "auto"]
    assert len(autos) == 20 and len([b for b in items if b["kind"] == "saved"]) == 1
    newest = backups.get(autos[0]["id"]).read_text()
    assert "js2_button54" in newest                          # the newest ones stay, oldest go
    assert not any("js2_button30\"" in backups.get(b["id"]).read_text() for b in autos)


def test_backup_back_to_old_content_is_kept_as_newest(tmp_path, monkeypatch):
    """Binds go back to an older state, then SC resets them: that older state must survive pruning."""
    from stick_citizen import backups
    live = _live_sc(tmp_path)
    monkeypatch.setenv("STICK_CITIZEN_HOME", str(tmp_path / "home"))
    good = DEMO.read_text()
    backups.snapshot(live, now=1_700_000_000)
    for i in range(19):
        live.write_text(good.replace("js2_button6", f"js2_button{30 + i}"))
        backups.snapshot(live, now=1_700_000_010 + i)
    live.write_text(good)                                    # back to the first state
    r = backups.snapshot(live, now=1_700_000_100)
    assert r["created"] and len(backups.list_backups()) == 20
    live.write_text(good.replace("js2_button6", "js2_button99"))   # then SC resets / changes again
    backups.snapshot(live, now=1_700_000_200)
    assert any(backups.get(b["id"]).read_text() == good for b in backups.list_backups())


def test_save_my_config_and_restore_as_export_never_writes_live(tmp_path, monkeypatch):
    from stick_citizen.actionmaps import load_profile as lp
    live = _live_sc(tmp_path, DEMO.read_text().replace(
        '<actionmap name="spaceship_movement">',
        '<actionmap name="spaceship_movement">\n   <action name="v_strafe_up"><rebind input="kb1_space"/></action>'))
    before, mtime = live.read_bytes(), live.stat().st_mtime
    monkeypatch.setenv("STICK_CITIZEN_HOME", str(tmp_path / "home"))
    from stick_citizen.webapi import Api, FakeHub
    api = Api(FakeHub([]), actionmaps=str(live))
    r = api.backup_now()
    assert r["ok"] and r["backup"]["kind"] == "saved" and r["suggest"].startswith("MyBinds-")
    out = api.backup_export(r["backup"]["id"], "My Binds!")
    assert out["ok"] and "Control Profiles" in out["msg"] and out["profile"] == "My-Binds"
    f = Path(out["path"])
    assert f.parent == live.parents[2] / "controls" / "mappings" and f.name == "layout_My-Binds_exported.xml"
    xml = f.read_text()
    assert 'profileName="My-Binds"' in xml and "<CustomisationUIHeader" in xml and 'input="kb1_space"' in xml   # keyboard too
    p = lp(f)
    assert p.lookup((2, "button", 6, ""))[0].action == "v_toggle_landing_system" and set(p.devices) == {1, 2}
    again = api.backup_export(r["backup"]["id"], "My Binds!")             # never overwrites an earlier export
    assert Path(again["path"]).name == "layout_My-Binds-2_exported.xml"
    assert api.backup_export(r["backup"]["id"], "x", str(live))["ok"] is False   # refuses the live file
    assert api.backup_export("../../actionmaps.xml", "x")["ok"] is False          # only real backups
    assert live.read_bytes() == before and live.stat().st_mtime == mtime          # the live file is never written


def test_restore_after_sc_reset_brings_back_old_binds(tmp_path, monkeypatch):
    """Tim's crash: SC resets to defaults. The backup from before still restores every custom bind."""
    live = _live_sc(tmp_path)
    monkeypatch.setenv("STICK_CITIZEN_HOME", str(tmp_path / "home"))
    from stick_citizen.actionmaps import load_profile as lp
    from stick_citizen.webapi import Api, FakeHub
    api = Api(FakeHub([]), actionmaps=str(live))
    live.write_text('<ActionMaps><ActionProfiles profileName="default"></ActionProfiles></ActionMaps>')   # reset
    os.utime(live, (live.stat().st_mtime + 5,) * 2)
    api._backup_tick()
    items = _backups(api)
    assert [b["binds"] for b in items] == [0, 19]            # newest first: you can see which one had your binds
    out = api.backup_export(items[1]["id"], "", str(tmp_path / "mappings" / "layout_Before_exported.xml"))
    assert out["ok"] and len(lp(out["path"]).bindings) == len(lp(DEMO).bindings) == 19


def test_backup_without_sc_install(tmp_path, monkeypatch):
    api, _hub = _api(tmp_path, monkeypatch)                  # demo file isn't SC's live actionmaps.xml
    assert api.backup_list()["live"] == "" and api.backup_now()["ok"] is False

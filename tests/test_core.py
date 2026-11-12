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
    assert api.poll()["captured"] == {"slot": slot, "key": "b1"}
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
    assert {"Main trigger", "Hat A1", "Red button A2", "Pinky D1", "Base F1"} <= groups
    trig = [c for c in r["controls"] if c["group"] == "Main trigger"]
    assert [c["inputs"].get("base") for c in trig] == ["b1", "b2"]                  # VKB default stages
    assert len(r["unassigned"]) > 20
    cid = r["unassigned"][0]
    res = api.assign_input(r["slot"], cid, "base", "b30")
    r2 = next(s for s in res["state"]["sticks"] if s["slot"] == r["slot"])
    assert cid not in r2["unassigned"]
    # learning persists across restarts
    api2, _ = _api(tmp_path, monkeypatch)
    r3 = next(s for s in api2.get_state()["sticks"] if s["side"] == "R")
    assert cid not in r3["unassigned"]


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

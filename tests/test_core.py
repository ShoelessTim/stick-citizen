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
    from stick_citizen import templates
    monkeypatch.setattr(templates, "templates_dir", lambda: tmp_path)
    t = templates.load_template("VKBsim Gladiator EVO R", 6, 2, 40)
    assert {"a0", "h1u", "h2r", "b40"} <= set(t.tiles)
    t.tiles["b1"] = [500, 20]
    t.save()
    assert templates.load_template("VKBsim Gladiator EVO R", 6, 2, 40).tiles["b1"] == [500, 20]
    assert templates.parse_tile_key("h12l") == ("hat", 12, "left")


def test_editor_smoke(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.chdir(tmp_path)
    from PySide6 import QtWidgets
    from stick_citizen import qt_app
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = qt_app.MainWindow()
    w.load_path(str(DEMO))
    w.assign((1, "button", 7, ""), "spaceship_missiles", "v_weapon_launch_missile")
    assert w.bset.at((1, "button", 7, ""))[0].action == "v_weapon_launch_missile"
    w.toggle_edit(True)
    v = w.views[1]
    v.tiles["b7"].setPos(400, 12)
    v.save_positions()
    assert (tmp_path / "templates").exists()
    w.bset.dirty = False
    w.close()

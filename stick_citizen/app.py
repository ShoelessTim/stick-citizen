"""Stick Citizen: fly a ring course with your real SC bindings, no SC required."""
from __future__ import annotations

import math
import os
import random
import time
from pathlib import Path

import pygame

from . import config as configmod
from .actionmaps import AXIS_NAMES, INVERT_OPTION, Profile, find_actionmaps, load_profile
from .callouts import describe, humanize, spoken
from .devices import DeviceManager, hat_dirs
from .sim import Controls, Course, Guns, Ship, dot, length, norm, sub

PANEL_W = 460
FOV = 0.9  # focal length as a fraction of view width

# palette
BG = (8, 10, 16)
FG = (220, 226, 236)
DIM = (110, 118, 132)
ACCENT = (255, 170, 40)
GOOD = (90, 220, 140)
BAD = (240, 90, 80)
RING = (80, 200, 255)
RING_NEXT = (255, 200, 60)
PANEL = (16, 19, 28)
CELL = (34, 38, 50)

AXIS_ACTIONS = {
    "v_pitch": ("pitch", 1.0),
    "v_yaw": ("yaw", 1.0),
    "v_roll": ("roll", 1.0),
    "v_strafe_lateral": ("strafe_x", 1.0),
    "v_strafe_vertical": ("strafe_y", 1.0),
    "v_strafe_longitudinal": ("strafe_z", -1.0),  # stick/throttle forward reads negative
}
HELD_DIRECTIONAL = {
    "v_strafe_up": ("strafe_y", 1), "v_strafe_down": ("strafe_y", -1),
    "v_strafe_left": ("strafe_x", -1), "v_strafe_right": ("strafe_x", 1),
    "v_strafe_forward": ("strafe_z", 1), "v_strafe_back": ("strafe_z", -1),
    "v_strafe_backward": ("strafe_z", -1),
    "v_pitch_up": ("pitch", 1), "v_pitch_down": ("pitch", -1),
    "v_yaw_left": ("yaw", -1), "v_yaw_right": ("yaw", 1),
    "v_roll_left": ("roll", -1), "v_roll_right": ("roll", 1),
}


def held_flag(action: str):
    a = action.lower()
    if "attack1" in a:
        return "fire"
    if "afterburner" in a or "boost" in a:
        return "boost"
    if "brake" in a:
        return "brake"
    return None


class App:
    def __init__(self, headless: bool = False, bindings_path: str | None = None):
        self.cfg = configmod.load()
        self.headless = headless
        pygame.init()
        flags = 0 if headless else pygame.RESIZABLE
        self.screen = pygame.display.set_mode((1600, 900), flags)
        pygame.display.set_caption("Stick Citizen")
        self.font = pygame.font.SysFont("consolas,dejavusansmono,monospace", 14)
        self.font_small = pygame.font.SysFont("consolas,dejavusansmono,monospace", 12)
        self.font_big = pygame.font.SysFont("bahnschrift,segoeui,dejavusans", 34, bold=True)
        self.font_mid = pygame.font.SysFont("bahnschrift,segoeui,dejavusans", 20, bold=True)
        self.clock = pygame.time.Clock()

        from .speech import Speaker
        self.speaker = Speaker(enabled=self.cfg.get("speech", True) and not headless)

        self.devices = DeviceManager(self.cfg)
        self.profile = Profile(None, "", {}, [])
        self.profile_mtime = 0.0
        self.profile_status = ""
        self.ship = Ship()
        self.course = Course(seed=7)
        self.guns = Guns()
        rng = random.Random(1)
        self.stars = [norm((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))) for _ in range(500)]

        self.big = ("", 0.0, FG)        # big callout text, time, colour
        self.log = []                   # (text, colour)
        self.flash = {}                 # (device_index, kind, idx, dir) -> time pressed
        self.hat_prev = {}              # (iid, hat) -> value
        self.axis_called = {}           # (inst, slot) -> value at last callout
        self.held = {}
        self.axis_binds = []
        self.held_binds = []
        self.show_help = False
        self.last_poll = 0.0

        self.devices.refresh()
        self.load_bindings(bindings_path or self.cfg.get("actionmaps_path") or find_actionmaps(), announce=False)

    # ---------- bindings ----------
    def load_bindings(self, path, announce=True):
        if not path:
            self.profile_status = "No SC bindings found. Press L to load actionmaps.xml or a layout export."
            self.devices.assign({}, [1, 2])
            return
        try:
            prof = load_profile(path)
        except Exception as e:  # bad XML, missing file
            self.profile_status = f"Couldn't read {Path(path).name}: {e}"
            self.callout("Bindings failed to load", BAD, speak="Bindings failed")
            return
        self.profile = prof
        self.profile_mtime = os.path.getmtime(path)
        self.profile_status = f"{Path(path).name}: {len(prof.bindings)} joystick bindings ({prof.name or 'unnamed'})"
        self.devices.assign(prof.devices, prof.instances)
        self.axis_binds = [b for b in prof.bindings if b.input.kind == "axis"]
        self.held_binds = [b for b in prof.bindings
                           if b.input.kind != "axis" and (b.action in HELD_DIRECTIONAL or held_flag(b.action))]
        if announce:
            self.callout(f"Bindings reloaded: {len(prof.bindings)}", GOOD, speak="Bindings reloaded")

    def poll_reload(self):
        now = time.time()
        if now - self.last_poll < 1.0 or not self.profile.path:
            return
        self.last_poll = now
        try:
            m = os.path.getmtime(self.profile.path)
        except OSError:
            return
        if m != self.profile_mtime:
            self.load_bindings(self.profile.path)

    def pick_file(self):
        try:
            import tkinter
            from tkinter import filedialog
            root = tkinter.Tk()
            root.withdraw()
            path = filedialog.askopenfilename(
                title="Load Star Citizen bindings",
                filetypes=[("Star Citizen bindings", "*.xml"), ("All files", "*.*")])
            root.destroy()
        except Exception:
            path = None
        if path:
            self.cfg["actionmaps_path"] = path
            configmod.save(self.cfg)
            self.load_bindings(path)

    # ---------- callouts ----------
    def callout(self, text, colour=FG, speak=None, big=True):
        if big:
            self.big = (text, time.time(), colour)
        self.log.append((text, colour))
        self.log = self.log[-7:]
        if speak:
            self.speaker.say(speak)

    def on_press(self, iid, kind, idx, direction=""):
        di = self.devices.index_of_iid(iid)
        if di is None:
            return
        self.flash[(di, kind, idx, direction)] = time.time()
        inst = self.devices.instance_of_index(di)
        if inst is None:
            return  # raw device SC doesn't see; it lights up in the panel only
        key = (inst, kind, idx, direction)
        binds = self.profile.lookup(key)
        label = (f"js{inst} button {idx}" if kind == "button" else f"js{inst} hat{idx} {direction}")
        if not binds:
            self.callout(f"{label}: unbound", DIM, big=False)
            return
        texts = [describe(b) for b in binds]
        colour = ACCENT if len(binds) > 1 else FG
        text = " / ".join(texts)
        if len(binds) > 1:
            text += f"   [{len(binds)} actions on {label}]"
        self.callout(text, colour, speak=spoken(binds[0].action))
        for b in binds:
            a = b.action.lower()
            if "landing_system" in a or "landing_gear" in a:
                self.ship.gear = not self.ship.gear
            if "decoupl" in a:
                self.ship.coupled = not self.ship.coupled
                self.callout("DECOUPLED" if not self.ship.coupled else "COUPLED", ACCENT, big=False)

    def input_active(self, inp) -> bool:
        if inp.kind == "button":
            return self.devices.button(inp.instance, inp.index)
        if inp.kind == "hat":
            return inp.direction in hat_dirs(self.devices.hat(inp.instance, inp.index))
        return False

    # ---------- controls ----------
    def read_controls(self) -> Controls:
        c = Controls()
        dz = self.cfg.get("deadzone", 0.04)
        invert = set(self.cfg.get("invert", []))
        throttle = None
        for b in self.axis_binds:
            v = self.devices.axis(b.input.instance, b.input.index)
            if v is None:
                continue
            key = (b.input.instance, b.input.index)
            last = self.axis_called.setdefault(key, v)
            if abs(v - last) > 0.7:
                self.axis_called[key] = v
                self.callout(f"{humanize(b.action)}  ({b.input.label()})", DIM, big=False)
            if b.action in invert or (b.input.instance, INVERT_OPTION.get(b.action)) in self.profile.inverts:
                v = -v
            if "throttle" in b.action.lower():
                throttle = max(0.0, min(1.0, (1.0 - v) / 2.0))
                continue
            if abs(v) < dz:
                v = 0.0
            m = AXIS_ACTIONS.get(b.action)
            if m:
                field, sign = m
                setattr(c, field, max(-1.0, min(1.0, getattr(c, field) + v * sign)))
        c.throttle = throttle
        for b in self.held_binds:
            if not self.input_active(b.input):
                continue
            if b.action in HELD_DIRECTIONAL:
                field, sign = HELD_DIRECTIONAL[b.action]
                setattr(c, field, max(-1.0, min(1.0, getattr(c, field) + sign)))
            flag = held_flag(b.action)
            if flag:
                setattr(c, flag, True)
        return c

    # ---------- main loop ----------
    def handle_events(self) -> bool:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return False
            if ev.type in (pygame.JOYDEVICEADDED, pygame.JOYDEVICEREMOVED):
                self.devices.refresh()
                self.devices.assign(self.profile.devices, self.profile.instances or [1, 2])
            elif ev.type == pygame.JOYBUTTONDOWN:
                self.on_press(ev.instance_id, "button", ev.button + 1)
            elif ev.type == pygame.JOYHATMOTION:
                k = (ev.instance_id, ev.hat)
                new = hat_dirs(ev.value) - hat_dirs(self.hat_prev.get(k, (0, 0)))
                self.hat_prev[k] = ev.value
                for d in sorted(new):
                    self.on_press(ev.instance_id, "hat", ev.hat + 1, d)
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    return False
                if ev.key == pygame.K_l:
                    self.pick_file()
                elif ev.key == pygame.K_r:
                    self.ship.reset()
                    self.course.reset()
                    self.callout("Course reset", GOOD, big=False)
                elif ev.key == pygame.K_m:
                    self.speaker.enabled = not self.speaker.enabled
                    self.callout("Voice " + ("on" if self.speaker.enabled else "muted"), DIM, big=False)
                elif ev.key == pygame.K_h:
                    self.show_help = not self.show_help
                elif pygame.K_F1 <= ev.key <= pygame.K_F4:
                    inst = ev.key - pygame.K_F1 + 1
                    self.devices.cycle(inst)
                    configmod.save(self.cfg)
                    d = self.devices.device_for(inst)
                    self.callout(f"js{inst} -> {d.name if d else 'none'}", GOOD, big=False)
        return True

    def step(self, dt):
        self.poll_reload()
        c = self.read_controls()
        prev = self.ship.pos
        self.ship.update(c, dt)
        self.guns.update(self.ship, c.fire, dt)
        result = self.course.update(prev, self.ship.pos, time.time())
        if result == "ring":
            self.speaker.say("Ring")
        elif result == "finish":
            t = self.course.elapsed(time.time())
            self.callout(f"Course complete: {t:.1f}s  (R to reset)", GOOD, speak=f"Course complete, {t:.0f} seconds")

    def run(self, max_frames=None):
        frames = 0
        running = True
        while running:
            dt = min(self.clock.tick(60) / 1000.0, 0.05)
            running = self.handle_events()
            self.step(dt)
            self.draw()
            frames += 1
            if max_frames and frames >= max_frames:
                break
        configmod.save(self.cfg)
        pygame.quit()

    # ---------- drawing ----------
    def draw(self):
        W, H = self.screen.get_size()
        view = pygame.Rect(0, 0, max(200, W - PANEL_W), H)
        self.screen.fill(BG)
        self.draw_world(view)
        self.draw_hud(view)
        self.draw_panel(pygame.Rect(view.right, 0, W - view.right, H))
        if self.show_help:
            self.draw_help(view)
        pygame.display.flip()

    def project(self, view, p, direction=False):
        s = self.ship
        rel = p if direction else sub(p, s.pos)
        x, y, z = dot(rel, s.right), dot(rel, s.up), dot(rel, s.fwd)
        if z < (0.01 if direction else 1.0):
            return None, (x, y, z)
        f = view.width * FOV
        return (view.centerx + f * x / z, view.centery - f * y / z), (x, y, z)

    def draw_world(self, view):
        for st in self.stars:
            p, _ = self.project(view, st, direction=True)
            if p and view.collidepoint(p):
                self.screen.set_at((int(p[0]), int(p[1])), (150, 156, 170))
        # rings, far to near
        from .sim import add, cross, mul, rotate
        order = sorted(range(len(self.course.rings)),
                       key=lambda i: -length(sub(self.course.rings[i][0], self.ship.pos)))
        for i in order:
            if i < self.course.next:
                continue
            c, n, r = self.course.rings[i]
            u = norm(cross(n, (0.0, 1.0, 0.0)) if abs(n[1]) < 0.95 else cross(n, (1.0, 0.0, 0.0)))
            pts = [add(c, mul(rotate(u, n, 2 * math.pi * k / 32), r)) for k in range(33)]
            proj = [self.project(view, p)[0] for p in pts]
            colour = RING_NEXT if i == self.course.next else RING
            width = 3 if i == self.course.next else 1
            for a, b in zip(proj, proj[1:]):
                if a and b and abs(a[0]) < 1e5 and abs(b[0]) < 1e5:
                    pygame.draw.line(self.screen, colour, a, b, width)
        for pos, vel, life in self.guns.rounds:
            a = self.project(view, pos)[0]
            b = self.project(view, sub(pos, mul(norm(vel), 25)))[0]
            if a and b:
                pygame.draw.line(self.screen, ACCENT, a, b, 2)

    def text(self, font, s, pos, colour=FG, anchor="topleft"):
        img = font.render(s, True, colour)
        r = img.get_rect(**{anchor: pos})
        self.screen.blit(img, r)
        return r

    def draw_hud(self, view):
        cx, cy = view.center
        pygame.draw.circle(self.screen, DIM, (cx, cy), 6, 1)
        pygame.draw.line(self.screen, DIM, (cx - 18, cy), (cx - 9, cy))
        pygame.draw.line(self.screen, DIM, (cx + 9, cy), (cx + 18, cy))
        s = self.ship
        if s.speed > 2:
            p, _ = self.project(view, s.vel, direction=True)
            if p:
                pygame.draw.circle(self.screen, GOOD, (int(p[0]), int(p[1])), 9, 2)
        # next ring pointer when off screen
        if not self.course.done:
            c = self.course.rings[self.course.next][0]
            p, (x, y, z) = self.project(view, c)
            if p is None or not view.inflate(-40, -40).collidepoint(p):
                ang = math.atan2(-y, x)
                ex, ey = cx + math.cos(ang) * (view.height * 0.4), cy + math.sin(ang) * (view.height * 0.4)
                tip = (ex + math.cos(ang) * 14, ey + math.sin(ang) * 14)
                left = (ex + math.cos(ang + 2.5) * 12, ey + math.sin(ang + 2.5) * 12)
                right = (ex + math.cos(ang - 2.5) * 12, ey + math.sin(ang - 2.5) * 12)
                pygame.draw.polygon(self.screen, RING_NEXT, [tip, left, right])
        # readouts
        mode = "COUPLED" if s.coupled else "DECOUPLED"
        self.text(self.font_mid, f"{s.speed:5.0f} m/s", (view.x + 20, view.bottom - 210))
        self.text(self.font, mode, (view.x + 20, view.bottom - 182), FG if s.coupled else ACCENT)
        self.text(self.font, "GEAR DOWN" if s.gear else "GEAR UP", (view.x + 20, view.bottom - 164),
                  ACCENT if s.gear else DIM)
        done = self.course.next
        self.text(self.font_mid, f"Ring {min(done + 1, self.course.count)}/{self.course.count}"
                  if not self.course.done else "Course complete",
                  (view.right - 20, view.bottom - 210), RING_NEXT, "topright")
        self.text(self.font, f"{self.course.elapsed(time.time()):6.1f} s",
                  (view.right - 20, view.bottom - 182), FG, "topright")
        # big callout
        msg, t0, colour = self.big
        age = time.time() - t0
        if msg and age < 2.2:
            fade = max(0.0, min(1.0, 2.2 - age))
            col = tuple(int(BG[i] + (colour[i] - BG[i]) * fade) for i in range(3))
            font = self.font_big if self.font_big.size(msg)[0] < view.width - 40 else self.font_mid
            self.text(font, msg, (cx, 60), col, "midtop")
        # log
        y = view.bottom - 140
        for i, (line, colour) in enumerate(self.log[-7:]):
            self.text(self.font, line, (view.x + 20, y + i * 18), colour)
        self.text(self.font_small, "H help   L load bindings   R reset   F1-F4 assign js1-4   M mute   Esc quit",
                  (view.x + 20, 14), DIM)

    def draw_panel(self, rect):
        pygame.draw.rect(self.screen, PANEL, rect)
        x, y = rect.x + 14, 12
        self.text(self.font_mid, "STICK CITIZEN", (x, y), ACCENT)
        y += 30
        for line in _wrap(self.profile_status or "No bindings", 58):
            self.text(self.font_small, line, (x, y), DIM)
            y += 15
        y += 6
        now = time.time()
        shown = set()
        rows = [(inst, self.devices.instance_map.get(inst)) for inst in self.devices.instances]
        rows += [(None, i) for i in range(len(self.devices.devices))
                 if i not in self.devices.instance_map.values()]
        for inst, di in rows:
            if y > rect.bottom - 40:
                break
            if di is None:
                self.text(self.font, f"js{inst}: no device  (F{inst} to assign)" if inst and inst <= 4
                          else f"js{inst}: no device", (x, y), BAD)
                y += 22
                continue
            if di in shown:
                continue
            shown.add(di)
            d = self.devices.devices[di]
            tag = f"SC js{inst}" if inst else "raw"
            self.text(self.font, f"{tag}  {d.name}", (x, y), GOOD if inst else DIM)
            y += 18
            # axes in two columns
            for a in range(min(d.num_axes, 8)):
                col, row = a % 2, a // 2
                ax_x = x + col * 215
                ay = y + row * 13
                slot_name = AXIS_NAMES[a] if inst else f"a{a}"
                self.text(self.font_small, slot_name, (ax_x, ay - 1), DIM)
                bar = pygame.Rect(ax_x + 52, ay + 2, 150, 8)
                pygame.draw.rect(self.screen, CELL, bar)
                v = d.js.get_axis(a)
                mid = bar.centerx
                end = mid + int(v * bar.width / 2)
                pygame.draw.rect(self.screen, GOOD if inst else DIM,
                                 pygame.Rect(min(mid, end), bar.y, max(2, abs(end - mid)), bar.height))
            y += ((min(d.num_axes, 8) + 1) // 2) * 13 + 4
            # buttons, 32 per row
            per = 32
            for b in range(min(d.num_buttons, 128)):
                cell = pygame.Rect(x + (b % per) * 13, y + (b // per) * 13, 11, 11)
                pressed = d.js.get_button(b)
                age = now - self.flash.get((di, "button", b + 1, ""), 0)
                bound = inst is not None and bool(self.profile.lookup((inst, "button", b + 1, "")))
                colour = ACCENT if pressed else (GOOD if age < 0.4 else (CELL if not bound else (52, 64, 80)))
                pygame.draw.rect(self.screen, colour, cell)
            y += ((min(d.num_buttons, 128) + per - 1) // per) * 13 + 2
            if d.num_hats:
                hats = "  ".join(f"hat{h + 1} {_hat_str(d.js.get_hat(h))}" for h in range(d.num_hats))
                self.text(self.font_small, hats, (x, y), DIM)
                y += 15
            y += 10
        self.text(self.font_small, "bright = bound in SC   flash = just pressed", (x, rect.bottom - 22), DIM)

    def draw_help(self, view):
        lines = [
            "Stick Citizen",
            "",
            "Reads the vJoy devices Star Citizen sees and your SC bindings file.",
            "Every press shows and speaks its SC action. Orange text = more than one action on that input.",
            "Raw devices (your NXT) only light up in the panel; SC never sees them through Gremlin.",
            "",
            "L  load an actionmaps.xml or exported layout   (auto-reloads when the file is saved)",
            "F1-F4  point SC js1-js4 at a different device if left/right are crossed",
            "R  reset ship and course     M  mute voice     H  close help",
        ]
        box = pygame.Rect(0, 0, 760, 30 + 20 * len(lines))
        box.center = view.center
        pygame.draw.rect(self.screen, PANEL, box)
        pygame.draw.rect(self.screen, ACCENT, box, 1)
        for i, l in enumerate(lines):
            self.text(self.font if i else self.font_mid, l, (box.x + 20, box.y + 14 + i * 20), FG if i else ACCENT)


def _hat_str(v):
    d = hat_dirs(v)
    return "/".join(sorted(d)) if d else "-"


def _wrap(s, n):
    words, lines, cur = s.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > n:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def main(bindings_path: str | None = None):
    App(bindings_path=bindings_path).run()


if __name__ == "__main__":
    main()

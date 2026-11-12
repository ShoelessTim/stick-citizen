"""Joystick discovery and SC js-instance -> physical device mapping."""
from __future__ import annotations

import re

import pygame


def _base_name(product: str) -> str:
    return re.sub(r"\{.*?\}", "", product or "").strip().lower()


class Device:
    def __init__(self, js):
        self.js = js
        self.iid = js.get_instance_id()
        self.name = js.get_name() or "Unknown device"
        self.num_axes = js.get_numaxes()
        self.num_buttons = js.get_numbuttons()
        self.num_hats = js.get_numhats()

    @property
    def is_vjoy(self) -> bool:
        return "vjoy" in self.name.lower()


class DeviceManager:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.devices: list[Device] = []
        self.instance_map: dict[int, int] = {}   # SC instance -> index into self.devices
        self.instances: list[int] = [1, 2]

    def refresh(self):
        if not pygame.joystick.get_init():
            pygame.joystick.init()
        self.devices = [Device(pygame.joystick.Joystick(i)) for i in range(pygame.joystick.get_count())]

    def assign(self, profile_devices: dict, instances: list):
        overrides = {int(k): v for k, v in self.cfg.get("instances", {}).items()}
        self.instances = sorted(set(instances) | set(overrides)) or [1, 2]
        self.instance_map = {}
        used = set()
        for inst in self.instances:
            o = overrides.get(inst)
            if isinstance(o, int) and 0 <= o < len(self.devices):
                self.instance_map[inst] = o
                used.add(o)
        for inst in self.instances:
            if inst in self.instance_map:
                continue
            want = _base_name(profile_devices.get(inst, ""))
            pick = None
            if want:
                pick = next((i for i, d in enumerate(self.devices)
                             if i not in used and want in d.name.lower()), None)
            if pick is None:  # SC normally sees vJoy, so fall back to the next vJoy device
                pick = next((i for i, d in enumerate(self.devices) if i not in used and d.is_vjoy), None)
            if pick is None:  # direct path: SC sees the sticks themselves, in Windows order
                pick = next((i for i in range(len(self.devices)) if i not in used), None)
            if pick is not None:
                self.instance_map[inst] = pick
                used.add(pick)

    def cycle(self, inst: int):
        """Point SC js<inst> at the next device; remembered in the config."""
        if not self.devices:
            return
        cur = self.instance_map.get(inst, -1)
        nxt = (cur + 1) % len(self.devices)
        self.instance_map[inst] = nxt
        self.cfg.setdefault("instances", {})[str(inst)] = nxt
        if inst not in self.instances:
            self.instances = sorted(self.instances + [inst])

    def index_of_iid(self, iid):
        return next((i for i, d in enumerate(self.devices) if d.iid == iid), None)

    def instance_of_index(self, idx):
        return next((inst for inst, i in self.instance_map.items() if i == idx), None)

    def device_for(self, inst):
        i = self.instance_map.get(inst)
        return self.devices[i] if i is not None and i < len(self.devices) else None

    def axis(self, inst, slot):
        d = self.device_for(inst)
        order = self.cfg.get("axis_order") or list(range(8))
        if d is None or slot >= len(order) or order[slot] >= d.num_axes:
            return None
        return d.js.get_axis(order[slot])

    def button(self, inst, number) -> bool:
        d = self.device_for(inst)
        return bool(d and 0 < number <= d.num_buttons and d.js.get_button(number - 1))

    def hat(self, inst, number):
        d = self.device_for(inst)
        if d is None or not (0 < number <= d.num_hats):
            return (0, 0)
        return d.js.get_hat(number - 1)


def hat_dirs(value) -> set:
    x, y = value
    out = set()
    if y > 0:
        out.add("up")
    if y < 0:
        out.add("down")
    if x < 0:
        out.add("left")
    if x > 0:
        out.add("right")
    return out

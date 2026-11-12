"""A deliberately crude 6DOF ship, a ring course and some tracers."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass


def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def length(a): return math.sqrt(dot(a, a))


def norm(a):
    n = length(a)
    return mul(a, 1.0 / n) if n > 1e-9 else (0.0, 0.0, 1.0)


def rotate(v, axis, ang):
    """Rodrigues rotation of v about unit axis by ang radians."""
    c, s = math.cos(ang), math.sin(ang)
    return add(add(mul(v, c), mul(cross(axis, v), s)), mul(axis, dot(axis, v) * (1 - c)))


def approach(cur, target, max_step):
    d = sub(target, cur)
    n = length(d)
    return target if n <= max_step else add(cur, mul(d, max_step / n))


@dataclass
class Controls:
    pitch: float = 0.0     # + nose up
    yaw: float = 0.0       # + nose right
    roll: float = 0.0      # + right wing down
    strafe_x: float = 0.0  # + right
    strafe_y: float = 0.0  # + up
    strafe_z: float = 0.0  # + forward
    throttle: float | None = None  # 0..1 when an absolute throttle axis is bound
    boost: bool = False
    brake: bool = False
    fire: bool = False


class Ship:
    RATES = (math.radians(70), math.radians(55), math.radians(130))  # pitch, yaw, roll per second
    SCM = 220.0
    ACCEL = 70.0

    def __init__(self):
        self.reset()

    def reset(self):
        self.pos = (0.0, 0.0, 0.0)
        self.vel = (0.0, 0.0, 0.0)
        self.right, self.up, self.fwd = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
        self.coupled = True
        self.gear = False

    def local(self, x, y, z):
        return add(add(mul(self.right, x), mul(self.up, y)), mul(self.fwd, z))

    def update(self, c: Controls, dt: float):
        rp, ry, rr = self.RATES
        # pitch about right, yaw about up, roll about forward
        a = -c.pitch * rp * dt
        self.up, self.fwd = rotate(self.up, self.right, a), rotate(self.fwd, self.right, a)
        a = c.yaw * ry * dt
        self.right, self.fwd = rotate(self.right, self.up, a), rotate(self.fwd, self.up, a)
        a = -c.roll * rr * dt
        self.right, self.up = rotate(self.right, self.fwd, a), rotate(self.up, self.fwd, a)
        self.fwd = norm(self.fwd)
        self.right = norm(cross(self.up, self.fwd))
        self.up = cross(self.fwd, self.right)

        fwd_cmd = c.throttle if c.throttle is not None else c.strafe_z
        cmd = (c.strafe_x, c.strafe_y, fwd_cmd)
        boost = 1.5 if c.boost else 1.0
        if c.brake:
            self.vel = approach(self.vel, (0.0, 0.0, 0.0), self.ACCEL * 2 * dt)
        elif self.coupled:
            target = self.local(*mul(cmd, self.SCM * boost))
            self.vel = approach(self.vel, target, self.ACCEL * boost * dt)
        else:
            self.vel = add(self.vel, mul(self.local(*cmd), self.ACCEL * boost * dt))
        self.pos = add(self.pos, mul(self.vel, dt))

    @property
    def speed(self):
        return length(self.vel)


class Course:
    def __init__(self, count: int = 15, seed: int | None = None):
        self.count = count
        self.seed = seed
        self.reset()

    def reset(self):
        rng = random.Random(self.seed)
        self.rings = []
        pos, d = (0.0, 0.0, 300.0), (0.0, 0.0, 1.0)
        up = (0.0, 1.0, 0.0)
        for i in range(self.count):
            radius = 45.0 - 20.0 * i / max(1, self.count - 1)
            self.rings.append((pos, d, radius))
            right = norm(cross(up, d))
            d = norm(rotate(rotate(d, up, rng.uniform(-0.45, 0.45)), right, rng.uniform(-0.25, 0.25)))
            pos = add(pos, mul(d, rng.uniform(350, 550)))
        self.next = 0
        self.start_time = None
        self.finish_time = None

    @property
    def done(self):
        return self.next >= len(self.rings)

    def update(self, prev, cur, t):
        """Returns 'ring', 'finish' or None."""
        if self.done:
            return None
        c, n, r = self.rings[self.next]
        d0, d1 = dot(sub(prev, c), n), dot(sub(cur, c), n)
        if d0 < 0 <= d1:
            f = d0 / (d0 - d1) if d0 != d1 else 0
            hit = add(prev, mul(sub(cur, prev), f))
            if length(sub(hit, c)) <= r:
                if self.start_time is None:
                    self.start_time = t
                self.next += 1
                if self.done:
                    self.finish_time = t
                    return "finish"
                return "ring"
        return None

    def elapsed(self, t):
        if self.start_time is None:
            return 0.0
        return (self.finish_time or t) - self.start_time


class Guns:
    SPEED = 900.0
    LIFE = 1.2
    RATE = 10.0

    def __init__(self):
        self.rounds = []
        self._cool = 0.0

    def update(self, ship: Ship, firing: bool, dt: float):
        self._cool -= dt
        if firing and self._cool <= 0:
            self._cool = 1.0 / self.RATE
            for side in (-4.0, 4.0):
                p = add(ship.pos, add(ship.local(side, -2.0, 6.0), (0, 0, 0)))
                self.rounds.append([p, add(ship.vel, mul(ship.fwd, self.SPEED)), self.LIFE])
        for r in self.rounds:
            r[0] = add(r[0], mul(r[1], dt))
            r[2] -= dt
        self.rounds = [r for r in self.rounds if r[2] > 0]

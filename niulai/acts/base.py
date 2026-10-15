# -*- coding: utf-8 -*-
"""分幕框架：Shot（镜头）+ pick_shot + 通用小工具。

每幕 = Shot 序列；Shot.camera(t_local) -> (eye, target)（纯函数）。
角色摆位 helper：place_quad（四足，origin=地面）/ place_calf（牛来，origin=躯干）。
"""
import math

from pyglet.math import Vec3


def smooth(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3.0 - 2.0 * u)


def lerp(a, b, u):
    return a + (b - a) * u


def lerp3(a, b, u):
    return (lerp(a[0], b[0], u), lerp(a[1], b[1], u), lerp(a[2], b[2], u))


class Shot:
    """一个镜头：[t0, t1) 秒，camera(t_local) -> (eye, target)。"""

    def __init__(self, t0, t1, camera, note=''):
        self.t0, self.t1 = t0, t1
        self.camera = camera
        self.note = note

    def contains(self, t):
        return self.t0 <= t < self.t1


def pick_shot(shots, t):
    """t -> (shot, t_local)。越界归入首/末幕（容错）。"""
    for s in shots:
        if s.contains(t):
            return s, t - s.t0
    return (shots[0], t) if t < shots[0].t0 else (shots[-1], t - shots[-1].t0)


def place_quad(q, x, z, yaw, ground):
    """四足摆位：origin 在地表（腿长已按 body_y 配好，蹄恰着地）。"""
    q.origin = Vec3(x, ground(x, z), z)
    q.yaw = yaw
    return q


def orbit_eye(target, ang, dist, up):
    """绕 target 的机位（水平角 + 高度）-> eye。"""
    return (target[0] + math.cos(ang) * dist,
            target[1] + up,
            target[2] + math.sin(ang) * dist)


def track_eye(target, ang, dist, up, sway_t=0.0):
    """orbit_eye + 确定性微风摆动（t 的显函数，不累积）。"""
    ex, ey, ez = orbit_eye(target, ang, dist, up)
    return (ex + 0.4 * math.sin(sway_t * 0.5), ey + 0.3 * math.sin(sway_t * 0.8 + 1.0), ez)

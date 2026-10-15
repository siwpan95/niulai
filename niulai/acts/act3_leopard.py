# -*- coding: utf-8 -*-
"""第三幕 · 豹拉（1380–2100s，12 min，黄昏）。

结识孤独小豹 -> 分奶结友 -> 妈妈约法三章 -> 狼群初袭豹拉引开追兵
-> 牛群误会，被迫分离。

镜头表（act-local 秒，总 720s）：
  0–90    沙丘上出现小豹剪影（远景）
  90–240  初遇：牛来不怕，"我别怕它，它是一条小溪流"
  240–360 分奶："满足你的胃，它会治愈悲伤的"
  360–450 妈妈介入：约法三章
  450–560 狼群初袭（2 只狼巡游），豹拉引开
  560–720 分离："就算分开我们还是朋友"
"""
import math

from pyglet.math import Vec3

from .. import MASTER_SEED
from ..cast import perf
from ..cast.calf import Calf
from ..cast.quadruped import Quadruped
from ..cast.specs import LEOPARD_SPEC, MOTHER_SPEC, WOLF_SPEC
from ..brains.world import CastWorld
from ..scenery import desert
from ..timeline import Timeline
from . import base
from .subtitles import SubtitleOverlay, SubtitleTrack

ACT = 'act3_leopard'
T_END = 720.0

SKY = (0.92, 0.72, 0.55)          # 黄昏暖橙
FOG_K = 0.0120

# 地理：河北岸草地（过河后）
CAMP = (30.0, 74.0)
LEO_START = (2.0, 80.0)
LEO_END = (16.0, 72.0)
MEET = (17.0, 63.0)

LINES = (
    (155.0, 162.0, '牛来', '我别怕它，它是一条小溪流。'),
    (335.0, 342.0, '牛来', '满足你的胃，它会治愈悲伤的。'),
    (343.0, 349.0, '牛来', '将就点，要不饿成狗！'),
    (455.0, 462.0, '牛妈妈', '你们以后必须要分开。'),
    (463.0, 469.0, '牛来', '妈妈，救救豹拉吧！'),
    (645.0, 652.0, '牛来', '就算分开我们还是朋友。'),
    (654.0, 660.0, '豹拉', '相信我，我还会在你身后出现的。'),
)


class LeopardScene:
    """第三幕场景。"""

    NAME = ACT
    SKY = SKY
    FOG_K = FOG_K

    def __init__(self, seed=MASTER_SEED, grid=192):
        self.timeline = Timeline()
        self.seed = seed
        self.ground = lambda x, z: desert.height_at(x, z, seed)
        self.terrain_md, _ = desert.build_terrain(seed, grid, 1.0)
        self.river_md = desert.build_river(seed)
        self.calf = Calf()
        self.mother = Quadruped(MOTHER_SPEC)
        self.leopard = Quadruped(LEOPARD_SPEC)
        self.wolves = [Quadruped(WOLF_SPEC) for _ in range(3)]
        self.herd = [Quadruped(MOTHER_SPEC) for _ in range(5)]
        self.cast = CastWorld()
        self.cast.register('niulai')
        self.cast.register('mother')
        self.cast.register('baola')
        for i in range(3):
            self.cast.register(f'wolf{i}')
        for i in range(5):
            self.cast.register(f'herd{i}')
        self._sub = SubtitleOverlay(SubtitleTrack(LINES))
        self.shots = self._build_shots()

    # ---------------------------------------------------------------- 走位 --
    def _leo_xy(self, t):
        """豹拉位置：沙丘 -> 150s 内走到初遇点 -> 引狼远去。"""
        if t < 150.0:
            u = base.smooth(t / 150.0)
            return (LEO_START[0] + (MEET[0] - LEO_START[0]) * u,
                    LEO_START[1] + (MEET[1] - LEO_START[1]) * u)
        if t < 560.0:
            u = base.smooth((t - 150.0) / 410.0)
            return (MEET[0] + 2.0 * u, MEET[1] + 1.0 * math.sin(u * 5.0))
        # 640s 后引开狼群，奔向远方沙丘
        u = base.smooth((t - 640.0) / 80.0)
        return (15.0 - 40.0 * u, 70.0 + 12.0 * u)

    def _calf_xy(self, t):
        if t < 240.0:
            return (MEET[0] + 2.5, MEET[1] - 1.5)
        u = base.smooth((t - 240.0) / 480.0)
        return (MEET[0] + 2.5 + 1.0 * math.sin(u * 6.0), MEET[1] - 1.5 - 0.5 * u)

    # ---------------------------------------------------------------- 镜头 --
    def _build_shots(self):
        def cam_silhouette(u, t):
            # 机位在牛来身后，眺望沙丘上走近的豹拉（双主体都入境）
            cx, cz = self._calf_xy(t)
            lx, lz = self._leo_xy(t)
            eye = (cx - 3.0, self.ground(cx, cz) + 1.6, cz + 4.0)
            return eye, (lx, self.ground(lx, lz) + 1.2, lz)

        def cam_meet(u, t):
            lx, lz = self._leo_xy(t)
            cx, cz = self._calf_xy(t)
            mid = ((lx + cx) / 2, self.ground((lx + cx) / 2, (lz + cz) / 2) + 0.9,
                   (lz + cz) / 2)
            ang = 1.7 + 0.25 * math.sin(u * 0.09)
            return base.orbit_eye(mid, ang, 7.0, 2.2), mid

        def cam_share(u, t):
            cx, cz = self._calf_xy(t)
            c = (cx, self.ground(cx, cz) + 0.8, cz)
            return base.orbit_eye(c, 2.2, 5.5, 1.4), c

        def cam_mother(u, t):
            c = (CAMP[0], self.ground(*CAMP) + 1.2, CAMP[1])
            ang = -0.6 + 0.2 * math.sin(u * 0.08)
            return base.orbit_eye(c, ang, 10.0, 3.0), c

        def cam_wolves(u, t):
            # 狼群初袭：低机位跟两只狼
            cx, cz = self._calf_xy(t)
            c = (cx + 4.0, self.ground(cx, cz) + 1.0, cz + 2.0)
            return base.orbit_eye(c, 0.2, 8.0, 1.8), c

        def cam_farewell(u, t):
            lx, lz = self._leo_xy(t)
            cx, cz = self._calf_xy(t)
            mid = ((lx + cx) / 2, self.ground((lx + cx) / 2, (lz + cz) / 2) + 1.2,
                   (lz + cz) / 2)
            ang = 1.1 + 0.25 * math.sin(u * 0.07)
            return base.orbit_eye(mid, ang, 14.0, 4.0), mid

        return [
            base.Shot(0.0, 150.0, cam_silhouette, '沙丘剪影'),
            base.Shot(150.0, 330.0, cam_meet, '初遇'),
            base.Shot(330.0, 450.0, cam_share, '分奶'),
            base.Shot(450.0, 540.0, cam_mother, '约法三章'),
            base.Shot(540.0, 640.0, cam_wolves, '狼群初袭'),
            base.Shot(640.0, T_END, cam_farewell, '分离'),
        ]

    # ---------------------------------------------------------------- 相机 --
    def camera(self, t):
        shot, u = base.pick_shot(self.shots, t)
        eye, tgt = shot.camera(u, t)
        g = self.ground(eye[0], eye[2]) + 1.0
        if eye[1] < g:
            eye = (eye[0], g, eye[2])
        return eye, tgt

    # ---------------------------------------------------------------- 姿装 --
    def meshes(self, t):
        tq = Timeline.quantize(t, perf.ANIM_FPS)
        lx, lz = self._leo_xy(t)
        cx, cz = self._calf_xy(t)
        # 豹拉
        ahead = self._leo_xy(t + 0.5)
        leo_yaw = math.atan2(ahead[1] - lz, ahead[0] - lx)
        base.place_quad(self.leopard, lx, lz, leo_yaw, self.ground)
        leo_mode = 'run' if (450.0 <= t < 560.0 or t >= 560.0) else 'walk'
        # 牛来
        self.calf.origin = Vec3(cx, self.ground(cx, cz) + 0.61, cz)
        # 妈妈（营地）
        base.place_quad(self.mother, CAMP[0], CAMP[1], -1.6, self.ground)
        # 狼（初袭段 2 只在远处巡游）
        for i, w in enumerate(self.wolves[:2] if 450.0 <= t < 560.0 else []):
            ang = t * 0.3 + i * 2.1
            wx, wz = cx + math.cos(ang) * 18.0, cz + math.sin(ang) * 12.0
            base.place_quad(w, wx, wz, ang + math.pi, self.ground)
            self.cast.set_pose(f'wolf{i}', wx, w.origin.y, wz, w.yaw, mode='walk')
        # 背景牛群
        for i, q in enumerate(self.herd):
            hx, hz = CAMP[0] + 6.0 + (i % 3) * 3.0, CAMP[1] - 4.0 + (i // 3) * 3.0
            base.place_quad(q, hx, hz, -1.8, self.ground)
            self.cast.set_pose(f'herd{i}', hx, q.origin.y, hz, q.yaw, mode='stand')
        out = [self.terrain_md, self.river_md]
        out.extend(self.leopard.meshes(tq, mode=leo_mode, speed=1.1))
        out.extend(self.calf.meshes(tq))
        out.extend(self.mother.meshes(tq, mode='stand'))
        for w in (self.wolves[:2] if 540.0 <= t < 640.0 else []):
            out.extend(w.meshes(tq, mode='walk', speed=1.2))
        for q in self.herd:
            out.extend(q.meshes(tq, mode='stand'))
        self.cast.set_pose('niulai', cx, self.calf.origin.y, cz)
        self.cast.set_pose('baola', lx, self.leopard.origin.y, lz, leo_yaw,
                           mode=leo_mode)
        self.cast.set_pose('mother', CAMP[0], self.mother.origin.y, CAMP[1])
        return out

    def overlays(self, t):
        return [self._sub.at(t)]

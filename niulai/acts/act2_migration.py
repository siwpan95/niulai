# -*- coding: utf-8 -*-
"""第二幕 · 迁徙与过溪（660–1380s，12 min，白日）。

梦境开始：牛群收拾迁徙 -> 沙漠干渴 -> 河岸惧蛇 -> 慌乱过溪。
牛群 36 头（全哥口径 30-50）走 migration.herd_slots 编队；
蛇在河岸登场（原片心理阴影的源头）。

镜头表（act-local 秒，总 720s）：
  0–60    牛群集结，妈妈发令（全景）
  60–240  沙漠行军（跟踪镜头，牛来在队列中）
  240–330 干渴：小牛倒地，妈妈摘果（近景）
  330–420 河岸：牛来惧溪不敢过（近景）
  420–470 蛇逼近！牛来慌乱跃入溪中（名场面）
  470–720 全群过河，远望北岸歪脖子树（全景收尾）
"""
import math

from pyglet.math import Vec3

from .. import MASTER_SEED
from ..cast import perf
from ..cast.calf import Calf
from ..cast.quadruped import Quadruped
from ..cast.snake import Snake
from ..cast.specs import MOTHER_SPEC
from ..brains import migration
from ..brains.world import CastWorld
from ..scenery import desert
from ..timeline import Timeline
from . import base
from .subtitles import SubtitleOverlay, SubtitleTrack

ACT = 'act2_migration'
T_END = 720.0

SKY = (0.88, 0.86, 0.76)
FOG_K = 0.0110

# 迁徙进度 -> act-local 时间的映射（0-330s 行进，330-470 渡口，470-720 过河）
def _progress(t):
    if t < 330.0:
        return (t / 330.0) * 0.72
    if t < 470.0:
        return 0.72 + (t - 330.0) / 140.0 * 0.10
    return 0.82 + (t - 470.0) / 250.0 * 0.18

# 牛来在编队中的槽位（第 7 槽，妈妈身后）
CALF_SLOT = 6

LINES = (
    (6.0, 13.0, '牛妈妈', '没错，这里虽然秋黄未到。但是安全第一，大家收拾收拾，准备迁徙。'),
    (250.0, 257.0, '牛妈妈', '我给你们摘果子，吃完了，就有力气了！'),
    (336.0, 343.0, '牛来', '妈妈，我怕……'),
    (350.0, 357.0, '牛妈妈', '别怕，水不深。'),
    (440.0, 446.0, '牛妈妈', '跳过来，勇敢点！'),
    (448.0, 454.0, '牛来', '别急，我还是长大一点再跳吧。'),
)


class MigrationScene:
    """第二幕场景。"""

    NAME = ACT
    SKY = SKY
    FOG_K = FOG_K

    def __init__(self, seed=MASTER_SEED, grid=192):
        self.timeline = Timeline()
        self.T0 = self.timeline.act_bounds(self.NAME)[0]  # 幕起点（全片秒）
        self.seed = seed
        self.ground = lambda x, z: desert.height_at(x, z, seed)
        self.terrain_md, _ = desert.build_terrain(seed, grid, 1.0)
        self.river_md = desert.build_river(seed)
        # 牛群：36 头（ECS 实体 + Quadruped 镜像）
        self.herd = [Quadruped(MOTHER_SPEC if i == 0 else _COW_LIKE)
                     for i in range(migration.HERD_SIZE)]
        self.calf = Calf()
        self.mother = Quadruped(MOTHER_SPEC)
        # 蛇：南岸渡口旁游走（自定义路径；默认路径在长幕 t 下会飞界外）
        self.snake = Snake(ground=self.ground, path_fn=lambda t: (
            14.0 + 2.5 * math.sin(t * 0.5), 44.5 + 1.8 * math.sin(t * 0.9 + 1.2)))
        self.cast = CastWorld()
        for i in range(migration.HERD_SIZE):
            self.cast.register(f'herd{i}')
        self.cast.register('niulai')
        self.cast.register('mother')
        self.cast.register('snake')
        self._sub = SubtitleOverlay(SubtitleTrack(LINES))
        self.shots = self._build_shots()

    # ---------------------------------------------------------------- 编队 --
    def _formation(self, t):
        """t -> (slots, calf_xy, mother_xy, herd_progress)。"""
        prog = _progress(t)
        slots = migration.herd_slots(prog)
        # 牛来单独行动段（渡口戏）：422-470s 冲到最前
        if 415.0 <= t < 470.0:
            u = base.smooth((t - 415.0) / 55.0)
            cx = 12.0 + 3.0 * u
            cz = 48.0 + 1.0 * u
            calf_xy = (cx, cz)
        else:
            sx, sz, _ = slots[CALF_SLOT]
            calf_xy = (sx, sz)
        mx, mz, _ = slots[0]
        return slots, calf_xy, (mx, mz), prog

    # ---------------------------------------------------------------- 镜头 --
    def _build_shots(self):
        def cam_assembly(u, t):
            slots, calf_xy, mother_xy, _ = self._formation(t)
            c = (mother_xy[0], self.ground(*mother_xy) + 1.2, mother_xy[1])
            ang = 1.2 + 0.2 * math.sin(u * 0.07)
            return base.orbit_eye(c, ang, 22.0, 6.0), c

        def cam_march(u, t):
            slots, calf_xy, _, _ = self._formation(t)
            c = (calf_xy[0], self.ground(*calf_xy) + 1.0, calf_xy[1])
            # 侧后方跟踪
            ang = 2.6 + 0.3 * math.sin(u * 0.05)
            return base.orbit_eye(c, ang, 12.0, 3.6), c

        def cam_thirst(u, t):
            slots, calf_xy, mother_xy, _ = self._formation(t)
            c = (calf_xy[0], self.ground(*calf_xy) + 0.8, calf_xy[1])
            return base.orbit_eye(c, 0.7, 6.0, 1.6), c

        def cam_fear(u, t):
            slots, calf_xy, _, _ = self._formation(t)
            c = (calf_xy[0], self.ground(*calf_xy) + 0.8, calf_xy[1])
            return base.orbit_eye(c, 0.35 + 0.1 * math.sin(u * 0.3), 5.0, 1.2), c

        def cam_leap(u, t):
            # 名场面：蛇逼近 + 牛来跃溪 —— 蛇与牛来之间的过肩
            slots, calf_xy, _, _ = self._formation(t)
            sx, sz = self.snake.path(t)
            mid = ((calf_xy[0] + sx) / 2, self.ground(calf_xy[0], calf_xy[1]) + 1.0,
                   (calf_xy[1] + sz) / 2)
            ang = 0.5 + 0.4 * math.sin(u * 0.25)
            return base.orbit_eye(mid, ang, 8.0, 2.2), mid

        def cam_crossing(u, t):
            slots, calf_xy, _, _ = self._formation(t)
            c = (calf_xy[0], self.ground(*calf_xy) + 1.2, calf_xy[1])
            ang = -0.9 + 0.25 * math.sin(u * 0.06)
            return base.orbit_eye(c, ang, 26.0, 8.0), c

        return [
            base.Shot(0.0, 60.0, cam_assembly, '集结'),
            base.Shot(60.0, 240.0, cam_march, '沙漠行军'),
            base.Shot(240.0, 330.0, cam_thirst, '干渴'),
            base.Shot(330.0, 420.0, cam_fear, '河岸惧溪'),
            base.Shot(420.0, 470.0, cam_leap, '蛇逼跃溪'),
            base.Shot(470.0, T_END, cam_crossing, '全群过河'),
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
        slots, calf_xy, mother_xy, prog = self._formation(t)
        # 牛群（编队 + 步行）
        for i, q in enumerate(self.herd):
            x, z, yaw = slots[i]
            base.place_quad(q, x, z, yaw, self.ground)
            self.cast.set_pose(f'herd{i}', x, q.origin.y, z, yaw, mode='walk')
        # 妈妈（领队）
        base.place_quad(self.mother, mother_xy[0], mother_xy[1],
                        slots[0][2], self.ground)
        # 牛来：迁徙中步行；渡口畏惧时站立不动；跃溪时小跑
        if 415.0 <= t < 470.0:
            calf_mode = 'run' if t > 442.0 else 'stand'
        else:
            calf_mode = 'walk'
        self.calf.origin = Vec3(calf_xy[0],
                                self.ground(*calf_xy) + 0.61, calf_xy[1])
        # 蛇：330s 后在河岸游走
        out = [self.terrain_md, self.river_md]
        for q in self.herd:
            out.extend(q.meshes(tq, mode='walk', speed=0.8))
        out.extend(self.mother.meshes(tq, mode='walk', speed=0.8))
        out.extend(self.calf.meshes(tq))
        if 330.0 <= t < 500.0:
            out.extend(self.snake.meshes(tq))
            sx, sz = self.snake.path(t)
            self.cast.set_pose('snake', sx, self.ground(sx, sz) + 0.1, sz)
        self.cast.set_pose('niulai', calf_xy[0], self.calf.origin.y, calf_xy[1])
        self.cast.set_pose('mother', mother_xy[0], self.mother.origin.y,
                           mother_xy[1], self.mother.yaw, mode='walk')
        return out

    def overlays(self, t):
        return [self._sub.at(t)]


# 牛群普通个体规格（棕褐，无角小牛/母牛混合）
_COW_LIKE = {
    'body': (1.7, 0.74, 0.68), 'body_y': 1.30,
    'neck': (0.52, 0.40, 0.38), 'head': (0.50, 0.42, 0.40),
    'muzzle': (0.24, 0.24, 0.28), 'ear': (0.10, 0.20, 0.08),
    'horn': (0.09, 0.26, 0.09), 'horns': False,
    'leg': (0.16, 0.90, 0.16), 'leg_x': 0.66, 'leg_z': 0.28,
    'tail': (0.52, 0.07, 0.07),
    'colors': {'body': (0.50, 0.38, 0.28), 'head': (0.46, 0.35, 0.26),
               'leg': (0.40, 0.30, 0.22), 'horn': (0.7, 0.64, 0.52),
               'ear': (0.44, 0.33, 0.25)},
}

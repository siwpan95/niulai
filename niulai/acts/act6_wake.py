# -*- coding: utf-8 -*-
"""第六幕 · 梦醒而立（4080–4800s，12 min，清晨）。

原片结局：牛来猛然惊醒 —— 原地仍是那头刚出生、站不稳的小牛，云雀还在原位；
借着梦境的力量，牛来奋力站起，奔向牛群，见到父亲，得到族群认可；
曾经无法高飞的云雀，也终于展翅翱翔。

**全片眼（循环呼应）**：本幕开场与第一幕开场**同一构图**（机位/角色位置逐分量
复位）——直接 import act1 的常量与开场相机函数，测试断言两侧等价。
"""
import math

from pyglet.math import Vec3

from .. import MASTER_SEED
from ..cast import perf
from ..cast.calf import Calf
from ..cast.quadruped import Quadruped
from ..cast.specs import FATHER_SPEC
from ..cast.skylark import Skylark
from ..brains.world import CastWorld
from ..scenery import desert
from ..timeline import Timeline
from . import base
from .act1_stand import BIRD_AT, CALF_AT, HERD_AT, MOTHER_AT, StandScene
from .subtitles import SubtitleOverlay, SubtitleTrack

ACT = 'act6_wake'
T_END = 720.0

FATHER_AT = (78.0, -4.0)
SKY = (0.96, 0.84, 0.72)          # 与 act1 同一清晨
FOG_K = 0.0125

LINES = (
    (12.0, 19.0, '牛妈妈', '站起来，睁开眼睛，别睡觉！'),
    (66.0, 73.0, '牛妈妈', '今天就是昨天的将来。'),
    (150.0, 157.0, '牛来', '妈妈，我站起来了！'),
    (420.0, 427.0, '牛爸爸', '翅膀硬了，自然要高飞了。'),
    (560.0, 567.0, '牛爸爸', '好吧，你先来点爸爸的专属。'),
)


class WakeScene:
    """第六幕场景（开幕与 act1 同一构图）。"""

    NAME = ACT
    SKY = SKY
    FOG_K = FOG_K

    def __init__(self, seed=MASTER_SEED, grid=192):
        self.timeline = Timeline()
        self.T0 = self.timeline.act_bounds(self.NAME)[0]
        self.seed = seed
        self.ground = lambda x, z: desert.height_at(x, z, seed)
        self.terrain_md, _ = desert.build_terrain(seed, grid, 1.0)
        self.river_md = desert.build_river(seed)
        # 角色（位置 = act1 开场基准）
        from ..cast.specs import MOTHER_SPEC
        gy = self.ground(*CALF_AT)
        self.calf = Calf(origin=(CALF_AT[0], gy + 0.61, CALF_AT[1]), yaw=2.55)
        self.mother = Quadruped(MOTHER_SPEC)
        base.place_quad(self.mother, *MOTHER_AT, yaw=-2.4, ground=self.ground)
        self.bird = Skylark()
        self.bird.origin = Vec3(BIRD_AT[0], self.ground(*BIRD_AT) + 0.55,
                                BIRD_AT[1])
        self.bird.yaw = 1.2
        self.father = Quadruped(FATHER_SPEC)
        base.place_quad(self.father, *FATHER_AT, yaw=-1.9, ground=self.ground)
        self.herd = [Quadruped(FATHER_SPEC) for _ in range(4)]
        for i, q in enumerate(self.herd):
            base.place_quad(q, FATHER_AT[0] - (i % 2) * 4.0,
                            FATHER_AT[1] + (i // 2) * 3.5, yaw=-1.8,
                            ground=self.ground)
        self.cast = CastWorld()
        for who in ('niulai', 'mother', 'yundi', 'father'):
            self.cast.register(who)
        for i in range(4):
            self.cast.register(f'herd{i}')
        self._sub = SubtitleOverlay(SubtitleTrack(LINES))
        # 开场相机 = act1 开场相机的同一函数（循环复位）
        self._ref = StandScene(seed=seed, grid=64)
        self.shots = self._build_shots()

    # ---------------------------------------------------------------- 走位 --
    def _rise_u(self, t):
        """奋力站起进度：60s 开始，150s 到位（前 6 秒蓄势、后猛起）。"""
        if t < 60.0:
            return 0.0
        if t > 150.0:
            return 1.0
        u = (t - 60.0) / 90.0
        return u * u * (3.0 - 2.0 * u)

    def _calf_xy(self, t):
        """牛来位置：原地（0-150s）-> 奔向牛群（150-420s）-> 父亲身旁（420s+）。"""
        if t < 150.0:
            return CALF_AT
        if t < 420.0:
            u = base.smooth((t - 150.0) / 270.0)
            return (CALF_AT[0] + (FATHER_AT[0] - 3.0 - CALF_AT[0]) * u,
                    CALF_AT[1] + (FATHER_AT[1] + 2.0 - CALF_AT[1]) * u)
        return (FATHER_AT[0] - 3.0, FATHER_AT[1] + 2.0)

    # ---------------------------------------------------------------- 镜头 --
    def _build_shots(self):
        calf0 = (CALF_AT[0], self.ground(*CALF_AT) + 0.9, CALF_AT[1])

        def cam_wake(u, t):
            # **与 act1 开场同一机位**（同函数同参数）
            ang = 2.2 + 0.25 * math.sin(u * 0.10)
            return base.orbit_eye(calf0, ang, 13.0, 4.2), calf0

        def cam_rise(u, t):
            # 奋力站起：贴近的低机位，随起身缓慢上摇
            u0 = self._rise_u(t)
            cx, cz = self._calf_xy(t)
            c = (cx, self.ground(cx, cz) + 0.5 + 0.55 * u0, cz)
            ang = 0.9 + 0.15 * math.sin(u * 0.2)
            return base.orbit_eye(c, ang, 5.0 + 1.5 * u0, 1.1 + 1.4 * u0), c

        def cam_run(u, t):
            cx, cz = self._calf_xy(t)
            c = (cx, self.ground(cx, cz) + 0.9, cz)
            ang = 2.6 + 0.3 * math.sin(u * 0.05)
            return base.orbit_eye(c, ang, 10.0, 3.2), c

        def cam_fly(u, t):
            # 云雀高飞：仰拍（镜头随鸟升起，但保持牛群在画面下缘）
            uf = base.smooth(max(0.0, (t - 420.0)) / 140.0)
            bx = BIRD_AT[0] + 8.0 * math.sin(uf * 3.0)
            bz = BIRD_AT[1] - 6.0 * uf
            by = self.ground(BIRD_AT[0], BIRD_AT[1]) + 0.6 + 10.0 * uf
            c = (bx, by, bz)
            return base.orbit_eye(c, 1.2, 8.0, 1.2), c

        def cam_reunion(u, t):
            fx, fz = FATHER_AT
            c = (fx - 1.0, self.ground(fx, fz) + 1.3, fz + 1.0)
            ang = -0.8 + 0.2 * math.sin(u * 0.06)
            return base.orbit_eye(c, ang, 12.0, 3.6), c

        return [
            base.Shot(0.0, 60.0, cam_wake, '梦醒（act1 同构图）'),
            base.Shot(60.0, 150.0, cam_rise, '奋力站起'),
            base.Shot(150.0, 420.0, cam_run, '奔向牛群'),
            base.Shot(420.0, 560.0, cam_fly, '云雀高飞'),
            base.Shot(560.0, T_END, cam_reunion, '族群认可'),
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
        gy = self.ground(*CALF_AT)
        cx, cz = self._calf_xy(t)
        u = self._rise_u(t)
        # 牛来：伏地 -> 奋力站起 -> 站稳（抬升/腿拉伸都在 calf._pose_rise 内；
        # origin 恒为 ground+0.61，蹄的绝对高度由腿拉伸守恒）
        self.calf.origin = Vec3(cx, self.ground(cx, cz) + 0.61, cz)
        self.calf.scale = 1.0 + 0.12 * u
        calf_mode = 'rise' if 60.0 <= t < 400.0 else ('stand' if u > 0 else 'lie')
        if calf_mode == 'stand':
            # 站稳后 borrow Quadruped 会超规格；保持 rise 满进度即"站住了"
            calf_mode = 'rise'
        # 妈妈：始终在旁（act1 位置）；150s 后目送
        base.place_quad(self.mother, *MOTHER_AT, yaw=-2.4, ground=self.ground)
        # 云雀：420s 后高飞（沿 cam_fly 同轨迹）
        if t < 420.0:
            self.bird.origin = Vec3(BIRD_AT[0], self.ground(*BIRD_AT) + 0.55,
                                    BIRD_AT[1])
            self.bird.yaw = 1.2
        else:
            uf = base.smooth((t - 420.0) / 140.0)
            self.bird.origin = Vec3(BIRD_AT[0] + 8.0 * math.sin(uf * 3.0),
                                    self.ground(*BIRD_AT) + 0.6 + 10.0 * uf,
                                    BIRD_AT[1] - 6.0 * uf)
            self.bird.yaw = -0.4
        out = [self.terrain_md, self.river_md]
        out.extend(self.mother.meshes(tq, mode='stand'))
        out.extend(self.calf.meshes(tq, mode=calf_mode, rise_u=u))
        out.extend(self.bird.meshes(tq))
        out.extend(self.father.meshes(tq, mode='stand'))
        for q in self.herd:
            out.extend(q.meshes(tq, mode='stand'))
        self.cast.set_pose('niulai', cx, self.calf.origin.y, cz)
        self.cast.set_pose('mother', MOTHER_AT[0], self.mother.origin.y,
                           MOTHER_AT[1], self.mother.yaw, mode='stand')
        self.cast.set_pose('yundi', self.bird.origin.x, self.bird.origin.y,
                           self.bird.origin.z, self.bird.yaw)
        self.cast.set_pose('father', FATHER_AT[0], self.father.origin.y,
                           FATHER_AT[1], self.father.yaw, mode='stand')
        return out

    def overlays(self, t):
        return [self._sub.at(t)]

# -*- coding: utf-8 -*-
"""第一幕 · 站不起来（360–660s，5 min，清晨）。

现实层：绿地清晨，初生牛犊双腿无力；牛妈妈催促；云玎（翅伤）落在一旁。
本幕与序幕同场地同构图基准（第六幕梦醒将精确复位至此）。

镜头表（act-local 秒）：
  0–45    全景：妈妈低头看牛来，长镜头
  45–100  近景：牛来伏地挣扎（侧摇/抬头/蹬后腿）
  100–140 云玎近景：伤翅扑腾，牛来侧目
  140–190 双人镜头：妈妈+牛来+云玎，日出色温
  190–300 妈妈起身走向牛群，牛来遥望（梦境过渡白闪起）
"""
import math

from pyglet.math import Vec3

from .. import MASTER_SEED
from ..cast import perf
from ..cast.calf import Calf
from ..cast.quadruped import Quadruped
from ..cast.skylark import Skylark
from ..cast.specs import MOTHER_SPEC
from ..brains.world import CastWorld
from ..scenery import desert
from ..timeline import Timeline
from . import base
from .subtitles import SubtitleOverlay, SubtitleTrack

ACT = 'act1_stand'
T_END = 300.0

# 场景地理（与序幕一致：绿地 = 牛来家）
CALF_AT = (60.0, -14.0)
MOTHER_AT = (66.0, -12.0)
BIRD_AT = (57.5, -10.5)
HERD_AT = (78.0, -6.0)

SKY = (0.96, 0.84, 0.72)          # 清晨暖霾
FOG_K = 0.0125

LINES = (
    (2.0, 8.0, '牛妈妈', '我的孩子，你来了，欢迎你，牛来。'),
    (20.0, 26.0, '牛妈妈', '站起来，睁开眼睛，别睡觉！'),
    (48.0, 54.0, '牛来', '妈妈，我饿了。'),
    (56.0, 62.0, '牛妈妈', '不是刚吃过吗？'),
    (70.0, 76.0, '牛妈妈', '走，跟妈妈锻炼去——吃饱了再去不好吗？'),
    (102.0, 108.0, '牛妈妈', '别担心，云玎，再调养调养就能高飞了。'),
    (146.0, 153.0, '牛妈妈', '长大是将来的事。'),
    (154.0, 161.0, '牛来', '将来有多远？'),
    (162.0, 169.0, '牛妈妈', '今天就是昨天的将来。'),
    (196.0, 203.0, '牛妈妈', '你以后会做大事情的，只是你现在眼界还不够开阔。'),
)


class StandScene:
    """第一幕场景。"""

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
        # 角色
        gy = self.ground(*CALF_AT)
        self.calf = Calf(origin=(CALF_AT[0], gy + 0.61, CALF_AT[1]), yaw=2.55)
        self.mother = Quadruped(MOTHER_SPEC)
        base.place_quad(self.mother, *MOTHER_AT, yaw=-2.4, ground=self.ground)
        self.bird = Skylark()
        self.bird.origin = Vec3(BIRD_AT[0], self.ground(*BIRD_AT) + 0.55,
                                BIRD_AT[1])
        self.bird.yaw = 1.2
        # 背景牛群（远处剪影：3 头静态）
        self.herd = [Quadruped(MOTHER_SPEC) for _ in range(3)]
        for i, q in enumerate(self.herd):
            base.place_quad(q, HERD_AT[0] + i * 3.2, HERD_AT[1] + (i % 2) * 2.4,
                            yaw=-1.9, ground=self.ground)
        # ECS 账本
        self.cast = CastWorld()
        self.cast.register('niulai', *CALF_AT)
        self.cast.register('mother', *MOTHER_AT)
        self.cast.register('yundi', *BIRD_AT)
        for i in range(3):
            self.cast.register(f'herd{i}', HERD_AT[0] + i * 3.2,
                               HERD_AT[1] + (i % 2) * 2.4)
        # 字幕
        self._sub = SubtitleOverlay(SubtitleTrack(LINES))
        self.shots = self._build_shots()

    # ---------------------------------------------------------------- 镜头 --
    def _build_shots(self):
        calf = (CALF_AT[0], self.ground(*CALF_AT) + 0.9, CALF_AT[1])
        mother = (MOTHER_AT[0], self.ground(*MOTHER_AT) + 1.1, MOTHER_AT[1])
        bird = (BIRD_AT[0], self.ground(*BIRD_AT) + 0.8, BIRD_AT[1])

        def cam_wide(u, t):
            # 全景：母牛低头看牛来，缓慢右摇
            ang = 2.2 + 0.25 * math.sin(u * 0.10)
            return base.orbit_eye(calf, ang, 13.0, 4.2), calf

        def cam_calf(u, t):
            # 近景：贴地机位推近挣扎的牛来
            d = 6.5 - 1.2 * base.smooth(u / 55.0)
            return base.orbit_eye(calf, 0.9 + 0.15 * math.sin(u * 0.2), d, 1.1), calf

        def cam_bird(u, t):
            return base.orbit_eye(bird, 3.6, 3.4, 0.9), bird

        def cam_two(u, t):
            mid = ((calf[0] + mother[0]) / 2, (calf[1] + mother[1]) / 2 + 0.3,
                   (calf[2] + mother[2]) / 2)
            ang = -0.7 + 0.3 * math.sin(u * 0.08)
            return base.orbit_eye(mid, ang, 11.0, 3.4), mid

        def cam_leave(u, t):
            # 妈妈走向牛群：牛来留在前景，母牛远去
            return base.orbit_eye(calf, 1.15, 7.5, 1.6), calf

        return [
            base.Shot(0.0, 45.0, cam_wide, '全景：妈妈与牛来'),
            base.Shot(45.0, 100.0, cam_calf, '近景：站不起来'),
            base.Shot(100.0, 140.0, cam_bird, '近景：云玎伤翅'),
            base.Shot(140.0, 190.0, cam_two, '双人：日出对白'),
            base.Shot(190.0, T_END, cam_leave, '妈妈离去，梦境过渡'),
        ]

    # ---------------------------------------------------------------- 相机 --
    def camera(self, t):
        shot, u = base.pick_shot(self.shots, t)
        eye, tgt = shot.camera(u, t)
        # 防穿地
        g = self.ground(eye[0], eye[2]) + 1.0
        if eye[1] < g:
            eye = (eye[0], g, eye[2])
        return eye, tgt

    # ---------------------------------------------------------------- 姿装 --
    def meshes(self, t):
        tq = Timeline.quantize(t, perf.ANIM_FPS)
        gy = self.ground(*CALF_AT)
        # 牛来：始终伏地挣扎（本幕不站起来）
        self.calf.origin = Vec3(CALF_AT[0], gy + 0.61, CALF_AT[1])
        # 妈妈：190s 后起身走向牛群
        if t < 190.0:
            self.mother.pose_mode = 'stand'
            base.place_quad(self.mother, *MOTHER_AT, yaw=-2.4, ground=self.ground)
        else:
            u = base.smooth((t - 190.0) / 60.0)
            mx = MOTHER_AT[0] + (HERD_AT[0] - MOTHER_AT[0]) * u
            mz = MOTHER_AT[1] + (HERD_AT[1] - MOTHER_AT[1]) * u
            base.place_quad(self.mother, mx, mz, yaw=-1.9, ground=self.ground)
            self.mother.pose_mode = 'walk'
        # 云玎：伤翅伏地，偶有扑腾（翅膀小角度）
        self.bird.origin = Vec3(BIRD_AT[0], self.ground(*BIRD_AT) + 0.5,
                                BIRD_AT[1])
        out = [self.terrain_md, self.river_md]
        out.extend(self.mother.meshes(tq, mode=self.mother.pose_mode, speed=0.7))
        out.extend(self.calf.meshes(tq))
        out.extend(self.bird.meshes(tq))
        for q in self.herd:
            out.extend(q.meshes(tq, mode='stand'))
        # ECS 镜像（姿态 -> Transform）
        self.cast.set_pose('niulai', CALF_AT[0], gy + 0.61, CALF_AT[1])
        self.cast.set_pose('mother', self.mother.origin.x, self.mother.origin.y,
                           self.mother.origin.z, self.mother.yaw,
                           mode=self.mother.pose_mode)
        self.cast.set_pose('yundi', BIRD_AT[0], self.ground(*BIRD_AT) + 0.5,
                           BIRD_AT[1])
        return out

    def overlays(self, t):
        return [self._sub.at(t)]

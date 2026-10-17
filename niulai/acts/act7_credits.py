# -*- coding: utf-8 -*-
"""第七幕 · 片尾（4800–5160s，6 min，金色黄昏）。

大团圆定格：牛来一家（爸爸/妈妈/牛来）+ 牛群 + 云玎在高坡上；
字幕走 staff（**明确标注同人复刻属性与原作信息**）；片尾曲气质民谣
（致敬原片片尾曲《雨后清风有香》——孙丽芳词曲唱；此处为程序化致敬，
非原曲）。
"""
import math

from pyglet.math import Vec3

from .. import MASTER_SEED
from ..cast import perf
from ..cast.quadruped import Quadruped
from ..cast.specs import ADULT_NIULAI_SPEC, FATHER_SPEC, MOTHER_SPEC
from ..cast.skylark import Skylark
from ..brains.world import CastWorld
from ..scenery import desert, tree as tree_mod
from ..timeline import Timeline
from . import base
from .subtitles import SubtitleOverlay, SubtitleTrack

ACT = 'act7_credits'
T_END = 360.0

RISE_AT = (40.0, 0.0)             # 团圆高坡
TREE_AT = (34.0, 8.0)
SKY = (0.93, 0.76, 0.55)          # 金色黄昏
FOG_K = 0.0120

# 字幕轨 = 片尾 staff（同人复刻声明 + 原作信息 + 本工程信息）
LINES = (
    (4.0, 14.0, '', '—— 同人学习性复刻 · 不商用 · 不传播成片 ——'),
    (16.0, 26.0, '', '复刻自动画电影《牛来》'),
    (28.0, 38.0, '', '导演 信雨萌 · 编剧 孙丽芳 · 片尾曲《雨后清风有香》'),
    (40.0, 50.0, '', '（本片为程序化致敬，非原片素材）'),
    (52.0, 64.0, '', '引擎复刻：world3d(3dworld) 渲染演出 × allin-engine 逻辑智能'),
    (66.0, 78.0, '', 'niulai 工程 · siwpan · MIT'),
    (80.0, 92.0, '', '程序化场景/角色/配乐 · 零外部素材 · 86 分钟全片'),
    (96.0, 120.0, '', '牛来，终将抵达。'),
)


class CreditsScene:
    """第七幕场景。"""

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
        self.tree_md = tree_mod.build_crooked_tree(TREE_AT[0], TREE_AT[1],
                                                   self.ground, seed)
        # 一家三口 + 牛群 + 云雀
        self.niulai = Quadruped(ADULT_NIULAI_SPEC)
        self.father = Quadruped(FATHER_SPEC)
        self.mother = Quadruped(MOTHER_SPEC)
        self.bird = Skylark()
        self.herd = [Quadruped(MOTHER_SPEC) for _ in range(8)]
        self.cast = CastWorld()
        for who in ('niulai', 'father', 'mother', 'yundi'):
            self.cast.register(who)
        for i in range(8):
            self.cast.register(f'herd{i}')
        self._sub = SubtitleOverlay(SubtitleTrack(LINES, font_size=30))
        self.shots = self._build_shots()
        self.use_instancing = True     # 群体戏 GPU 实例化（等价性测试可关）

    def _layout(self):
        """家庭布局（纯函数，无时间依赖 —— 定格）。"""
        gx, gz = RISE_AT
        return {
            'niulai': (gx + 1.5, gz + 1.0),
            'father': (gx - 2.5, gz - 1.0),
            'mother': (gx + 0.5, gz - 2.5),
            'bird': (gx + 6.0, gz + 4.0),
        }

    # ---------------------------------------------------------------- 镜头 --
    def _build_shots(self):
        lay = self._layout()

        def cam_wide(u, t):
            c = (RISE_AT[0], self.ground(*RISE_AT) + 2.0, RISE_AT[1])
            ang = 0.9 + 0.18 * math.sin(u * 0.05)
            return base.orbit_eye(c, ang, 20.0, 5.5), c

        def cam_family(u, t):
            c = (lay['niulai'][0], self.ground(*lay['niulai']) + 1.6,
                 lay['niulai'][1])
            ang = 1.6 + 0.2 * math.sin(u * 0.06)
            return base.orbit_eye(c, ang, 11.0, 3.2), c

        def cam_herd(u, t):
            c = (RISE_AT[0] - 6.0,
                 self.ground(RISE_AT[0] - 6.0, RISE_AT[1]) + 1.8,
                 RISE_AT[1] + 6.0)
            ang = -0.5 + 0.22 * math.sin(u * 0.05)
            return base.orbit_eye(c, ang, 16.0, 4.5), c

        def cam_finale(u, t):
            # 终景：拉远大全景（云雀入画）
            c = (RISE_AT[0], self.ground(*RISE_AT) + 2.5, RISE_AT[1])
            ang = 0.7 + 0.12 * math.sin(u * 0.04)
            return base.orbit_eye(c, ang, 30.0 + 8.0 * u, 9.0), c

        return [
            base.Shot(0.0, 90.0, cam_wide, '团圆大全景'),
            base.Shot(90.0, 180.0, cam_family, '一家三口'),
            base.Shot(180.0, 260.0, cam_herd, '牛群'),
            base.Shot(260.0, T_END, cam_finale, '终景拉远'),
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
        lay = self._layout()
        # 一家三口（站立，呼吸）
        base.place_quad(self.niulai, *lay['niulai'], yaw=-2.6,
                        ground=self.ground)
        base.place_quad(self.father, *lay['father'], yaw=-2.4,
                        ground=self.ground)
        base.place_quad(self.mother, *lay['mother'], yaw=-2.7,
                        ground=self.ground)
        # 牛群环绕高坡（instancing 开时由 crowd() 画）
        if not self.use_instancing:
            for i, q in enumerate(self.herd):
                ang = (i / len(self.herd)) * math.tau
                hx = RISE_AT[0] + math.cos(ang) * 9.0
                hz = RISE_AT[1] + math.sin(ang) * 7.0
                base.place_quad(q, hx, hz, -1.8, ground=self.ground)
                self.cast.set_pose(f'herd{i}', hx, q.origin.y, hz, q.yaw,
                                   mode='stand')
        # 云雀：终景前飞入画面（260s 后盘旋升高）
        bx, bz = lay['bird']
        if t < 260.0:
            by = self.ground(bx, bz) + 3.0
        else:
            u = base.smooth((t - 260.0) / 100.0)
            by = self.ground(bx, bz) + 3.0 + 5.0 * u
            bx += 3.0 * math.sin(t * 0.4)
        self.bird.origin = Vec3(bx, by, bz)
        self.bird.yaw = -0.3
        out = [self.terrain_md, self.river_md, self.tree_md]
        out.extend(self.father.meshes(tq, mode='stand'))
        out.extend(self.mother.meshes(tq, mode='stand'))
        out.extend(self.niulai.meshes(tq, mode='stand'))
        out.extend(self.bird.meshes(tq))
        if not self.use_instancing:
            for q in self.herd:
                out.extend(q.meshes(tq, mode='stand'))
        self.cast.set_pose('niulai', lay['niulai'][0], self.niulai.origin.y,
                           lay['niulai'][1])
        self.cast.set_pose('father', lay['father'][0], self.father.origin.y,
                           lay['father'][1])
        self.cast.set_pose('mother', lay['mother'][0], self.mother.origin.y,
                           lay['mother'][1])
        self.cast.set_pose('yundi', bx, by, bz)
        return out

    def crowd(self, t):
        """群体戏实例化：环绕牛群（定格场景，姿态恒定）。"""
        if not self.use_instancing:
            return None
        tq = Timeline.quantize(t, perf.ANIM_FPS)
        pose = self.herd[0].meshes_identity(tq, mode='stand')
        bases = []
        for i, q in enumerate(self.herd):
            ang = (i / len(self.herd)) * math.tau
            hx = RISE_AT[0] + math.cos(ang) * 9.0
            hz = RISE_AT[1] + math.sin(ang) * 7.0
            base.place_quad(q, hx, hz, -1.8, ground=self.ground)
            bases.append(tuple(q._base_matrix()))
            self.cast.set_pose(f'herd{i}', hx, q.origin.y, hz, q.yaw,
                               mode='stand')
        return [(pose, bases)]

    def overlays(self, t):
        return [self._sub.at(t)]

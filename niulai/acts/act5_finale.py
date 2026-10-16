# -*- coding: utf-8 -*-
"""第五幕 · 传承与决战（3180–4080s，15 min，昼夜推进）。

原片后段：岁月更迭，牛来与豹拉长大 -> 重回母亲牺牲之地 -> 猛兽再来，
豹拉复刻牛妈妈的抉择断后 -> 盗猎车辆出现，牛来战吼、以自己为诱饵引开危险。

本幕是**大气系统**的首秀：天空/雾/色调随幕内时间从白昼推到黄昏、入夜、黎明。

镜头表（act-local 秒，总 900s）：
  0–150    岁月更迭：牛群在新草地吃草，昼夜快切（atmosphere 循环）
  150–330  长大：成年牛来与成年豹拉并肩（成长蒙太奇）
  330–480  重回牺牲之地：歪脖子树下，回忆（静默，风）
  480–660  豹拉断后：狼群再来，豹拉说出当年妈妈的嘱托，引狼远去
  660–900  决战：盗猎车出现，牛来战吼，以自身为诱饵引开
"""
import math

from pyglet.math import Vec3

from .. import MASTER_SEED
from ..cast import perf
from ..cast.quadruped import Quadruped
from ..cast.humans import Poacher, PoacherTruck
from ..cast.specs import (ADULT_NIULAI_SPEC, LEOPARD_SPEC, MOTHER_SPEC,
                          WOLF_SPEC)
from ..cast.skylark import Skylark
from ..brains.world import CastState, CastWorld
from ..brains import wolves
from ..scenery import desert, tree as tree_mod
from ..timeline import Timeline
from . import base
from .subtitles import SubtitleOverlay, SubtitleTrack

ACT = 'act5_finale'
T_END = 900.0

TREE_AT = (10.0, 64.0)
GROVE_AT = (-46.0, 6.0)          # 新家园小树林
CAMP = (0.0, 30.0)

# 大气关键帧（幕内秒 -> (sky, fog_k, tint)）：白昼 -> 黄昏 -> 夜 -> 黎明
ATMOS_KEYS = (
    (0.0, (0.86, 0.85, 0.76), 0.0110, (1.00, 1.00, 1.00)),      # 白昼
    (150.0, (0.90, 0.74, 0.58), 0.0125, (1.00, 0.96, 0.92)),    # 黄昏
    (330.0, (0.16, 0.18, 0.26), 0.0160, (0.60, 0.64, 0.80)),    # 夜（重回牺牲之地）
    (480.0, (0.12, 0.14, 0.22), 0.0165, (0.55, 0.60, 0.78)),    # 深夜（豹拉断后）
    (660.0, (0.20, 0.22, 0.30), 0.0155, (0.62, 0.66, 0.82)),    # 战前（将晓）
    (900.0, (0.85, 0.72, 0.58), 0.0120, (1.00, 0.95, 0.88)),    # 黎明（决战生晨）
)

LINES = (
    (30.0, 38.0, '牛爸爸', '翅膀硬了，自然要高飞了。'),
    (500.0, 508.0, '豹拉', '相信我，我还会在你身后出现的。'),
    (670.0, 678.0, '牛来', '时间会证明牛来的。'),
    (760.0, 768.0, '牛来', '打跑它们！好嘞！'),
)


def _atmosphere(t):
    """t -> (sky, fog_k, tint)：关键帧线性插值（确定性）。"""
    if t <= ATMOS_KEYS[0][0]:
        return ATMOS_KEYS[0][1], ATMOS_KEYS[0][2], ATMOS_KEYS[0][3]
    for i in range(len(ATMOS_KEYS) - 1):
        t0, sky0, fk0, tn0 = ATMOS_KEYS[i]
        t1, sky1, fk1, tn1 = ATMOS_KEYS[i + 1]
        if t0 <= t < t1:
            u = (t - t0) / (t1 - t0)
            sky = tuple(sky0[k] + (sky1[k] - sky0[k]) * u for k in range(3))
            tn = tuple(tn0[k] + (tn1[k] - tn0[k]) * u for k in range(3))
            return sky, fk0 + (fk1 - fk0) * u, tn
    return ATMOS_KEYS[-1][1], ATMOS_KEYS[-1][2], ATMOS_KEYS[-1][3]


class FinaleScene:
    """第五幕场景。"""

    NAME = ACT
    SKY = ATMOS_KEYS[0][1]
    FOG_K = ATMOS_KEYS[0][2]

    def __init__(self, seed=MASTER_SEED, grid=192):
        self.timeline = Timeline()
        self.T0 = self.timeline.act_bounds(self.NAME)[0]
        self.seed = seed
        self.ground = lambda x, z: desert.height_at(x, z, seed)
        self.terrain_md, _ = desert.build_terrain(seed, grid, 1.0)
        self.river_md = desert.build_river(seed)
        self.tree_md = tree_mod.build_crooked_tree(TREE_AT[0], TREE_AT[1],
                                                   self.ground, seed)
        # 新家园小树林（复用歪脖子树建造器，位置/角度略异）
        self.grove = [tree_mod.build_crooked_tree(
            GROVE_AT[0] + i * 7.0, GROVE_AT[1] + (i % 3) * 9.0, self.ground,
            seed + 100 + i) for i in range(5)]
        # 角色
        self.niulai = Quadruped(ADULT_NIULAI_SPEC)
        self.baola = Quadruped(LEOPARD_SPEC)
        self.father = Quadruped(MOTHER_SPEC)      # 体型近似即可（P2 可细化）
        self.mother_tree = None
        self.leopard_adult = Quadruped(LEOPARD_SPEC)
        self.pack = [Quadruped(WOLF_SPEC) for _ in range(wolves.WOLF_COUNT)]
        self.poacher = Poacher()
        self.truck = PoacherTruck()
        self.bird = Skylark()
        self.cast = CastWorld()
        for who in ('niulai', 'baola', 'father', 'poacher'):
            self.cast.register(who)
        for i in range(wolves.WOLF_COUNT):
            self.cast.register(f'wolf{i}')
        self._sub = SubtitleOverlay(SubtitleTrack(LINES))
        self.shots = self._build_shots()

    def atmosphere(self, t):
        return _atmosphere(t)

    # ---------------------------------------------------------------- 走位 --
    def _niulai_xy(self, t):
        if t < 330.0:
            u = base.smooth(t / 330.0)
            return (CAMP[0] - 6.0 + 3.0 * math.sin(u * 4.0),
                    CAMP[1] + 4.0 * u)
        if t < 660.0:
            u = base.smooth((t - 330.0) / 330.0)
            return (CAMP[0] - 6.0 + (TREE_AT[0] + 5.0 - CAMP[0] + 6.0) * u,
                    CAMP[1] + 4.0 + (TREE_AT[1] - 4.0 - CAMP[1] - 4.0) * u)
        # 660s 后：战吼引开盗猎车 —— 向西南方诱引
        u = base.smooth((t - 660.0) / 240.0)
        return (TREE_AT[0] + 5.0 + 22.0 * u, TREE_AT[1] - 4.0 + 16.0 * u)

    def _baola_xy(self, t):
        if t < 480.0:
            return (CAMP[0] - 2.0, CAMP[1] + 6.0)
        if t < 660.0:
            u = base.smooth((t - 480.0) / 180.0)
            return (CAMP[0] - 2.0 + (TREE_AT[0] + 8.0 - CAMP[0] + 2.0) * u,
                    CAMP[1] + 6.0 + (TREE_AT[1] + 2.0 - CAMP[1] - 6.0) * u)
        # 断后：引狼向西北远去
        u = base.smooth((t - 660.0) / 240.0)
        return (TREE_AT[0] + 8.0 - 26.0 * u, TREE_AT[1] + 2.0 + 10.0 * u)

    def _truck_xy(self, t):
        """盗猎车：660s 后从北面登场，被牛来引向西南。"""
        if t < 660.0:
            return None
        u = base.smooth((t - 660.0) / 240.0)
        x = TREE_AT[0] + 30.0 - 30.0 * u
        z = TREE_AT[1] + 26.0 - 26.0 * u
        return (x, z)

    # ---------------------------------------------------------------- 镜头 --
    def _build_shots(self):
        def cam_years(u, t):
            # 岁月更迭：营地全景，缓慢环绕
            c = (CAMP[0], self.ground(*CAMP) + 1.5, CAMP[1])
            ang = 0.8 + 0.4 * math.sin(u * 0.04)
            return base.orbit_eye(c, ang, 26.0, 7.0), c

        def cam_grow(u, t):
            nx, nz = self._niulai_xy(t)
            c = (nx, self.ground(nx, nz) + 1.2, nz)
            ang = 1.9 + 0.3 * math.sin(u * 0.07)
            return base.orbit_eye(c, ang, 10.0, 3.0), c

        def cam_memorial(u, t):
            c = (TREE_AT[0], self.ground(*TREE_AT) + 4.0, TREE_AT[1])
            ang = 0.6 + 0.25 * math.sin(u * 0.05)
            return base.orbit_eye(c, ang, 14.0, 3.5), c

        def cam_leopard_last(u, t):
            bx, bz = self._baola_xy(t)
            c = (bx, self.ground(bx, bz) + 1.0, bz)
            ang = 2.7 + 0.2 * math.sin(u * 0.07)
            return base.orbit_eye(c, ang, 8.0, 2.4), c

        def cam_standoff(u, t):
            nx, nz = self._niulai_xy(t)
            truck = self._truck_xy(t)
            if truck:
                mid = ((nx + truck[0]) / 2, self.ground(nx, nz) + 1.2,
                       (nz + truck[1]) / 2)
            else:
                mid = (nx, self.ground(nx, nz) + 1.2, nz)
            ang = 0.5 + 0.35 * math.sin(u * 0.08)
            return base.orbit_eye(mid, ang, 16.0, 4.5), mid

        return [
            base.Shot(0.0, 150.0, cam_years, '岁月更迭'),
            base.Shot(150.0, 330.0, cam_grow, '长大'),
            base.Shot(330.0, 480.0, cam_memorial, '重回牺牲之地'),
            base.Shot(480.0, 660.0, cam_leopard_last, '豹拉断后'),
            base.Shot(660.0, T_END, cam_standoff, '决战'),
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
        nx, nz = self._niulai_xy(t)
        bx, bz = self._baola_xy(t)
        truck = self._truck_xy(t)
        # 牛来（成年）
        ahead = self._niulai_xy(t + 0.5)
        nyaw = math.atan2(ahead[1] - nz, ahead[0] - nx)
        base.place_quad(self.niulai, nx, nz, nyaw, self.ground)
        nmode = 'walk' if t < 660.0 else 'run'
        # 豹拉（480s 后引狼奔逃）
        bahead = self._baola_xy(t + 0.5)
        byaw = math.atan2(bahead[1] - bz, bahead[0] - bx)
        base.place_quad(self.baola, bx, bz, byaw, self.ground)
        bmode = 'walk' if t < 480.0 else 'run'
        # 狼群（480s 后追豹拉；之前在北面远处）
        pack = wolves.pack_positions(t, center=(TREE_AT[0] + 8.0, TREE_AT[1] + 2.0))
        if t >= 480.0:
            for i, (_, _, yaw, _) in enumerate(pack):
                ang = (i / len(pack)) * math.tau
                pack[i] = (bx + math.cos(ang) * 7.0, bz + math.sin(ang) * 6.0,
                           yaw, 'run')
        # 盗猎车 + 猎人（660s 后）
        if truck:
            th_ahead = self._truck_xy(t + 0.5)
            tyaw = math.atan2(th_ahead[1] - truck[1], th_ahead[0] - truck[0])
            self.truck.origin = Vec3(truck[0], self.ground(*truck) + 0.38, truck[1])
            self.truck.yaw = -tyaw
            self.poacher.origin = Vec3(truck[0], self.ground(*truck) + 0.62,
                                       truck[1])
            self.poacher.yaw = -tyaw
        out = [self.terrain_md, self.river_md, self.tree_md]
        out.extend(self.grove)
        out.extend(self.niulai.meshes(tq, mode=nmode, speed=1.1))
        out.extend(self.baola.meshes(tq, mode=bmode, speed=1.3))
        out.extend(self.father.meshes(tq, mode='stand'))
        for i, (wx, wz, wyaw, wmode) in enumerate(pack):
            if t >= 480.0:
                base.place_quad(self.pack[i], wx, wz, wyaw, self.ground)
                out.extend(self.pack[i].meshes(tq, mode=wmode, speed=1.4))
                self.cast.set_pose(f'wolf{i}', wx, self.pack[i].origin.y, wz,
                                   wyaw, mode=wmode)
        if truck:
            out.extend(self.truck.meshes(tq))
            out.extend(self.poacher.meshes(tq, mode='swing'))
        self.cast.set_pose('niulai', nx, self.niulai.origin.y, nz, nyaw,
                           mode=nmode)
        self.cast.set_pose('baola', bx, self.baola.origin.y, bz, byaw,
                           mode=bmode)
        if t >= 660.0 and self.cast.entities['baola'].get(CastState).state == 'alive':
            self.cast.set_state('baola', 'separated')
        return out

    def overlays(self, t):
        return [self._sub.at(t)]

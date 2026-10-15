# -*- coding: utf-8 -*-
"""序幕 · 荒漠飞雀（P0 切片：前 60 秒）。

原片开场：云雀飞行近 5 分钟的长镜头后，落在无法站立的牛来身旁。
P0 只复刻前 60s：云玎高空俯冲滑翔 → 蜿蜒越丘 → 末段下降接近幕末绿地，
牛来（伏地挣扎）进入画面 —— 切片以"人雀对视"的 payoff 帧收尾。

相机脚本（t 的纯函数，无跨帧累积 —— 离线逐帧渲染可复现的根基）：
- t < 52s：追雀机位（身后上方，前注视点）；
- t >= 52s：8 秒过渡到"雀 + 牛"双人镜头（推近绿地）。
"""
import math

from pyglet.math import Vec3

from ..cast import perf
from ..cast.calf import Calf
from ..cast.skylark import Skylark, flight_head
from ..scenery import desert
from ..timeline import Timeline

TAU = 6.283185307

# 牛来躺卧点（绿地内）；躯干高度 = 当地地面 + 0.61（四蹄恰着地、肚皮低伏）
CALF_AT = (62.0, -16.0)
CALF_BELLY_CLEAR = 0.61

# 追雀机位参数
CHASE_DIST, CHASE_UP, LOOKAHEAD = 13.0, 4.5, 8.0
# 双人镜头参数（终态机位）
DUAL_DIST, DUAL_UP = 9.0, 2.6
BLEND_T0, BLEND_T1 = 52.0, 60.0


def _smooth(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3.0 - 2.0 * u)


class PrologueScene:
    """序幕场景：静态地形 + 云玎 + 牛来 + 相机脚本。"""

    NAME = 'act0_prologue'
    SKY = perf.DESERT_SKY
    FOG_K = 0.0105

    def __init__(self, seed, grid=192, step=1.0):
        self.timeline = Timeline()
        self.terrain_md, self.heights = desert.build_terrain(seed, grid, step)
        self.grid, self.step = grid, step
        # 躯干高度贴地计算（绿地整平高程 0.9~1.4，写死会把牛来埋进地里）
        ground = desert.height_at(CALF_AT[0], CALF_AT[1], seed)
        self.calf_y = ground + CALF_BELLY_CLEAR
        self.calf = Calf(origin=(CALF_AT[0], self.calf_y, CALF_AT[1]), yaw=2.55)
        self.bird = Skylark()

    # ---------------------------------------------------------------- 地形 --
    def ground_at(self, wx, wz):
        """世界坐标 -> 高程（相机防穿地用）。"""
        return desert.height_at(wx, wz, self.timeline.seed)

    # ---------------------------------------------------------------- 相机 --
    def camera(self, t):
        """t -> (eye, target)。纯函数；末段 8s 过渡到双人镜头。"""
        self.bird.place(t)
        p = self.bird.origin
        head = flight_head(t)
        fwd = Vec3(math.cos(head), 0.0, math.sin(head))
        # 追雀机位
        eye_chase = Vec3(p.x - fwd.x * CHASE_DIST,
                         p.y + CHASE_UP,
                         p.z - fwd.z * CHASE_DIST)
        tgt_chase = Vec3(p.x + fwd.x * LOOKAHEAD, p.y, p.z + fwd.z * LOOKAHEAD)
        # 确定性微风摆动（不累积，t 的显函数）
        sway = 0.6 * math.sin(t * 0.37) + 0.35 * math.sin(t * 0.91 + 1.3)
        eye_chase = Vec3(eye_chase.x, eye_chase.y + sway, eye_chase.z)
        # 双人镜头终态：牛来侧前方，把雀与牛同时纳入
        calf = self.calf.origin
        mid = Vec3((calf.x + p.x) * 0.5, calf.y + 1.6, (calf.z + p.z) * 0.5)
        ang = math.atan2(p.z - calf.z, p.x - calf.x) + 2.35
        eye_dual = Vec3(calf.x + math.cos(ang) * DUAL_DIST,
                        calf.y + DUAL_UP,
                        calf.z + math.sin(ang) * DUAL_DIST)
        # 过渡
        u = _smooth((t - BLEND_T0) / (BLEND_T1 - BLEND_T0))
        eye = Vec3(eye_chase.x + (eye_dual.x - eye_chase.x) * u,
                   eye_chase.y + (eye_dual.y - eye_chase.y) * u,
                   eye_chase.z + (eye_dual.z - eye_chase.z) * u)
        target = Vec3(tgt_chase.x + (mid.x - tgt_chase.x) * u,
                      tgt_chase.y + (mid.y - tgt_chase.y) * u,
                      tgt_chase.z + (mid.z - tgt_chase.z) * u)
        # 防穿地：眼点不低于地面 +1.2
        g = self.ground_at(eye.x, eye.z) + 1.2
        if eye.y < g:
            eye = Vec3(eye.x, g, eye.z)
        return eye, target

    # ---------------------------------------------------------------- 姿装 --
    def meshes(self, t):
        """t -> 本帧全部 MeshData（地形 + 云玎 + 牛来）。"""
        tq = Timeline.quantize(t, perf.ANIM_FPS)
        self.bird.place(t)
        out = [self.terrain_md]
        out.extend(self.bird.meshes(tq))
        out.extend(self.calf.meshes(tq))
        return out

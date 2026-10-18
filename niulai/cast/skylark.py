# -*- coding: utf-8 -*-
"""云玎（云雀）：程序化飞行 + 振翅。

飞行航线是 t 的纯函数（荒漠飞雀长镜头，60s P0 切片）：
从高空远端俯冲滑翔、蜿蜒越丘、末段下降接近幕末绿地（牛来躺卧处）。
所有频率/幅度硬编码，无随机 —— 确定性由调用方传入量化后的 t。
"""
import math

from pyglet.math import Vec3

from . import perf
from .rig import Rig, part_matrix

TAU = 6.283185307

# 序幕全幕窗口（秒）：原片云雀空镜飞行约 5 分钟，全幕 6 分钟
WINDOW = 360.0
# 航线世界坐标（绿地中心 = 幕末落点；世界地形 192x192，范围 [-96, 96]）
LANDING = (62.0, -16.0)
START = (-88.0, 42.0, 55.0)
END = (58.0, 5.5, -12.0)        # 60s 末：已大幅下降，尚未着陆（着陆属 act1 镜头）


def _smooth(u):
    """smoothstep（起降缓入缓出）。"""
    u = min(1.0, max(0.0, u))
    return u * u * (3.0 - 2.0 * u)


def flight_pos(t):
    """t -> 世界位置 Vec3（纯函数）。

    航线：从荒漠远端 (-88, 55) 俯冲滑翔到幕末绿地旁 (56, -14)，
    x/z 各带小幅确定性蜿蜒（振幅随航程衰减，末段稳定对准落点）。
    """
    u = t / WINDOW
    s = _smooth(u)
    x = START[0] + (END[0] - START[0]) * s + 5.0 * math.sin(u * 6.1 + 0.6)
    z = START[2] + (END[2] - START[2]) * s + 5.0 * math.sin(u * 4.3 + 2.1)
    y = START[1] + (END[1] - START[1]) * s + 2.6 * math.sin(u * 9.3)
    return Vec3(x, y, z)


def flight_head(t):
    """t -> 航向角（弧度，atan2(dz, dx) 口径；数值差分，dt=0.5s）。"""
    p, q = flight_pos(t), flight_pos(min(WINDOW, t + 0.5))
    return math.atan2(q.z - p.z, q.x - p.x)


def flight_roll(t):
    """t -> 侧倾（弧度）：由航向变化率驱动，转弯时机身 banking。"""
    h0, h1 = flight_head(t), flight_head(min(WINDOW, t + 0.5))
    dh = (h1 - h0 + math.pi) % TAU - math.pi
    return max(-0.55, min(0.55, -dh * 2.2))


class Skylark(Rig):
    """云玎：躯干 + 头 + 喙 + 尾 + 双翼。局部 +X 为前方。

    尺寸按"影片主角雀"放大（实物云雀太小，追雀机位下读不出戏）——
    粗粝美学下"比例失真"是特征而非缺陷。
    """

    PARTS = (
        ('body', 1.36, 0.33, 0.33, perf.BIRD_BODY, (0.0, 0.0, 0.0)),
        ('head', 0.35, 0.29, 0.29, perf.BIRD_HEAD, (0.80, 0.06, 0.0)),
        ('beak', 0.26, 0.08, 0.08, perf.BIRD_BEAK, (1.10, 0.02, 0.0)),
        ('tail', 0.57, 0.04, 0.22, perf.BIRD_WING, (-0.88, 0.02, 0.0)),
        ('wing_l', 0.66, 0.055, 1.36, perf.BIRD_WING, (0.0, 0.10, 0.74)),
        ('wing_r', 0.66, 0.055, 1.36, perf.BIRD_WING, (0.0, 0.10, -0.74)),
    )

    def __init__(self, t=0.0):
        super().__init__(origin=(0.0, 0.0, 0.0), yaw=0.0, kind='skylark')
        self.place(t)

    def place(self, t):
        """把角色摆到 t 时刻的航点（世界坐标 + 航向 + 侧倾）。"""
        p = flight_pos(t)
        self.origin = Vec3(p.x, p.y, p.z)
        self.yaw = -flight_head(t)      # 局部 +X 前方：yaw = -heading
        self.roll = flight_roll(t)
        return self

    def pose(self, t, **_kw):
        flap = math.sin(TAU * perf.BIRD_FLAP_HZ * t) * perf.BIRD_FLAP_AMP
        bob = 0.05 * math.sin(TAU * perf.BIRD_FLAP_HZ * t + 0.8)
        return {
            'body': part_matrix(pos=(0.0, bob, 0.0), roll=self.roll),
            'head': part_matrix(pos=(0.0, bob, 0.0), roll=self.roll),
            'beak': part_matrix(pos=(0.0, bob, 0.0), roll=self.roll),
            'tail': part_matrix(pos=(0.0, bob, 0.0), roll=self.roll),
            # 双翼绕纵轴（X）上下扑：内端在翼根，故 pitch 即扑角
            'wing_l': part_matrix(pos=(0.0, bob, 0.0), roll=self.roll, pitch=flap),
            'wing_r': part_matrix(pos=(0.0, bob, 0.0), roll=self.roll, pitch=-flap),
        }

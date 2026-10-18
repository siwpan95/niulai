# -*- coding: utf-8 -*-
"""草蛇：多段盒体沿正弦路径滑行（原片"被蛇咬/怕蛇"的心理阴影来源）。

段位置是 t 的纯函数：头沿路径前进，各段依次跟随（滞后相位），形成蠕动。
蛇在**世界坐标**直接布局（origin/yaw 恒为单位变换），高度贴地形
（ground 回调由场景注入，仍是确定性纯函数）。
"""
import math

from .rig import Rig, part_matrix


class Snake(Rig):
    """草蛇：SEGMENTS 段小盒 + 头部。"""

    SEGMENTS = 9
    SEG = (0.16, 0.13, 0.13)
    HEAD = (0.24, 0.18, 0.18)
    COLOR = (0.35, 0.45, 0.24)
    HEAD_COLOR = (0.40, 0.50, 0.27)

    def __init__(self, ground=None, yaw=0.0, path_fn=None):
        self.PARTS = tuple(
            [(f'seg{i}', *self.SEG, self.COLOR, (0.0, 0.0, 0.0))
             for i in range(self.SEGMENTS)]
            + [('head', *self.HEAD, self.HEAD_COLOR, (0.0, 0.0, 0.0))])
        super().__init__(origin=(0.0, 0.0, 0.0), yaw=yaw, kind='snake')
        self.ground = ground or (lambda x, z: 0.0)
        # path_fn：场景可注入自定义路径（纯函数 t -> (x, z)）。
        # 默认路径按小 t 设计（序幕尺度）；**长幕必须注入**——
        # 否则 t=400 时默认路径已飞到 x≈1300 界外，相机会被拖去追蛇（实测踩坑）
        self._path_fn = path_fn

    def path(self, t):
        """世界路径点 (x, z)（确定性纯函数）。"""
        if self._path_fn is not None:
            return self._path_fn(t)
        x = -30.0 + 3.2 * t
        z = 42.0 + 6.0 * math.sin(t * 0.6)
        return x, z

    def pose(self, t):
        """段布局：头在前，各段沿路径历史位置错位排开（蠕动滞后）。"""
        out = {}
        for i in range(self.SEGMENTS):
            lag = t - i * 0.12                     # 段间时间滞后 -> 波动传递
            x, z = self.path(lag)
            dx, dz = self.path(lag + 0.05)
            yaw = math.atan2(dz - z, dx - x)
            y = self.ground(x, z) + 0.10 + 0.05 * math.sin(lag * 3.0 + i * 0.8)
            out[f'seg{i}'] = part_matrix((x, y, z), yaw=-yaw)
        hx, hz = self.path(t + 0.35)
        dx, dz = self.path(t + 0.4)
        out['head'] = part_matrix(
            (hx, self.ground(hx, hz) + 0.12, hz),
            yaw=-math.atan2(dz - hz, dx - hx))
        return out

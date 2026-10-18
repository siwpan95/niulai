# -*- coding: utf-8 -*-
"""牛来（幼崽）：初生牛犊，**站不起来**。

原片开场形态：双腿无力、肚皮贴地、摇晃抬头。姿态 = t 的纯函数：
- 躯干低位（y ≈ CALF_BELLY_H_OK），侧摇 + 抬头挣扎；
- 四腿外劈（CALF_LEG_SPLAY），蹄子扒地 —— 幼肢划水感；
- 12fps 量化由调用方保证（niulai.timeline.Timeline.quantize）。
"""
import math

from pyglet.math import Vec3

from . import perf
from .rig import Rig, part_matrix

TAU = 6.283185307


class Calf(Rig):
    """牛来幼态。局部 +X 为前方，躯干中心在局部 y=CALF_BELLY_H_OK。"""

    PARTS = (
        # 躯干（长条盒，侧躺/伏地姿态）
        ('body', 1.30, 0.62, 0.56, perf.CALF_BODY, (0.0, 0.0, 0.0)),
        ('belly', 1.10, 0.18, 0.50, perf.CALF_BELLY, (0.0, -0.26, 0.0)),
        # 头（抬不起，低垂在躯干前方）
        ('head', 0.44, 0.40, 0.40, perf.CALF_HEAD, (0.80, -0.10, 0.0)),
        ('muzzle', 0.16, 0.20, 0.26, perf.CALF_MUZZLE, (1.08, -0.16, 0.0)),
        ('ear_l', 0.07, 0.16, 0.10, perf.CALF_EAR, (0.72, 0.10, 0.20)),
        ('ear_r', 0.07, 0.16, 0.10, perf.CALF_EAR, (0.72, 0.10, -0.20)),
        # 四腿：外劈、短、抖
        ('leg_fl', 0.16, 0.46, 0.16, perf.CALF_HEAD, (0.52, -0.42, 0.30)),
        ('leg_fr', 0.16, 0.46, 0.16, perf.CALF_HEAD, (0.52, -0.42, -0.30)),
        ('leg_bl', 0.16, 0.46, 0.16, perf.CALF_HEAD, (-0.48, -0.42, 0.30)),
        ('leg_br', 0.16, 0.46, 0.16, perf.CALF_HEAD, (-0.48, -0.42, -0.30)),
        ('tail', 0.34, 0.05, 0.05, perf.CALF_EAR, (-0.78, 0.12, 0.0)),
    )

    def __init__(self, origin=(0.0, 0.0, 0.0), yaw=0.0):
        super().__init__(origin=origin, yaw=yaw, kind='calf')

    def pose(self, t, mode='lie', rise_u=0.0, **_kw):
        """伏地挣扎 / 奋力站起（rise）。

        轴向约定（角色局部）：+X 前 / +Y 上 / +Z 右侧。
        低头 = 绕 Z 侧倾（roll）；腿外劈 = 绕 X 纵轴（pitch）；
        腿前后蹬 = 绕 Z 侧轴（roll）。
        rise_u：0 = 伏地，1 = 站起（躯干抬升、四肢收直、头抬起、微伸展）。
        """
        if mode == 'rise':
            return self._pose_rise(t, rise_u)
        w = math.sin(TAU * perf.CALF_WOBBLE_HZ * t)
        head_droop = -0.26 + 0.14 * w          # 低头（幅度收敛：口鼻不扎进草皮）
        kick = 0.22 * max(0.0, math.sin(TAU * 2.6 * t))     # 后腿间歇蹬踏
        splay = perf.CALF_LEG_SPLAY
        sway = w * perf.CALF_WOBBLE_AMP
        return {
            'body': part_matrix(roll=sway),
            'belly': part_matrix(roll=sway),
            'head': part_matrix(pos=(0.06 * w, 0.02, 0.0), roll=head_droop),
            'muzzle': part_matrix(pos=(0.06 * w, 0.02, 0.0), roll=head_droop),
            'ear_l': part_matrix(pos=(0.06 * w, 0.02, 0.0), roll=head_droop),
            'ear_r': part_matrix(pos=(0.06 * w, 0.02, 0.0), roll=head_droop),
            # 前腿前伸（roll 正 = 蹄子向前）、后腿后撑（roll 负）
            'leg_fl': part_matrix(pitch=splay, roll=0.55),
            'leg_fr': part_matrix(pitch=-splay, roll=0.55),
            'leg_bl': part_matrix(pitch=splay, roll=-0.55 - kick),
            'leg_br': part_matrix(pitch=-splay, roll=-0.55 - kick),
            'tail': part_matrix(roll=0.55 + 0.30 * w),
        }

    def _pose_rise(self, t, u):
        """奋力站起：躯体组上移 0.17u、腿绕髋顶拉伸（k=1+0.37u）、头抬起。

        关键几何：腿的枢轴在髋顶（局部 y=-0.19），拉伸后蹄的绝对高度
        恒为 -0.65（= 伏地时的着地点）—— 躯体上移不浮蹄；
        部件只做"纯 y 增量"平移（x/z 仍由 PARTS 烘焙偏移提供），
        不重复叠加已烘焙位置（实测踩坑）。
        """
        u = min(1.0, max(0.0, u))
        splay = perf.CALF_LEG_SPLAY * (1.0 - u)
        wobble = perf.CALF_WOBBLE_AMP * (1.0 + 1.6 * u)
        sway = math.sin(TAU * perf.CALF_WOBBLE_HZ * t) * wobble
        head_roll = -0.26 * (1.0 - u)          # 头从低垂抬到平
        rise = 0.17 * u                         # 躯体组纯 y 增量
        k = 1.0 + 0.37 * u                      # 腿拉伸系数（绕髋顶）
        pivot = -0.19                           # 髋顶（腿盒中心 -0.42 + 半高 0.23）
        return {
            'body': part_matrix((0.0, rise, 0.0), roll=sway),
            'belly': part_matrix((0.0, rise, 0.0), roll=sway),
            'head': part_matrix((0.0, rise, 0.0), roll=head_roll),
            'muzzle': part_matrix((0.0, rise, 0.0), roll=head_roll),
            'ear_l': part_matrix((0.0, rise, 0.0), roll=head_roll),
            'ear_r': part_matrix((0.0, rise, 0.0), roll=head_roll),
            'tail': part_matrix((0.0, rise, 0.0), roll=0.3),
            # 四肢：上移 + 绕髋顶拉伸 + 外劈收拢
            'leg_fl': part_matrix((0.0, rise, 0.0), pitch=splay * 0.8,
                                  roll=0.55 * (1.0 - u), sy=k, pivot_y=pivot),
            'leg_fr': part_matrix((0.0, rise, 0.0), pitch=-splay * 0.8,
                                  roll=-0.55 * (1.0 - u), sy=k, pivot_y=pivot),
            'leg_bl': part_matrix((0.0, rise, 0.0),
                                  pitch=-splay * 0.6 - 0.22 * (1.0 - u),
                                  roll=0.9 * (1.0 - u), sy=k, pivot_y=pivot),
            'leg_br': part_matrix((0.0, rise, 0.0),
                                  pitch=splay * 0.6 + 0.22 * (1.0 - u),
                                  roll=-0.9 * (1.0 - u), sy=k, pivot_y=pivot),
        }

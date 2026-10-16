# -*- coding: utf-8 -*-
"""盗猎人 + 盗猎车（第五幕反派：原片"长期破坏森林家园的人类"）。

程序化盒体：人 = 躯干+头+四肢（站/挥臂姿态）；车 = 车身+车斗+4 轮
（轮子装饰性旋转）。全部确定性纯函数姿态。
"""
import math

from .rig import Rig, part_matrix

HUMAN_COLORS = {'body': (0.55, 0.50, 0.42), 'head': (0.72, 0.60, 0.48),
                'limb': (0.48, 0.44, 0.38)}
VEHICLE_COLORS = {'body': (0.35, 0.42, 0.30), 'bed': (0.30, 0.36, 0.26),
                  'wheel': (0.15, 0.15, 0.16)}


class Poacher(Rig):
    """盗猎人：站立/挥臂。局部 +X 前。"""

    # offset 全零：位置一律由 pose() 的平移给（与 Quadruped 同模型）
    PARTS = (
        ('body', 0.42, 0.72, 0.30, HUMAN_COLORS['body'], (0.0, 0.0, 0.0)),
        ('head', 0.26, 0.26, 0.26, HUMAN_COLORS['head'], (0.0, 0.0, 0.0)),
        ('arm_l', 0.12, 0.52, 0.12, HUMAN_COLORS['limb'], (0.0, 0.0, 0.0)),
        ('arm_r', 0.12, 0.52, 0.12, HUMAN_COLORS['limb'], (0.0, 0.0, 0.0)),
        ('leg_l', 0.14, 0.62, 0.14, HUMAN_COLORS['limb'], (0.0, 0.0, 0.0)),
        ('leg_r', 0.14, 0.62, 0.14, HUMAN_COLORS['limb'], (0.0, 0.0, 0.0)),
        ('hat', 0.30, 0.08, 0.30, HUMAN_COLORS['limb'], (0.0, 0.0, 0.0)),
    )

    def __init__(self, origin=(0.0, 0.0, 0.0), yaw=0.0):
        super().__init__(origin=origin, yaw=yaw)

    def pose(self, t, mode='stand'):
        """站立（呼吸）/ 挥臂（驱赶/举枪）。"""
        breath = 0.02 * math.sin(2.0 * math.pi * 0.8 * t)
        if mode == 'swing':
            arm = 0.9 * math.sin(2.0 * math.pi * 1.4 * t)
            return {
                'body': part_matrix((0.0, breath, 0.0)),
                'head': part_matrix((0.0, 0.49 + breath, 0.0)),
                'arm_l': part_matrix((0.0, 0.26 + breath, 0.21), pitch=arm),
                'arm_r': part_matrix((0.0, 0.26 + breath, -0.21), pitch=-arm),
                'leg_l': part_matrix((0.0, -0.31, 0.10)),
                'leg_r': part_matrix((0.0, -0.31, -0.10)),
                'hat': part_matrix((0.0, 0.64 + breath, 0.0)),
            }
        return {
            'body': part_matrix((0.0, breath, 0.0)),
            'head': part_matrix((0.0, 0.49 + breath, 0.0)),
            'arm_l': part_matrix((0.0, 0.26 + breath, 0.21)),
            'arm_r': part_matrix((0.0, 0.26 + breath, -0.21)),
            'leg_l': part_matrix((0.0, -0.31, 0.10)),
            'leg_r': part_matrix((0.0, -0.31, -0.10)),
            'hat': part_matrix((0.0, 0.64 + breath, 0.0)),
        }


class PoacherTruck(Rig):
    """盗猎车：皮卡（驾驶室 + 车斗 + 4 轮）。局部 +X 前。"""

    # offset 全零：位置（含轮心）由 pose() 给；轮子绕**自身轮心**自转
    PARTS = (
        ('cab', 1.30, 0.62, 0.90, VEHICLE_COLORS['body'], (0.0, 0.0, 0.0)),
        ('bed', 1.10, 0.42, 0.92, VEHICLE_COLORS['bed'], (0.0, 0.0, 0.0)),
        ('cage', 0.90, 0.50, 0.86, VEHICLE_COLORS['wheel'], (0.0, 0.0, 0.0)),
        ('wheel_fl', 0.34, 0.34, 0.16, VEHICLE_COLORS['wheel'], (0.0, 0.0, 0.0)),
        ('wheel_fr', 0.34, 0.34, 0.16, VEHICLE_COLORS['wheel'], (0.0, 0.0, 0.0)),
        ('wheel_bl', 0.34, 0.34, 0.16, VEHICLE_COLORS['wheel'], (0.0, 0.0, 0.0)),
        ('wheel_br', 0.34, 0.34, 0.16, VEHICLE_COLORS['wheel'], (0.0, 0.0, 0.0)),
    )

    def __init__(self, origin=(0.0, 0.0, 0.0), yaw=0.0):
        super().__init__(origin=origin, yaw=yaw)

    def pose(self, t):
        """车身静止；车轮绕自身轮心装饰性旋转（roll）。"""
        spin = 6.0 * t
        return {
            'cab': part_matrix((0.30, 0.10, 0.0)),
            'bed': part_matrix((-0.85, 0.10, 0.0)),
            'cage': part_matrix((-0.85, 0.42, 0.0)),
            'wheel_fl': part_matrix((0.55, -0.17, 0.50), roll=spin),
            'wheel_fr': part_matrix((0.55, -0.17, -0.50), roll=spin),
            'wheel_bl': part_matrix((-0.90, -0.17, 0.50), roll=spin),
            'wheel_br': part_matrix((-0.90, -0.17, -0.50), roll=spin),
        }

    @property
    def wheelbase_y(self):
        return 0.42          # 车轮中心离地（origin 设在车轮高度）

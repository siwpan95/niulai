# -*- coding: utf-8 -*-
"""通用四足骨架：牛妈妈 / 豹拉 / 狼 / 牛爸爸共用。

规格驱动（spec dict）：一次定义，四角色复用。局部坐标系 +X 前 / +Y 上 / +Z 右。

枢轴模型（与 rig.part_matrix 配合的关键约定）：
- PARTS 的 offset **只放几何悬挂提示**：腿 = (0, -腿长/2, 0)（几何从枢轴向下垂），
  其余段 = (0,0,0)（几何以枢轴为中心）；
- **位置全部由 pose() 的平移矩阵给**：v = T(局部位置) @ R(旋转) @ (v_box + offset)。
  于是腿的枢轴精确落在髋部接点（T 的落点），摆步是绕自身髋关节转，
  而不是绕角色原点（脊柱）转 —— 后者会把整条腿甩成风车。
"""
import math

from .rig import Rig, part_matrix

TAU = 6.283185307


def gait_phase(t, speed=1.0):
    """步态相位（弧度）。speed = 步/秒。"""
    return TAU * speed * t


# 四足默认规格（牛妈妈）
COW_SPEC = {
    'body': (1.9, 0.78, 0.72),        # (长, 高, 宽)
    'body_y': 1.39,                    # 躯干中心离地（站立）
    'neck': (0.55, 0.42, 0.40),
    'head': (0.52, 0.44, 0.42),
    'muzzle': (0.26, 0.26, 0.30),
    'ear': (0.10, 0.22, 0.08),
    'horn': (0.10, 0.30, 0.10),
    'horns': True,
    'leg': (0.17, 0.98, 0.17),         # 腿长（枢轴在髋顶）
    'leg_x': 0.72, 'leg_z': 0.30,      # 髋接点分布
    'tail': (0.55, 0.07, 0.07),
    'colors': {'body': (0.44, 0.33, 0.24), 'head': (0.40, 0.30, 0.22),
               'leg': (0.36, 0.27, 0.20), 'horn': (0.78, 0.72, 0.60),
               'ear': (0.38, 0.28, 0.21)},
}


def _build_parts(spec):
    """规格 -> PARTS 六元组 (name, sx, sy, sz, color, offset)。

    offset 仅几何悬挂提示：腿为 (0, -腿长/2, 0)，其余 (0,0,0)。
    位置一律不进 offset —— 见模块 docstring 的枢轴模型。
    """
    c = spec['colors']
    bl, bh, bw = spec['body']
    nl, nh, nw = spec['neck']
    hl, hh, hw = spec['head']
    ml, mh, mw = spec['muzzle']
    el, eh, ew = spec['ear']
    ll, lh, lw = spec['leg']
    tl, th, tw = spec['tail']
    leg_off = (0.0, -lh / 2.0, 0.0)      # 几何从枢轴向下垂
    zero = (0.0, 0.0, 0.0)
    parts = [
        ('body', bl, bh, bw, c['body'], zero),
        ('neck', nl, nh, nw, c['body'], zero),
        ('head', hl, hh, hw, c['head'], zero),
        ('muzzle', ml, mh, mw, c['head'], zero),
        ('ear_l', el, eh, ew, c['ear'], zero),
        ('ear_r', el, eh, ew, c['ear'], zero),
        ('tail', tl, th, tw, c['body'], zero),
        ('leg_fl', ll, lh, lw, c['leg'], leg_off),
        ('leg_fr', ll, lh, lw, c['leg'], leg_off),
        ('leg_bl', ll, lh, lw, c['leg'], leg_off),
        ('leg_br', ll, lh, lw, c['leg'], leg_off),
    ]
    if spec.get('horns'):
        hl2, hh2, hw2 = spec['horn']
        parts.append(('horn_l', hl2, hh2, hw2, c['horn'], zero))
        parts.append(('horn_r', hl2, hh2, hw2, c['horn'], zero))
    return tuple(parts)


class Quadruped(Rig):
    """四足角色。pose 模式：walk / run / stand / lie。"""

    def __init__(self, spec, origin=(0.0, 0.0, 0.0), yaw=0.0, kind=None):
        self.spec = spec
        self.PARTS = _build_parts(spec)
        from .specs import SPEC_KIND
        super().__init__(origin=origin, yaw=yaw,
                         kind=kind or SPEC_KIND.get(id(spec), 'quadruped'))

    # ------------------------------------------------------------ 布局常量 --
    def _layout(self, body_y):
        """躯干中心在 body_y 时，各段的局部位置（头颈随躯干走）。"""
        s = self.spec
        bl, bh, _ = s['body']
        nl = s['neck'][0]
        hl = s['head'][0]
        lx, lz = s['leg_x'], s['leg_z']
        hip_y = s['body_y'] - s['body'][1] / 2.0
        head_x = bl / 2 + nl - 0.06 + hl / 2
        return {
            'body': (0.0, body_y, 0.0),
            'neck': (bl / 2 + nl / 2 - 0.06, body_y + 0.16, 0.0),
            'head': (head_x, body_y + 0.34, 0.0),
            'muzzle': (head_x + hl / 2 + s['muzzle'][0] / 2 - 0.04,
                       body_y + 0.22, 0.0),
            'ear_l': (head_x, body_y + 0.34 + s['head'][1] / 2, lz * 0.55),
            'ear_r': (head_x, body_y + 0.34 + s['head'][1] / 2, -lz * 0.55),
            'horn_l': (head_x, body_y + 0.34 + s['head'][1] / 2
                       + s['horn'][1] / 2 - 0.04, lz * 0.5),
            'horn_r': (head_x, body_y + 0.34 + s['head'][1] / 2
                       + s['horn'][1] / 2 - 0.04, -lz * 0.5),
            'tail': (-bl / 2 - s['tail'][0] / 2, body_y + 0.1, 0.0),
            'hip_fl': (lx, hip_y, lz), 'hip_fr': (lx, hip_y, -lz),
            'hip_bl': (-lx, hip_y, lz), 'hip_br': (-lx, hip_y, -lz),
        }

    # ---------------------------------------------------------------- 姿态 --
    def pose(self, t, mode='stand', speed=1.0, phase0=0.0):
        """t -> {段名: Mat4}（纯函数）。腿绕自身髋接点摆动；躯干随步频 bob。"""
        s = self.spec
        by = s['body_y']

        if mode == 'lie':
            return self._pose_lie(t)

        if mode in ('walk', 'run'):
            amp = 0.45 if mode == 'walk' else 0.78
            freq = 1.6 if mode == 'walk' else 2.6
            ph = gait_phase(t, speed * freq) + phase0
            bob = 0.045 * amp * math.sin(2 * ph)
            body_y = by + bob
            L = self._layout(body_y)
            swing = amp * math.sin(ph)
            head_bob = 0.03 * math.sin(2 * ph + 0.7)
            L['head'] = (L['head'][0], L['head'][1] + head_bob, L['head'][2])
            L['muzzle'] = (L['muzzle'][0], L['muzzle'][1] + head_bob, L['muzzle'][2])
            L['ear_l'] = (L['ear_l'][0], L['ear_l'][1] + head_bob, L['ear_l'][2])
            L['ear_r'] = (L['ear_r'][0], L['ear_r'][1] + head_bob, L['ear_r'][2])
            L['horn_l'] = (L['horn_l'][0], L['horn_l'][1] + head_bob, L['horn_l'][2])
            L['horn_r'] = (L['horn_r'][0], L['horn_r'][1] + head_bob, L['horn_r'][2])
            d = {
                'body': part_matrix(L['body']),
                'neck': part_matrix(L['neck'], pitch=-0.06),
                'head': part_matrix(L['head']),
                'muzzle': part_matrix(L['muzzle']),
                'ear_l': part_matrix(L['ear_l']),
                'ear_r': part_matrix(L['ear_r']),
                'tail': part_matrix(L['tail'], pitch=0.35 * math.sin(ph * 0.5)),
                'leg_fl': part_matrix(L['hip_fl'], pitch=swing),
                'leg_br': part_matrix(L['hip_br'], pitch=swing),
                'leg_fr': part_matrix(L['hip_fr'], pitch=-swing),
                'leg_bl': part_matrix(L['hip_bl'], pitch=-swing),
            }
            if s.get('horns'):
                d['horn_l'] = part_matrix(L['horn_l'])
                d['horn_r'] = part_matrix(L['horn_r'])
            return d

        # stand：静止站立，呼吸微起伏
        breath = 0.012 * math.sin(TAU * 0.9 * t)
        L = self._layout(by + breath)
        d = {
            'body': part_matrix(L['body']),
            'neck': part_matrix(L['neck'], pitch=-0.05),
            'head': part_matrix(L['head']),
            'muzzle': part_matrix(L['muzzle']),
            'ear_l': part_matrix(L['ear_l']),
            'ear_r': part_matrix(L['ear_r']),
            'tail': part_matrix(L['tail'], pitch=0.18 * math.sin(TAU * 0.5 * t)),
            'leg_fl': part_matrix(L['hip_fl']),
            'leg_fr': part_matrix(L['hip_fr']),
            'leg_bl': part_matrix(L['hip_bl']),
            'leg_br': part_matrix(L['hip_br']),
        }
        if s.get('horns'):
            d['horn_l'] = part_matrix(L['horn_l'])
            d['horn_r'] = part_matrix(L['horn_r'])
        return d

    def _pose_lie(self, t):
        """卧伏：躯干降到 0.42，前腿前伸、后腿屈于身下。"""
        s = self.spec
        bl = s['body'][0]
        nl = s['neck'][0]
        hl = s['head'][0]
        lx, lz = s['leg_x'], s['leg_z']
        lie_y = 0.42
        breath = 0.015 * math.sin(TAU * 1.1 * t)
        body_y = lie_y + breath
        head_x = bl / 2 + nl - 0.06 + hl / 2
        d = {
            'body': part_matrix((0.0, body_y, 0.0), roll=0.04),
            'neck': part_matrix((bl / 2 + nl / 2 - 0.06, body_y + 0.16, 0.0),
                                pitch=-0.10),
            'head': part_matrix((head_x, body_y + 0.30, 0.0), roll=-0.12),
            'muzzle': part_matrix((head_x + hl / 2 + s['muzzle'][0] / 2 - 0.04,
                                   body_y + 0.18, 0.0), roll=-0.12),
            'ear_l': part_matrix((head_x, body_y + 0.30, lz * 0.55), roll=-0.12),
            'ear_r': part_matrix((head_x, body_y + 0.30, -lz * 0.55), roll=-0.12),
            'tail': part_matrix((-bl / 2 - s['tail'][0] / 2, body_y + 0.12, 0.0),
                                pitch=0.3),
            'leg_fl': part_matrix((lx, body_y + 0.02, lz), pitch=0.35, roll=1.35),
            'leg_fr': part_matrix((lx, body_y + 0.02, -lz), pitch=0.35, roll=-1.35),
            'leg_bl': part_matrix((-lx, body_y + 0.02, lz), pitch=-0.40, roll=1.30),
            'leg_br': part_matrix((-lx, body_y + 0.02, -lz), pitch=-0.40, roll=-1.30),
        }
        if s.get('horns'):
            d['horn_l'] = part_matrix((head_x, body_y + 0.30
                                       + s['head'][1] / 2 + s['horn'][1] / 2 - 0.04,
                                       lz * 0.5), roll=-0.12)
            d['horn_r'] = part_matrix((head_x, body_y + 0.30
                                       + s['head'][1] / 2 + s['horn'][1] / 2 - 0.04,
                                       -lz * 0.5), roll=-0.12)
        return d

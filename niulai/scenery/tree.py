# -*- coding: utf-8 -*-
"""歪脖子树：牛妈妈牺牲之地的地标（第四幕情感锚点，第六幕呼应）。

程序化：逐段倾斜的树干（越往上越歪）+ 数根枝杈 + 稀疏树冠簇。
建一次静态 MeshData，之后每帧只有 draw。位置/尺寸确定性（硬编码）。
"""
import math

from world3d.engine.geometry import MeshData, box

TRUNK_COLOR = (0.32, 0.24, 0.17)
BRANCH_COLOR = (0.28, 0.21, 0.15)
LEAF_COLOR = (0.30, 0.42, 0.22)
LEAF_COLOR_2 = (0.38, 0.48, 0.26)


def _seg(cx, cy, cz, sx, sy, sz, roll, color):
    """一段：盒体 + 绕 Z 的倾斜（roll），平移到 (cx, cy, cz)。"""
    md = box(sx, sy, sz, color=color)
    from pyglet.math import Mat4, Vec3
    m = Mat4.from_translation(Vec3(cx, cy, cz)) @ Mat4.from_rotation(
        roll, Vec3(0.0, 0.0, 1.0))
    return md.transform(m)


def build_crooked_tree(bx, bz, ground_at, seed=20260805):
    """在 (bx, bz) 建一棵歪脖子树。返回 MeshData（含树干/枝/叶）。

    形状：5 段主干，每段倾斜角递增（"歪脖子"）；3 根枝杈；6 簇叶。
    """
    parts = []
    segs = 5
    x, y, z = bx, ground_at(bx, bz), bz
    lean = 0.0
    for i in range(segs):
        lean += 0.085 + 0.02 * ((i * 37 + seed) % 5) / 5.0   # 逐段加歪
        sy = 0.85
        y0 = y
        y = y0 + sy * math.cos(lean)
        x = x + sy * math.sin(lean) * 0.55
        parts.append(_seg(x, y0 + sy / 2, z, 0.42 - 0.05 * i, sy, 0.42 - 0.05 * i,
                          lean, TRUNK_COLOR))
    top_x, top_y = x, y
    # 枝杈（从顶部两节伸出）
    for k, (blen, ang, ydec) in enumerate(((1.5, 0.9, 0.9), (1.2, -1.1, 1.5),
                                           (1.0, 0.4, 2.1))):
        by = y - ydec
        bxs = x - (y - by) * math.sin(lean) * 0.55 * 0.5
        parts.append(_seg(bxs + math.cos(ang) * blen / 2, by + 0.25,
                          z + (k - 1) * 0.55, blen, 0.16, 0.16, ang * 0.6,
                          BRANCH_COLOR))
    # 树冠簇（顶部大小不一的扁盒）
    clusters = ((0.0, 0.0, 1.5, LEAF_COLOR), (-0.7, 0.3, 1.1, LEAF_COLOR_2),
                (0.7, -0.2, 1.2, LEAF_COLOR), (0.2, 0.6, 0.9, LEAF_COLOR_2),
                (-0.3, -0.6, 1.0, LEAF_COLOR), (0.5, 0.5, 0.8, LEAF_COLOR_2))
    for dx, dz, s, col in clusters:
        parts.append(_seg(top_x + dx, top_y + 0.55, z + dz, s, s * 0.55,
                          s, 0.12, col))
    # 合并
    pos, col = [], []
    for md in parts:
        pos.extend(md.positions)
        col.extend(md.colors)
    return MeshData(pos, colors=col, name='crooked_tree')


def tree_top(bx, bz, ground_at):
    """树冠中心高度（相机取景/测试用）。"""
    return ground_at(bx, bz) + 5.2

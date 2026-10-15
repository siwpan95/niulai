# -*- coding: utf-8 -*-
"""盒体骨架：Part 规格 + 每帧矩阵 -> 可绘 MeshData。

- 规格是静态的（段尺寸/颜色），姿态是动态的（每帧 Mat4）；
- 每面一个明暗档（FACE_SHADE），CPU 烘焙进顶点色 —— 复刻"低帧手搓"的硬朗面；
- 矩阵用 pyglet.math.Mat4 组合（T @ Rz @ Ry @ Rx，与 terrain_flyover 同款坑位：
  矩阵相乘必须用 @，* 只用于矩阵乘向量）。
"""
from pyglet.gl import GL_TRIANGLES
from pyglet.math import Mat4, Vec3

from world3d.engine.geometry import MeshData, box

# 六面明暗档：索引顺序与 world3d.engine.geometry.box 的 faces 一致
# （+Z, -Z, +Y, -Y, +X, -X）。顶面最亮、底面最暗，侧面中间 —— 无光照也可读。
FACE_SHADE = (0.86, 0.66, 1.00, 0.44, 0.76, 0.76)


def part_matrix(pos=(0.0, 0.0, 0.0), yaw=0.0, pitch=0.0, roll=0.0):
    """欧拉角 + 平移 -> Mat4。约定：局部 +X 为角色前方，yaw 绕 +Y。"""
    m = Mat4.from_rotation(roll, Vec3(0.0, 0.0, 1.0))
    m = m @ Mat4.from_rotation(yaw, Vec3(0.0, 1.0, 0.0))
    m = m @ Mat4.from_rotation(pitch, Vec3(1.0, 0.0, 0.0))
    return Mat4.from_translation(Vec3(*pos)) @ m


def shaded_box(sx, sy, sz, color, offset=(0.0, 0.0, 0.0)):
    """带每面明暗的盒体 MeshData（36 顶点，非索引）。"""
    md = box(sx, sy, sz, offset=offset, color=color)
    cols = md.colors
    for face in range(6):
        k = FACE_SHADE[face]
        base = face * 6 * 4          # 每面 6 顶点 x 4 float
        for v in range(6):
            i = base + v * 4
            cols[i] *= k
            cols[i + 1] *= k
            cols[i + 2] *= k
    return md


class Rig:
    """角色骨架：静态段规格 + pose(t) -> {段名: Mat4}。

    子类实现 PARTS（(name, sx, sy, sz, color, pivot_offset)）与 pose(t)。
    pivot_offset 是段局部原点相对关节的偏移（box 沿偏移展开）。
    """

    PARTS = ()

    def __init__(self, origin=(0.0, 0.0, 0.0), yaw=0.0):
        self.origin = Vec3(*origin)
        self.yaw = yaw

    def pose(self, t):
        """t -> {段名: Mat4}（纯函数；确定性由调用方用量化后的 t 保证）。"""
        raise NotImplementedError

    def meshes(self, t, **pose_kw):
        """t -> 该角色的 MeshData 列表（已烘世界变换）。

        pose_kw 透传给 pose()（如 Quadruped 的 mode/speed/phase0）。
        基矩阵 = T(origin) @ Ry(yaw)：先搬到世界位置、再绕自身竖轴转向，
        于是各段的局部旋转（roll/pitch）发生在**角色自身坐标系**里。
        """
        pose = self.pose(t, **pose_kw)
        base = Mat4.from_translation(self.origin) @ \
            Mat4.from_rotation(self.yaw, Vec3(0.0, 1.0, 0.0))
        out = []
        for name, sx, sy, sz, color, off in self.PARTS:
            m = base @ pose[name]
            out.append(shaded_box(sx, sy, sz, color, offset=off).transform(m))
        return out


def merge_draw(program, meshes):
    """把若干 MeshData 的位置/颜色拼成一个 vertex_list 并返回（调用方负责 delete）。"""
    pos, col = [], []
    for md in meshes:
        pos.extend(md.positions)
        col.extend(md.colors)
    return program.vertex_list(len(pos) // 3, GL_TRIANGLES,
                               position=('f', pos), colors=('f', col))


def bounds_of(meshes):
    """MeshData 合并后的 AABB（测试用：钉住角色站/躺的高度包络）。"""
    lo = [float('inf')] * 3
    hi = [float('-inf')] * 3
    for md in meshes:
        p = md.positions
        for i in range(0, len(p), 3):
            for k in range(3):
                lo[k] = min(lo[k], p[i + k])
                hi[k] = max(hi[k], p[i + k])
    return tuple(lo), tuple(hi)

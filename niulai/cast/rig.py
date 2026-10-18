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


def part_matrix(pos=(0.0, 0.0, 0.0), yaw=0.0, pitch=0.0, roll=0.0,
                sy=1.0, pivot_y=None):
    """欧拉角 + 平移 -> Mat4。约定：局部 +X 为角色前方，yaw 绕 +Y。

    sy/pivot_y：绕局部 Y=pivot_y 枢轴的 Y 缩放（牛来站起时腿绕髋顶拉伸，
    蹄的绝对高度不变、躯体上移 —— 见 calf._pose_rise）。
    """
    m = Mat4.from_rotation(roll, Vec3(0.0, 0.0, 1.0))
    m = m @ Mat4.from_rotation(yaw, Vec3(0.0, 1.0, 0.0))
    m = m @ Mat4.from_rotation(pitch, Vec3(1.0, 0.0, 0.0))
    if sy != 1.0 and pivot_y is not None:
        m = m @ Mat4.from_translation(Vec3(0.0, pivot_y, 0.0)) \
            @ Mat4.from_scale(Vec3(1.0, sy, 1.0)) \
            @ Mat4.from_translation(Vec3(0.0, -pivot_y, 0.0))
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

    def __init__(self, origin=(0.0, 0.0, 0.0), yaw=0.0, scale=1.0, kind=None):
        self.origin = Vec3(*origin)
        self.yaw = yaw
        self.scale = scale          # 整体缩放（牛来"奋力站起"的伸展用）
        # PBR 材质映射键（pbr_bridge 按网格名前缀选材质）：
        # kind 默认取类名小写；Quadruped 由 spec 身份派生（specs.SPEC_KIND）。
        self.kind = kind or self.__class__.__name__.lower()

    def pose(self, t):
        """t -> {段名: Mat4}（纯函数；确定性由调用方用量化后的 t 保证）。"""
        raise NotImplementedError

    def meshes_identity(self, t, **pose_kw):
        """t -> 姿态几何（**base = 单位阵**）：群体戏实例化的共享几何。"""
        return self._bake(self.pose(t, **pose_kw), Mat4())

    def meshes(self, t, **pose_kw):
        """t -> 该角色的 MeshData 列表（已烘世界变换）。

        pose_kw 透传给 pose()（如 Quadruped 的 mode/speed/phase0）。
        基矩阵 = T(origin) @ Ry(yaw) @ S(scale)：先搬到世界位置、再绕自身
        竖轴转向，各段的局部旋转发生在角色自身坐标系里。
        """
        return self._bake(self.pose(t, **pose_kw), self._base_matrix())

    def _base_matrix(self):
        """T(origin) @ Ry(yaw) @ S(scale)（列主序 Mat4）。"""
        return Mat4.from_translation(self.origin) @ \
            Mat4.from_rotation(self.yaw, Vec3(0.0, 1.0, 0.0)) @ \
            Mat4.from_scale(Vec3(self.scale, self.scale, self.scale))

    def _bake(self, pose, base):
        out = []
        for name, sx, sy, sz, color, off in self.PARTS:
            m = base @ pose[name]
            md = shaded_box(sx, sy, sz, color, offset=off).transform(m)
            md.name = f'{self.kind}:{name}'   # PBR 材质映射键（pbr_bridge）
            out.append(md)
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

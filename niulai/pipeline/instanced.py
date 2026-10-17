# -*- coding: utf-8 -*-
"""群体戏 GPU 实例化：同规格同姿态的牛群/狼群一次 draw call 画完。

背景：全片 36 头牛 × 13 盒体段的 CPU 逐头合并是吞吐瓶颈（act2 4.5fps vs
轻幕 7.6fps）。群体成员的**姿态完全相同**（同一 tq 同一 mode），只有
base 矩阵（origin/yaw）不同 —— 实例化的天然场景。

等价性要求（本模块的验收标准）：
- 顶点着色器与 CPU 合并路径**同构**（position/colors + i_model 列矩阵），
  片段着色器**同一份**（雾/色调/清屏色一致）；
- 同一帧两种路径产出**逐字节相同的 RGBA**（跨路径 md5 断言，见
  tests/test_instancing.py）。
"""
from pyglet.gl import GL_TRIANGLES
from pyglet.graphics.shader import Shader, ShaderProgram

from .render import FRAGMENT_SRC, merge_draw

INSTANCED_VERTEX_SRC = '''#version 330 core
in vec3 position;
in vec4 colors;
in vec4 i_m0;            // 实例模型矩阵的四列（column-major 拆 4×vec4）
in vec4 i_m1;
in vec4 i_m2;
in vec4 i_m3;
uniform WindowBlock { mat4 projection; mat4 view; } window;
out vec4 v_col;
out vec3 v_world;
void main() {
    mat4 i_model = mat4(i_m0, i_m1, i_m2, i_m3);
    vec4 world = i_model * vec4(position, 1.0);
    v_col = colors;
    v_world = world.xyz;
    gl_Position = window.projection * window.view * world;
}'''

_ATTRS = ('i_m0', 'i_m1', 'i_m2', 'i_m3')


def _mat_columns(m):
    """列主序 16 元组 -> 4 列 vec4（与 world3d build_instance_matrix 同构）。"""
    return (tuple(m[0:4]), tuple(m[4:8]), tuple(m[8:12]), tuple(m[12:16]))


def _flatten_meshes(meshes):
    """MeshData 列表 -> (flat_pos, flat_col, vertex_count)。"""
    pos, col = [], []
    for md in meshes:
        pos.extend(md.positions)
        col.extend(md.colors)
    return pos, col, len(pos) // 3


class InstancedBatch:
    """一份动态几何 + N 份实例矩阵（按顶点数缓存 vlist）。"""

    def __init__(self, vertex_count, capacity=64):
        self.vertex_count = vertex_count
        self.capacity = capacity
        self.program = ShaderProgram(Shader(INSTANCED_VERTEX_SRC, 'vertex'),
                                     Shader(FRAGMENT_SRC, 'fragment'))
        zeros_v = [0.0] * (vertex_count * 3)
        zeros_c = [0.0] * (vertex_count * 4)
        zeros_i = [0.0] * (vertex_count * 4)   # 实例属性初始数据按顶点数给
        self.vlist = self.program.vertex_list_instanced(
            vertex_count, GL_TRIANGLES, list(_ATTRS),
            position=('f', zeros_v), colors=('f', zeros_c),
            **{a: ('f', zeros_i) for a in _ATTRS})
        zeros4 = (0.0, 0.0, 0.0, 0.0)
        for _ in range(1, capacity):
            self.vlist.add_instance(**{a: zeros4 for a in _ATTRS})

    def draw(self, meshes, bases, eye, sky, fog_k, tint):
        """pose 几何 + N 个 base 矩阵 -> 一次实例化 draw。

        bases：[(T @ Ry, ...)] 16 元组列主序（与 CPU 路径的 base 同构）。
        """
        prog = self.program
        prog.use()
        prog['u_eye'] = (eye[0], eye[1], eye[2])
        prog['u_fog'] = sky
        prog['u_fog_k'] = fog_k
        prog['u_tint'] = tint
        pos, col, nverts = _flatten_meshes(meshes)
        assert nverts == self.vertex_count, \
            f'pose 几何顶点数变化 {nverts} != {self.vertex_count}'
        bufs = self.vlist.domain.attrib_name_buffers
        bufs['position'].set_region(0, nverts, pos)
        bufs['colors'].set_region(0, nverts, col)
        count = min(len(bases), self.capacity)
        cols = [[] for _ in range(4)]
        for i in range(count):
            for c in range(4):
                cols[c].extend(bases[i][c * 4:c * 4 + 4])
        for c, a in enumerate(_ATTRS):
            bufs[a].set_region(0, count, cols[c])
        # pyglet 无公开 setter：直接写实例数（拿不到则退化画全部，功能不丢）
        domain = getattr(self.vlist, 'domain', None)
        if domain is not None and hasattr(domain, '_instances'):
            domain._instances = count
        self.vlist.draw(GL_TRIANGLES)
        return count


def merge_heroes(program, meshes):
    """英雄角色（姿态各异）仍走 CPU 合并路径。"""
    if not meshes:
        return None
    vlist = merge_draw(program, meshes)
    vlist.draw(GL_TRIANGLES)
    vlist.delete()

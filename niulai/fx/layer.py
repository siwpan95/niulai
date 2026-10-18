# -*- coding: utf-8 -*-
"""粒子渲染层：GL 点精灵（世界空间，带雾/色调）。

与主体渲染的三条同构口径：
- 同一 `WindowBlock`（projection/view 由 pyglet 自动绑定，照抄
  pipeline/instanced.py 的 ShaderProgram 用法）；
- 片段雾/色调公式与 render.py FRAGMENT_SRC **逐字一致**（否则粒子在
  远处会"飘"出场景——雾色必须等于清屏色这条铁律同样约束粒子）；
- 圆形软边 sprite（gl_PointCoord），生命透明度由粒子场侧算好。

调用点：pipeline/render.py::render_frame_raw 的 particles 钩子
（3D 之后、overlays 之前，深度测试开、混合开关自理）。
"""

import numpy as np
from pyglet.gl import GL_BLEND, GL_ONE_MINUS_SRC_ALPHA, GL_POINTS, \
    GL_SRC_ALPHA, glBlendFunc, glDisable, glEnable
from pyglet.graphics.shader import Shader, ShaderProgram

POINT_VERTEX_SRC = '''#version 330 core
in vec3 position;
in vec4 colors;
uniform WindowBlock { mat4 projection; mat4 view; } window;
uniform float u_point_size;
out vec4 v_col;
out vec3 v_world;
void main() {
    v_col = colors;
    v_world = position;
    gl_Position = window.projection * window.view * vec4(position, 1.0);
    gl_PointSize = u_point_size;
}'''

# 雾/色调公式与 render.py FRAGMENT_SRC 一致（u_fog == 清屏色铁律）
POINT_FRAGMENT_SRC = '''#version 330 core
in vec4 v_col;
in vec3 v_world;
uniform vec3 u_eye;
uniform vec3 u_fog;
uniform float u_fog_k;
uniform vec3 u_tint;
out vec4 final_colors;
void main() {
    vec2 pc = gl_PointCoord - vec2(0.5);
    float d = length(pc);
    float a = smoothstep(0.5, 0.12, d) * v_col.a;
    if (a <= 0.004) discard;
    float dist = distance(v_world, u_eye);
    float fog = 1.0 - exp(-dist * u_fog_k);
    vec3 rgb = v_col.rgb * u_tint;
    final_colors = vec4(mix(rgb, u_fog, clamp(fog, 0.0, 1.0)), a);
}'''


class ParticleLayer:
    """把 ParticleField 的某帧状态画成点精灵。

    point_size 为像素直径（离屏渲染下即屏幕像素；粗粝美学下 2-4px 刚好）。
    流程：场景 `particles(t)` 调 `layer.update(t)`（推进粒子场到该帧，
    纯函数确定性）-> 渲染管线在 3D 之后调 `layer.draw(...)`。
    每帧重建 vertex list（与 merge_draw 同风格，量级几百个点可忽略）。
    """

    def __init__(self, field, point_size=3.0):
        self.field = field
        self.point_size = float(point_size)
        self.program = ShaderProgram(Shader(POINT_VERTEX_SRC, 'vertex'),
                                     Shader(POINT_FRAGMENT_SRC, 'fragment'))
        self._state = None

    def update(self, t):
        """推进粒子场到时刻 t 并缓存渲染状态（场景侧每帧调一次）。"""
        self._state = self.field.state_at(t)
        return self

    def draw(self, win, eye, sky, fog_k, tint):
        state = self._state
        n = 0 if state is None else int(state['count'])
        if n <= 0:
            return 0
        prog = self.program
        prog.use()
        prog['u_eye'] = (eye[0], eye[1], eye[2])
        prog['u_fog'] = sky
        prog['u_fog_k'] = fog_k
        prog['u_tint'] = tint
        prog['u_point_size'] = self.point_size
        pos = np.asarray(state['pos'], dtype=np.float32).ravel().tolist()
        col = np.asarray(state['rgba'], dtype=np.float32).ravel().tolist()
        vlist = prog.vertex_list(n, GL_POINTS,
                                 position=('f', pos), colors=('f', col))
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        vlist.draw(GL_POINTS)
        glDisable(GL_BLEND)
        vlist.delete()
        return n
